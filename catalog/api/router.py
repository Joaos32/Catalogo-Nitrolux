"""Registro de routers da API."""

from fastapi import FastAPI

from catalog.auth import auth_router
from catalog.routes import router as catalog_router
from .endpoints.health import router as health_router


def register_api_routes(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(catalog_router, prefix="/catalog")
