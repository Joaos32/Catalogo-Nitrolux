"""Endpoints técnicos de integração do catálogo."""

from __future__ import annotations

import asyncio
import hashlib
import json
import unicodedata
from collections import Counter
from functools import lru_cache

from fastapi import APIRouter, Depends, Query, Request, Response

from ..security import require_integration_api_key
from ...services.catalog_service import _load_prebuilt_catalog
from .catalog import _catalog_headers, _catalog_payload


router = APIRouter()


@lru_cache(maxsize=1)
def _integration_catalog_products() -> tuple[dict, ...]:
    """Prioriza o snapshot validado para evitar varreduras locais demoradas."""
    products = _load_prebuilt_catalog()
    if products is None:
        payload, _ = _catalog_payload()
        products = json.loads(payload)
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


@router.get(
    "/integration/products",
    dependencies=[Depends(require_integration_api_key)],
)
async def integration_products(
    request: Request,
    category: str | None = Query(default=None, max_length=100),
):
    """Retorna o cadastro consolidado para consumidores técnicos autorizados."""
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
    "/integration/categories",
    dependencies=[Depends(require_integration_api_key)],
)
async def integration_categories():
    """Lista as categorias e quantidades disponíveis para consulta."""
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
