"""Inicializacao e composicao da aplicacao."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from catalog.api import register_api_routes, register_frontend_routes
from catalog.core import configure_logging, load_settings


logger = logging.getLogger(__name__)
SECURITY_HEADERS = {
    "Content-Security-Policy": "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
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
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains",
            )
        return response


def _register_disabled_docs_routes(app: FastAPI) -> None:
    @app.get("/docs")
    @app.get("/redoc")
    @app.get("/openapi.json")
    async def disabled_api_docs():
        return JSONResponse(status_code=404, content={"error": "API docs disabled"})


def create_app() -> FastAPI:
    # Carrega o .env antes de importar modulos que dependem do ambiente.
    if os.getenv("CATALOG_SKIP_DOTENV", "").strip().lower() not in {"1", "true", "yes", "on"}:
        load_dotenv()
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
    if not settings.api_docs_enabled:
        _register_disabled_docs_routes(app)
    register_api_routes(app)
    register_frontend_routes(
        app,
        frontend_dir=settings.frontend_dir,
        index_file=settings.frontend_index,
    )
    return app
