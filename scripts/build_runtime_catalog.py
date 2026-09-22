"""Precompute the immutable catalog bundled with Vercel deployments."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from catalog.services.catalog_service import (  # noqa: E402
    PREBUILT_CATALOG_PATH,
    _build_catalog_products_from_sources,
    prebuilt_source_hashes,
)


def main() -> None:
    # Match Vercel's filesystem: there is no user OneDrive directory, while
    # catalog/json remains available as a bundled stock source.
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer", "USERPROFILE"):
        os.environ.pop(name, None)
    os.environ["CATALOG_LOCAL_PRODUCTS_HOME_FALLBACK"] = "false"
    products = _build_catalog_products_from_sources()
    payload = {
        "version": 1,
        "source_hashes": prebuilt_source_hashes(),
        "products": products,
    }
    PREBUILT_CATALOG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Prepared {len(products)} products at {PREBUILT_CATALOG_PATH}")


if __name__ == "__main__":
    main()
