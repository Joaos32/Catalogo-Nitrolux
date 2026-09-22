"""Midia do catalogo armazenada em um Vercel Blob privado."""

from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import Any, Dict, List
from urllib.parse import quote

from .cache import cached
from .local_catalog import IMG_EXTENSIONS
from .product_media import _classify_variant, _local_file_sort_key, _match_filename


DEFAULT_MEDIA_PREFIX = "catalogo/media/"


def _optional_env(name: str) -> str:
    return str(os.getenv(name) or "").strip()


def _parse_bool(value: str, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on", "sim"}


def blob_token() -> str:
    return _optional_env("CATALOG_MEDIA_BLOB_TOKEN") or _optional_env("BLOB_READ_WRITE_TOKEN")


def media_prefix() -> str:
    prefix = _optional_env("CATALOG_MEDIA_BLOB_PREFIX") or DEFAULT_MEDIA_PREFIX
    normalized = prefix.replace("\\", "/").strip("/")
    return f"{normalized}/" if normalized else ""


def is_configured() -> bool:
    return bool(blob_token()) and _parse_bool(_optional_env("CATALOG_MEDIA_BLOB_ENABLED"))


def _asset_url(pathname: str) -> str:
    # `path` conflita com o parametro curinga `:path*` do rewrite do Vercel.
    return f"/catalog/blob/asset?blobPath={quote(pathname, safe='')}"


@cached
def _list_media_items() -> List[Dict[str, Any]]:
    if not is_configured():
        return []

    from vercel.blob import iter_objects

    prefix = media_prefix()
    items: List[Dict[str, Any]] = []
    for blob in iter_objects(prefix=prefix, token=blob_token(), batch_size=1000):
        pathname = str(blob.pathname or "")
        suffix = PurePosixPath(pathname).suffix.lower()
        if not pathname.startswith(prefix) or suffix not in IMG_EXTENSIONS:
            continue
        items.append(
            {
                "name": PurePosixPath(pathname).name,
                "rel_path": pathname[len(prefix) :],
                "pathname": pathname,
                "size": int(blob.size or 0),
            }
        )
    return items


def _find_images_for_code(code: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_code = str(code or "").strip()
    matches = [item for item in items if _match_filename(item["name"], normalized_code) is not None]
    matches.sort(key=lambda item: _local_file_sort_key(item, normalized_code))
    return [
        {
            "name": item["name"],
            "variant": _match_filename(item["name"], normalized_code) or 0,
            "url": _asset_url(item["pathname"]),
        }
        for item in matches
    ]


def find_images_for_code(code: str) -> List[Dict[str, Any]]:
    return _find_images_for_code(code, _list_media_items())


def _categorize_photos_for_code(code: str, items: List[Dict[str, Any]]) -> Dict[str, str | None]:
    images = _find_images_for_code(code, items)
    categorized: Dict[str, str | None] = {
        "white_background": None,
        "ambient": None,
        "measures": None,
    }
    others: List[str] = []
    for image in images:
        category = _classify_variant(image["name"], str(code))
        if category in categorized and not categorized[category]:
            categorized[category] = image["url"]
        else:
            others.append(image["url"])

    chosen = {value for value in categorized.values() if value}
    for category in ("white_background", "ambient", "measures"):
        if categorized[category]:
            continue
        fallback = next((url for url in others if url not in chosen), None)
        if fallback:
            categorized[category] = fallback
            chosen.add(fallback)
    return categorized


def categorize_photos_for_code(code: str) -> Dict[str, str | None]:
    return _categorize_photos_for_code(code, _list_media_items())


def enrich_products_with_photos(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not is_configured():
        return products

    items = _list_media_items()
    enriched: List[Dict[str, Any]] = []
    for product in products:
        merged = dict(product)
        code = str(merged.get("Codigo") or "").strip()
        photos = _categorize_photos_for_code(code, items) if code else {}
        white = photos.get("white_background")
        ambient = photos.get("ambient")
        measures = photos.get("measures")
        if white:
            merged["FotoBranco"] = white
        if ambient:
            merged["FotoAmbient"] = ambient
        if measures:
            merged["FotoMedidas"] = measures
        cover = ambient or white or measures
        if cover:
            merged["URLFoto"] = cover
        enriched.append(merged)
    return enriched


def get_asset(pathname: str):
    normalized = str(pathname or "").replace("\\", "/").lstrip("/")
    prefix = media_prefix()
    if not is_configured() or not normalized.startswith(prefix):
        return None
    if PurePosixPath(normalized).suffix.lower() not in IMG_EXTENSIONS:
        return None

    from vercel.blob import BlobNotFoundError, get

    try:
        return get(normalized, access="private", token=blob_token())
    except BlobNotFoundError:
        return None
