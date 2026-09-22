"""Vercel ASGI entry point for the Catalogo FastAPI application."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode

from catalog.bootstrap import create_app


backend_app = create_app()
_ROUTED_PATH_PARAMETER = "__catalog_path"


async def app(scope, receive, send):
    """Restore the public API path after Vercel routes it to this function."""
    if scope.get("type") not in {"http", "websocket"}:
        await backend_app(scope, receive, send)
        return

    routed_scope = dict(scope)
    query_pairs = parse_qsl(
        scope.get("query_string", b"").decode("utf-8"),
        keep_blank_values=True,
    )
    routed_path = next(
        (value for key, value in query_pairs if key == _ROUTED_PATH_PARAMETER),
        "",
    )

    if routed_path:
        routed_scope["path"] = routed_path
        routed_scope["raw_path"] = routed_path.encode("utf-8")
        remaining_query = [
            (key, value)
            for key, value in query_pairs
            if key != _ROUTED_PATH_PARAMETER
        ]
        routed_scope["query_string"] = urlencode(remaining_query, doseq=True).encode("utf-8")
    else:
        path = str(scope.get("path") or "/")
        if path == "/api" or path == "/api/index.py":
            routed_scope["path"] = "/"
            routed_scope["raw_path"] = b"/"
        elif path.startswith("/api/"):
            stripped_path = path[4:] or "/"
            routed_scope["path"] = stripped_path
            routed_scope["raw_path"] = stripped_path.encode("utf-8")

    await backend_app(routed_scope, receive, send)
