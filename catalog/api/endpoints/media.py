"""Endpoints de fotos, imagens e recursos de midia do catalogo."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from ..errors import internal_server_error_response
from ..security import require_representative_access
from ..schemas import ProductImagesResponseSchema, ProductPhotosSchema
from ...services import (
    get_google_drive_images_payload,
    get_google_drive_photos_payload,
    get_product_images_payload,
    get_product_photos_payload,
    get_s3_images_payload,
    get_s3_photos_payload,
)


router = APIRouter(dependencies=[Depends(require_representative_access)])
logger = logging.getLogger(__name__)


@router.get("/photos", response_model=ProductPhotosSchema)
async def photos(response: Response, shareUrl: str | None = None, code: str | None = None):
    """Retorna URLs de fotos categorizadas do OneDrive local ou Microsoft Graph."""
    try:
        response.headers["Cache-Control"] = "private, max-age=60"
        return get_product_photos_payload(code=code, share_url=shareUrl)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error fetching photos: %s", exc)
        return internal_server_error_response()


@router.get("/produtos/{codigo}/imagens", response_model=ProductImagesResponseSchema)
async def product_images(codigo: str, response: Response, shareUrl: str | None = None):
    """Retorna todas as variacoes de imagem para um codigo de produto."""
    try:
        response.headers["Cache-Control"] = "private, max-age=60"
        return get_product_images_payload(codigo, share_url=shareUrl)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error searching product images: %s", exc)
        return internal_server_error_response()


@router.get("/google-drive/photos", response_model=ProductPhotosSchema)
async def google_drive_photos(response: Response, code: str | None = None):
    """Retorna fotos categorizadas encontradas no Google Drive para um codigo."""
    try:
        response.headers["Cache-Control"] = "private, max-age=60"
        return get_google_drive_photos_payload(code or "")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error fetching Google Drive photos: %s", exc)
        return internal_server_error_response()


@router.get("/google-drive/produtos/{codigo}/imagens", response_model=ProductImagesResponseSchema)
async def google_drive_product_images(codigo: str, response: Response):
    """Retorna a galeria de imagens do Google Drive para um codigo de produto."""
    try:
        response.headers["Cache-Control"] = "private, max-age=60"
        return get_google_drive_images_payload(codigo)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error searching Google Drive product images: %s", exc)
        return internal_server_error_response()


@router.get("/s3/photos", response_model=ProductPhotosSchema)
async def s3_photos(response: Response, code: str | None = None):
    """Retorna fotos categorizadas encontradas no S3 para um codigo."""
    try:
        response.headers["Cache-Control"] = "private, max-age=60"
        return get_s3_photos_payload(code or "")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error fetching S3 photos: %s", exc)
        return internal_server_error_response()


@router.get("/s3/produtos/{codigo}/imagens", response_model=ProductImagesResponseSchema)
async def s3_product_images(codigo: str, response: Response):
    """Retorna a galeria de imagens do S3 para um codigo de produto."""
    try:
        response.headers["Cache-Control"] = "private, max-age=60"
        return get_s3_images_payload(codigo)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error searching S3 product images: %s", exc)
        return internal_server_error_response()
