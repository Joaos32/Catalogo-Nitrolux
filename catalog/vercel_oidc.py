"""Captura o token OIDC temporario enviado pelo runtime do Vercel."""

from __future__ import annotations

import os
from contextvars import ContextVar, Token


_oidc_token: ContextVar[str] = ContextVar("vercel_oidc_token", default="")


def set_request_token(value: str | None) -> Token:
    return _oidc_token.set(str(value or "").strip())


def reset_request_token(token: Token) -> None:
    _oidc_token.reset(token)


def get_request_token() -> str:
    return _oidc_token.get() or str(os.getenv("VERCEL_OIDC_TOKEN") or "").strip()
