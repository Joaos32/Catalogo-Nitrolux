"""Endpoints gerais de dados do catalogo."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from ..errors import internal_server_error_response
from ..security import require_representative_access
from ..schemas import CatalogProductSchema
from ...services import fetch_sheet_or_local_products, list_catalog_products


router = APIRouter(dependencies=[Depends(require_representative_access)])
logger = logging.getLogger(__name__)


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


@router.get("/local/produtos", response_model=list[CatalogProductSchema])
async def local_products(response: Response):
    """Retorna produtos encontrados na pasta local do OneDrive."""
    try:
        response.headers["Cache-Control"] = "private, max-age=30"
        return list_catalog_products()
    except Exception as exc:
        logger.exception("Error loading local products: %s", exc)
        return internal_server_error_response()
