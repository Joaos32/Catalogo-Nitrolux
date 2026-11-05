"""Inicializacao e composicao da aplicacao."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from catalog.api import register_api_routes, register_frontend_routes
from catalog.core import configure_logging, load_settings


logger = logging.getLogger(__name__)
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob: https:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self' https:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self' https://login.microsoftonline.com",
    # A visualizacao de produtos usa a camera, mas continua bloqueada para
    # origens/frames de terceiros. Microfone e geolocalizacao nao sao usados.
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Permitted-Cross-Domain-Policies": "none",
}


def _configure_cors(app: FastAPI, allow_origins: list[str], allow_credentials: bool) -> None:
    try:
        from fastapi.middleware.cors import CORSMiddleware
    except Exception:
        logger.warning("fastapi CORS middleware not installed; cross-origin requests may fail.")
        return

    # Navegadores rejeitam origem coringa quando credenciais estao habilitadas.
    if allow_credentials and "*" in allow_origins:
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _configure_sessions(
    app: FastAPI,
    secret_key: str,
    max_age_seconds: int,
    cookie_secure: bool,
) -> None:
    try:
        from starlette.middleware.sessions import SessionMiddleware
    except Exception:
        logger.warning("starlette SessionMiddleware not installed; browser admin login will be unavailable.")
        return

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie="catalog_admin_session",
        same_site="lax",
        https_only=cookie_secure,
        max_age=max_age_seconds,
    )


def _configure_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        from .browser_security import mutation_is_trusted
        if mutation_is_trusted(request):
            response = await call_next(request)
        else:
            response = JSONResponse(status_code=403, content={"detail": "Untrusted browser request"})
        if request.url.path.startswith("/auth/"):
            response.headers["Cache-Control"] = "no-store"
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains",
            )
        return response


def _configure_vercel_oidc(app: FastAPI) -> None:
    @app.middleware("http")
    async def capture_vercel_oidc_token(request: Request, call_next):
        from .vercel_oidc import reset_request_token, set_request_token

        context_token = set_request_token(request.headers.get("x-vercel-oidc-token"))
        try:
            return await call_next(request)
        finally:
            reset_request_token(context_token)


def _configure_representative_idle_timeout(app: FastAPI) -> None:
    @app.middleware("http")
    async def refresh_active_representative_session(request: Request, call_next):
        from starlette.concurrency import run_in_threadpool
        from .auth import (
            _build_representative_token,
            _representative_jwt_expires_seconds,
            _set_representative_cookie,
            get_representative_claims,
        )

        is_health_probe = request.url.path == "/health" or request.url.path.startswith("/health/")
        claims = None if is_health_probe else await run_in_threadpool(get_representative_claims,
            request,
            request.headers.get("authorization"),
        )
        response = await call_next(request)
        logout_paths = {"/auth/logout", "/auth/representative/logout"}
        expires_at = int(claims.get("exp") or 0) if claims else 0
        refresh_threshold = max(_representative_jwt_expires_seconds() // 2, 60)
        should_refresh = expires_at - int(time.time()) <= refresh_threshold
        if (
            claims
            and should_refresh
            and request.url.path not in logout_paths
            and response.status_code < 400
        ):
            refreshed_token, _ = _build_representative_token(
                {
                    "email": str(claims.get("email") or claims.get("sub") or ""),
                    "name": str(claims.get("name") or claims.get("email") or "Representante"),
                    "_credential_version": str(claims.get("credential_version") or ""),
                    "_session_id": str(claims["session_id"]),
                    "_session_expires_at": int(claims["session_expires_at"]),
                }
            )
            _set_representative_cookie(response, request, refreshed_token)
        return response


def _register_disabled_docs_routes(app: FastAPI) -> None:
    @app.get("/docs")
    @app.get("/redoc")
    @app.get("/openapi.json")
    async def disabled_api_docs():
        return JSONResponse(status_code=404, content={"error": "API docs disabled"})


def _load_runtime_environment(base_dir: Path | None = None) -> None:
    """Load local configuration while preserving explicit process environment values."""
    if os.getenv("CATALOG_SKIP_DOTENV", "").strip().lower() not in {"1", "true", "yes", "on"}:
        root = base_dir or Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env.local")
        load_dotenv(root / ".env")


def create_app() -> FastAPI:
    _load_runtime_environment()
    configure_logging()
    settings = load_settings()

    logger.info("Starting Catalogo API with Python executable %s", sys.executable)
    if settings.session_secret_generated:
        logger.warning(
            "CATALOG_SESSION_SECRET is not set; using a temporary per-process secret. "
            "Sessions and representative JWTs that reuse it will be invalid after restart."
        )
    if settings.allow_open_admin:
        logger.warning(
            "CATALOG_ALLOW_OPEN_ADMIN is enabled; administrative routes are open without login or token."
        )
    if settings.representative_login_password and not settings.representative_jwt_secret:
        logger.warning(
            "CATALOG_REPRESENTATIVE_JWT_SECRET is not set; representative JWTs will use CATALOG_SESSION_SECRET."
        )

    app = FastAPI(
        title="Catalogo API",
        version="1.0.0",
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    _configure_cors(
        app,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
    )
    _configure_sessions(
        app,
        secret_key=settings.session_secret,
        max_age_seconds=settings.session_max_age_seconds,
        cookie_secure=settings.session_cookie_secure,
    )
    _configure_security_headers(app)
    _configure_vercel_oidc(app)
    _configure_representative_idle_timeout(app)
    if not settings.api_docs_enabled:
        _register_disabled_docs_routes(app)
    register_api_routes(app)
    register_frontend_routes(
        app,
        frontend_dir=settings.frontend_dir,
        index_file=settings.frontend_index,
    )
    return app
