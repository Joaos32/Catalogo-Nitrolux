"""Private PostgreSQL state shared by catalog serverless instances."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4


REPRESENTATIVES_KEY = "representative_users.json"
ERP_KEY = "erp_products.json"


class StateWriteConflictError(ValueError):
    """Another writer changed or already initialized the stored object."""


@dataclass(frozen=True)
class StateObject:
    content: bytes
    etag: str
    updated_at: str


def backend_preference() -> str:
    backend = str(os.getenv("CATALOG_STATE_BACKEND") or "auto").strip().lower()
    if backend not in {"auto", "blob", "postgres"}:
        raise ValueError("CATALOG_STATE_BACKEND must be auto, blob or postgres")
    return backend


def is_configured() -> bool:
    backend = backend_preference()
    if backend == "blob":
        return False
    configured = bool(str(os.getenv("CATALOG_STATE_DATABASE_URL") or "").strip())
    if backend == "postgres" and not configured:
        raise RuntimeError("CATALOG_STATE_DATABASE_URL is required for the postgres backend")
    return configured


def _connect():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    url = str(os.getenv("CATALOG_STATE_DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("Catalog state database is not configured")
    parameters = conninfo_to_dict(url)
    # A default desktop installation may have TLS disabled. Permit that only
    # for explicit loopback connections; remote servers always require TLS.
    hosts = parameters.get("hostaddr") or os.getenv("PGHOSTADDR") or parameters.get("host") or os.getenv("PGHOST") or ""
    local = bool(hosts) and all(host.strip().lower() in {"127.0.0.1", "::1", "localhost"} for host in hosts.split(","))
    sslmode = parameters.get("sslmode") or ("prefer" if local else "require")
    if not local and sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("Remote catalog database connections require TLS")
    # Transaction poolers used by serverless hosts do not support prepared statements.
    return psycopg.connect(url, sslmode=sslmode, connect_timeout=5, prepare_threshold=None)


def load_object(key: str) -> StateObject | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT content, version, updated_at FROM catalog_private.objects WHERE object_key = %s",
            (key,),
        ).fetchone()
    if row is None:
        return None
    return StateObject(bytes(row[0]), str(row[1]), row[2].isoformat())


def list_object_metadata(prefix: str) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT object_key, octet_length(content), updated_at FROM catalog_private.objects "
            "WHERE starts_with(object_key, %s) ORDER BY updated_at DESC",
            (prefix,),
        ).fetchall()
    return [{"key": row[0], "size_bytes": row[1], "updated_at": row[2].isoformat()} for row in rows]


def _insert_object(connection, key: str, content: bytes, version: str):
    return connection.execute(
        "INSERT INTO catalog_private.objects (object_key, content, version) VALUES (%s, %s, %s) "
        "ON CONFLICT (object_key) DO NOTHING RETURNING version",
        (key, content, version),
    ).fetchone()


def write_object(
    key: str,
    content: bytes,
    *,
    expected_etag: str | None = None,
    expected_missing: bool = False,
) -> str:
    version = uuid4().hex
    with _connect() as connection:
        if expected_missing:
            row = _insert_object(connection, key, content, version)
        elif expected_etag is not None:
            row = connection.execute(
                "UPDATE catalog_private.objects SET content = %s, version = %s, updated_at = now() "
                "WHERE object_key = %s AND version = %s RETURNING version",
                (content, version, key, expected_etag),
            ).fetchone()
        else:
            row = connection.execute(
                "INSERT INTO catalog_private.objects (object_key, content, version) VALUES (%s, %s, %s) "
                "ON CONFLICT (object_key) DO UPDATE SET content = EXCLUDED.content, "
                "version = EXCLUDED.version, updated_at = now() RETURNING version",
                (key, content, version),
            ).fetchone()
        if row is None:
            raise StateWriteConflictError("Stored catalog state changed; reload and retry")
    return str(row[0])


def seed_objects(objects: dict[str, bytes]) -> None:
    """Initialize all supplied objects atomically, preserving existing destination data."""
    with _connect() as connection:
        for key, content in objects.items():
            if _insert_object(connection, key, content, uuid4().hex) is None:
                raise StateWriteConflictError("Destination already contains catalog state; migration aborted")


def record_activity(email: str, name: str, last_seen: datetime) -> None:
    with _connect() as connection:
        # At most one row per user, and one shared update per minute across tabs/instances.
        connection.execute(
            "INSERT INTO catalog_private.presence (email, name, last_seen_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, last_seen_at = EXCLUDED.last_seen_at "
            "WHERE catalog_private.presence.last_seen_at <= EXCLUDED.last_seen_at - interval '60 seconds'",
            (email, name, last_seen),
        )


def list_activity(window_seconds: int) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT email, name, last_seen_at FROM catalog_private.presence "
            "WHERE last_seen_at >= now() - (%s * interval '1 second')",
            (window_seconds,),
        ).fetchall()
    return [{"email": row[0], "name": row[1], "last_seen_at": row[2].isoformat()} for row in rows]
