import importlib
import os

from fastapi.testclient import TestClient

import catalog.auth as auth_module
from catalog.bootstrap import SECURITY_HEADERS, create_app
from catalog.core.settings import load_settings


def test_load_settings_uses_safe_local_cors_defaults():
    settings = load_settings()

    assert "*" not in settings.cors_allow_origins
    assert "http://127.0.0.1:5173" in settings.cors_allow_origins
    assert "http://localhost:8000" in settings.cors_allow_origins


def test_load_settings_exposes_optional_security_flags(monkeypatch):
    monkeypatch.setenv("CATALOG_ENABLE_API_DOCS", "false")
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "super-secret-token")
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "true")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "very-secret-password")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", "rep@example.com")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", "rep-password")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_NAME", "Equipe Comercial")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_JWT_SECRET", "rep-jwt-secret")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_JWT_EXPIRES_MINUTES", "90")
    monkeypatch.setenv("CATALOG_SESSION_SECRET", "unit-test-secret")

    settings = load_settings()

    assert settings.api_docs_enabled is False
    assert settings.erp_admin_token == "super-secret-token"
    assert settings.allow_open_admin is True
    assert settings.admin_login_email == "admin@example.com"
    assert settings.admin_login_password == "very-secret-password"
    assert settings.representative_login_email == "rep@example.com"
    assert settings.representative_login_password == "rep-password"
    assert settings.representative_login_name == "Equipe Comercial"
    assert settings.representative_jwt_secret == "rep-jwt-secret"
    assert settings.representative_jwt_expires_minutes == 90
    assert settings.session_secret == "unit-test-secret"


def test_security_headers_are_present():
    client = TestClient(create_app())
    response = client.get("/")

    for header, value in SECURITY_HEADERS.items():
        assert response.headers.get(header.lower()) == value


def test_hsts_header_is_added_on_https():
    client = TestClient(create_app(), base_url="https://testserver")
    response = client.get("/")

    assert response.headers.get("strict-transport-security") == "max-age=63072000; includeSubDomains"


def test_api_docs_can_be_disabled(monkeypatch):
    monkeypatch.setenv("CATALOG_ENABLE_API_DOCS", "false")

    client = TestClient(create_app())

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_erp_routes_require_admin_token_when_configured(monkeypatch):
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "super-secret-token")

    client = TestClient(create_app())

    missing = client.get("/catalog/erp/status")
    assert missing.status_code == 401
    assert missing.json() == {"detail": "Admin login required"}

    invalid = client.get(
        "/catalog/erp/status",
        headers={"X-Catalog-Admin-Token": "wrong-token"},
    )
    assert invalid.status_code == 403
    assert invalid.json() == {"detail": "Invalid ERP admin token"}

    valid = client.get(
        "/catalog/erp/status",
        headers={"X-Catalog-Admin-Token": "super-secret-token"},
    )
    assert valid.status_code == 200
    assert "products_loaded" in valid.json()


def test_erp_routes_fail_closed_without_admin_configuration(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "")

    client = TestClient(create_app())

    response = client.get("/catalog/erp/status")
    assert response.status_code == 401
    assert response.json() == {"detail": "Admin login required"}


def test_erp_routes_can_be_explicitly_opened_for_development(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "true")
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "")

    client = TestClient(create_app())

    response = client.get("/catalog/erp/status")
    assert response.status_code == 200
    assert "products_loaded" in response.json()


def test_erp_routes_accept_bearer_admin_token(monkeypatch):
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "super-secret-token")

    client = TestClient(create_app())
    response = client.get(
        "/catalog/erp/status",
        headers={"Authorization": "Bearer super-secret-token"},
    )

    assert response.status_code == 200
    assert "products_loaded" in response.json()


def test_erp_routes_accept_admin_browser_session(monkeypatch):
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "super-secret-token")

    client = TestClient(create_app())
    login = client.post(
        "/auth/admin/login",
        json={"email": "admin@example.com", "password": "super-secret-token"},
    )

    assert login.status_code == 200
    assert login.json()["authenticated"] is True
    assert login.json()["provider"] == "password"

    response = client.get("/catalog/erp/status")
    assert response.status_code == 200
    assert "products_loaded" in response.json()

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["authenticated"] is False

    blocked = client.get("/catalog/erp/status")
    assert blocked.status_code == 401


def test_auth_session_endpoint_reports_available_login_methods(monkeypatch):
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "super-secret-token")

    client = TestClient(create_app())
    response = client.get("/auth/session")

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is False
    assert payload["password_login_available"] is True
    assert payload["password_login_requires_email"] is True
    assert payload["protection_enabled"] is True


def test_representative_session_endpoint_reports_open_access_by_default(monkeypatch):
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_NAME", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_JSON", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_JWT_SECRET", "")

    client = TestClient(create_app())
    response = client.get("/auth/representative/session")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": False,
        "provider": None,
        "expires_at": None,
        "login_available": False,
        "protection_enabled": False,
        "user": None,
    }


def test_catalog_routes_require_representative_jwt_when_configured(monkeypatch):
    monkeypatch.setenv(
        "CATALOG_REPRESENTATIVE_USERS_JSON",
        '[{"email":"rep@example.com","password":"rep-secret","name":"Representante Recife"}]',
    )
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_JWT_SECRET", "catalog-rep-jwt-secret")

    client = TestClient(create_app())

    blocked = client.get("/catalog/local/produtos")
    assert blocked.status_code == 401
    assert blocked.json() == {"detail": "Representative login required"}

    invalid_login = client.post(
        "/auth/representative/login",
        json={"email": "rep@example.com", "password": "wrong-secret"},
    )
    assert invalid_login.status_code == 403
    assert invalid_login.json() == {"detail": "Invalid representative credentials"}

    login = client.post(
        "/auth/representative/login",
        json={"email": "rep@example.com", "password": "rep-secret"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["authenticated"] is True
    assert payload["provider"] == "jwt"
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] > 0
    assert payload["user"] == {
        "email": "rep@example.com",
        "name": "Representante Recife",
    }

    session = client.get("/auth/representative/session")
    assert session.status_code == 200
    assert session.json()["authenticated"] is True
    assert session.json()["user"]["email"] == "rep@example.com"

    allowed = client.get("/catalog/local/produtos")
    assert allowed.status_code == 200

    bearer_allowed = client.get(
        "/catalog/local/produtos",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert bearer_allowed.status_code == 200

    invalid_token = client.get(
        "/catalog/local/produtos",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert invalid_token.status_code == 403
    assert invalid_token.json() == {"detail": "Invalid representative token"}

    logout = client.post("/auth/representative/logout")
    assert logout.status_code == 200
    assert logout.json() == {"success": True, "authenticated": False}

    blocked_again = client.get("/catalog/local/produtos")
    assert blocked_again.status_code == 401


def test_representative_login_rate_limits_repeated_failures(monkeypatch):
    monkeypatch.setenv(
        "CATALOG_REPRESENTATIVE_USERS_JSON",
        '[{"email":"rep@example.com","password":"rep-secret","name":"Representante Recife"}]',
    )
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_JWT_SECRET", "catalog-rep-jwt-secret")

    client = TestClient(create_app())

    for _ in range(auth_module.AUTH_RATE_LIMIT_MAX_ATTEMPTS):
        response = client.post(
            "/auth/representative/login",
            json={"email": "rep@example.com", "password": "wrong-secret"},
        )
        assert response.status_code == 403

    limited = client.post(
        "/auth/representative/login",
        json={"email": "rep@example.com", "password": "wrong-secret"},
    )
    assert limited.status_code == 429
    assert limited.json() == {"detail": "Too many authentication attempts"}


def test_admin_login_clears_rate_limit_after_success(monkeypatch):
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "super-secret-token")

    client = TestClient(create_app())
    for _ in range(3):
        response = client.post(
            "/auth/admin/login",
            json={"email": "admin@example.com", "password": "wrong-secret"},
        )
        assert response.status_code == 403

    success = client.post(
        "/auth/admin/login",
        json={"email": "admin@example.com", "password": "super-secret-token"},
    )
    assert success.status_code == 200
    assert success.json()["authenticated"] is True

    logout = client.post("/auth/logout")
    assert logout.status_code == 200

    retry = client.post(
        "/auth/admin/login",
        json={"email": "admin@example.com", "password": "wrong-secret"},
    )
    assert retry.status_code == 403


def test_representative_login_accepts_managed_user_created_by_admin(monkeypatch, tmp_path):
    managed_path = tmp_path / "representatives.json"
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "")
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "")
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "true")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_NAME", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_JSON", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_FILE", str(managed_path))
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_JWT_SECRET", "catalog-rep-jwt-secret")

    client = TestClient(create_app())
    create = client.put(
        "/catalog/representatives/managed@example.com",
        json={
            "email": "managed@example.com",
            "name": "Representante Managed",
            "password": "rep-secret",
        },
    )
    assert create.status_code == 200
    assert create.json()["managed_users"] == 1

    login = client.post(
        "/auth/representative/login",
        json={"email": "managed@example.com", "password": "rep-secret"},
    )
    assert login.status_code == 200
    assert login.json()["authenticated"] is True
    assert login.json()["user"] == {
        "email": "managed@example.com",
        "name": "Representante Managed",
    }

    allowed = client.get("/catalog/local/produtos")
    assert allowed.status_code == 200


def test_representative_can_reset_password_with_admin_code(monkeypatch, tmp_path):
    managed_path = tmp_path / "representatives.json"
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "")
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "")
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "true")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", "env-rep@example.com")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", "old-secret")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_NAME", "Representante Ambiente")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_JSON", "")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_FILE", str(managed_path))
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_JWT_SECRET", "catalog-rep-jwt-secret")

    client = TestClient(create_app())

    reset = client.post("/catalog/representatives/env-rep@example.com/password-reset")
    assert reset.status_code == 200
    reset_payload = reset.json()
    assert reset_payload["reset_code"]
    assert reset_payload["user"]["email"] == "env-rep@example.com"
    assert reset_payload["user"]["password_reset_pending"] is True

    invalid_code = client.post(
        "/auth/representative/reset-password",
        json={
            "email": "env-rep@example.com",
            "reset_code": "wrong-code",
            "new_password": "new-secret",
        },
    )
    assert invalid_code.status_code == 400

    changed = client.post(
        "/auth/representative/reset-password",
        json={
            "email": "env-rep@example.com",
            "reset_code": reset_payload["reset_code"],
            "new_password": "new-secret",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["success"] is True

    old_login = client.post(
        "/auth/representative/login",
        json={"email": "env-rep@example.com", "password": "old-secret"},
    )
    assert old_login.status_code == 403

    new_login = client.post(
        "/auth/representative/login",
        json={"email": "env-rep@example.com", "password": "new-secret"},
    )
    assert new_login.status_code == 200
    assert new_login.json()["authenticated"] is True


def test_auth_cache_file_can_be_overridden(monkeypatch):
    target_cache = os.path.join(os.getcwd(), "reports", "_test_secure_cache", "token_cache.bin")
    monkeypatch.setenv("CATALOG_TOKEN_CACHE_FILE", str(target_cache))

    reloaded = importlib.reload(auth_module)
    try:
        assert reloaded.CACHE_FILE == os.path.abspath(str(target_cache))
    finally:
        monkeypatch.delenv("CATALOG_TOKEN_CACHE_FILE", raising=False)
        importlib.reload(auth_module)
