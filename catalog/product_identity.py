"""Stable product identity across catalog sources; no grouping by name or photograph."""
from __future__ import annotations

import math
import re
from typing import Any

_CODE_KEYS = ("codigo", "code", "codprod", "sku", "id")
_PHOTO_KEYS = {"urlfoto", "fotobranco", "fotoambient", "fotomedidas", "image", "imagem", "foto", "url"}


def normalize_product_code(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    text = str(value).strip()
    # Excel/JSON may spell an integer as 5160.0; leading zeros and SKU prefixes matter.
    return re.sub(r"\.0+$", "", text) if re.fullmatch(r"\d+\.0+", text) else text


def product_code(product: dict) -> str:
    fields = {str(key).casefold().replace("_", ""): value for key, value in product.items()}
    return next((code for key in _CODE_KEYS if (code := normalize_product_code(fields.get(key)))), "")


def _missing(value: Any, key: str) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return True
    if isinstance(value, str):
        if not value.strip():
            return True
        if key.casefold().replace("_", "") in _PHOTO_KEYS:
            return "placehold.co" in value.lower() or value.lower().startswith("data:image/svg+xml")
    return False


def deduplicate_products(products: list[dict]) -> list[dict]:
    """Keep the first row per code, filling absent fields without summing sales."""
    result: list[dict] = []
    by_code: dict[str, dict] = {}
    for product in products:
        code = product_code(product)
        if not code or code not in by_code:
            kept = dict(product)
            if code:
                kept["Codigo"] = code
                by_code[code] = kept
            result.append(kept)
            continue
        kept = by_code[code]
        for key, value in product.items():
            if _missing(kept.get(key), key) and not _missing(value, key):
                kept[key] = value
    return result
