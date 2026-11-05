"""Atividade recente dos representantes autenticados."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import load_settings
from .representative_registry import list_representative_login_users
from . import state_database


logger = logging.getLogger(__name__)
ONLINE_WINDOW_SECONDS = 5 * 60
PRESENCE_PREFIX = "catalogo/online-users/"
_LOCAL_PRESENCE_LOCK = threading.Lock()


def _presence_object_name(email: str) -> str:
    email_hash = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return f"{PRESENCE_PREFIX}{email_hash}.json"


def _presence_table_name() -> str:
    return str(os.getenv("CATALOG_ONLINE_USERS_TABLE") or "").strip()


def _presence_table():
    import boto3

    return boto3.resource("dynamodb").Table(_presence_table_name())


def _local_presence_file() -> Path:
    configured_path = str(os.getenv("CATALOG_ONLINE_USERS_FILE") or "").strip()
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return load_settings().base_dir / "reports" / "online_users.json"


def _is_serverless_runtime() -> bool:
    vercel_runtime = str(os.getenv("VERCEL") or "").strip().lower() in {"1", "true", "yes", "on"}
    return vercel_runtime or bool(str(os.getenv("AWS_LAMBDA_FUNCTION_NAME") or "").strip())


def activity_tracking_available() -> bool:
    return bool(state_database.is_configured() or _presence_table_name() or not _is_serverless_runtime())


def _read_local_records() -> list[dict[str, Any]]:
    target = _local_presence_file()
    if not target.is_file():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Unable to read local online-user activity file", exc_info=True)
        return []
    records = payload.get("users", []) if isinstance(payload, dict) else []
    return [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []


def _write_local_record(record: dict[str, Any]) -> None:
    target = _local_presence_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    email = str(record.get("email") or "").strip().lower()
    with _LOCAL_PRESENCE_LOCK:
        records = _read_local_records()
        records = [item for item in records if str(item.get("email") or "").strip().lower() != email]
        records.append(record)
        target.write_text(
            json.dumps({"users": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _write_shared_record(record: dict[str, Any]) -> None:
    if state_database.is_configured():
        state_database.record_activity(
            record["email"], record["name"], datetime.fromisoformat(record["last_seen_at"])
        )
        return
    object_name = _presence_object_name(str(record["email"]))

    table_name = _presence_table_name()
    if table_name:
        _presence_table().update_item(
            Key={"user_key": object_name.rsplit("/", maxsplit=1)[-1].removesuffix(".json")},
            UpdateExpression="SET #email = :email, #name = :name, last_seen_at = :last_seen_at, expires_at = :expires_at",
            ExpressionAttributeNames={"#email": "email", "#name": "name"},
            ExpressionAttributeValues={
                ":email": record["email"],
                ":name": record["name"],
                ":last_seen_at": record["last_seen_at"],
                ":expires_at": int(datetime.now(timezone.utc).timestamp()) + ONLINE_WINDOW_SECONDS * 3,
            },
        )
        return

    if _is_serverless_runtime():
        return
    _write_local_record(record)


def _read_shared_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    representatives = list_representative_login_users()

    if state_database.is_configured():
        known_emails = {str(user["email"]).strip().lower() for user in representatives}
        return [
            record for record in state_database.list_activity(ONLINE_WINDOW_SECONDS)
            if str(record.get("email") or "").strip().lower() in known_emails
        ]

    table_name = _presence_table_name()
    if table_name:
        from boto3.dynamodb.conditions import Attr

        table = _presence_table()
        response = table.scan(
            FilterExpression=Attr("expires_at").gt(int(datetime.now(timezone.utc).timestamp())),
            ProjectionExpression="#email, #name, last_seen_at, expires_at",
            ExpressionAttributeNames={"#email": "email", "#name": "name"},
        )
        records.extend(response.get("Items", []))
        while response.get("LastEvaluatedKey"):
            response = table.scan(
                FilterExpression=Attr("expires_at").gt(int(datetime.now(timezone.utc).timestamp())),
                ProjectionExpression="#email, #name, last_seen_at, expires_at",
                ExpressionAttributeNames={"#email": "email", "#name": "name"},
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            records.extend(response.get("Items", []))
        known_emails = {str(user["email"]).strip().lower() for user in representatives}
        return [
            record
            for record in records
            if str(record.get("email") or "").strip().lower() in known_emails
        ]

    if _is_serverless_runtime():
        return []

    known_emails = {str(user["email"]).strip().lower() for user in representatives}
    return [
        record
        for record in _read_local_records()
        if str(record.get("email") or "").strip().lower() in known_emails
    ]


def record_representative_activity(claims: dict[str, Any]) -> None:
    """Save one shared heartbeat for the authenticated representative."""

    if not activity_tracking_available():
        return
    email = str(claims.get("email") or claims.get("sub") or "").strip().lower()
    if not email:
        return
    record = {
        "email": email,
        "name": str(claims.get("name") or email).strip() or email,
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_shared_record(record)


def list_online_representatives() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_timestamp = now.timestamp()
    users = []
    tracking_available = activity_tracking_available()
    for record in _read_shared_records() if tracking_available else []:
        email = str(record.get("email") or "").strip().lower()
        last_seen_at = str(record.get("last_seen_at") or "").strip()
        try:
            parsed_last_seen = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
            if parsed_last_seen.tzinfo is None:
                parsed_last_seen = parsed_last_seen.replace(tzinfo=timezone.utc)
            age_seconds = now_timestamp - parsed_last_seen.timestamp()
        except (ValueError, OverflowError):
            continue
        if not email or age_seconds < 0 or age_seconds > ONLINE_WINDOW_SECONDS:
            continue
        users.append(
            {
                "email": email,
                "name": str(record.get("name") or email),
                "last_seen_at": parsed_last_seen.astimezone(timezone.utc).isoformat(),
            }
        )

    users.sort(key=lambda user: user["last_seen_at"], reverse=True)
    return {
        "users": users,
        "total_online": len(users),
        "checked_at": now.isoformat(),
        "online_window_seconds": ONLINE_WINDOW_SECONDS,
        "tracking_available": tracking_available,
    }
