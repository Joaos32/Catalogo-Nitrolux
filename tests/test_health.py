from fastapi.testclient import TestClient

from catalog.bootstrap import create_app


def test_liveness_probe_is_public_and_does_not_read_dependencies():
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_local_readiness_does_not_depend_on_a_serverless_snapshot(monkeypatch):
    from catalog.api.endpoints import health

    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setattr(health, "_runtime_catalog_available", lambda: False)
    client = TestClient(create_app())

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"catalog_bundle": "not_required"},
    }


def test_serverless_readiness_fails_when_catalog_bundle_is_unavailable(monkeypatch):
    from catalog.api.endpoints import health

    monkeypatch.setenv("VERCEL", "true")
    monkeypatch.setenv("CATALOG_REQUIRE_REPRESENTATIVE_LOGIN", "true")
    monkeypatch.setattr(health, "_erp_storage_is_ready", lambda: True)
    monkeypatch.setattr(
        "catalog.representative_registry.list_representative_login_users",
        lambda: [{"email": "rep@example.com"}],
    )
    monkeypatch.setattr(health, "_runtime_catalog_available", lambda: False)
    client = TestClient(create_app())

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "catalog_bundle": "unavailable",
            "shared_session_key": "ok",
            "representative_login": "ok",
            "erp_storage": "ok",
        },
    }


def test_serverless_readiness_reports_a_valid_catalog_bundle(monkeypatch):
    from catalog.api.endpoints import health

    monkeypatch.setenv("VERCEL", "true")
    monkeypatch.setenv("CATALOG_REQUIRE_REPRESENTATIVE_LOGIN", "true")
    monkeypatch.setattr(health, "_erp_storage_is_ready", lambda: True)
    monkeypatch.setattr(
        "catalog.representative_registry.list_representative_login_users",
        lambda: [{"email": "rep@example.com"}],
    )
    monkeypatch.setattr(health, "_runtime_catalog_available", lambda: True)
    client = TestClient(create_app())

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "catalog_bundle": "ok",
            "shared_session_key": "ok",
            "representative_login": "ok",
            "erp_storage": "ok",
        },
    }


def test_serverless_readiness_fails_without_a_shared_session_signing_key(monkeypatch):
    from catalog.api.endpoints import health

    monkeypatch.setenv("VERCEL", "true")
    monkeypatch.setenv("CATALOG_REQUIRE_REPRESENTATIVE_LOGIN", "true")
    monkeypatch.setattr(health, "_erp_storage_is_ready", lambda: True)
    monkeypatch.setattr(
        "catalog.representative_registry.list_representative_login_users",
        lambda: [{"email": "rep@example.com"}],
    )
    monkeypatch.delenv("CATALOG_SESSION_SECRET", raising=False)
    monkeypatch.setattr(health, "_runtime_catalog_available", lambda: True)
    client = TestClient(create_app())

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "catalog_bundle": "ok",
            "shared_session_key": "missing",
            "representative_login": "ok",
            "erp_storage": "ok",
        },
    }
