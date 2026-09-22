"""Servicos de leitura de fotos e galerias do catalogo."""

from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def get_product_photos_payload(code: str | None = None, share_url: str | None = None) -> Dict:
    from .. import cdn_media, google_drive, onedrive, s3_media, vercel_blob_media

    if code:
        try:
            local_photos = onedrive.categorize_local_photos(code=code)
            if any(local_photos.values()):
                return local_photos
            if (
                onedrive.resolve_local_products_root()
                and not cdn_media.is_configured()
                and not vercel_blob_media.is_configured()
                and not s3_media.is_configured()
                and not google_drive.is_configured()
            ):
                return local_photos
        except Exception as local_exc:
            logger.warning(
                "Local photo lookup failed, trying remote fallbacks: %s",
                local_exc,
                exc_info=True,
            )

        if cdn_media.is_configured():
            cdn_photos = cdn_media.categorize_photos_for_code(code)
            if any(cdn_photos.values()):
                return cdn_photos

        if vercel_blob_media.is_configured():
            try:
                blob_photos = vercel_blob_media.categorize_photos_for_code(code)
                if any(blob_photos.values()):
                    return blob_photos
            except Exception as blob_exc:
                logger.warning(
                    "Vercel Blob photo lookup failed, trying next fallback: %s",
                    blob_exc,
                    exc_info=True,
                )

        if s3_media.is_configured():
            try:
                s3_photos = s3_media.categorize_photos_for_code(code)
                if any(s3_photos.values()):
                    return s3_photos
            except Exception as s3_exc:
                logger.warning(
                    "S3 photo lookup failed, trying next fallback: %s",
                    s3_exc,
                    exc_info=True,
                )

        if google_drive.is_configured():
            try:
                drive_photos = google_drive.categorize_photos_for_code(code)
                if any(drive_photos.values()):
                    return drive_photos
            except Exception as drive_exc:
                logger.warning(
                    "Google Drive photo lookup failed, trying Graph fallback: %s",
                    drive_exc,
                    exc_info=True,
                )

    if not share_url:
        raise ValueError("missing shareUrl query parameter")

    try:
        items = onedrive.list_shared_items(share_url)
        return onedrive.categorize_photos(items, code=code)
    except (EnvironmentError, ValueError) as exc:
        logger.warning("Photos disabled due to environment issue: %s", exc, exc_info=True)
        demo = {
            "white_background": "https://placehold.co/150x150?text=Branco",
            "ambient": "https://placehold.co/150x150?text=Ambient",
            "measures": "https://placehold.co/150x150?text=Medidas",
        }
        if code:
            demo = {key: value + f"+{code}" for key, value in demo.items()}
        return demo


def get_product_images_payload(code: str, share_url: str | None = None) -> Dict:
    from .. import cdn_media, google_drive, onedrive, s3_media, vercel_blob_media

    try:
        local_images = onedrive.find_local_images_for_code(code)
        if local_images or (
            onedrive.resolve_local_products_root()
            and not cdn_media.is_configured()
            and not vercel_blob_media.is_configured()
            and not s3_media.is_configured()
            and not google_drive.is_configured()
        ):
            return {"codigo": code, "imagens": local_images}
    except Exception as local_exc:
        logger.warning(
            "Local image lookup failed, trying remote fallbacks: %s",
            local_exc,
            exc_info=True,
        )

    if cdn_media.is_configured():
        cdn_images = cdn_media.find_images_for_code(code)
        if cdn_images:
            return {"codigo": code, "imagens": cdn_images}

    if vercel_blob_media.is_configured():
        try:
            blob_images = vercel_blob_media.find_images_for_code(code)
            if blob_images:
                return {"codigo": code, "imagens": blob_images}
        except Exception as blob_exc:
            logger.warning(
                "Vercel Blob image lookup failed, trying next fallback: %s",
                blob_exc,
                exc_info=True,
            )

    if s3_media.is_configured():
        try:
            s3_images = s3_media.find_images_for_code(code)
            if s3_images:
                return {"codigo": code, "imagens": s3_images}
        except Exception as s3_exc:
            logger.warning(
                "S3 image lookup failed, trying next fallback: %s",
                s3_exc,
                exc_info=True,
            )

    if google_drive.is_configured():
        try:
            drive_images = google_drive.find_images_for_code(code)
            if drive_images:
                return {"codigo": code, "imagens": drive_images}
        except Exception as drive_exc:
            logger.warning(
                "Google Drive image lookup failed, trying Graph fallback: %s",
                drive_exc,
                exc_info=True,
            )

    if not share_url:
        raise ValueError("missing shareUrl query parameter")

    images = onedrive.find_images_for_code(share_url, code)
    return {"codigo": code, "imagens": images}


def get_google_drive_photos_payload(code: str) -> Dict:
    from .. import google_drive

    if not code:
        raise ValueError("missing code query parameter")
    if not google_drive.is_configured():
        raise ValueError("missing CATALOG_GOOGLE_DRIVE_FOLDER_ID or CATALOG_GOOGLE_DRIVE_API_KEY configuration")
    return google_drive.categorize_photos_for_code(code)


def get_google_drive_photos_batch_payload(codes: list[str]) -> Dict[str, Dict[str, str | None]]:
    from .. import google_drive

    if not codes:
        return {}
    if not google_drive.is_configured():
        raise ValueError("missing CATALOG_GOOGLE_DRIVE_FOLDER_ID or CATALOG_GOOGLE_DRIVE_API_KEY configuration")
    return google_drive.categorize_photos_for_codes(codes)


def get_google_drive_images_payload(code: str) -> Dict:
    from .. import google_drive

    if not code:
        raise ValueError("missing product code")
    if not google_drive.is_configured():
        raise ValueError("missing CATALOG_GOOGLE_DRIVE_FOLDER_ID or CATALOG_GOOGLE_DRIVE_API_KEY configuration")
    return {"codigo": code, "imagens": google_drive.find_images_for_code(code)}


def get_s3_photos_payload(code: str) -> Dict:
    from .. import s3_media

    if not code:
        raise ValueError("missing code query parameter")
    if not s3_media.is_configured():
        raise ValueError("missing CATALOG_S3_MEDIA_BUCKET configuration")
    return s3_media.categorize_photos_for_code(code)


def get_s3_images_payload(code: str) -> Dict:
    from .. import s3_media

    if not code:
        raise ValueError("missing product code")
    if not s3_media.is_configured():
        raise ValueError("missing CATALOG_S3_MEDIA_BUCKET configuration")
    return {"codigo": code, "imagens": s3_media.find_images_for_code(code)}
