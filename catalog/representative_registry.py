"""Cadastro persistido de representantes para acesso ao catalogo."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
from contextlib import nullcontext
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .core import load_settings
from . import blob_cache, state_database
from .blob_versioning import put_versioned, BlobWriteConflictError
from .file_lock import document_lock


logger = logging.getLogger(__name__)
MANAGED_USERS_FILENAME = "representative_users.json"
MANAGED_USERS_BLOB_PATH = "catalogo/representative_users.json"
MANAGED_USERS_S3_KEY = "private/representative_users.json"
PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 390000
MIN_REPRESENTATIVE_PASSWORD_LENGTH = 10
PASSWORD_RESET_CODE_BYTES = 9
PASSWORD_RESET_EXPIRES_MINUTES = 60


class RegistryWriteConflictError(ValueError):
    """A different writer changed the representative registry."""


_mutation_snapshot: ContextVar[dict | None] = ContextVar("registry_mutation", default=None)


def _registry_mutation(function):
    @wraps(function)
    def mutate(*args, **kwargs):
        remote = state_database.is_configured() or _s3_registry_is_configured() or bool(_blob_token())
        with nullcontext() if remote else document_lock(_managed_users_path()):
            snapshot = _load_managed_users_payload(fresh=True)
            users = snapshot.get("users") if isinstance(snapshot, dict) else None
            if not isinstance(users, list) or any(not isinstance(user, dict) for user in users):
                raise RuntimeError("Invalid representative registry; refusing to overwrite it")
            emails = [_normalize_email(user.get("email") or user.get("login")) for user in users]
            if any(not email for email in emails) or len(set(emails)) != len(emails):
                raise RuntimeError("Invalid representative registry; refusing to discard records")
            context_token = _mutation_snapshot.set(snapshot)
            try:
                return function(*args, **kwargs)
            except (state_database.StateWriteConflictError, BlobWriteConflictError, TimeoutError) as exc:
                raise RegistryWriteConflictError("Representative data changed; reload and retry") from exc
            finally:
                _mutation_snapshot.reset(context_token)
    return mutate


def _stringify(value: Any) -> str:
    return str(value or "").strip()


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _stringify(value).lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on", "sim", "admin", "administrator"}


def _normalize_email(value: Any) -> str:
    return _stringify(value).lower()


def _configured_admin_emails() -> set[str]:
    """Retorna e-mails administrativos de outras fontes de autenticação."""
    try:
        from .admin_registry import list_admin_login_users

        return {
            _normalize_email(user.get("email"))
            for user in list_admin_login_users()
            if _normalize_email(user.get("email"))
        }
    except Exception:
        logger.debug("Unable to inspect the administrative registry", exc_info=True)
        return set()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw_value = _stringify(value)
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _managed_users_path() -> Path:
    explicit = _stringify(os.getenv("CATALOG_REPRESENTATIVE_USERS_FILE"))
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (load_settings().base_dir / "reports" / MANAGED_USERS_FILENAME).resolve()


def _blob_token() -> str:
    return _stringify(os.getenv("BLOB_READ_WRITE_TOKEN"))


def _managed_users_blob_path() -> str:
    return _stringify(os.getenv("CATALOG_REPRESENTATIVE_BLOB_PATH")) or MANAGED_USERS_BLOB_PATH


def _s3_registry_config() -> dict[str, str]:
    return {
        "bucket": _stringify(os.getenv("CATALOG_REPRESENTATIVE_S3_BUCKET")),
        "key": _stringify(os.getenv("CATALOG_REPRESENTATIVE_S3_KEY")) or MANAGED_USERS_S3_KEY,
        "region": _stringify(os.getenv("CATALOG_REPRESENTATIVE_S3_REGION")) or "sa-east-1",
        "access_key": _stringify(os.getenv("CATALOG_REPRESENTATIVE_S3_ACCESS_KEY_ID")),
        "secret_key": _stringify(os.getenv("CATALOG_REPRESENTATIVE_S3_SECRET_ACCESS_KEY")),
        "role_arn": _stringify(os.getenv("CATALOG_REPRESENTATIVE_S3_ROLE_ARN")),
    }


def _s3_registry_is_configured() -> bool:
    if state_database.backend_preference() == "blob":
        return False
    config = _s3_registry_config()
    if config["bucket"] and config["access_key"] and config["secret_key"]:
        return True
    if config["bucket"] and config["role_arn"]:
        from .vercel_oidc import get_request_token

        return bool(get_request_token())
    return bool(config["bucket"] and os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def representative_login_storage_is_configured() -> bool:
    """Report login availability without performing remote storage I/O."""

    config = _s3_registry_config()
    s3_configured = bool(
        state_database.backend_preference() != "blob"
        and config["bucket"]
        and (
            (config["access_key"] and config["secret_key"])
            or config["role_arn"]
            or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
        )
    )
    return bool(
        _parse_environment_representatives()
        or state_database.is_configured()
        or s3_configured
        or _blob_token()
        or _managed_users_path().is_file()
    )


@lru_cache(maxsize=8)
def _assume_registry_role(role_arn: str, oidc_token: str, region: str) -> dict[str, str]:
    import boto3

    response = boto3.client("sts", region_name=region).assume_role_with_web_identity(
        RoleArn=role_arn,
        RoleSessionName="catalogo-vercel-registry",
        WebIdentityToken=oidc_token,
        DurationSeconds=900,
    )
    credentials = response["Credentials"]
    return {
        "access_key": credentials["AccessKeyId"],
        "secret_key": credentials["SecretAccessKey"],
        "session_token": credentials["SessionToken"],
    }


def _s3_registry_client():
    import boto3

    config = _s3_registry_config()
    if config["role_arn"]:
        from .vercel_oidc import get_request_token

        credentials = _assume_registry_role(config["role_arn"], get_request_token(), config["region"])
        return boto3.client(
            "s3",
            region_name=config["region"],
            aws_access_key_id=credentials["access_key"],
            aws_secret_access_key=credentials["secret_key"],
            aws_session_token=credentials["session_token"],
        )
    if config["access_key"] and config["secret_key"]:
        return boto3.client(
            "s3",
            region_name=config["region"],
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
        )
    return boto3.client("s3", region_name=config["region"])


def _load_s3_payload() -> dict[str, Any]:
    from botocore.exceptions import ClientError

    config = _s3_registry_config()
    try:
        response = _s3_registry_client().get_object(Bucket=config["bucket"], Key=config["key"])
    except ClientError as exc:
        if str(exc.response.get("Error", {}).get("Code") or "") in {"NoSuchKey", "404"}:
            return {"users": [], "_storage_missing": True}
        raise
    payload = json.loads(response["Body"].read().decode("utf-8"))
    if isinstance(payload, dict):
        return {**payload, "_storage_etag": response.get("ETag"), "_storage_missing": False}
    if isinstance(payload, list):
        return {"users": payload, "_storage_etag": response.get("ETag"), "_storage_missing": False}
    raise ValueError("Invalid representative state")


def _write_s3_payload(payload: dict[str, Any]) -> None:
    config = _s3_registry_config()
    from botocore.exceptions import ClientError
    snapshot = _mutation_snapshot.get()
    condition = _write_condition(snapshot)
    try:
        _s3_registry_client().put_object(
            Bucket=config["bucket"],
            Key=config["key"],
            Body=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
            CacheControl="no-store",
            ServerSideEncryption="AES256",
            **({"IfNoneMatch": "*"} if condition["expected_missing"] else {"IfMatch": condition["expected_etag"]}),
        )
    except ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") in {409, 412} or exc.response.get("Error", {}).get("Code") in {"PreconditionFailed", "ConditionalRequestConflict"}:
            raise RegistryWriteConflictError("Representative data changed; reload and retry") from exc
        raise


def _load_blob_payload(*, fresh: bool = False) -> dict[str, Any] | None:
    token = _blob_token()
    if not token:
        return None
    from vercel.blob import BlobNotFoundError, get

    pathname = _managed_users_blob_path()

    def fetch() -> tuple[bytes | None, str | None]:
        try:
            result = get(pathname, access="private", token=token, use_cache=False)
        except BlobNotFoundError:
            return None, None
        content = bytes(result.content) if result and result.content else None
        if content:
            json.loads(content.decode("utf-8"))
        return content, result.etag if result else None

    content, etag = blob_cache.read_versioned(token, pathname, fetch, fresh=fresh)
    if not content:
        return {"users": [], "_storage_missing": True}
    payload = json.loads(content.decode("utf-8"))
    if isinstance(payload, dict):
        return {**payload, "_storage_etag": etag, "_storage_missing": False}
    if isinstance(payload, list):
        return {"users": payload, "_storage_etag": etag, "_storage_missing": False}
    raise ValueError("Invalid representative state")


def _write_blob_payload(payload: dict[str, Any]) -> bool:
    token = _blob_token()
    if not token:
        return False
    pathname = _managed_users_blob_path()
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    blob_cache.write_versioned(token, pathname, content, lambda: put_versioned(
        pathname, content, token=token, **_write_condition(_mutation_snapshot.get()),
    ))
    return True


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def hash_representative_password(password: str) -> str:
    normalized_password = _stringify(password)
    if not normalized_password:
        raise ValueError("Missing representative password")
    if len(normalized_password) < MIN_REPRESENTATIVE_PASSWORD_LENGTH:
        raise ValueError(
            f"Representative passwords must have at least {MIN_REPRESENTATIVE_PASSWORD_LENGTH} characters"
        )

    salt = secrets.token_bytes(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        normalized_password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return (
        f"{PASSWORD_HASH_SCHEME}$"
        f"{PASSWORD_HASH_ITERATIONS}$"
        f"{_b64encode(salt)}$"
        f"{_b64encode(derived_key)}"
    )


def verify_representative_password(user: dict[str, Any], provided_password: str) -> bool:
    normalized_password = _stringify(provided_password)
    if not normalized_password:
        return False

    stored_hash = _stringify(user.get("password_hash") or user.get("passwordHash"))
    if stored_hash:
        try:
            scheme, raw_iterations, salt_value, expected_value = stored_hash.split("$", 3)
            if scheme != PASSWORD_HASH_SCHEME:
                return False
            iterations = int(raw_iterations)
            derived_key = hashlib.pbkdf2_hmac(
                "sha256",
                normalized_password.encode("utf-8"),
                _b64decode(salt_value),
                iterations,
            )
        except (ValueError, TypeError):
            logger.warning("Ignoring invalid representative password hash for %s", user.get("email"))
            return False
        return secrets.compare_digest(_b64encode(derived_key), expected_value)

    stored_password = _stringify(user.get("password"))
    if not stored_password:
        return False
    return secrets.compare_digest(stored_password, normalized_password)


def _normalize_login_user(
    item: Any,
    *,
    source: str,
    managed: bool,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    email = _normalize_email(item.get("email") or item.get("login"))
    password = _stringify(item.get("password"))
    password_hash = _stringify(item.get("password_hash") or item.get("passwordHash"))
    name = _stringify(item.get("name") or item.get("display_name") or email or "Representante")
    if not email or not name:
        return None
    if not password and not password_hash:
        return None

    return {
        **item,
        "email": email,
        "name": name,
        "password": password,
        "password_hash": password_hash,
        "managed": managed,
        "is_admin": _parse_bool(item.get("is_admin") if "is_admin" in item else item.get("admin")),
        "source": source,
        "created_at": _stringify(item.get("created_at")) or None,
        "updated_at": _stringify(item.get("updated_at")) or None,
    }


def _parse_environment_representatives() -> list[dict[str, Any]]:
    settings = load_settings()
    candidates: list[Any] = []

    raw_users_json = _stringify(settings.representative_users_json)
    if raw_users_json:
        try:
            parsed = json.loads(raw_users_json)
        except json.JSONDecodeError as exc:
            logger.warning("Ignoring invalid representative users JSON: %s", exc)
            parsed = []

        if isinstance(parsed, dict) and isinstance(parsed.get("users"), list):
            candidates.extend(parsed.get("users") or [])
        elif isinstance(parsed, list):
            candidates.extend(parsed)
        elif isinstance(parsed, dict):
            candidates.append(parsed)

    if settings.representative_login_password:
        candidates.append(
            {
                "email": settings.representative_login_email or "",
                "password": settings.representative_login_password,
                "name": settings.representative_login_name
                or settings.representative_login_email
                or "Representante",
            }
        )

    users: list[dict[str, Any]] = []
    seen_emails: set[str] = set()
    configured_admin_emails = _configured_admin_emails()
    for item in candidates:
        normalized = _normalize_login_user(item, source="environment", managed=False)
        if not normalized or normalized["email"] in seen_emails:
            continue
        if normalized["email"] in configured_admin_emails:
            normalized["is_admin"] = True
        users.append(normalized)
        seen_emails.add(normalized["email"])
    return users


def _load_managed_users_payload(*, fresh: bool = False) -> dict[str, Any]:
    snapshot = _mutation_snapshot.get()
    if snapshot is not None:
        return snapshot
    if state_database.is_configured():
        try:
            stored = state_database.load_object(state_database.REPRESENTATIVES_KEY)
            if stored is None:
                return {"users": [], "_storage_missing": True}
            payload = json.loads(stored.content.decode("utf-8"))
            if isinstance(payload, dict):
                return {**payload, "_storage_etag": stored.etag, "_storage_missing": False}
            if isinstance(payload, list):
                return {"users": payload, "_storage_etag": stored.etag, "_storage_missing": False}
            raise ValueError("Invalid representative state")
        except Exception as exc:
            raise RuntimeError("Representative storage is temporarily unavailable") from exc

    if _s3_registry_is_configured():
        try:
            return _load_s3_payload()
        except Exception as exc:
            logger.exception("Unable to read representative registry from private S3 storage: %s", exc)
            raise RuntimeError("Representative storage is temporarily unavailable") from exc

    if _blob_token():
        try:
            return (_load_blob_payload(fresh=True) if fresh else _load_blob_payload()) or {"users": []}
        except Exception as exc:
            logger.exception("Unable to read representative registry from Vercel Blob: %s", exc)
            raise RuntimeError("Representative storage is temporarily unavailable") from exc

    target = _managed_users_path()
    if not target.is_file():
        return {"users": []}

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Representative storage is temporarily unavailable") from exc

    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"users": payload}
    raise RuntimeError("Invalid representative registry; refusing to overwrite it")


def _login_registry_state(*, fresh: bool = False) -> dict[str, Any]:
    """Read identity and revocation state together; provider errors never restore credentials."""
    payload = _load_managed_users_payload(fresh=fresh)
    raw_users = payload.get("users")
    revoked = payload.get("revoked_sessions", {})
    if not isinstance(raw_users, list) or not isinstance(revoked, dict):
        raise RuntimeError("Invalid representative registry")
    users, seen, blocked = [], set(), set()
    configured_admin_emails = _configured_admin_emails()
    for item in raw_users:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid representative registry")
        email = _normalize_email(item.get("email") or item.get("login"))
        if _parse_bool(item.get("disabled")):
            blocked.add(email)
            continue
        normalized = _normalize_login_user(item, source="managed", managed=True)
        if normalized and email not in seen:
            if email in configured_admin_emails:
                normalized["is_admin"] = True
            users.append(normalized)
            seen.add(email)
    for user in _parse_environment_representatives():
        if user["email"] not in seen and user["email"] not in blocked:
            users.append(user)
            seen.add(user["email"])
    for user in users:
        user["_revoked_sessions"] = revoked
    return {"users": users, "blocked_emails": blocked, "revoked_sessions": revoked}


def _serialize_managed_user(user: dict[str, Any]) -> dict[str, Any]:
    transient = {"managed", "source", "password", "password_hash", "passwordHash",
                 "password_reset_token_hash", "password_reset_expires_at", "password_reset_created_at"}
    payload = {
        **{key: value for key, value in user.items() if key not in transient},
        "session_version": user.get("session_version"),
        "email": user["email"],
        "name": user["name"],
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "is_admin": bool(user.get("is_admin")),
    }
    if user.get("password_hash"):
        payload["password_hash"] = user["password_hash"]
    elif user.get("password"):
        payload["password"] = user["password"]
    if user.get("password_reset_token_hash"):
        payload["password_reset_token_hash"] = user["password_reset_token_hash"]
        payload["password_reset_expires_at"] = user.get("password_reset_expires_at")
        payload["password_reset_created_at"] = user.get("password_reset_created_at")
    return payload


def _write_condition(snapshot: dict | None) -> dict:
    if snapshot is None:
        raise RegistryWriteConflictError("Registry update requires a versioned snapshot")
    missing = bool(snapshot.get("_storage_missing"))
    etag = snapshot.get("_storage_etag")
    if not missing and not etag:
        raise RegistryWriteConflictError("Registry version unavailable; reload and retry")
    return {"expected_etag": etag, "expected_missing": missing}


def _write_managed_users(users: list[dict[str, Any]]) -> None:
    snapshot = _mutation_snapshot.get() or {}
    payload = {
        "revoked_sessions": snapshot.get("revoked_sessions", {}),
        "users": [_serialize_managed_user(user) for user in users],
        "updated_at": _utcnow_iso(),
    }
    if state_database.is_configured():
        state_database.write_object(
            state_database.REPRESENTATIVES_KEY,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            **_write_condition(_mutation_snapshot.get()),
        )
        return
    if _s3_registry_is_configured():
        _write_s3_payload(payload)
        return
    if _write_blob_payload(payload):
        return

    target = _managed_users_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def list_representative_login_users(*, strict: bool = False, fresh: bool = False) -> list[dict[str, Any]]:
    try:
        return _login_registry_state(fresh=fresh)["users"]
    except RuntimeError:
        if strict:
            raise
        logger.error("Representative registry unavailable; denying authentication")
        return []


@_registry_mutation
def revoke_auth_sessions(sessions: list[tuple[str, int]]) -> None:
    """Persist session-specific revocations with the same CAS/lock as identity changes."""
    import time
    now = int(time.time())
    snapshot = _mutation_snapshot.get()
    revoked = snapshot.get("revoked_sessions", {})
    if not isinstance(revoked, dict):
        raise RuntimeError("Invalid session revocation state")
    active = {key: expiry for key, expiry in revoked.items() if int(expiry) > now}
    for session_id, expiry in sessions:
        if session_id and expiry > now:
            active[hashlib.sha256(session_id.encode("utf-8")).hexdigest()] = expiry
    if len(active) > 10000:
        raise RuntimeError("Session revocation capacity exceeded")
    snapshot["revoked_sessions"] = active
    _write_managed_users(_load_managed_users_raw())


def _sanitize_admin_user(user: dict[str, Any]) -> dict[str, Any]:
    reset_expires_at = user.get("password_reset_expires_at")
    return {
        "email": user["email"],
        "name": user["name"],
        "managed": bool(user.get("managed")),
        "is_admin": bool(user.get("is_admin")),
        "role": "admin" if user.get("is_admin") else "representative",
        "source": str(user.get("source") or "managed"),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "password_reset_expires_at": reset_expires_at,
        "password_reset_pending": bool(reset_expires_at and _is_password_reset_active(user)),
    }


def _hash_password_reset_code(code: str) -> str:
    normalized_code = _stringify(code).upper()
    return hashlib.sha256(normalized_code.encode("utf-8")).hexdigest()


def _is_password_reset_active(user: dict[str, Any]) -> bool:
    if not _stringify(user.get("password_reset_token_hash")):
        return False
    expires_at = _parse_iso_datetime(user.get("password_reset_expires_at"))
    if not expires_at:
        return False
    return expires_at > datetime.now(timezone.utc)


def _generate_password_reset_code() -> str:
    return secrets.token_urlsafe(PASSWORD_RESET_CODE_BYTES).replace("-", "").replace("_", "").upper()[:12]


def _load_managed_users_raw(*, fresh: bool = True) -> list[dict[str, Any]]:
    payload = _load_managed_users_payload(fresh=fresh)
    raw_users = payload.get("users") if isinstance(payload, dict) else []
    if not isinstance(raw_users, list):
        return []
    return [
        {
            **item,
            "email": _normalize_email(item.get("email") or item.get("login")),
            "name": _stringify(item.get("name") or item.get("display_name") or item.get("email") or item.get("login")),
            "password_hash": item.get("password_hash") or item.get("passwordHash") or "",
            "is_admin": _parse_bool(item.get("is_admin") if "is_admin" in item else item.get("admin")),
            "managed": True,
            "source": "managed",
        }
        for item in raw_users if isinstance(item, dict)
    ]


def _sanitize_reset_user(user: dict[str, Any]) -> dict[str, Any]:
    return _sanitize_admin_user(
        {
            **user,
            "managed": True,
            "source": "managed",
        }
    )


def build_representative_admin_summary() -> dict[str, Any]:
    merged_users = list_representative_login_users()
    # A reset-only record may overlay a user still authenticating from environment settings.
    recovery_state = {user["email"]: user for user in _load_managed_users_raw(fresh=False)}
    for user in merged_users:
        pending = recovery_state.get(user["email"], {})
        user.update({key: pending[key] for key in ("password_reset_token_hash", "password_reset_expires_at", "password_reset_created_at") if key in pending})
    sanitized = sorted(
        (_sanitize_admin_user(user) for user in merged_users),
        key=lambda item: (0 if item["managed"] else 1, item["name"].lower(), item["email"]),
    )
    managed_users = [user for user in sanitized if user["managed"]]
    environment_users = [user for user in sanitized if not user["managed"]]
    return {
        "users": sanitized,
        "total_users": len(sanitized),
        "managed_users": len(managed_users),
        "environment_users": len(environment_users),
        "admin_users": sum(1 for user in sanitized if user["is_admin"]),
        "representative_users": sum(1 for user in sanitized if not user["is_admin"]),
    }


@_registry_mutation
def upsert_managed_representative(
    email: str,
    name: str,
    password: str | None = None,
    is_admin: bool | None = None,
) -> tuple[bool, dict[str, Any]]:
    normalized_email = _normalize_email(email)
    normalized_name = _stringify(name)
    normalized_password = _stringify(password)
    if not normalized_email:
        raise ValueError("Missing representative email")
    if "@" not in normalized_email:
        raise ValueError("Representative email is invalid")
    if not normalized_name:
        raise ValueError("Missing representative name")

    managed_users = _load_managed_users_raw()
    existing_user = next((user for user in managed_users if user["email"] == normalized_email), None)
    environment_users = {user["email"] for user in _parse_environment_representatives()}
    if normalized_email in environment_users and existing_user is None:
        raise ValueError("Representative email is managed by environment configuration")

    timestamp = _utcnow_iso()
    if existing_user:
        if existing_user.get("disabled") and not normalized_password:
            raise ValueError("A new password is required to reactivate an account")
        existing_user.pop("disabled", None)
        existing_user["name"] = normalized_name
        existing_user["updated_at"] = timestamp
        if normalized_password:
            existing_user["password_hash"] = hash_representative_password(normalized_password)
            existing_user["password"] = ""
            for key in ("password_reset_token_hash", "password_reset_expires_at", "password_reset_created_at"):
                existing_user.pop(key, None)
        if is_admin is not None:
            if bool(existing_user.get("is_admin")) != is_admin:
                existing_user["session_version"] = uuid4().hex
            existing_user["is_admin"] = bool(is_admin)
        _write_managed_users(managed_users)
        return False, _sanitize_admin_user(existing_user)

    if not normalized_password:
        raise ValueError("Missing representative password")

    created_user = {
        "email": normalized_email,
        "name": normalized_name,
        "password": "",
        "password_hash": hash_representative_password(normalized_password),
        "managed": True,
        "source": "managed",
        "is_admin": bool(is_admin),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    managed_users.append(created_user)
    _write_managed_users(managed_users)
    return True, _sanitize_admin_user(created_user)


@_registry_mutation
def delete_managed_representative(email: str) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        raise ValueError("Missing representative email")

    managed_users = _load_managed_users_raw()
    kept_users = [user for user in managed_users if user["email"] != normalized_email]
    if len(kept_users) == len(managed_users):
        raise KeyError(normalized_email)

    # Retain a tombstone so another credential source cannot reactivate this identity.
    kept_users.append({"email": normalized_email, "name": normalized_email,
                       "disabled": True, "is_admin": False, "session_version": uuid4().hex})
    _write_managed_users(kept_users)
    return {"deleted": True, "email": normalized_email}


@_registry_mutation
def create_representative_password_reset(email: str) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        raise ValueError("Missing representative email")

    raw_managed_users = _load_managed_users_raw()
    existing_login_user = next((user for user in list_representative_login_users() if user["email"] == normalized_email), None)
    raw_user = next(
        (
            user
            for user in raw_managed_users
            if _normalize_email(user.get("email") or user.get("login")) == normalized_email
        ),
        None,
    )

    if (existing_login_user is None and raw_user is None) or (raw_user and raw_user.get("disabled")):
        raise KeyError(normalized_email)

    timestamp = _utcnow_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_EXPIRES_MINUTES)).isoformat()
    reset_code = _generate_password_reset_code()
    configured_admin = normalized_email in _configured_admin_emails() or bool(
        existing_login_user and existing_login_user.get("is_admin")
    )

    if raw_user is None:
        raw_user = {
            "email": normalized_email,
            "name": existing_login_user["name"],
            "created_at": timestamp,
            "is_admin": configured_admin,
        }
        raw_managed_users.append(raw_user)

    raw_user["email"] = normalized_email
    raw_user["name"] = _stringify(raw_user.get("name")) or (existing_login_user or {}).get("name") or normalized_email
    if configured_admin:
        raw_user["is_admin"] = True
    raw_user["updated_at"] = timestamp
    raw_user["password_reset_token_hash"] = _hash_password_reset_code(reset_code)
    raw_user["password_reset_created_at"] = timestamp
    raw_user["password_reset_expires_at"] = expires_at

    _write_managed_users(raw_managed_users)
    return {
        "reset_code": reset_code,
        "expires_at": expires_at,
        "user": _sanitize_reset_user(raw_user),
    }


@_registry_mutation
def reset_representative_password_with_code(email: str, reset_code: str, new_password: str) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    normalized_code = _stringify(reset_code).upper()
    normalized_password = _stringify(new_password)
    if not normalized_email:
        raise ValueError("Missing representative email")
    if not normalized_code:
        raise ValueError("Missing reset code")
    if not normalized_password:
        raise ValueError("Missing new password")
    if len(normalized_password) < MIN_REPRESENTATIVE_PASSWORD_LENGTH:
        raise ValueError(
            f"New password must have at least {MIN_REPRESENTATIVE_PASSWORD_LENGTH} characters"
        )

    raw_managed_users = _load_managed_users_raw()
    raw_user = next(
        (
            user
            for user in raw_managed_users
            if _normalize_email(user.get("email") or user.get("login")) == normalized_email
        ),
        None,
    )
    if raw_user is None:
        raise KeyError(normalized_email)

    if not _is_password_reset_active(raw_user):
        raise ValueError("Reset code expired or unavailable")

    expected_hash = _stringify(raw_user.get("password_reset_token_hash"))
    if not secrets.compare_digest(expected_hash, _hash_password_reset_code(normalized_code)):
        raise ValueError("Invalid reset code")

    timestamp = _utcnow_iso()
    raw_user["email"] = normalized_email
    raw_user["name"] = _stringify(raw_user.get("name")) or normalized_email
    raw_user["password"] = ""
    raw_user["password_hash"] = hash_representative_password(normalized_password)
    raw_user["updated_at"] = timestamp
    raw_user.pop("password_reset_token_hash", None)
    raw_user.pop("password_reset_created_at", None)
    raw_user.pop("password_reset_expires_at", None)

    _write_managed_users(raw_managed_users)
    return _sanitize_reset_user(raw_user)
