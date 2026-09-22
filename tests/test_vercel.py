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
