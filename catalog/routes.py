"""Fachada de compatibilidade para as rotas de catalogo."""

from io import BytesIO
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse, Response

from catalog.api.errors import internal_server_error_response
from catalog.api.endpoints.catalog import router as catalog_data_router
from catalog.api.endpoints.integration import router as integration_router
from catalog.api.endpoints.erp import router as erp_router
from catalog.api.endpoints.export import router as export_router
from catalog.api.endpoints.media import router as media_router
from catalog.api.endpoints.representatives import router as representatives_router
from catalog.api.security import require_representative_access
from catalog.local_catalog import IMG_EXTENSIONS


router = APIRouter()
router.include_router(integration_router)
router.include_router(catalog_data_router)
router.include_router(media_router)
router.include_router(erp_router)
router.include_router(export_router)
router.include_router(representatives_router)
logger = logging.getLogger(__name__)
CONVERTIBLE_LOCAL_ASSET_EXTENSIONS = {".psd", ".heic", ".heif"}


def _tiff_to_jpeg_bytes(asset_path: str) -> bytes | None:
    """Converte formatos raster locais para bytes JPEG para compatibilidade no navegador."""
    ext = Path(asset_path).suffix.lower()
    if ext not in {".tif", ".tiff", ".psd", ".heic", ".heif"}:
        return None

    try:
        from PIL import Image
    except Exception:
        # Pillow e opcional; se indisponivel, mantem resposta original.
        return None

    try:
        with Image.open(asset_path) as image:
            # Achata transparencia sobre fundo branco para compatibilidade com JPEG.
            if image.mode in ("RGBA", "LA"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                alpha = image.split()[-1]
                background.paste(image.convert("RGB"), mask=alpha)
                converted = background
            else:
                converted = image.convert("RGB") if image.mode != "RGB" else image

            output = BytesIO()
            converted.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue()
    except Exception:
        return None
@router.get("/local/asset", dependencies=[Depends(require_representative_access)])
async def local_asset(path: str | None = None):
    """Serve um arquivo de imagem local da pasta de produtos configurada no OneDrive."""
    if not path:
        return JSONResponse(status_code=400, content={"error": "missing path query parameter"})
    try:
        from .onedrive import resolve_local_asset_path

        asset_path = resolve_local_asset_path(path)
        if not asset_path:
            return JSONResponse(status_code=404, content={"error": "asset not found"})

        suffix = Path(asset_path).suffix.lower()
        allowed_extensions = set(IMG_EXTENSIONS) | CONVERTIBLE_LOCAL_ASSET_EXTENSIONS
        if suffix not in allowed_extensions:
            return JSONResponse(status_code=403, content={"error": "unsupported asset type"})

        converted = _tiff_to_jpeg_bytes(asset_path)
        if converted is not None:
            return Response(content=converted, media_type="image/jpeg")

        return FileResponse(asset_path)
    except Exception as e:
        logger.exception("Error serving local asset: %s", e)
        return internal_server_error_response()


@router.get("/blob/asset", dependencies=[Depends(require_representative_access)])
async def blob_asset(blobPath: str | None = None):
    """Serve uma imagem privada armazenada no Vercel Blob."""
    if not blobPath:
        return JSONResponse(status_code=400, content={"error": "missing blobPath query parameter"})
    try:
        from .vercel_blob_media import get_asset

        asset = get_asset(blobPath)
        if asset is None:
            return JSONResponse(status_code=404, content={"error": "asset not found"})
        return Response(
            content=asset.content,
            media_type=asset.content_type or "application/octet-stream",
            headers={"Cache-Control": "private, max-age=3600"},
        )
    except Exception as exc:
        logger.exception("Error serving Vercel Blob asset: %s", exc)
        return internal_server_error_response()


