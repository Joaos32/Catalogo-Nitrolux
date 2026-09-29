"""Endpoints de importacao e status do ERP."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from ..errors import internal_server_error_response
from ..security import require_erp_admin
from ...erp_storage import ERPWriteConflictError


router = APIRouter(dependencies=[Depends(require_erp_admin)])
logger = logging.getLogger(__name__)


@router.post("/erp/import")
async def import_erp_products(payload: dict | list = Body(...)):
    """Importa um payload JSON do ERP e atualiza o espelho de produtos por codigo."""
    try:
        from ...erp_catalog import import_erp_payload

        return import_erp_payload(payload)
    except ERPWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error importing ERP payload: %s", exc)
        return internal_server_error_response()


@router.post("/erp/upload")
async def upload_erp_file(request: Request, filename: str | None = None):
    """Recebe um arquivo JSON bruto no corpo da requisicao e importa para o catalogo."""
    try:
        from ...erp_catalog import get_max_upload_size_bytes, receive_erp_file

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = 0
            if declared_length > get_max_upload_size_bytes():
                return JSONResponse(status_code=413, content={"error": "ERP upload too large"})

        body = await request.body()
        if not body:
            return JSONResponse(status_code=400, content={"error": "empty request body"})

        selected_name = (
            filename
            or request.headers.get("x-file-name")
            or request.headers.get("x-filename")
            or "erp_upload.json"
        )

        return receive_erp_file(filename=selected_name, content=body)
    except ERPWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error uploading ERP file: %s", exc)
        return internal_server_error_response()


@router.post("/erp/stage-file")
async def stage_erp_file_upload(request: Request, filename: str | None = None):
    """Recebe um arquivo JSON bruto, valida e deixa pronto para implantacao."""
    try:
        from ...erp_catalog import get_max_upload_size_bytes, stage_erp_file

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = 0
            if declared_length > get_max_upload_size_bytes():
                return JSONResponse(status_code=413, content={"error": "ERP upload too large"})

        body = await request.body()
        if not body:
            return JSONResponse(status_code=400, content={"error": "empty request body"})

        selected_name = (
            filename
            or request.headers.get("x-file-name")
            or request.headers.get("x-filename")
            or "erp_upload.json"
        )

        return stage_erp_file(filename=selected_name, content=body)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error staging ERP file: %s", exc)
        return internal_server_error_response()


@router.post("/erp/import-file")
async def import_erp_file_from_backend(payload: dict = Body(...)):
    """Importa um arquivo JSON ja depositado no backend."""
    try:
        file_path = str(payload.get("file_path") or payload.get("path") or "").strip()
        if not file_path:
            return JSONResponse(status_code=400, content={"error": "missing file_path"})

        from ...erp_catalog import import_erp_file

        return import_erp_file(file_path)
    except ERPWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error importing ERP file from backend: %s", exc)
        return internal_server_error_response()


@router.get("/erp/files")
async def list_backend_erp_files():
    """Lista os arquivos JSON do ERP encontrados na infraestrutura local do backend."""
    try:
        from ...erp_catalog import list_erp_files

        return {"files": list_erp_files()}
    except Exception as exc:
        logger.exception("Error listing ERP files: %s", exc)
        return internal_server_error_response()


@router.get("/erp/files/preview")
async def preview_backend_erp_file(file_path: str | None = None):
    """Gera um resumo de um arquivo JSON antes da implantacao."""
    try:
        selected_path = str(file_path or "").strip()
        if not selected_path:
            return JSONResponse(status_code=400, content={"error": "missing file_path"})

        from ...erp_catalog import preview_erp_file

        return preview_erp_file(selected_path)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error previewing ERP file: %s", exc)
        return internal_server_error_response()


@router.get("/erp/products")
async def list_backend_erp_products():
    """Lista os produtos atualmente persistidos no JSON ERP ativo."""
    try:
        from ...erp_catalog import list_erp_products

        return list_erp_products()
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error listing ERP products: %s", exc)
        return internal_server_error_response()


@router.put("/erp/products/{codigo}")
async def save_backend_erp_product(codigo: str, payload: dict = Body(...)):
    """Atualiza ou inclui um produto individual no JSON ERP ativo."""
    try:
        from ...erp_catalog import upsert_erp_product

        return upsert_erp_product(payload, code=codigo)
    except ERPWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error saving ERP product %s: %s", codigo, exc)
        return internal_server_error_response()


@router.get("/erp/status")
async def erp_status():
    """Retorna status da carga JSON do ERP utilizada para enriquecer o catalogo."""
    try:
        from ...erp_catalog import get_erp_status

        return get_erp_status()
    except Exception as exc:
        logger.exception("Error reading ERP status: %s", exc)
        return internal_server_error_response()
