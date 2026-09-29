"""Durable object storage for the active ERP catalog snapshot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


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
    if bucket:
        key = str(os.getenv("CATALOG_ERP_S3_KEY") or DEFAULT_ERP_S3_KEY).strip("/")
        return "s3", bucket, key

    blob_token = str(os.getenv("BLOB_READ_WRITE_TOKEN") or "").strip()
    if blob_token and _truthy(os.getenv("CATALOG_ERP_BLOB_ENABLED")):
        path = str(os.getenv("CATALOG_ERP_BLOB_PATH") or DEFAULT_ERP_BLOB_PATH).strip("/")
        return "blob", path, blob_token
    return None


def storage_uri() -> str | None:
    backend = _backend()
    if backend is None:
        return None
    kind, container, key_or_token = backend
    if kind == "s3":
        return f"s3://{container}/{key_or_token}"
    return f"vercel-blob://{container}"


def load_active() -> ERPObject | None:
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

    try:
        response = get(container, access="private", token=key_or_token, use_cache=False)
    except BlobNotFoundError:
        return None
    if response is None or not response.content:
        return None
    return ERPObject(content=response.content, etag=None, updated_at=None)


def write_active(content: bytes, *, expected_etag: str | None, expected_missing: bool) -> str:
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

    from vercel.blob import put

    put(
        container,
        content,
        access="private",
        content_type="application/json; charset=utf-8",
        add_random_suffix=False,
        overwrite=True,
        cache_control_max_age=0,
        token=key_or_token,
    )
    return ""
