"""Busca de imagens de produtos em bucket S3."""

from __future__ import annotations

import os
import re
from pathlib import PurePosixPath
from typing import Dict, Iterable, List
from urllib.parse import quote

from .cache import cached
from .local_catalog import IMG_EXTENSIONS
from .product_media import _classify_variant, _match_filename


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _normalize_prefix(value: str | None) -> str:
    cleaned = (value or "").strip().strip("/")
    return f"{cleaned}/" if cleaned else ""


def is_configured() -> bool:
    return bool(_optional_env("CATALOG_S3_MEDIA_BUCKET"))


def _is_image_key(key: str) -> bool:
    lowered = key.lower()
    return any(lowered.endswith(ext) for ext in IMG_EXTENSIONS)


def _matches_code(name: str, code: str) -> bool:
    if _match_filename(name, code) is not None:
        return True
    return re.search(rf"(?<!\d){re.escape(str(code))}(?!\d)", name or "") is not None


def _image_sort_key(item: Dict, code: str) -> tuple:
    name = str(item.get("name") or "")
    variant = _match_filename(name, code)
    if variant is None:
        variant = 99
    return (variant, name.lower())


def _iter_s3_objects(bucket: str, prefix: str) -> Iterable[Dict]:
    import boto3

    client = boto3.client("s3", region_name=_optional_env("AWS_REGION") or _optional_env("AWS_DEFAULT_REGION"))
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents") or []:
            if isinstance(item, dict):
                yield item


def _public_object_url(bucket: str, key: str) -> str:
    public_base_url = _optional_env("CATALOG_S3_MEDIA_PUBLIC_BASE_URL")
    if public_base_url:
        return f"{public_base_url.rstrip('/')}/{quote(key, safe='/')}"

    region = _optional_env("AWS_REGION") or _optional_env("AWS_DEFAULT_REGION") or "us-east-1"
    if region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{quote(key, safe='/')}"


def _object_url(bucket: str, key: str) -> str:
    if not _parse_bool_env("CATALOG_S3_MEDIA_PRESIGNED_URLS", default=False):
        return _public_object_url(bucket, key)

    import boto3

    expires = int(os.getenv("CATALOG_S3_MEDIA_PRESIGNED_EXPIRES_SECONDS", "3600"))
    client = boto3.client("s3", region_name=_optional_env("AWS_REGION") or _optional_env("AWS_DEFAULT_REGION"))
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


@cached(stale_if_error=True)
def list_s3_images(bucket: str | None = None, prefix: str | None = None) -> List[Dict]:
    media_bucket = bucket or _optional_env("CATALOG_S3_MEDIA_BUCKET")
    if not media_bucket:
        return []

    media_prefix = _normalize_prefix(prefix if prefix is not None else _optional_env("CATALOG_S3_MEDIA_PREFIX"))
    images: List[Dict] = []

    for item in _iter_s3_objects(media_bucket, media_prefix):
        key = str(item.get("Key") or "")
        if not key or key.endswith("/") or not _is_image_key(key):
            continue
        name = PurePosixPath(key).name
        images.append(
            {
                "bucket": media_bucket,
                "key": key,
                "name": name,
                "url": _object_url(media_bucket, key),
            }
        )

    return images


def find_images_for_code(code: str, bucket: str | None = None, prefix: str | None = None) -> List[Dict]:
    code_text = str(code or "").strip()
    if not code_text:
        return []

    matches = [
        item
        for item in list_s3_images(bucket=bucket, prefix=prefix)
        if _matches_code(str(item.get("name") or ""), code_text)
    ]
    matches.sort(key=lambda item: _image_sort_key(item, code_text))

    return [
        {
            "name": str(item.get("name") or ""),
            "variant": _match_filename(str(item.get("name") or ""), code_text) or 0,
            "url": str(item.get("url") or ""),
        }
        for item in matches
    ]


def categorize_photos_for_code(code: str, bucket: str | None = None, prefix: str | None = None) -> Dict[str, str | None]:
    photos: Dict[str, str | None] = {
        "white_background": None,
        "ambient": None,
        "measures": None,
    }

    for image in find_images_for_code(code, bucket=bucket, prefix=prefix):
        variant = _classify_variant(str(image.get("name") or ""), code)
        if variant in photos and not photos[variant]:
            photos[variant] = str(image.get("url") or "") or None

    return photos
