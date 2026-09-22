"""Endpoints de exportacao do catalogo."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
from functools import lru_cache

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from ..errors import internal_server_error_response
from ..security import require_representative_access


router = APIRouter(dependencies=[Depends(require_representative_access)])
logger = logging.getLogger(__name__)
EXPORT_CACHE_CONTROL = "private, no-cache"
_export_build_lock = threading.Lock()


@lru_cache(maxsize=8)
def _cached_export(
    format_name: str,
    query: str,
    category: str,
    code: str,
    brand: str,
) -> tuple[bytes, str, str]:
    from ...exporter import build_catalog_export

    return build_catalog_export(
        format_name=format_name,
        query=query,
        category=category,
        code=code,
        brand=brand,
    )


def _build_export(
    *,
    format_name: str,
    query: str,
    category: str,
    code: str,
    brand: str,
) -> tuple[bytes, str, str]:
    from ...exporter import build_catalog_export

    normalized_format = format_name.lower().strip()
    cacheable_format = normalized_format in {"csv", "json", "xlsx", "xls"} or (
        normalized_format in {"pdf", "ficha"} and bool(code)
    )
    on_vercel = str(os.getenv("VERCEL") or "").strip().lower() in {"1", "true", "yes"}
    if on_vercel and cacheable_format:
        # Prevent duplicate CPU-heavy generation inside a concurrent Fluid
        # Compute instance. The bounded cache avoids unrestrained memory use.
        with _export_build_lock:
            return _cached_export(normalized_format, query, category, code, brand)
    return build_catalog_export(
        format_name=normalized_format,
        query=query,
        category=category,
        code=code,
        brand=brand,
    )


@router.get("/export")
async def export_catalog(
    request: Request,
    format: str = "csv",
    query: str | None = None,
    category: str | None = None,
    code: str | None = None,
    brand: str | None = None,
):
    """Gera uma exportacao do catalogo em CSV, Excel, JSON, PDF ou ZIP."""
    try:
        normalized_query = str(query or "").strip()
        normalized_category = str(category or "").strip()
        normalized_code = str(code or "").strip()
        normalized_brand = str(brand or "").strip()
        payload, media_type, filename = await asyncio.to_thread(
            _build_export,
            format_name=format,
            query=normalized_query,
            category=normalized_category,
            code=normalized_code,
            brand=normalized_brand,
        )
        etag = f'"{hashlib.sha256(payload).hexdigest()}"'
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": EXPORT_CACHE_CONTROL,
            "ETag": etag,
            "Vary": "Authorization, Cookie, Accept-Encoding",
        }
        if etag in {item.strip() for item in request.headers.get("if-none-match", "").split(",")}:
            return Response(status_code=304, headers=headers)
        return Response(
            content=payload,
            media_type=media_type,
            headers=headers,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error exporting catalog: %s", exc)
        return internal_server_error_response()
