"""Review uploads survive read-only deployments and independent requests."""
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
import json

import pytest
from fastapi.testclient import TestClient

from app import app
from catalog import erp_catalog, erp_storage, state_database


@pytest.fixture
def private_blob(monkeypatch):
    import vercel.blob
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("CATALOG_STATE_BACKEND", "blob")
    monkeypatch.setenv("CATALOG_ERP_BLOB_ENABLED", "true")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "synthetic-test-token")
    objects = {}
    calls = []
    uploaded = datetime(2026, 10, 29, tzinfo=timezone.utc)
    def get(key, **kwargs):
        assert kwargs["access"] == "private"
        assert kwargs["use_cache"] is False
        calls.append(("get", key))
        if key not in objects:
            return None
        content = objects[key]
        return SimpleNamespace(content=content, uploaded_at=uploaded, etag=sha256(content).hexdigest())
    def put(key, content, **kwargs):
        assert key.startswith(erp_storage.INBOX_PREFIX)
        assert kwargs["access"] == "private"
        assert kwargs["overwrite"] is False
        assert kwargs["add_random_suffix"] is False
        assert kwargs["cache_control_max_age"] == 0
        assert key not in objects
        objects[key] = content
        calls.append(("put", key))
    def listing(**kwargs):
        assert kwargs["prefix"] == erp_storage.INBOX_PREFIX
        return iter(SimpleNamespace(pathname=key, size=len(content), uploaded_at=uploaded)
            for key, content in objects.items() if key.startswith(kwargs["prefix"]))
    def write_active(key, content, **kwargs):
        old = objects.get(key)
        assert kwargs["expected_missing"] == (old is None)
        if old is not None:
            assert kwargs["expected_etag"] == sha256(old).hexdigest()
        objects[key] = content
        calls.append(("activate", key))
        return sha256(content).hexdigest()
    monkeypatch.setattr(vercel.blob, "get", get)
    monkeypatch.setattr(vercel.blob, "put", put)
    monkeypatch.setattr(vercel.blob, "iter_objects", listing)
    monkeypatch.setattr(erp_storage, "put_versioned", write_active)
    def forbidden_write(*args, **kwargs):
        raise AssertionError("Read-only deployment files must not be written")
    monkeypatch.setattr(erp_catalog, "_atomic_write_bytes", forbidden_write)
    return objects, calls


def _stage(client, filename="pcprodut_novo.json", code="5160"):
    return client.post("/catalog/erp/stage-file", params={"filename": filename},
        json={"products": [{"Codigo": code, "Nome": "TARTARUGA LED 10W", "Categoria": "TARTARUGA"}]})


def test_review_survives_other_requests_and_activation_uses_exact_uploaded_file(private_blob):
    objects, calls = private_blob
    active_key = erp_storage.DEFAULT_ERP_BLOB_PATH
    active = json.dumps({"products": [{"Codigo": "1641", "Nome": "Produto ativo"}]}).encode()
    objects[active_key] = active
    client = TestClient(app)
    response = _stage(client)
    assert response.status_code == 200, response.text
    staged = response.json()
    assert staged["staged"] is True
    assert staged["path"].startswith("erp-inbox://")
    assert staged["products_loaded"] == 1
    assert staged["change_summary"]["added_count"] == 1
    assert objects[active_key] == active
    assert not any(call[0] == "activate" for call in calls)

    # Another client, with local catalog/Blob caches cleared: only shared objects survive.
    from catalog.cache import cache
    from catalog.blob_cache import snapshots
    cache.store.clear()
    snapshots.store.clear()
    client = TestClient(app)
    listed = client.get("/catalog/erp/files")
    assert listed.status_code == 200, listed.text
    assert any(row["path"] == staged["path"] for row in listed.json()["files"])
    preview = client.get("/catalog/erp/files/preview", params={"file_path": staged["path"]})
    assert preview.status_code == 200, preview.text
    assert preview.json()["sample_products"][0]["Codigo"] == "5160"
    assert objects[active_key] == active

    activated = client.post("/catalog/erp/import-file", json={"file_path": staged["path"]})
    assert activated.status_code == 200, activated.text
    assert activated.json()["source_path"] == staged["path"]
    assert [row["Codigo"] for row in json.loads(objects[active_key])["products"]] == ["5160"]
    files = client.get("/catalog/erp/files").json()["files"]
    assert next(row for row in files if row["path"] == staged["path"])["is_deployed_source"] is True


def test_identical_upload_names_do_not_overwrite_reviews(private_blob):
    objects, _ = private_blob
    client = TestClient(app)
    first, second = _stage(client, code="5160"), _stage(client, code="5161")
    assert first.status_code == second.status_code == 200
    assert first.json()["name"] == second.json()["name"] == "pcprodut_novo.json"
    assert first.json()["path"] != second.json()["path"]
    for response, code in [(first, "5160"), (second, "5161")]:
        preview = client.get("/catalog/erp/files/preview", params={"file_path": response.json()["path"]})
        assert preview.json()["sample_products"][0]["Codigo"] == code
    assert len(objects) == 2


@pytest.mark.parametrize("reference", [
    "erp-inbox://../../representative_users.json",
    "erp-inbox://" + "a" * 32 + "/../erp_products.json",
    "erp-inbox://" + "a" * 32 + "/%2e%2e%2fsecret.json",
    "erp-inbox://" + "a" * 32 + "/foo.json?token=secret",
    "erp-inbox://catalogo/erp_products.json",
])
def test_review_reference_cannot_read_other_private_objects(private_blob, reference):
    _, calls = private_blob
    with pytest.raises(ValueError, match="Invalid ERP review file reference"):
        erp_storage.load_inbox_file(reference)
    assert calls == []
    client = TestClient(app)
    response = client.get("/catalog/erp/files/preview", params={"file_path": reference})
    assert response.status_code == 400
    # Authentication may read its own store, but the forged reference does not.
    assert all(key == "catalogo/representative_users.json" for operation, key in calls)


def test_missing_review_returns_validation_error(private_blob):
    client = TestClient(app)
    response = client.get("/catalog/erp/files/preview", params={"file_path": "erp-inbox://" + "a" * 32 + "/missing.json"})
    assert response.status_code == 400
    assert response.json()["error"] == "ERP review file not found"


@pytest.mark.parametrize("payload", [b"broken JSON", b'{"products":[]}'])
def test_invalid_upload_is_not_saved(private_blob, payload):
    objects, _ = private_blob
    response = TestClient(app).post("/catalog/erp/stage-file", content=payload, headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert objects == {}


def test_upload_budget_is_enforced_before_private_storage(private_blob, monkeypatch):
    objects, _ = private_blob
    monkeypatch.setenv("CATALOG_ERP_MAX_UPLOAD_BYTES", "16")
    assert _stage(TestClient(app)).status_code == 413
    assert objects == {}


def test_serverless_without_shared_storage_returns_actionable_error(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    response = _stage(TestClient(app))
    assert response.status_code == 503
    assert "armazenamento compartilhado" in response.json()["error"]


def test_shared_review_routes_require_admin(private_blob, monkeypatch):
    objects, _ = private_blob
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "false")
    response = _stage(TestClient(app))
    assert response.status_code == 401
    assert objects == {}


def test_postgres_review_storage_uses_shared_objects(monkeypatch):
    monkeypatch.setattr(state_database, "is_configured", lambda: True)
    objects = {}
    now = "2026-10-29T13:00:00+00:00"
    def write(key, content, **kwargs):
        assert kwargs == {"expected_missing": True}
        objects[key] = content
    monkeypatch.setattr(state_database, "write_object", write)
    monkeypatch.setattr(state_database, "load_object", lambda key: SimpleNamespace(content=objects[key], updated_at=now) if key in objects else None)
    monkeypatch.setattr(state_database, "list_object_metadata", lambda prefix: [{"key": key, "size_bytes": len(content), "updated_at": now} for key, content in objects.items() if key.startswith(prefix)])
    stored = erp_storage.store_inbox_file("review.json", b"{}")
    assert erp_storage.load_inbox_file(stored["path"])[0] == b"{}"
    assert erp_storage.list_inbox_files()[0]["path"] == stored["path"]


def test_s3_review_storage_uses_private_immutable_objects(monkeypatch):
    import boto3
    from io import BytesIO
    monkeypatch.setenv("CATALOG_ERP_S3_BUCKET", "test-bucket")
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    objects = {}
    class Client:
        def put_object(self, **kwargs):
            assert kwargs["IfNoneMatch"] == "*"
            assert kwargs["ServerSideEncryption"] == "AES256"
            assert "ACL" not in kwargs
            objects[kwargs["Key"]] = kwargs["Body"]
        def get_object(self, **kwargs):
            return {"Body": BytesIO(objects[kwargs["Key"]]), "LastModified": now}
        def get_paginator(self, operation):
            assert operation == "list_objects_v2"
            return self
        def paginate(self, **kwargs):
            return [{"Contents": [{"Key": key, "Size": len(content), "LastModified": now} for key, content in objects.items() if key.startswith(kwargs["Prefix"])]}]
    monkeypatch.setattr(boto3, "client", lambda service: Client())
    stored = erp_storage.store_inbox_file("review.json", b"{}")
    assert erp_storage.load_inbox_file(stored["path"])[0] == b"{}"
    assert erp_storage.list_inbox_files()[0]["path"] == stored["path"]


def test_full_erp_json_review_preserves_active_catalog(private_blob):
    from pathlib import Path
    objects, calls = private_blob
    content = (Path(__file__).resolve().parents[1] / "reports/erp_products.json").read_bytes()
    objects[erp_storage.DEFAULT_ERP_BLOB_PATH] = content
    expected_count = len(json.loads(content)["products"])
    client = TestClient(app)
    response = client.post("/catalog/erp/stage-file", params={"filename": "pcprodut_full.json"},
        content=content, headers={"Content-Type": "application/json"})
    assert response.status_code == 200, response.text
    assert response.json()["products_loaded"] == expected_count
    assert response.json()["change_summary"]["unchanged_count"] == expected_count
    assert objects[erp_storage.DEFAULT_ERP_BLOB_PATH] == content
    assert not any(operation == "activate" for operation, key in calls)
    preview = client.get("/catalog/erp/files/preview", params={"file_path": response.json()["path"]})
    assert preview.status_code == 200
    assert preview.json()["products_loaded"] == expected_count


def test_review_counts_compare_unique_codes_with_active_catalog(private_blob):
    objects, _ = private_blob
    active = json.dumps({"products": [
        {"Codigo": "1001", "Nome": "Nome anterior"},
        {"Codigo": "1002", "Nome": "Produto removido"},
        {"Codigo": "1003", "Nome": "Sem alteração"},
    ]}, ensure_ascii=False).encode()
    objects[erp_storage.DEFAULT_ERP_BLOB_PATH] = active
    payload = {"products": [
        {"Codigo": "1001", "Nome": "Nome atualizado"},
        {"Codigo": "1003", "Nome": "Sem alteração"},
        {"Codigo": "1004", "Nome": "Produto novo"},
        {"Codigo": "1004", "Nome": "Produto novo"},
    ]}
    client = TestClient(app)
    response = client.post("/catalog/erp/stage-file", params={"filename": "comparacao.json"}, json=payload)
    assert response.status_code == 200, response.text
    staged = response.json()
    for preview in [staged, client.get("/catalog/erp/files/preview", params={"file_path": staged["path"]}).json()]:
        summary = preview["change_summary"]
        assert {kind: summary[kind + "_count"] for kind in ("added", "updated", "removed", "unchanged")} == {
            "added": 1, "updated": 1, "removed": 1, "unchanged": 1,
        }
        assert preview["products_loaded"] == 3
        assert preview["ignored_records"] == 1
        assert {(change["change_type"], change["code"]) for change in summary["changes"]} == {
            ("added", "1004"), ("updated", "1001"), ("removed", "1002"),
        }
    assert objects[erp_storage.DEFAULT_ERP_BLOB_PATH] == active


def test_active_remote_json_can_be_previewed(private_blob):
    objects, _ = private_blob
    objects[erp_storage.DEFAULT_ERP_BLOB_PATH] = json.dumps({"products": [{"Codigo": "1001", "Nome": "Ativo"}]}).encode()
    client = TestClient(app)
    response = client.get("/catalog/erp/files/preview", params={"file_path": erp_storage.storage_uri()})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["is_active"] is True
    assert preview["change_summary"]["unchanged_count"] == 1
    assert all(preview["change_summary"][kind + "_count"] == 0 for kind in ("added", "updated", "removed"))


def test_review_refresh_compares_against_latest_remote_active_version(private_blob):
    objects, _ = private_blob
    objects[erp_storage.DEFAULT_ERP_BLOB_PATH] = json.dumps({"products": [{"Codigo": "1001", "Nome": "Anterior"}]}).encode()
    # Prime the ordinary active catalog cache, as the status request does.
    assert erp_catalog.load_erp_index()["1001"]["Nome"] == "Anterior"
    client = TestClient(app)
    response = _stage(client, code="5160")
    assert response.status_code == 200
    assert response.json()["change_summary"]["added_count"] == 1
    assert response.json()["change_summary"]["removed_count"] == 1
    reference = response.json()["path"]
    # Simulate another instance activating this content, without touching local caches.
    current = json.dumps({"products": [{"Codigo": "5160", "Nome": "TARTARUGA LED 10W", "Categoria": "TARTARUGA"}]}).encode()
    objects[erp_storage.DEFAULT_ERP_BLOB_PATH] = current
    refreshed = client.get("/catalog/erp/files/preview", params={"file_path": reference})
    assert refreshed.status_code == 200
    summary = refreshed.json()["change_summary"]
    assert all(summary[kind + "_count"] == 0 for kind in ("added", "updated", "removed"))
    assert summary["unchanged_count"] == 1
    assert objects[erp_storage.DEFAULT_ERP_BLOB_PATH] == current


def test_remote_active_file_is_not_confused_with_bundled_seed(private_blob):
    objects, _ = private_blob
    remote = json.dumps({"products": [{"Codigo": "1001", "Nome": "Ativo remoto"}]}).encode()
    objects[erp_storage.DEFAULT_ERP_BLOB_PATH] = remote
    client = TestClient(app)
    staged = _stage(client)
    assert staged.status_code == 200
    files = client.get("/catalog/erp/files").json()["files"]
    assert [item["path"] for item in files if item["is_active"]] == [erp_storage.storage_uri()]
    review = next(item for item in files if item["path"] == staged.json()["path"])
    assert review["is_review"] is True
    assert review["is_deployed_source"] is False
    assert objects[erp_storage.DEFAULT_ERP_BLOB_PATH] == remote
