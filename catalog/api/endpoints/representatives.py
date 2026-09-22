"""Endpoints administrativos para cadastro de representantes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from ..errors import internal_server_error_response
from ..security import require_erp_admin


router = APIRouter(dependencies=[Depends(require_erp_admin)])
logger = logging.getLogger(__name__)


@router.get("/representatives")
async def list_representatives():
    try:
        from ...representative_registry import build_representative_admin_summary

        return build_representative_admin_summary()
    except Exception as exc:
        logger.exception("Error listing representative users: %s", exc)
        return internal_server_error_response()


@router.put("/representatives/{email}")
async def save_representative(email: str, payload: dict = Body(...)):
    try:
        provided_email = str(payload.get("email") or email or "").strip()
        if not provided_email:
            return JSONResponse(status_code=400, content={"error": "missing representative email"})

        if provided_email.strip().lower() != str(email or "").strip().lower():
            return JSONResponse(status_code=400, content={"error": "email mismatch"})

        from ...representative_registry import (
            build_representative_admin_summary,
            upsert_managed_representative,
        )

        created, user = upsert_managed_representative(
            provided_email,
            str(payload.get("name") or "").strip(),
            str(payload.get("password") or "").strip(),
            bool(payload.get("is_admin")) if "is_admin" in payload else None,
        )
        return {
            "created": created,
            "user": user,
            **build_representative_admin_summary(),
        }
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error saving representative %s: %s", email, exc)
        return internal_server_error_response()


@router.post("/representatives/{email}/password-reset")
async def create_password_reset(email: str):
    try:
        from ...representative_registry import (
            build_representative_admin_summary,
            create_representative_password_reset,
        )

        reset = create_representative_password_reset(email)
        return {
            **reset,
            **build_representative_admin_summary(),
        }
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "representative not found"})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error creating representative password reset for %s: %s", email, exc)
        return internal_server_error_response()


@router.delete("/representatives/{email}")
async def remove_representative(email: str):
    try:
        from ...representative_registry import (
            build_representative_admin_summary,
            delete_managed_representative,
        )

        deleted = delete_managed_representative(email)
        return {
            **deleted,
            **build_representative_admin_summary(),
        }
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "representative not found"})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error deleting representative %s: %s", email, exc)
        return internal_server_error_response()
