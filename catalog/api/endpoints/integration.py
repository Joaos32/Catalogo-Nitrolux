"""Endpoints técnicos de integração do catálogo."""

from __future__ import annotations

import asyncio
import hashlib
import json
import unicodedata
import threading
import time
from collections import Counter
from functools import lru_cache

from fastapi import APIRouter, Depends, Query, Request, Response

from ..security import require_integration_api_key
from ...services.catalog_service import _load_prebuilt_catalog
from .catalog import _catalog_headers, _catalog_payload


router = APIRouter()
_INTEGRATION_CACHE_TTL_SECONDS = 10
_integration_cache_lock = threading.Lock()
_integration_cache_refreshed_at = 0.0


def _refresh_integration_cache_if_stale() -> None:
    global _integration_cache_refreshed_at
    now = time.monotonic()
    with _integration_cache_lock:
        if now - _integration_cache_refreshed_at < _INTEGRATION_CACHE_TTL_SECONDS:
            return
        _integration_catalog_products.cache_clear()
        _integration_catalog_payload.cache_clear()
        _pienza_products_payload.cache_clear()
        _integration_cache_refreshed_at = now


def invalidate_integration_catalog_cache() -> None:
    """Drop process-local feed snapshots after the ERP catalog changes."""
    global _integration_cache_refreshed_at
    with _integration_cache_lock:
        _integration_catalog_products.cache_clear()
        _integration_catalog_payload.cache_clear()
        _pienza_products_payload.cache_clear()
        _integration_cache_refreshed_at = time.monotonic()


@lru_cache(maxsize=1)
def _integration_catalog_products() -> tuple[dict, ...]:
    """Prioriza o snapshot validado para evitar varreduras locais demoradas."""
    products = _load_prebuilt_catalog()
    if products is None:
        payload, _ = _catalog_payload()
        products = json.loads(payload)
    else:
        from ...erp_catalog import merge_products_with_erp

        products = merge_products_with_erp(products)
    return tuple(products)


def _normalized_category(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


@lru_cache(maxsize=64)
def _integration_catalog_payload(category: str = "") -> tuple[bytes, str]:
    products = _integration_catalog_products()
    normalized_category = _normalized_category(category)
    if normalized_category:
        products = tuple(
            product
            for product in products
            if _normalized_category(str(product.get("Categoria") or "")) == normalized_category
        )
    payload = json.dumps(products, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return payload, f'"{hashlib.sha256(payload).hexdigest()}"'


@lru_cache(maxsize=1)
def _pienza_products_payload() -> tuple[bytes, str]:
    """Builds the Pienza website feed with only product code and description."""
    products = []
    for product in _integration_catalog_products():
        brand_code = str(product.get("CODMARCA") or product.get("CodMarca") or "").strip()
        if brand_code not in {"2", "2.0"}:
            continue

        code = str(product.get("Codigo") or product.get("CODPROD") or "").strip()
        description = str(
            product.get("Descricao") or product.get("DESCRICAO") or product.get("Nome") or ""
        ).strip()
        if code and description:
            products.append({"codigo": code, "descricao": description})

    payload = json.dumps(products, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return payload, f'"{hashlib.sha256(payload).hexdigest()}"'


@router.get(
    "/integration/products",
    dependencies=[Depends(require_integration_api_key)],
)
async def integration_products(
    request: Request,
    category: str | None = Query(default=None, max_length=100),
):
    """Retorna o cadastro consolidado para consumidores técnicos autorizados."""
    _refresh_integration_cache_if_stale()
    payload, etag = await asyncio.to_thread(
        _integration_catalog_payload,
        category or "",
    )
    requested_etags = {
        item.strip() for item in request.headers.get("if-none-match", "").split(",")
    }
    if etag in requested_etags:
        return Response(status_code=304, headers=_catalog_headers(etag))
    return Response(
        content=payload,
        media_type="application/json; charset=utf-8",
        headers=_catalog_headers(etag),
    )


@router.get(
    "/integration/pienza/products",
    dependencies=[Depends(require_integration_api_key)],
)
async def integration_pienza_products(request: Request):
    """Returns the Pienza product feed with only code and description."""
    _refresh_integration_cache_if_stale()
    payload, etag = await asyncio.to_thread(_pienza_products_payload)
    requested_etags = {
        item.strip() for item in request.headers.get("if-none-match", "").split(",")
    }
    if etag in requested_etags:
        return Response(status_code=304, headers=_catalog_headers(etag))
    return Response(
        content=payload,
        media_type="application/json; charset=utf-8",
        headers=_catalog_headers(etag),
    )


@router.get(
    "/integration/categories",
    dependencies=[Depends(require_integration_api_key)],
)
async def integration_categories():
    """Lista as categorias e quantidades disponíveis para consulta."""
    _refresh_integration_cache_if_stale()
    counts = Counter(
        str(product.get("Categoria") or "Sem categoria").strip() or "Sem categoria"
        for product in _integration_catalog_products()
    )
    return {
        "categories": [
            {"name": name, "total": total}
            for name, total in sorted(counts.items(), key=lambda item: item[0].casefold())
        ]
    }
