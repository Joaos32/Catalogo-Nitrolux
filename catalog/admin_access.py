"""Restricao de acesso administrativo por host configurado."""

from __future__ import annotations

from fastapi import HTTPException, Request

from catalog.core import load_settings


def _normalize_host(value: str | None) -> str:
    return str(value or "").strip().lower().rstrip(".")


def require_admin_host(request: Request) -> None:
    """Oculta login e APIs administrativas fora dos hosts internos."""
    allowed_hosts = {
        _normalize_host(host)
        for host in load_settings().admin_hosts
        if _normalize_host(host)
    }
    if not allowed_hosts:
        return

    request_host = _normalize_host(request.url.hostname)
    if request_host not in allowed_hosts:
        raise HTTPException(status_code=404, detail="Not found")
