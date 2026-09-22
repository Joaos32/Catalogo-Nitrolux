"""Endpoints gerais de dados do catalogo."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
from functools import lru_cache

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from ..errors import internal_server_error_response
from ..security import require_representative_access
from ..schemas import CatalogProductSchema
from ...services import fetch_sheet_or_local_products, list_catalog_products


router = APIRouter(dependencies=[Depends(require_representative_access)])
logger = logging.getLogger(__name__)
CATALOG_CACHE_CONTROL = "private, no-cache"
_catalog_build_lock = threading.Lock()


def _serialize_catalog_products() -> tuple[bytes, str]:
    payload = json.dumps(
        list_catalog_products(),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    etag = f'"{hashlib.sha256(payload).hexdigest()}"'
    return payload, etag


@lru_cache(maxsize=1)
def _cached_vercel_catalog_payload() -> tuple[bytes, str]:
    return _serialize_catalog_products()


def _catalog_payload() -> tuple[bytes, str]:
    if str(os.getenv("VERCEL") or "").strip().lower() in {"1", "true", "yes"}:
        with _catalog_build_lock:
            return _cached_vercel_catalog_payload()
    return _serialize_catalog_products()


def _catalog_headers(etag: str) -> dict[str, str]:
    return {
        "Cache-Control": CATALOG_CACHE_CONTROL,
        "ETag": etag,
        "Vary": "Authorization, Cookie, Accept-Encoding",
    }


@router.get("/sheet", response_model=list[CatalogProductSchema])
async def sheet_data(url: str | None = None):
    """Retorna dados JSON de uma planilha Google via parametro de consulta `url`."""
    if not url:
        return JSONResponse(status_code=400, content={"error": "missing url query parameter"})
    try:
        return fetch_sheet_or_local_products(url)
    except Exception as exc:
        logger.exception("Error fetching sheet data: %s", exc)
        return internal_server_error_response()


@router.get("/local/produtos")
async def local_products(request: Request):
    """Retorna produtos encontrados na pasta local do OneDrive."""
    try:
        payload, etag = await asyncio.to_thread(_catalog_payload)
        if etag in {item.strip() for item in request.headers.get("if-none-match", "").split(",")}:
            return Response(status_code=304, headers=_catalog_headers(etag))
        return Response(
            content=payload,
            media_type="application/json; charset=utf-8",
            headers=_catalog_headers(etag),
        )
    except Exception as exc:
        logger.exception("Error loading local products: %s", exc)
        return internal_server_error_response()
