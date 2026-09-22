"""Servicos de leitura de produtos do catalogo."""

from __future__ import annotations

import logging
import os
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from ..spreadsheet import fetch_sheet


logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]
PREBUILT_CATALOG_PATH = BASE_DIR / "reports" / "catalog_runtime.json"
PREBUILT_SOURCE_PATHS = {
    "erp_products": BASE_DIR / "reports" / "erp_products.json",
    "media_manifest": BASE_DIR / "reports" / "media_manifest.json",
    **{
        f"catalog_json/{path.name}": path
        for path in sorted((BASE_DIR / "catalog" / "json").glob("*.json"))
    },
}
PHOTO_FIELDS = ("URLFoto", "FotoBranco", "FotoAmbient", "FotoMedidas")


def _remove_unavailable_local_photo_urls(products: List[Dict]) -> List[Dict]:
    """Remove workstation-only image URLs from a serverless catalog."""
    cleaned: List[Dict] = []
    for product in products:
        merged = dict(product)
        for field in PHOTO_FIELDS:
            value = str(merged.get(field) or "").strip()
            if value.startswith("/catalog/local/asset"):
                merged[field] = ""
        cleaned.append(merged)
    return cleaned


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prebuilt_source_hashes() -> Dict[str, str]:
    return {
        name: _file_sha256(path)
        for name, path in PREBUILT_SOURCE_PATHS.items()
        if path.is_file()
    }


def _load_prebuilt_catalog() -> List[Dict] | None:
    if not PREBUILT_CATALOG_PATH.is_file():
        return None
    try:
        payload = json.loads(PREBUILT_CATALOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("source_hashes") != prebuilt_source_hashes():
            return None
        products = payload.get("products")
        return products if isinstance(products, list) else None
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring invalid prebuilt catalog at %s", PREBUILT_CATALOG_PATH)
        return None


def _build_catalog_products_from_sources() -> List[Dict]:
    from .. import cdn_media, onedrive, vercel_blob_media

    products = onedrive.list_local_products()
    products = cdn_media.enrich_products_with_photos(products)
    return vercel_blob_media.enrich_products_with_photos(products)


def _build_catalog_products() -> List[Dict]:
    if str(os.getenv("VERCEL") or "").strip().lower() in {"1", "true", "yes"}:
        prebuilt = _load_prebuilt_catalog()
        if prebuilt is not None:
            # The snapshot can be generated on a workstation where product
            # photos use /catalog/local/asset URLs. Those files do not exist in
            # Vercel's immutable filesystem, so replace them with the media
            # providers configured in the deployment before caching the result.
            from .. import cdn_media, vercel_blob_media

            products = cdn_media.enrich_products_with_photos(prebuilt)
            products = vercel_blob_media.enrich_products_with_photos(products)
            return _remove_unavailable_local_photo_urls(products)
    return _build_catalog_products_from_sources()


@lru_cache(maxsize=1)
def _cached_catalog_products() -> tuple[Dict, ...]:
    return tuple(_build_catalog_products())


def list_catalog_products() -> List[Dict]:
    # Files bundled into a Vercel deployment are immutable. Reusing the merged
    # catalog avoids reparsing and enriching thousands of products per request.
    if str(os.getenv("VERCEL") or "").strip().lower() in {"1", "true", "yes"}:
        return list(_cached_catalog_products())
    return _build_catalog_products()


def fetch_sheet_or_local_products(url: str) -> List[Dict]:
    try:
        return fetch_sheet(url)
    except ValueError as exc:
        logger.warning("Sheet fetch failed, trying local fallback: %s", exc, exc_info=True)
        try:
            local_products = list_catalog_products()
            if local_products:
                return local_products
        except Exception as local_exc:
            logger.exception("Local products fallback failed after sheet fetch error: %s", local_exc)
        return []
