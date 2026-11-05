"""Security regressions use only isolated accounts and mocked providers."""
import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from catalog import auth, representative_registry as registry
from catalog.api.endpoints import media
from catalog.bootstrap import create_app, SECURITY_HEADERS


def rep_login(client, email="rep@example.test", password="original-password"):
    result = client.post("/auth/representative/login", json={"email":email,"password":password})
    assert result.status_code == 200
    return result.json()["access_token"]


def admin_login(client):
    result = client.post("/auth/admin/login",json={"email":"admin@example.test","password":"original-password"})
    assert result.status_code == 200
    return client.cookies.get("catalog_admin_session")


@pytest.fixture
def accounts(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN","false")
    monkeypatch.setenv("CATALOG_REQUIRE_REPRESENTATIVE_LOGIN","true")
    registry.upsert_managed_representative("admin@example.test","Admin","original-password",True)
    registry.upsert_managed_representative("rep@example.test","Rep","original-password")
    return create_app()


def test_old_environment_credentials_never_return_after_outage_or_deletion(monkeypatch):
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_JSON",json.dumps([{"email":"rep@example.test","password":"original-password"}]))
    client=TestClient(create_app())
    token=rep_login(client)
    reset=registry.create_representative_password_reset("rep@example.test")
    registry.reset_representative_password_with_code("rep@example.test",reset["reset_code"],"changed-password")
    with monkeypatch.context() as patch:
        patch.setattr(registry,"_load_managed_users_payload",Mock(side_effect=RuntimeError("synthetic outage")))
        assert client.post("/auth/representative/login",json={"email":"rep@example.test","password":"original-password"}).status_code==503
        assert not client.get("/auth/representative/session",headers={"Authorization":"Bearer "+token}).json()["authenticated"]
    registry.delete_managed_representative("rep@example.test")
    assert client.post("/auth/representative/login",json={"email":"rep@example.test","password":"original-password"}).status_code!=200
    assert not client.get("/auth/representative/session",headers={"Authorization":"Bearer "+token}).json()["authenticated"]
    with pytest.raises(KeyError): registry.create_representative_password_reset("rep@example.test")


def test_deleted_managed_admin_cannot_reappear_from_environment(accounts, monkeypatch):
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL","admin@example.test")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD","original-password")
    registry.delete_managed_representative("admin@example.test")
    response=TestClient(accounts).post("/auth/admin/login",json={"email":"admin@example.test","password":"original-password"})
    assert response.status_code != 200


def test_admin_logout_revokes_only_current_session_across_apps(accounts):
    first, other = TestClient(accounts), TestClient(create_app())
    copied=admin_login(first)
    admin_login(other)
    assert first.post("/auth/logout").status_code==200
    replay=TestClient(create_app()).get("/catalog/representatives",headers={"Cookie":"catalog_admin_session="+copied})
    assert replay.status_code==401
    assert other.get("/catalog/representatives").status_code==200
    admin_login(first)
    assert first.get("/catalog/representatives").status_code==200


def test_representative_logout_survives_other_registry_writes(accounts):
    first,other=TestClient(accounts),TestClient(create_app())
    copied=rep_login(first)
    rep_login(other)
    assert first.post("/auth/representative/logout").status_code==200
    registry.upsert_managed_representative("additional@example.test","Additional","original-password")
    response=TestClient(create_app()).get("/auth/representative/session",headers={"Authorization":"Bearer "+copied})
    assert response.json()["authenticated"] is False
    assert other.get("/auth/representative/session").json()["authenticated"] is True


@pytest.mark.parametrize("admin",[False,True])
def test_logout_does_not_claim_success_when_revocation_store_fails(accounts,monkeypatch,admin):
    client=TestClient(accounts)
    admin_login(client) if admin else rep_login(client)
    monkeypatch.setattr(registry,"_load_managed_users_payload",Mock(side_effect=RuntimeError("synthetic outage")))
    response=client.post("/auth/logout" if admin else "/auth/representative/logout")
    assert response.status_code==503
    assert "unable to confirm logout" in response.json()["detail"].lower()


def test_revocation_conflicts_retry_without_losing_another_session(accounts,monkeypatch):
    client=TestClient(accounts); copied=rep_login(client)
    real=auth.revoke_auth_sessions
    call=Mock(side_effect=[registry.RegistryWriteConflictError("synthetic conflict"),None])
    def revoke(items):
        call(items)
        if call.call_count==2: real(items)
    monkeypatch.setattr(auth,"revoke_auth_sessions",revoke)
    assert client.post("/auth/representative/logout").status_code==200
    assert call.call_count==2
    assert not TestClient(create_app()).get("/auth/representative/session",headers={"Authorization":"Bearer "+copied}).json()["authenticated"]


def test_refresh_keeps_session_identity_and_absolute_limit(accounts,monkeypatch):
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_IDLE_TIMEOUT_MINUTES","1")
    client=TestClient(accounts); old=rep_login(client)
    claims=auth._decode_representative_token(old)
    client.get("/auth/representative/session")
    refreshed=auth._decode_representative_token(client.cookies.get(auth.REPRESENTATIVE_COOKIE_NAME))
    assert refreshed["session_id"]==claims["session_id"]
    assert refreshed["session_expires_at"]==claims["session_expires_at"]
    assert client.post("/auth/representative/logout").status_code==200
    assert not TestClient(create_app()).get("/auth/representative/session",headers={"Authorization":"Bearer "+old}).json()["authenticated"]


@pytest.mark.parametrize("origin,header,expected",[("https://untrusted.example.test",True,403),("https://app.example.test",False,403),("https://app.example.test",True,200),("null",True,403),("https://[",True,403)])
def test_browser_mutation_checks_origin_and_custom_header(accounts,origin,header,expected):
    client=TestClient(accounts,base_url="https://app.example.test"); admin_login(client)
    headers={"Origin":origin,"Content-Type":"application/json","Sec-Fetch-Site":"same-site"}
    if header: headers["X-Catalog-Request"]="1"
    response=client.post("/catalog/erp/upload?filename=security-fixture.json",content=json.dumps([{"Codigo":"987654","Nome":"Synthetic"}]),headers=headers)
    assert response.status_code==expected


def test_simple_upload_rejected_and_token_integration_preserved(accounts,monkeypatch):
    client=TestClient(accounts); admin_login(client)
    assert client.post("/catalog/erp/upload",content="{}",headers={"Content-Type":"text/plain"}).status_code==415
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN","synthetic-integration-token")
    response=TestClient(create_app()).post("/catalog/erp/upload?filename=service.json",content=json.dumps([{"Codigo":"987654","Nome":"Synthetic"}]),headers={"Content-Type":"application/json","X-Catalog-Admin-Token":"synthetic-integration-token"})
    assert response.status_code==200


def test_authenticated_media_never_enters_shared_cache(accounts,monkeypatch):
    monkeypatch.setattr(media,"fetch_google_drive_image",lambda *a,**k:(b"synthetic-image","image/png"))
    client=TestClient(accounts);rep_login(client)
    response=client.get("/catalog/media/google-drive/synthetic_file")
    assert response.status_code==200
    assert response.headers["cache-control"]=="private, no-store"
    assert TestClient(create_app()).get("/catalog/media/google-drive/synthetic_file").status_code==401


def test_vercel_document_headers_match_backend_policy():
    config=json.loads((Path(__file__).resolve().parents[1]/"vercel.json").read_text(encoding="utf-8"))
    headers={h["key"]:h["value"] for rule in config["headers"] if rule["source"]=="/(.*)" for h in rule["headers"]}
    for name in ("Content-Security-Policy","X-Frame-Options","X-Content-Type-Options","Referrer-Policy","Permissions-Policy"):
        assert headers[name]==SECURITY_HEADERS[name]
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "'unsafe-eval'" not in headers["Content-Security-Policy"]
