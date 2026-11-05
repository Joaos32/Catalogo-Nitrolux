"""Endpoints de importacao e status do ERP."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..errors import internal_server_error_response
from ..security import require_erp_admin
from ...erp_storage import ERPWriteConflictError


router = APIRouter(dependencies=[Depends(require_erp_admin)])
logger = logging.getLogger(__name__)


async def _read_upload(request: Request, *, excel: bool = False) -> bytes:
    from ...erp_catalog import get_max_upload_size_bytes
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    allowed_types = {"application/octet-stream", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"} if excel else {"application/json", "application/octet-stream"}
    if content_type and content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Envie uma planilha Excel .xlsx." if excel else "ERP uploads require application/json")
    limit = get_max_upload_size_bytes()
    if excel:
        from ...technical_sheet import MAX_UPLOAD_BYTES
        limit = min(limit, MAX_UPLOAD_BYTES)
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            size = int(declared)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length")
        if size < 0:
            raise HTTPException(status_code=400, detail="Invalid Content-Length")
        if size > limit:
            raise HTTPException(status_code=413, detail="A planilha excede o limite de envio." if excel else "ERP upload too large")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail="A planilha excede o limite de envio." if excel else "ERP upload too large")
        content.extend(chunk)
    return bytes(content)


@router.post("/erp/import")
def import_erp_products(payload: dict | list = Body(...)):
    """Importa um payload JSON do ERP e atualiza o espelho de produtos por codigo."""
    try:
        from ...erp_catalog import import_erp_payload

        return import_erp_payload(payload)
    except ERPWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error importing ERP payload: %s", exc)
        return internal_server_error_response()


@router.post("/erp/upload")
async def upload_erp_file(request: Request, filename: str | None = None):
    """Recebe um arquivo JSON bruto no corpo da requisicao e importa para o catalogo."""
    try:
        from ...erp_catalog import receive_erp_file

        body = await _read_upload(request)
        if not body:
            return JSONResponse(status_code=400, content={"error": "empty request body"})

        selected_name = (
            filename
            or request.headers.get("x-file-name")
            or request.headers.get("x-filename")
            or "erp_upload.json"
        )

        return await run_in_threadpool(receive_erp_file, filename=selected_name, content=body)
    except ERPWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error uploading ERP file: %s", exc)
        return internal_server_error_response()


@router.post("/erp/stage-file")
async def stage_erp_file_upload(request: Request, filename: str | None = None):
    """Recebe um arquivo JSON bruto, valida e deixa pronto para implantacao."""
    try:
        from ...erp_catalog import stage_erp_file

        body = await _read_upload(request)
        if not body:
            return JSONResponse(status_code=400, content={"error": "empty request body"})

        selected_name = (
            filename
            or request.headers.get("x-file-name")
            or request.headers.get("x-filename")
            or "erp_upload.json"
        )

        return await run_in_threadpool(stage_erp_file, filename=selected_name, content=body)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error staging ERP file: %s", exc)
        return internal_server_error_response()


@router.post("/erp/import-file")
def import_erp_file_from_backend(payload: dict = Body(...)):
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
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error importing ERP file from backend: %s", exc)
        return internal_server_error_response()


@router.get("/erp/files")
def list_backend_erp_files():
    """Lista os arquivos JSON do ERP encontrados na infraestrutura local do backend."""
    try:
        from ...erp_catalog import list_erp_files

        return {"files": list_erp_files()}
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error listing ERP files: %s", exc)
        return internal_server_error_response()


@router.get("/erp/files/preview")
def preview_backend_erp_file(file_path: str | None = None):
    """Gera um resumo de um arquivo JSON antes da implantacao."""
    try:
        selected_path = str(file_path or "").strip()
        if not selected_path:
            return JSONResponse(status_code=400, content={"error": "missing file_path"})

        from ...erp_catalog import preview_erp_file

        return preview_erp_file(selected_path)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error previewing ERP file: %s", exc)
        return internal_server_error_response()


@router.get("/erp/products")
def list_backend_erp_products():
    """Lista os produtos atualmente persistidos no JSON ERP ativo."""
    try:
        from ...erp_catalog import list_erp_products

        return list_erp_products()
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error listing ERP products: %s", exc)
        return internal_server_error_response()


@router.put("/erp/products/{codigo}")
def save_backend_erp_product(codigo: str, payload: dict = Body(...)):
    """Atualiza ou inclui um produto individual no JSON ERP ativo."""
    try:
        from ...erp_catalog import upsert_erp_product

        return upsert_erp_product(payload, code=codigo)
    except ERPWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error saving ERP product %s: %s", codigo, exc)
        return internal_server_error_response()


@router.get("/erp/status")
def erp_status():
    """Retorna status da carga JSON do ERP utilizada para enriquecer o catalogo."""
    try:
        from ...erp_catalog import get_erp_status

        return get_erp_status()
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception as exc:
        logger.exception("Error reading ERP status: %s", exc)
        return internal_server_error_response()


@router.post("/erp/technical-sheet/preview")
@router.post("/erp/technical-sheet/import")
async def technical_sheet_upload(request: Request, filename: str = "dados-tecnicos.xlsx", sheet: str | None = None, preview_key: str | None = None):
    """Read Excel and apply only reviewed specifications to existing product codes."""
    from ...technical_sheet import StaleTechnicalPreview, read_technical_sheet

    try:
        applying = request.url.path.endswith("/import")
        if applying and not preview_key:
            raise ValueError("Leia a planilha e confira a previa antes de aplicar os dados tecnicos.")
        content = await _read_upload(request, excel=True)
        return await run_in_threadpool(read_technical_sheet, content, filename, sheet, preview_key=preview_key if applying else None)
    except (StaleTechnicalPreview, ERPWriteConflictError) as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception:
        logger.exception("Error reading technical spreadsheet")
        return internal_server_error_response()
