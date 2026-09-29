"""Health probes that avoid external services and sensitive configuration."""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...core import load_settings

router = APIRouter(prefix="/health", tags=["health"])


def _is_serverless_runtime() -> bool:
    return bool(
        str(os.getenv("VERCEL") or "").strip().lower() in {"1", "true", "yes"}
        or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    )


def _runtime_catalog_available() -> bool:
    from ...services.catalog_service import _load_prebuilt_catalog

    try:
        products = _load_prebuilt_catalog()
    except Exception:
        return False
    return bool(products)


def _erp_storage_is_ready() -> bool:
    from ...erp_storage import load_active, storage_uri

    if not storage_uri():
        return False
    try:
        load_active()
    except Exception:
        return False
    return True


@router.get("")
@router.get("/live")
async def liveness():
    """Signal that the API process can receive requests."""
    return {"status": "live"}


@router.get("/ready")
async def readiness():
    """Check the bundled catalog required by serverless deployments."""
    if not _is_serverless_runtime():
        return {"status": "ready", "checks": {"catalog_bundle": "not_required"}}

    settings = load_settings()
    try:
        from ...representative_registry import list_representative_login_users

        has_representative_login = bool(list_representative_login_users())
    except Exception:
        has_representative_login = False

    checks = {
        "catalog_bundle": "ok" if _runtime_catalog_available() else "unavailable",
        "shared_session_key": "ok" if not settings.session_secret_generated else "missing",
        "representative_login": (
            "ok"
            if settings.representative_login_required and has_representative_login
            else "missing"
        ),
        "erp_storage": "ok" if _erp_storage_is_ready() else "missing",
    }
    if "unavailable" in checks.values() or "missing" in checks.values():
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}
