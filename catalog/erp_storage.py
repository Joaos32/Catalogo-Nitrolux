"""Durable object storage for the active ERP catalog snapshot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from . import blob_cache, state_database
from .blob_versioning import BlobWriteConflictError, put_versioned


DEFAULT_ERP_S3_KEY = "catalog/erp_products.json"
DEFAULT_ERP_BLOB_PATH = "catalogo/erp_products.json"


class ERPWriteConflictError(ValueError):
    """Raised when another writer changed the active catalog snapshot."""


@dataclass(frozen=True)
class ERPObject:
    content: bytes
    etag: str | None
    updated_at: str | None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _backend() -> tuple[Literal["s3", "blob"], str, str] | None:
    bucket = str(os.getenv("CATALOG_ERP_S3_BUCKET") or "").strip()
    if bucket and state_database.backend_preference() != "blob":
        key = str(os.getenv("CATALOG_ERP_S3_KEY") or DEFAULT_ERP_S3_KEY).strip("/")
        return "s3", bucket, key

    blob_token = str(os.getenv("BLOB_READ_WRITE_TOKEN") or "").strip()
    if blob_token and _truthy(os.getenv("CATALOG_ERP_BLOB_ENABLED")):
        path = str(os.getenv("CATALOG_ERP_BLOB_PATH") or DEFAULT_ERP_BLOB_PATH).strip("/")
        return "blob", path, blob_token
    return None


def storage_uri() -> str | None:
    if state_database.is_configured():
        return f"postgres-state://{state_database.ERP_KEY}"
    backend = _backend()
    if backend is None:
        return None
    kind, container, key_or_token = backend
    if kind == "s3":
        return f"s3://{container}/{key_or_token}"
    return f"vercel-blob://{container}"


def load_active(*, fresh: bool = False) -> ERPObject | None:
    if state_database.is_configured():
        stored = state_database.load_object(state_database.ERP_KEY)
        if stored is None:
            return None
        return ERPObject(stored.content, stored.etag, stored.updated_at)
    backend = _backend()
    if backend is None:
        return None

    kind, container, key_or_token = backend
    if kind == "s3":
        import boto3
        from botocore.exceptions import ClientError

        try:
            response = boto3.client("s3").get_object(Bucket=container, Key=key_or_token)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise
        return ERPObject(
            content=response["Body"].read(),
            etag=str(response.get("ETag") or "").strip('"') or None,
            updated_at=response.get("LastModified").isoformat()
            if response.get("LastModified")
            else None,
        )

    from vercel.blob import BlobNotFoundError, get

    def fetch() -> tuple[bytes | None, str | None]:
        try:
            response = get(container, access="private", token=key_or_token, use_cache=False)
        except BlobNotFoundError:
            return None, None
        return (bytes(response.content), response.etag) if response and response.content else (None, None)

    content, etag = blob_cache.read_versioned(key_or_token, container, fetch, fresh=fresh)
    return ERPObject(content=content, etag=etag, updated_at=None) if content else None



def write_active(content: bytes, *, expected_etag: str | None, expected_missing: bool) -> str:
    if state_database.is_configured():
        if not expected_missing and not expected_etag:
            raise ERPWriteConflictError("The ERP snapshot changed; reload the catalog and retry.")
        try:
            return state_database.write_object(
                state_database.ERP_KEY,
                content,
                expected_etag=expected_etag,
                expected_missing=expected_missing,
            )
        except state_database.StateWriteConflictError as exc:
            raise ERPWriteConflictError("The ERP snapshot changed; reload the catalog and retry.") from exc
    backend = _backend()
    if backend is None:
        raise RuntimeError("ERP remote storage is not configured")

    kind, container, key_or_token = backend
    if kind == "s3":
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client("s3")
        request: dict[str, object] = {
            "Bucket": container,
            "Key": key_or_token,
            "Body": content,
            "ContentType": "application/json; charset=utf-8",
            "CacheControl": "no-store",
            "ServerSideEncryption": "AES256",
        }
        if expected_missing:
            request["IfNoneMatch"] = "*"
        elif expected_etag:
            request["IfMatch"] = f'"{expected_etag.strip(chr(34))}"'
        else:
            raise ERPWriteConflictError("The ERP snapshot changed; reload the catalog and retry.")

        try:
            response = client.put_object(**request)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"PreconditionFailed", "ConditionalRequestConflict"} or status in {409, 412}:
                raise ERPWriteConflictError(
                    "The ERP snapshot changed during this update; reload the catalog and retry."
                ) from exc
            raise
        return str(response.get("ETag") or "").strip('"')

    try:
        return blob_cache.write_versioned(key_or_token, container, content, lambda: put_versioned(
            container, content, token=key_or_token,
            expected_etag=expected_etag, expected_missing=expected_missing,
        ))
    except BlobWriteConflictError as exc:
        raise ERPWriteConflictError(str(exc)) from exc


# Inbox objects are immutable and separate from the active catalog. A review can
# therefore run on a different serverless instance without losing the upload.
INBOX_PREFIX = "catalogo/erp_inbox/"
INBOX_URI_PREFIX = "erp-inbox://"


def _inbox_key(reference: str) -> str:
    import re
    suffix = reference.removeprefix(INBOX_URI_PREFIX)
    if not reference.startswith(INBOX_URI_PREFIX) or not re.fullmatch(r"[a-f0-9]{32}/[A-Za-z0-9._-]+\.json", suffix, re.IGNORECASE):
        raise ValueError("Invalid ERP review file reference")
    return INBOX_PREFIX + suffix


def _inbox_metadata(key: str, size: int, updated_at: str) -> dict:
    reference = INBOX_URI_PREFIX + key.removeprefix(INBOX_PREFIX)
    if _inbox_key(reference) != key:
        raise ValueError("Invalid ERP review file reference")
    return {"path": reference, "name": key.rsplit("/", 1)[-1], "size_bytes": size, "updated_at": updated_at}


def store_inbox_file(name: str, content: bytes) -> dict:
    from datetime import datetime, timezone
    from uuid import uuid4
    key = _inbox_key(INBOX_URI_PREFIX + uuid4().hex + "/" + name)
    if state_database.is_configured():
        state_database.write_object(key, content, expected_missing=True)
    else:
        backend = _backend()
        if backend is None:
            raise RuntimeError("ERP remote storage is not configured")
        kind, container, key_or_token = backend
        if kind == "s3":
            import boto3
            boto3.client("s3").put_object(Bucket=container, Key=key, Body=content,
                ContentType="application/json; charset=utf-8", CacheControl="no-store",
                ServerSideEncryption="AES256", IfNoneMatch="*")
        else:
            from vercel.blob import put
            put(key, content, access="private", token=key_or_token,
                content_type="application/json; charset=utf-8", add_random_suffix=False,
                overwrite=False, cache_control_max_age=0)
    return _inbox_metadata(key, len(content), datetime.now(timezone.utc).isoformat())


def load_inbox_file(reference: str) -> tuple[bytes, dict]:
    key = _inbox_key(reference)
    if state_database.is_configured():
        stored = state_database.load_object(key)
        if stored is None:
            raise ValueError("ERP review file not found")
        content, updated_at = stored.content, stored.updated_at
    else:
        backend = _backend()
        if backend is None:
            raise ValueError("ERP review storage is not configured")
        kind, container, key_or_token = backend
        if kind == "s3":
            import boto3
            from botocore.exceptions import ClientError
            try:
                response = boto3.client("s3").get_object(Bucket=container, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
                    raise ValueError("ERP review file not found") from exc
                raise
            with response["Body"] as body:
                content = body.read()
            updated_at = response["LastModified"].isoformat()
        else:
            from vercel.blob import BlobNotFoundError, get
            try:
                stored = get(key, access="private", token=key_or_token, use_cache=False, timeout=20)
            except BlobNotFoundError as exc:
                raise ValueError("ERP review file not found") from exc
            if stored is None:
                raise ValueError("ERP review file not found")
            content, updated_at = bytes(stored.content), stored.uploaded_at.isoformat()
    return content, _inbox_metadata(key, len(content), updated_at)


def list_inbox_files() -> list[dict]:
    if state_database.is_configured():
        entries = state_database.list_object_metadata(INBOX_PREFIX)
    else:
        backend = _backend()
        if backend is None:
            return []
        kind, container, key_or_token = backend
        if kind == "s3":
            import boto3
            pages = boto3.client("s3").get_paginator("list_objects_v2").paginate(Bucket=container, Prefix=INBOX_PREFIX)
            entries = [{"key": item["Key"], "size_bytes": item["Size"], "updated_at": item["LastModified"].isoformat()}
                for page in pages for item in page.get("Contents", [])]
        else:
            from vercel.blob import iter_objects
            entries = [{"key": item.pathname, "size_bytes": item.size, "updated_at": item.uploaded_at.isoformat()}
                for item in iter_objects(prefix=INBOX_PREFIX, token=key_or_token, batch_size=100)]
    files = []
    for item in entries:
        try:
            files.append(_inbox_metadata(item["key"], item["size_bytes"], item["updated_at"]))
        except ValueError:
            # Ignore foreign objects; references only address immutable inbox JSONs.
            continue
    return files
