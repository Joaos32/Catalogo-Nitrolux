"""Endpoints administrativos para cadastro de representantes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from ..errors import internal_server_error_response
from ..security import require_erp_admin
from ...representative_registry import RegistryWriteConflictError
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class RepresentativeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str | None = Field(default=None, max_length=254)
    name: str = Field(min_length=1, max_length=200)
    password: str | None = Field(default=None, max_length=1024)
    is_admin: StrictBool | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value is not None and (value.count("@") != 1 or any(c.isspace() for c in value) or not all(value.split("@"))):
            raise ValueError("Invalid email")
        return value



router = APIRouter(dependencies=[Depends(require_erp_admin)])
logger = logging.getLogger(__name__)


@router.get("/representatives")
def list_representatives():
    try:
        from ...representative_registry import build_representative_admin_summary

        return build_representative_admin_summary()
    except Exception as exc:
        logger.exception("Error listing representative users: %s", exc)
        return internal_server_error_response()


@router.get("/online-users")
def list_online_users(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        from ...online_users import list_online_representatives

        return list_online_representatives()
    except Exception as exc:
        logger.exception("Error listing online representatives: %s", exc)
        return internal_server_error_response()


@router.put("/representatives/{email}")
def save_representative(email: str, payload: RepresentativeUpdate):
    try:
        provided_email = str(payload.email or email or "").strip()
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
            payload.name,
            payload.password,
            payload.is_admin,
        )
        return {
            "created": created,
            "user": user,
            **build_representative_admin_summary(),
        }
    except RegistryWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error saving representative %s: %s", email, exc)
        return internal_server_error_response()


@router.post("/representatives/{email}/password-reset")
def create_password_reset(email: str):
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
    except RegistryWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error creating representative password reset for %s: %s", email, exc)
        return internal_server_error_response()


@router.delete("/representatives/{email}")
def remove_representative(email: str):
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
    except RegistryWriteConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Error deleting representative %s: %s", email, exc)
        return internal_server_error_response()
