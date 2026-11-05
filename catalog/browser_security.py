"""Browser mutation policy. Service clients authenticate without browser Origin headers."""
from __future__ import annotations

import os
from urllib.parse import urlsplit
from fastapi import Request


def mutation_is_trusted(request: Request) -> bool:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    if not request.url.path.startswith(("/auth/", "/catalog/")):
        return True
    origin = request.headers.get("origin")
    fetch_site = request.headers.get("sec-fetch-site")
    if origin is None:
        # Non-browser integrations do not send Fetch Metadata. Browser mutations
        # without Origin must still carry our non-simple header and a same-origin context.
        return not fetch_site or (fetch_site == "same-origin" and request.headers.get("x-catalog-request") == "1")
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        return False
    trusted = {str(request.base_url).rstrip("/")}
    trusted.update(value.strip().rstrip("/") for value in os.getenv("CATALOG_TRUSTED_ORIGINS", "").split(",") if value.strip())
    if os.getenv("VERCEL", "").lower() not in {"1", "true"}:
        from .core import load_settings
        trusted.update(value.rstrip("/") for value in load_settings().cors_allow_origins if value != "*")
    return origin in trusted and request.headers.get("x-catalog-request") == "1"
