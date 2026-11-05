"""Endpoints de fotos, imagens e recursos de midia do catalogo."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from ...google_drive import fetch_google_drive_image
from ..errors import internal_server_error_response
from ..security import require_representative_access
from ..schemas import ProductImagesResponseSchema, ProductPhotosSchema
from ...services import (
    get_google_drive_images_payload,
    get_google_drive_photos_batch_payload,
    get_google_drive_photos_payload,
    get_product_images_payload,
    get_product_photos_payload,
    get_s3_images_payload,
    get_s3_photos_payload,
)


router = APIRouter(dependencies=[Depends(require_representative_access)])
logger = logging.getLogger(__name__)


@router.get("/photos", response_model=ProductPhotosSchema)
def photos(response: Response, shareUrl: str | None = None, code: str | None = None):
    """Retorna URLs de fotos categorizadas do OneDrive local ou Microsoft Graph."""
    try:
        response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=600"
        return get_product_photos_payload(code=code, share_url=shareUrl)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error fetching photos: %s", exc)
        return internal_server_error_response()


@router.get("/photos/batch", response_model=dict[str, ProductPhotosSchema])
def photos_batch(response: Response, codes: str | None = None):
    """Retorna as fotos de varios produtos em uma unica chamada."""
    requested_codes = list(dict.fromkeys(
        item.strip() for item in str(codes or "").split(",") if item.strip()
    ))
    if not requested_codes:
        return JSONResponse(status_code=400, content={"error": "missing codes query parameter"})
    if len(requested_codes) > 30:
        return JSONResponse(status_code=400, content={"error": "too many product codes"})

    drive_failed = False
    try:
        drive_payload = get_google_drive_photos_batch_payload(requested_codes)
    except ValueError:
        # A missing provider configuration is different from an upstream outage.
        drive_payload = None
    except Exception:
        drive_failed = True
        logger.exception("Photo batch provider failed: provider=google-drive count=%s", len(requested_codes))
        drive_payload = None

    payload: dict[str, dict[str, str | None]] = {}
    for product_code in requested_codes:
        photos_payload = (drive_payload or {}).get(product_code) or {}
        if not any(photos_payload.get(field) for field in ("white_background", "ambient", "measures")):
            try:
                fallback = get_product_photos_payload(code=product_code)
                if drive_failed and not any(fallback.values()):
                    raise RuntimeError("No photo provider recovered the failed lookup")
            except Exception:
                logger.exception("Photo batch fallback failed: code=%s", product_code)
                return JSONResponse(
                    status_code=503, content={"error": "Fotos temporariamente indisponíveis. Tente novamente."},
                    headers={"Cache-Control": "no-store", "Retry-After": "10"},
                )
            photos_payload = {
                field: photos_payload.get(field) or fallback.get(field)
                for field in ("white_background", "ambient", "measures")
            }
        payload[product_code] = {
            field: photos_payload.get(field)
            for field in ("white_background", "ambient", "measures")
        }
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=600"
    return payload


@router.get("/produtos/{codigo}/imagens", response_model=ProductImagesResponseSchema)
def product_images(codigo: str, response: Response, shareUrl: str | None = None):
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
def google_drive_photos(response: Response, code: str | None = None):
    """Retorna fotos categorizadas encontradas no Google Drive para um codigo."""
    try:
        response.headers["Cache-Control"] = "private, max-age=60"
        return get_google_drive_photos_payload(code or "")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error fetching Google Drive photos: %s", exc)
        return internal_server_error_response()


@router.get("/media/google-drive/{file_id}")
def google_drive_media(file_id: str, size: str = "detail"):
    """Serve uma imagem do Google Drive no mesmo dominio do catalogo."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,200}", str(file_id or "")):
        return JSONResponse(status_code=400, content={"error": "invalid Google Drive file id"})

    try:
        content, media_type = fetch_google_drive_image(file_id, size=size)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "private, no-store"},
        )
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:
        logger.warning("Error serving Google Drive image %s: %s", file_id, exc)
        return JSONResponse(status_code=404, content={"error": "Google Drive image not found"})


@router.get("/google-drive/produtos/{codigo}/imagens", response_model=ProductImagesResponseSchema)
def google_drive_product_images(codigo: str, response: Response):
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
def s3_photos(response: Response, code: str | None = None):
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
def s3_product_images(codigo: str, response: Response):
    """Retorna a galeria de imagens do S3 para um codigo de produto."""
    try:
        response.headers["Cache-Control"] = "private, max-age=60"
        return get_s3_images_payload(codigo)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error searching S3 product images: %s", exc)
        return internal_server_error_response()
