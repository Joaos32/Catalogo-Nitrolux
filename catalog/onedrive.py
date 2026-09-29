"""Utilitarios para integrar OneDrive via Microsoft Graph e pastas locais."""

import os
import re
from typing import List, Dict

from . import graph_catalog as _graph_catalog
from . import local_catalog as _local_catalog
from . import product_catalog as _product_catalog
from .graph_client import get_share_info, list_children
from .cache import cached
from .local_catalog import IMG_EXTENSIONS
from .product_media import (
    _asset_url,
    _canonical_category,
    _code_sort_key,
    _local_file_sort_key,
    _match_filename,
)
from .stock_catalog import (
    _enrich_stock_products_with_photos,
    _get_stock_photo_records_for_codes,
    _get_stock_photo_record_for_code,
    _load_products_from_available_stock_report,
    _resolve_stock_photos_root,
)

def _encode_share_url(url: str) -> str:
    return _graph_catalog.encode_share_url(url)


def list_shared_items(share_url: str):
    return _graph_catalog.list_shared_items(
        share_url,
        get_share_info_fn=get_share_info,
        list_children_fn=list_children,
    )


def categorize_photos(items: list, code: str = None) -> dict:
    return _graph_catalog.categorize_photos(items, code=code)


@cached(stale_if_error=True)
def find_images_for_code(share_url: str, code: str, max_depth: int = 5) -> List[Dict]:
    return _graph_catalog.find_images_for_code(
        share_url,
        code,
        max_depth=max_depth,
        get_share_info_fn=get_share_info,
        list_children_fn=list_children,
        match_filename_fn=_match_filename,
        img_extensions=IMG_EXTENSIONS,
    )


def _existing_local_roots(path_override: str | None = None) -> List[str]:
    return _local_catalog.existing_local_roots(path_override)


def resolve_local_products_root(path_override: str | None = None) -> str | None:
    return _local_catalog.resolve_local_products_root(path_override)


def _normalize_category_label(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    if cleaned in {"***", "-", "â€”"}:
        return ""
    return cleaned


def _resolve_shortcut_targets(scan_root: str) -> Dict[str, str]:
    return _local_catalog.resolve_shortcut_targets(scan_root)


def _scan_local_photo_index(root: str) -> Dict[str, Dict]:
    return _local_catalog.scan_local_photo_index(
        root,
        allowed_roots=_existing_local_roots(),
        shortcut_targets=_resolve_shortcut_targets(os.path.abspath(root)),
    )


@cached(stale_if_error=True)
def build_local_photo_index(root_path: str | None = None) -> Dict[str, Dict]:
    return _local_catalog.build_local_photo_index(
        root_path,
        resolve_root=resolve_local_products_root,
        existing_roots_resolver=_existing_local_roots,
        shortcut_target_resolver=_resolve_shortcut_targets,
    )


def _get_local_index(path_override: str | None = None) -> Dict[str, Dict]:
    """Carrega o indice local do disco para refletir alteracoes de pasta imediatamente."""
    return _local_catalog.get_local_index(
        path_override,
        existing_roots_resolver=_existing_local_roots,
        shortcut_target_resolver=_resolve_shortcut_targets,
    )


def list_local_products(path_override: str | None = None) -> List[Dict]:
    return _product_catalog.list_local_products(
        path_override,
        get_local_index=_get_local_index,
        load_stock_products=_load_products_from_available_stock_report,
        enrich_stock_products_with_photos=_enrich_stock_products_with_photos,
        get_stock_photo_records_for_codes=_get_stock_photo_records_for_codes,
        asset_url=_asset_url,
        canonical_category=_canonical_category,
        code_sort_key=_code_sort_key,
    )


def categorize_local_photos(code: str, path_override: str | None = None) -> Dict[str, str | None]:
    return _product_catalog.categorize_local_photos(
        code,
        path_override,
        get_local_index=_get_local_index,
        get_stock_photo_record_for_code=_get_stock_photo_record_for_code,
        asset_url=_asset_url,
    )


def find_local_images_for_code(code: str, path_override: str | None = None) -> List[Dict]:
    return _product_catalog.find_local_images_for_code(
        code,
        path_override,
        get_local_index=_get_local_index,
        get_stock_photo_record_for_code=_get_stock_photo_record_for_code,
        local_file_sort_key=_local_file_sort_key,
        asset_url=_asset_url,
    )


def resolve_local_asset_path(rel_path: str, path_override: str | None = None) -> str | None:
    return _product_catalog.resolve_local_asset_path(
        rel_path,
        path_override,
        existing_local_roots=_existing_local_roots,
        resolve_stock_photos_root=_resolve_stock_photos_root,
    )
