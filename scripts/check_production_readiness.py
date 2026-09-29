"""Validate production-oriented configuration before deploying.

Usage:
    python scripts/check_production_readiness.py --env-file .env.production --frontend-env frontend/.env.production
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


LOCAL_HOST_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0")
WEAK_SECRET_MARKERS = ("change-me", "changeme", "replace-with", "example", "secret")


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _merged_env(env_file: Path | None) -> dict[str, str]:
    values = dict(os.environ)
    if env_file:
        values.update(_parse_env_file(env_file))
    return values


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _is_true(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_false(value: str) -> bool:
    return str(value or "").strip().lower() in {"0", "false", "no", "off"}


def _looks_weak_secret(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if len(normalized) < 32:
        return True
    return any(marker in normalized for marker in WEAK_SECRET_MARKERS)


def _has_local_marker(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return any(marker in normalized for marker in LOCAL_HOST_MARKERS)


def _add_required_secret(errors: list[str], values: dict[str, str], key: str) -> None:
    value = values.get(key, "")
    if _looks_weak_secret(value):
        errors.append(f"{key} must be set to a unique secret with at least 32 characters.")


def _has_login_credential(user: object) -> bool:
    if not isinstance(user, dict):
        return False
    email = str(user.get("email") or user.get("login") or "").strip()
    password = str(user.get("password") or "").strip()
    password_hash = str(user.get("password_hash") or user.get("passwordHash") or "").strip()
    return bool(email and (len(password) >= 10 or password_hash.startswith("pbkdf2_sha256$")))


def _representative_users_from_json(raw_value: str) -> list[object]:
    parsed = json.loads(raw_value)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("users"), list):
        return parsed["users"]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _validate_backend(values: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    _add_required_secret(errors, values, "CATALOG_SESSION_SECRET")

    representative_secret = values.get("CATALOG_REPRESENTATIVE_JWT_SECRET", "")
    if representative_secret and _looks_weak_secret(representative_secret):
        errors.append("CATALOG_REPRESENTATIVE_JWT_SECRET is set but looks weak or placeholder-like.")

    if not _is_true(values.get("CATALOG_SESSION_COOKIE_SECURE", "")):
        errors.append("CATALOG_SESSION_COOKIE_SECURE must be true for HTTPS production.")

    if not _is_false(values.get("CATALOG_ENABLE_API_DOCS", "")):
        errors.append("CATALOG_ENABLE_API_DOCS must be false in production.")

    if _is_true(values.get("CATALOG_ALLOW_OPEN_ADMIN", "")):
        errors.append("CATALOG_ALLOW_OPEN_ADMIN must not be true in production.")

    origins = _csv_values(values.get("CATALOG_CORS_ALLOW_ORIGINS", ""))
    if not origins:
        warnings.append(
            "CATALOG_CORS_ALLOW_ORIGINS is empty; this is appropriate for a same-origin deployment."
        )
    if "*" in origins:
        errors.append("CATALOG_CORS_ALLOW_ORIGINS must not contain '*'.")
    if any(_has_local_marker(origin) for origin in origins):
        errors.append("CATALOG_CORS_ALLOW_ORIGINS must not point to localhost/127.0.0.1.")

    has_admin_login = bool(values.get("CATALOG_ADMIN_LOGIN_PASSWORD") or values.get("CATALOG_ADMIN_USERS_FILE"))
    has_admin_token = bool(values.get("CATALOG_ERP_ADMIN_TOKEN"))
    if not has_admin_login and not has_admin_token:
        errors.append("Configure admin access with CATALOG_ADMIN_LOGIN_PASSWORD, CATALOG_ADMIN_USERS_FILE, or CATALOG_ERP_ADMIN_TOKEN.")

    if not _is_true(values.get("CATALOG_REQUIRE_REPRESENTATIVE_LOGIN", "")):
        errors.append("CATALOG_REQUIRE_REPRESENTATIVE_LOGIN must be true in production.")

    has_representatives = False
    users_json = values.get("CATALOG_REPRESENTATIVE_USERS_JSON", "").strip()
    if users_json:
        try:
            has_representatives = any(
                _has_login_credential(user)
                for user in _representative_users_from_json(users_json)
            )
        except json.JSONDecodeError:
            errors.append("CATALOG_REPRESENTATIVE_USERS_JSON must contain valid JSON.")

    single_user = {
        "email": values.get("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", ""),
        "password": values.get("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", ""),
    }
    has_representatives = has_representatives or _has_login_credential(single_user)

    users_file = values.get("CATALOG_REPRESENTATIVE_USERS_FILE", "").strip()
    if users_file and Path(users_file).is_file():
        try:
            has_representatives = has_representatives or any(
                _has_login_credential(user)
                for user in _representative_users_from_json(
                    Path(users_file).read_text(encoding="utf-8")
                )
            )
        except (OSError, json.JSONDecodeError):
            errors.append("CATALOG_REPRESENTATIVE_USERS_FILE must point to a valid JSON login registry.")

    has_remote_representative_registry = bool(
        values.get("CATALOG_REPRESENTATIVE_S3_BUCKET")
        or values.get("BLOB_READ_WRITE_TOKEN")
    )
    if not has_representatives and not has_remote_representative_registry:
        errors.append("Configure at least one representative email and password/password_hash.")
    elif not has_representatives:
        warnings.append(
            "A remote representative registry is configured; confirm it contains an active user with /health/ready after deployment."
        )

    if not values.get("CATALOG_S3_MEDIA_BUCKET"):
        warnings.append("CATALOG_S3_MEDIA_BUCKET is empty; Lambda production will not have the local photo folder.")

    if values.get("CATALOG_GOOGLE_DRIVE_FOLDER_ID") and not values.get("CATALOG_GOOGLE_DRIVE_API_KEY"):
        warnings.append("Google Drive folder is configured without CATALOG_GOOGLE_DRIVE_API_KEY.")

    for key in ("CATALOG_STOCK_PHOTOS_ROOT", "CATALOG_STOCK_REPORT_PATH", "CATALOG_ERP_JSON_PATH"):
        value = values.get(key, "")
        if value and (":\\" in value or value.startswith("/") or _has_local_marker(value)):
            warnings.append(f"{key} points to a local path; confirm this exists in the production runtime.")

    return errors, warnings


def _validate_frontend(path: Path | None) -> tuple[list[str], list[str]]:
    if not path:
        return [], ["Frontend env file was not provided; skipping VITE_API_BASES validation."]

    values = _parse_env_file(path)
    errors: list[str] = []
    warnings: list[str] = []
    bases = _csv_values(values.get("VITE_API_BASES", ""))
    if not bases:
        errors.append("VITE_API_BASES must be set in the frontend production env.")
    if any(_has_local_marker(base) for base in bases):
        errors.append("VITE_API_BASES must not point to localhost/127.0.0.1 in production.")
    if any(base.startswith("http://") for base in bases):
        warnings.append("VITE_API_BASES contains an http:// origin; HTTPS is recommended.")
    return errors, warnings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check production readiness for Catalogo.")
    parser.add_argument("--env-file", type=Path, help="Backend env file to validate.")
    parser.add_argument("--frontend-env", type=Path, help="Frontend production env file to validate.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    backend_values = _merged_env(args.env_file)
    backend_errors, backend_warnings = _validate_backend(backend_values)
    frontend_errors, frontend_warnings = _validate_frontend(args.frontend_env)

    errors = backend_errors + frontend_errors
    warnings = backend_warnings + frontend_warnings

    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print(f"Production readiness failed with {len(errors)} error(s).")
        return 1

    print("Production readiness check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
