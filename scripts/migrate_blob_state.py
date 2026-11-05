"""Copy private Blob state to PostgreSQL, or restore JSON backups; dry-run by default."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from catalog import state_database  # noqa: E402


def _read_source(local_file: Path | None, blob_path: str) -> bytes:
    if local_file is not None:
        return local_file.read_bytes()
    from vercel.blob import get

    token = str(os.getenv("BLOB_READ_WRITE_TOKEN") or "").strip()
    if not token:
        raise ValueError("Configure BLOB_READ_WRITE_TOKEN or supply local JSON backups")
    result = get(blob_path, access="private", token=token, use_cache=False)
    if result is None or not result.content:
        raise ValueError("Source object is missing; migration aborted")
    return result.content


def prepare_objects(users_file: Path | None, erp_file: Path | None) -> dict[str, bytes]:
    users = _read_source(
        users_file,
        str(os.getenv("CATALOG_REPRESENTATIVE_BLOB_PATH") or "catalogo/representative_users.json"),
    )
    erp = _read_source(
        erp_file, str(os.getenv("CATALOG_ERP_BLOB_PATH") or "catalogo/erp_products.json"),
    )
    return validate_objects(users, erp)


def validate_objects(users: bytes, erp: bytes) -> dict[str, bytes]:
    """Validate both snapshots without changing credentials, roles or ERP metadata."""
    parsed_users = json.loads(users.decode("utf-8-sig"))
    entries = parsed_users.get("users") if isinstance(parsed_users, dict) else parsed_users
    if not isinstance(entries, list) or not entries:
        raise ValueError("Representative source must contain a non-empty users list")
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("email") or not (
            entry.get("password_hash") or entry.get("passwordHash") or entry.get("password")
        ):
            raise ValueError("Representative source contains an invalid login record")
    parsed_erp = json.loads(erp.decode("utf-8-sig"))
    from catalog.erp_catalog import _build_index

    if not _build_index(parsed_erp):
        raise ValueError("ERP source must contain valid products")
    # Normalize BOM only; retain password hashes, roles, and ERP metadata as supplied.
    return {
        state_database.REPRESENTATIVES_KEY: users.decode("utf-8-sig").encode("utf-8"),
        state_database.ERP_KEY: erp.decode("utf-8-sig").encode("utf-8"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users-file", type=Path, help="Local representative JSON backup")
    parser.add_argument("--erp-file", type=Path, help="Local active ERP JSON backup")
    parser.add_argument("--apply", action="store_true", help="Write both objects in one transaction")
    args = parser.parse_args(argv)
    try:
        objects = prepare_objects(args.users_file, args.erp_file)
        for key, content in objects.items():
            print(f"Validated {key}: {len(content)} bytes")
        if not args.apply:
            print("Dry-run complete; no destination writes. Use --apply after creating the private schema.")
            return 0
        if not state_database.is_configured():
            raise ValueError("Configure CATALOG_STATE_DATABASE_URL before applying the migration")
        state_database.seed_objects(objects)
        print("Migration complete. Existing Blob objects were preserved.")
        return 0
    except Exception as exc:
        # Driver/provider exceptions may contain configuration; never print their details.
        error_kind = type(exc).__name__
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            error_kind += f", HTTP {status}"
            if "suspend" in str(getattr(response, "text", "")).lower():
                error_kind += ", source store suspended"
        print(f"Migration aborted ({error_kind}). Check source access, schema, and destination state.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env.local")
    load_dotenv(BASE_DIR / ".env")
    raise SystemExit(main())
