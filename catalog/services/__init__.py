"""Camada de servicos da aplicacao."""

from .catalog_service import fetch_sheet_or_local_products, list_catalog_products
from .media_service import (
    get_google_drive_images_payload,
    get_google_drive_photos_batch_payload,
    get_google_drive_photos_payload,
    get_product_images_payload,
    get_product_photos_payload,
    get_s3_images_payload,
    get_s3_photos_payload,
)

__all__ = [
    "fetch_sheet_or_local_products",
    "get_google_drive_images_payload",
    "get_google_drive_photos_batch_payload",
    "get_google_drive_photos_payload",
    "get_product_images_payload",
    "get_product_photos_payload",
    "get_s3_images_payload",
    "get_s3_photos_payload",
    "list_catalog_products",
]
