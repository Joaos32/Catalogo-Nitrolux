"""Dependencias e utilitarios de seguranca da API."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request

from catalog.auth import (
    _extract_bearer_token,
    get_representative_claims,
    is_admin_login_configured,
    is_admin_session_authenticated,
    is_representative_login_configured,
)
from catalog.core import load_settings


def require_erp_admin(
    request: Request,
    x_catalog_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Protege rotas de ERP com token administrativo opcional."""
    settings = load_settings()
    configured_token = settings.erp_admin_token
    if is_admin_session_authenticated(request):
        return

    provided_token = x_catalog_admin_token or _extract_bearer_token(authorization)

    if configured_token and provided_token:
        if not secrets.compare_digest(provided_token, configured_token):
            raise HTTPException(status_code=403, detail="Invalid ERP admin token")
        return

    if not configured_token and not is_admin_login_configured() and settings.allow_open_admin:
        return

    raise HTTPException(status_code=401, detail="Admin login required")


def require_representative_access(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Protege as rotas do catalogo para representantes autenticados via JWT."""
    if not is_representative_login_configured():
        return

    try:
        claims = get_representative_claims(request, authorization, raise_on_invalid=True)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid representative token") from exc

    if claims:
        return

    raise HTTPException(status_code=401, detail="Representative login required")
