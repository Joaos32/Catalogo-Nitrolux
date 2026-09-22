"""Galeria de imagens publicada por CDN a partir de um manifesto local."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

from .core import load_settings
from .product_media import (
    SEGMENT_PREFIX_CODE_PATTERN,
    _classify_variant,
    _local_file_sort_key,
    _match_filename,
)


DEFAULT_MANIFEST_PATH = "reports/media_manifest.json"


def _optional_env(name: str) -> str:
    return str(os.getenv(name) or "").strip()


def cdn_base_url() -> str:
    return _optional_env("CATALOG_MEDIA_CDN_BASE_URL").rstrip("/")


def manifest_path() -> Path:
    explicit = _optional_env("CATALOG_MEDIA_MANIFEST_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (load_settings().base_dir / DEFAULT_MANIFEST_PATH).resolve()


def is_configured() -> bool:
    return bool(cdn_base_url()) and manifest_path().is_file()


def _asset_url(key: str) -> str:
    return f"{cdn_base_url()}/{quote(str(key or '').lstrip('/'), safe='/')}"


@lru_cache(maxsize=4)
def _load_index(path_value: str) -> Dict[str, List[Dict[str, Any]]]:
    path = Path(path_value)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items = payload.get("images") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        return {}

    index: Dict[str, List[Dict[str, Any]]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        key = str(raw_item.get("key") or "").strip().replace("\\", "/")
        name = str(raw_item.get("name") or Path(key).name).strip()
        stem = Path(name).stem.strip()
        match = SEGMENT_PREFIX_CODE_PATTERN.match(stem)
        if not key or not name or not match:
            continue
        code = match.group("code")
        if _match_filename(name, code) is None:
            continue
        index.setdefault(code, []).append({"key": key, "name": name, "rel_path": key})

    for code, items in index.items():
        items.sort(key=lambda item: _local_file_sort_key(item, code))
    return index


def _index() -> Dict[str, List[Dict[str, Any]]]:
    return _load_index(str(manifest_path())) if is_configured() else {}


def find_images_for_code(code: str) -> List[Dict[str, Any]]:
    normalized_code = str(code or "").strip()
    return [
        {
            "name": item["name"],
            "variant": _match_filename(item["name"], normalized_code) or 0,
            "url": _asset_url(item["key"]),
        }
        for item in _index().get(normalized_code, [])
    ]


def categorize_photos_for_code(code: str) -> Dict[str, str | None]:
    photos: Dict[str, str | None] = {
        "white_background": None,
        "ambient": None,
        "measures": None,
    }
    fallback_urls: List[str] = []
    for image in find_images_for_code(code):
        category = _classify_variant(image["name"], str(code))
        if category in photos and not photos[category]:
            photos[category] = image["url"]
        else:
            fallback_urls.append(image["url"])

    chosen = {url for url in photos.values() if url}
    for category in ("white_background", "ambient", "measures"):
        if photos[category]:
            continue
        fallback = next((url for url in fallback_urls if url not in chosen), None)
        if fallback:
            photos[category] = fallback
            chosen.add(fallback)
    return photos


def enrich_products_with_photos(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not is_configured():
        return products
    index = _index()
    enriched: List[Dict[str, Any]] = []
    for product in products:
        merged = dict(product)
        code = str(merged.get("Codigo") or "").strip()
        if code in index:
            photos = categorize_photos_for_code(code)
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
