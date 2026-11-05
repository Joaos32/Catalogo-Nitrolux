"""Regression coverage for the failures reproduced in the backend review."""

import asyncio
import csv
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from catalog import auth, blob_versioning, erp_storage, exporter, representative_registry as registry, state_database
from catalog.api.endpoints import erp, media
from catalog.bootstrap import create_app
from catalog.resource_limits import ExportLimitError


@pytest.mark.parametrize("mutation", ["demote", "delete", "password"])
def test_admin_session_is_revoked_by_account_changes(monkeypatch, mutation):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    registry.upsert_managed_representative("admin@example.test", "Admin", "original-password", True)
    with TestClient(create_app()) as client:
        assert client.post("/auth/admin/login", json={"email": "admin@example.test", "password": "original-password"}).json()["authenticated"]
        if mutation == "demote":
            registry.upsert_managed_representative("admin@example.test", "Admin", is_admin=False)
        elif mutation == "delete":
            registry.delete_managed_representative("admin@example.test")
        else:
            registry.upsert_managed_representative("admin@example.test", "Admin", "changed-password")
        assert client.get("/catalog/representatives").status_code == 401
        assert client.get("/auth/session").json()["authenticated"] is False


def test_regranting_admin_does_not_reactivate_old_session(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    registry.upsert_managed_representative("admin@example.test", "Admin", "original-password", True)
    with TestClient(create_app()) as client:
        client.post("/auth/admin/login", json={"email": "admin@example.test", "password": "original-password"})
        registry.upsert_managed_representative("admin@example.test", "Admin", is_admin=False)
        registry.upsert_managed_representative("admin@example.test", "Admin", is_admin=True)
        assert client.get("/catalog/representatives").status_code == 401


def test_admin_absolute_expiration_cannot_be_extended_by_cookie_renewal(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    monkeypatch.setenv("CATALOG_SESSION_MAX_AGE_SECONDS", "300")
    monkeypatch.setenv("CATALOG_ADMIN_SESSION_ABSOLUTE_MAX_SECONDS", "300")
    registry.upsert_managed_representative("admin@example.test", "Admin", "original-password", True)
    with TestClient(create_app()) as client:
        client.post("/auth/admin/login", json={"email": "admin@example.test", "password": "original-password"})
        current_time = datetime.now(timezone.utc)

        class FutureDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return current_time + timedelta(seconds=301)

        monkeypatch.setattr(auth, "datetime", FutureDateTime)
        assert client.get("/catalog/representatives").status_code == 401


@pytest.mark.parametrize("operation", ["edit", "delete"])
def test_other_account_changes_preserve_pending_password_recovery(operation):
    registry.upsert_managed_representative("alpha@example.test", "Alpha", "original-password")
    registry.upsert_managed_representative("beta@example.test", "Beta", "original-password")
    reset = registry.create_representative_password_reset("alpha@example.test")
    if operation == "edit":
        registry.upsert_managed_representative("beta@example.test", "New name")
    else:
        registry.delete_managed_representative("beta@example.test")
    summary = registry.build_representative_admin_summary()
    assert next(user for user in summary["users"] if user["email"] == "alpha@example.test")["password_reset_pending"]
    registry.reset_representative_password_with_code("alpha@example.test", reset["reset_code"], "changed-password")
    with pytest.raises(ValueError, match="expired or unavailable"):
        registry.reset_representative_password_with_code("alpha@example.test", reset["reset_code"], "another-password")


def test_direct_password_change_invalidates_pending_recovery():
    registry.upsert_managed_representative("alpha@example.test", "Alpha", "original-password")
    reset = registry.create_representative_password_reset("alpha@example.test")
    registry.upsert_managed_representative("alpha@example.test", "Alpha", "changed-password")
    with pytest.raises(ValueError, match="expired or unavailable"):
        registry.reset_representative_password_with_code("alpha@example.test", reset["reset_code"], "another-password")


def test_concurrent_local_creations_preserve_both_users():
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda email: registry.upsert_managed_representative(email, "Concurrent", "original-password"), ["one@example.test", "two@example.test"]))
    assert all(created for created, _ in results)
    assert {u["email"] for u in registry.list_representative_login_users()} == {"one@example.test", "two@example.test"}


def test_concurrent_database_registry_updates_report_conflict(monkeypatch):
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://synthetic-test")
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    stored = [None]

    def load(key):
        snapshot = stored[0]
        barrier.wait(timeout=5)
        return snapshot

    def write(key, content, *, expected_etag, expected_missing):
        with lock:
            if expected_missing and stored[0] is not None:
                raise state_database.StateWriteConflictError()
            stored[0] = SimpleNamespace(content=content, etag="new", updated_at="now")
            return "new"

    monkeypatch.setattr(state_database, "load_object", load)
    monkeypatch.setattr(state_database, "write_object", write)

    def create(email):
        try:
            registry.upsert_managed_representative(email, "Concurrent", "original-password")
            return "created"
        except registry.RegistryWriteConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, ["one@example.test", "two@example.test"])) == ["conflict", "created"]
    assert len(json.loads(stored[0].content)["users"]) == 1


@pytest.mark.parametrize("is_admin", ["false", "true", 0, 1, [], {}])
def test_admin_flag_rejects_non_boolean_values(is_admin):
    with TestClient(create_app()) as client:
        response = client.put("/catalog/representatives/typed@example.test", json={"name": "Typed", "password": "original-password", "is_admin": is_admin})
        assert response.status_code == 422
    assert registry.list_representative_login_users() == []


def test_false_admin_flag_remains_false():
    with TestClient(create_app()) as client:
        response = client.put("/catalog/representatives/typed@example.test", json={"name": "Typed", "password": "original-password", "is_admin": False})
        assert response.status_code == 200
        assert response.json()["user"]["is_admin"] is False


@pytest.mark.parametrize("missing", [True, False])
def test_blob_writes_send_atomic_precondition(monkeypatch, missing):
    response = Mock(status_code=200)
    response.json.return_value = {"etag": '"new-version"'}
    put = Mock(return_value=response)
    monkeypatch.setattr(blob_versioning.requests, "put", put)
    version = blob_versioning.put_versioned("private.json", b"{}", token="synthetic-token", expected_etag=None if missing else '"old-version"', expected_missing=missing)
    assert version == '"new-version"'
    headers = put.call_args.kwargs["headers"]
    assert headers["x-allow-overwrite"] == ("0" if missing else "1")
    assert headers.get("x-if-match") == (None if missing else '"old-version"')
    assert put.call_args.kwargs["allow_redirects"] is False
    response.close.assert_called_once()


@pytest.mark.parametrize("status,error", [(412, {"code": "precondition_failed"}), (400, {"code": "bad_request", "message": "Blob already exists"})])
def test_blob_conflicts_are_not_retried_as_unconditional_writes(monkeypatch, status, error):
    response = Mock(status_code=status)
    response.json.return_value = {"error": error}
    put = Mock(return_value=response)
    monkeypatch.setattr(blob_versioning.requests, "put", put)
    with pytest.raises(blob_versioning.BlobWriteConflictError):
        blob_versioning.put_versioned("private.json", b"{}", token="synthetic-token", expected_etag="old", expected_missing=status == 400)
    assert put.call_count == 1
    response.close.assert_called_once()


def test_blob_existing_object_requires_known_version(monkeypatch):
    put = Mock(side_effect=AssertionError("Must not perform network I/O"))
    monkeypatch.setattr(blob_versioning.requests, "put", put)
    with pytest.raises(blob_versioning.BlobWriteConflictError):
        blob_versioning.put_versioned("private.json", b"{}", token="synthetic-token", expected_etag=None, expected_missing=False)
    put.assert_not_called()


def test_provider_outage_returns_uncacheable_503(monkeypatch):
    monkeypatch.setattr(media, "get_google_drive_photos_batch_payload", Mock(side_effect=ConnectionError("synthetic outage")))
    monkeypatch.setattr(media, "get_product_photos_payload", Mock(side_effect=ConnectionError("synthetic outage")))
    with TestClient(create_app()) as client:
        response = client.get("/catalog/photos/batch?codes=1001")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "1001" not in response.json()


def test_empty_fallback_does_not_hide_primary_provider_failure(monkeypatch):
    monkeypatch.setattr(media, "get_google_drive_photos_batch_payload", Mock(side_effect=ConnectionError("synthetic outage")))
    monkeypatch.setattr(media, "get_product_photos_payload", lambda **_: {"white_background": None})
    with TestClient(create_app()) as client:
        assert client.get("/catalog/photos/batch?codes=1001").status_code == 503


def test_confirmed_missing_photos_remain_successful(monkeypatch):
    monkeypatch.setattr(media, "get_google_drive_photos_batch_payload", lambda codes: {})
    monkeypatch.setattr(media, "get_product_photos_payload", lambda **_: {})
    with TestClient(create_app()) as client:
        response = client.get("/catalog/photos/batch?codes=1001")
    assert response.status_code == 200
    assert not any(response.json()["1001"].values())


def test_slow_media_provider_does_not_block_liveness(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def provider(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return b"image", "image/png"

    monkeypatch.setattr(media, "fetch_google_drive_image", provider)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://testserver") as client:
            image = asyncio.create_task(client.get("/catalog/media/google-drive/abcdefgh1234"))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                live = await asyncio.wait_for(client.get("/health/live"), timeout=2)
                assert live.status_code == 200
            finally:
                release.set()
                assert (await image).status_code == 200

    asyncio.run(scenario())


def test_unknown_length_upload_is_rejected_during_read(monkeypatch):
    monkeypatch.setenv("CATALOG_ERP_MAX_UPLOAD_BYTES", "8")
    chunks = iter([b"12345", b"67890", b"must-not-read"])
    consumed = []

    async def receive():
        chunk = next(chunks)
        consumed.append(chunk)
        return {"type": "http.request", "body": chunk, "more_body": True}

    request = Request({"type": "http", "method": "POST", "headers": []}, receive)
    with pytest.raises(HTTPException) as error:
        asyncio.run(erp._read_upload(request))
    assert error.value.status_code == 413
    assert len(consumed) == 2


def test_vercel_upload_cap_overrides_larger_configuration(monkeypatch):
    from catalog.erp_catalog import get_max_upload_size_bytes
    from catalog.resource_limits import VERCEL_BODY_LIMIT
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("CATALOG_ERP_MAX_UPLOAD_BYTES", "10485760")
    assert get_max_upload_size_bytes() == VERCEL_BODY_LIMIT


@pytest.mark.parametrize("value", ["=1+1", "+SUM(A1)", "@SUM(A1)", "-CMD()", "\t=1+1", "  =1+1"])
def test_spreadsheet_text_is_never_a_formula(value):
    products = [{"Codigo": "1", "Nome": value, "Peso": -1.5}]
    workbook = load_workbook(io.BytesIO(exporter._build_xlsx_bytes(products)))
    header = [cell.value for cell in workbook.active[1]]
    cell = workbook.active.cell(2, header.index("Nome") + 1)
    assert cell.data_type == "s"
    csv_rows = list(csv.DictReader(io.StringIO(exporter._build_csv_bytes(products).decode("utf-8-sig")), delimiter=";"))
    assert csv_rows[0]["Nome"].startswith("'")
    assert csv_rows[0]["Peso"] == "-1.5"


def test_zip_manifest_also_escapes_formulas():
    payload = exporter._csv_from_rows([{"Nome": "=1+1"}], ["Nome"])
    assert list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig")), delimiter=";"))[0]["Nome"] == "'=1+1"


@pytest.mark.parametrize("format_name,setting", [("zip", "CATALOG_EXPORT_MAX_ZIP_PRODUCTS"), ("pdf", "CATALOG_EXPORT_MAX_PDF_PRODUCTS")])
def test_large_heavy_export_is_rejected_before_generation(monkeypatch, format_name, setting):
    monkeypatch.setenv(setting, "1")
    monkeypatch.setattr(exporter, "_load_products", lambda: [{"Codigo": "1"}, {"Codigo": "2"}])
    generate = Mock(side_effect=AssertionError("Must reject before rendering"))
    monkeypatch.setattr(exporter, "_build_zip_bytes" if format_name == "zip" else "_build_pdf_bytes", generate)
    with pytest.raises(ExportLimitError):
        exporter.build_catalog_export(format_name=format_name)
    generate.assert_not_called()


def test_export_output_limit_returns_actionable_413(monkeypatch):
    from catalog.api.endpoints import export
    monkeypatch.setenv("CATALOG_EXPORT_MAX_BYTES", "2")
    monkeypatch.setattr(export, "_build_export", lambda **_: (b"too large", "text/csv", "products.csv"))
    with TestClient(create_app()) as client:
        response = client.get("/catalog/export?format=csv")
    assert response.status_code == 413
    assert "Filtre" in response.json()["error"]


def test_drive_download_limit_applies_without_content_length(monkeypatch):
    from catalog import google_drive
    monkeypatch.setenv("CATALOG_MEDIA_MAX_IMAGE_BYTES", "8")
    response = Mock(headers={"content-type": "image/png"})
    response.iter_content.return_value = iter([b"12345", b"67890"])
    monkeypatch.setattr(google_drive.requests, "get", Mock(return_value=response))
    with pytest.raises(ValueError, match="size limit"):
        google_drive.fetch_google_drive_image("abcdefgh1234")
    response.close.assert_called_once()


@pytest.mark.parametrize("path", ["/auth/admin/login", "/auth/representative/login", "/auth/representative/reset-password"])
def test_auth_rejects_unbounded_or_non_string_credentials(path):
    with TestClient(create_app()) as client:
        assert client.post(path, json={"email": "user@example.test", "password": "x" * 1025}).status_code == 422
        assert client.post(path, json={"email": [], "password": "password"}).status_code == 422


def test_admin_revalidation_bypasses_another_instances_stale_blob_cache(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    monkeypatch.setenv("CATALOG_STATE_BACKEND", "blob")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "synthetic-store")
    user = {"email":"admin@example.test", "name":"Admin", "password_hash":registry.hash_representative_password("original-password"), "is_admin":True}
    persisted = {"users":[user]}
    monkeypatch.setattr("vercel.blob.get", lambda *args, **kwargs: SimpleNamespace(content=json.dumps(persisted).encode(), etag="version-1"))
    with TestClient(create_app()) as client:
        login = client.post("/auth/admin/login", json={"email":user["email"],"password":"original-password"})
        assert login.json()["authenticated"]
        user["is_admin"] = False  # Another instance changed remote state, without invalidating this process's cache.
        assert client.get("/catalog/representatives").status_code == 401


def test_successful_login_does_not_clear_other_identities_ip_failures():
    ip = "admin-login:ip:shared"
    identity = "admin-login:identity:own@example.test"
    auth._record_auth_failure((ip, identity))
    auth._clear_auth_failures((ip, identity))
    assert len(auth._prune_auth_failures(ip)) == 1
    assert auth._prune_auth_failures(identity) == []


def test_existing_operational_metadata_survives_account_edit():
    registry.upsert_managed_representative("user@example.test", "User", "original-password")
    target = registry._managed_users_path()
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["users"][0]["operational_metadata"] = {"migration":"preserve-me"}
    target.write_text(json.dumps(payload),encoding="utf-8")
    registry.upsert_managed_representative("user@example.test", "Updated")
    assert json.loads(target.read_text(encoding="utf-8"))["users"][0]["operational_metadata"] == {"migration":"preserve-me"}


def test_export_deadline_is_enforced_and_does_not_leak_to_next_request(monkeypatch):
    from catalog import resource_limits
    ticks = [0.0]
    monkeypatch.setenv("CATALOG_EXPORT_MAX_SECONDS", "1")
    monkeypatch.setattr(resource_limits, "time", SimpleNamespace(monotonic=lambda: ticks[0]))
    monkeypatch.setattr(exporter, "_load_products", lambda: [{"Codigo":"1"}])

    def slow_csv(products):
        ticks[0] = 2
        return b"csv"

    monkeypatch.setattr(exporter, "_build_csv_bytes", slow_csv)
    with pytest.raises(ExportLimitError, match="tempo"):
        exporter.build_catalog_export(format_name="csv")
    resource_limits.check_export_budget()  # Failed request's deadline was reset.
    monkeypatch.setattr(exporter, "_build_csv_bytes", lambda products: b"csv")
    assert exporter.build_catalog_export(format_name="csv")[0] == b"csv"


def test_export_concurrency_rejects_excess_work_and_releases_slots(monkeypatch):
    from catalog.api.endpoints import export
    export._export_slots.acquire()
    export._export_slots.acquire()
    try:
        with TestClient(create_app()) as client:
            response = client.get("/catalog/export?format=csv")
        assert response.status_code == 503
        assert response.headers["retry-after"] == "5"
    finally:
        export._export_slots.release()
        export._export_slots.release()
    monkeypatch.setattr(export, "_build_export_with_cache", Mock(side_effect=ValueError("synthetic error")))
    for _ in range(3):
        with pytest.raises(ValueError, match="synthetic"):
            export._build_export(format_name="csv")


@pytest.mark.parametrize("email", ["unlisted@example.test", ""])
def test_azure_login_requires_a_current_admin_record(monkeypatch, email):
    monkeypatch.setattr(auth, "AUTH_CONFIGURED", True)
    monkeypatch.setattr(auth, "_save_cache", lambda: None)
    provider = Mock()
    provider.acquire_token_by_authorization_code.return_value = {"access_token":"synthetic-access-token", "id_token_claims":{"preferred_username":email}}
    monkeypatch.setattr(auth, "_build_msal_app", lambda: provider)
    with TestClient(create_app()) as client:
        client.cookies.set(auth.STATE_COOKIE_NAME, "synthetic-state")
        response = client.get("/auth/callback?code=synthetic-code&state=synthetic-state")
        assert response.status_code == 403
        assert client.get("/auth/session").json()["authenticated"] is False


def test_azure_admin_session_is_revoked_after_demotion(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    registry.upsert_managed_representative("azure@example.test", "Azure Admin", "original-password", True)
    monkeypatch.setattr(auth, "AUTH_CONFIGURED", True)
    monkeypatch.setattr(auth, "_save_cache", lambda: None)
    provider = Mock()
    provider.acquire_token_by_authorization_code.return_value = {"access_token":"synthetic-access-token", "id_token_claims":{"preferred_username":"azure@example.test"}}
    monkeypatch.setattr(auth, "_build_msal_app", lambda: provider)
    with TestClient(create_app()) as client:
        client.cookies.set(auth.STATE_COOKIE_NAME, "synthetic-state")
        response = client.get("/auth/callback?code=synthetic-code&state=synthetic-state", follow_redirects=False)
        assert response.status_code == 303
        assert client.get("/auth/session").json()["authenticated"] is True
        registry.upsert_managed_representative("azure@example.test", "Azure Admin", is_admin=False)
        assert client.get("/catalog/representatives").status_code == 401



def test_registry_conflict_is_reported_as_http_409(monkeypatch):
    monkeypatch.setattr(registry, "upsert_managed_representative", Mock(side_effect=registry.RegistryWriteConflictError("synthetic conflict")))
    with TestClient(create_app()) as client:
        response = client.put("/catalog/representatives/user@example.test", json={"name":"User", "password":"original-password"})
    assert response.status_code == 409


def test_blob_erp_stale_writer_cannot_replace_newer_content(monkeypatch):
    monkeypatch.setenv("CATALOG_STATE_BACKEND", "blob")
    monkeypatch.setenv("CATALOG_ERP_BLOB_ENABLED", "true")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "synthetic-store")
    stored = {"content":b"original", "etag":'"version-1"'}
    monkeypatch.setattr("vercel.blob.get", lambda *args, **kwargs: SimpleNamespace(**stored))

    def conditional_put(url, *, params, data, headers, **kwargs):
        response = Mock()
        if headers["x-if-match"] != stored["etag"]:
            response.status_code = 412
            response.json.return_value = {"error":{"code":"precondition_failed"}}
        else:
            stored.update(content=data,etag='"version-2"')
            response.status_code = 200
            response.json.return_value = {"etag":stored["etag"]}
        return response

    monkeypatch.setattr(blob_versioning.requests,"put",conditional_put)
    original = erp_storage.load_active(fresh=True)
    erp_storage.write_active(b"newer",expected_etag=original.etag,expected_missing=False)
    with pytest.raises(erp_storage.ERPWriteConflictError):
        erp_storage.write_active(b"stale",expected_etag=original.etag,expected_missing=False)
    assert stored["content"] == b"newer"


@pytest.mark.parametrize("invalid", [42, {"users":"invalid"}, {"users":[False]}, {"users":[{"unknown":"shape"}]}])
def test_invalid_registry_is_never_silently_replaced(invalid):
    target = registry._managed_users_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    original = json.dumps(invalid)
    target.write_text(original, encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid representative registry"):
        registry.upsert_managed_representative("new@example.test", "New", "original-password")
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("operation", ["edit", "delete"])
def test_environment_account_recovery_survives_other_account_changes(monkeypatch, operation):
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_JSON", json.dumps([{"email":"alpha@example.test", "name":"Alpha", "password":"environment-password"}]))
    registry.upsert_managed_representative("beta@example.test", "Beta", "original-password")
    reset = registry.create_representative_password_reset("alpha@example.test")
    if operation == "edit":
        registry.upsert_managed_representative("beta@example.test", "Updated")
    else:
        registry.delete_managed_representative("beta@example.test")
    summary = registry.build_representative_admin_summary()
    alpha = next(user for user in summary["users"] if user["email"] == "alpha@example.test")
    assert alpha["password_reset_pending"] is True
    registry.reset_representative_password_with_code("alpha@example.test", reset["reset_code"], "changed-password")
    user = next(user for user in registry.list_representative_login_users() if user["email"] == "alpha@example.test")
    assert registry.verify_representative_password(user, "changed-password")
    assert not registry.verify_representative_password(user, "environment-password")



def test_edit_preserves_legacy_admin_and_password_hash_aliases():
    target = registry._managed_users_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    password_hash = registry.hash_representative_password("original-password")
    target.write_text(json.dumps({"users":[{"login":"legacy@example.test", "display_name":"Legacy", "passwordHash":password_hash, "admin":True}]}),encoding="utf-8")
    created, user = registry.upsert_managed_representative("legacy@example.test", "Updated")
    assert not created and user["is_admin"] is True
    stored = registry.list_representative_login_users()[0]
    assert stored["is_admin"] is True
    assert registry.verify_representative_password(stored,"original-password")



def test_admin_login_never_reports_success_when_revalidation_fails(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "original-password")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "synthetic-store")
    from vercel.blob import BlobNotFoundError
    reads = [0]

    def provider(*args, **kwargs):
        reads[0] += 1
        if reads[0] == 1:
            raise BlobNotFoundError()
        raise ImportError("synthetic incompatible SDK")

    monkeypatch.setattr("vercel.blob.get", provider)
    with TestClient(create_app()) as client:
        response = client.post("/auth/admin/login",json={"email":"admin@example.test", "password":"original-password"})
        assert response.status_code == 503
        assert "confirmar" in response.json()["detail"]
        assert client.get("/auth/session").json()["authenticated"] is False


def test_sdk_blob_read_failure_does_not_create_an_admin_session(monkeypatch):
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("CATALOG_ADMIN_LOGIN_PASSWORD", "original-password")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "synthetic-store")
    monkeypatch.setattr("vercel.blob.get", Mock(side_effect=ImportError("synthetic missing get")))
    with TestClient(create_app()) as client:
        response = client.post("/auth/admin/login",json={"email":"admin@example.test", "password":"original-password"})
        assert response.status_code == 503
        assert client.get("/catalog/representatives").status_code == 401
