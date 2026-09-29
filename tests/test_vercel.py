import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import index as vercel_entrypoint


def test_vercel_entrypoint_restores_routed_path_and_query(monkeypatch):
    captured_scope = {}

    async def capture_app(scope, receive, send):
        captured_scope.update(scope)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    monkeypatch.setattr(vercel_entrypoint, "backend_app", capture_app)
    client = TestClient(vercel_entrypoint.app)

    response = client.get(
        "/api/index.py",
        params={
            "__catalog_path": "/catalog/photos",
            "code": "1578",
        },
    )

    assert response.status_code == 204
    assert captured_scope["path"] == "/catalog/photos"
    assert captured_scope["raw_path"] == b"/catalog/photos"
    assert captured_scope["query_string"] == b"code=1578"


def test_vercel_entrypoint_serves_existing_auth_route():
    client = TestClient(vercel_entrypoint.app)

    response = client.get(
        "/api/index.py",
        params={"__catalog_path": "/auth/session"},
    )

    assert response.status_code == 200
    assert "authenticated" in response.json()


def test_vercel_entrypoint_serves_health_probe_after_rewrite():
    client = TestClient(vercel_entrypoint.app)

    response = client.get(
        "/api/index.py",
        params={"__catalog_path": "/health/live"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_vercel_routes_public_health_paths_to_the_api_function():
    config = json.loads((Path(__file__).resolve().parents[1] / "vercel.json").read_text("utf-8"))
    rewrites = config["rewrites"]

    assert any(
        item["source"] == "/health"
        and item["destination"] == "/api/index.py?__catalog_path=/health"
        for item in rewrites
    )
    assert any(
        item["source"] == "/health/:path*"
        and item["destination"] == "/api/index.py?__catalog_path=/health/:path*"
        for item in rewrites
    )
