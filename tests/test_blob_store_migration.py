import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from vercel.blob import BlobNotFoundError

from scripts import migrate_blob_store


@pytest.fixture
def blob_stores(monkeypatch):
    source = {
        "catalogo/representative_users.json": json.dumps({"users": [{"email": "user@example.com", "password_hash": "preserved-hash", "is_admin": True}]}).encode(),
        "catalogo/erp_products.json": json.dumps({"products": [{"Codigo": "1234", "Nome": "Current product"}]}).encode(),
    }
    destination = {}
    calls = []
    monkeypatch.setenv("CATALOG_SOURCE_BLOB_READ_WRITE_TOKEN", "test-source-token")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "test-destination-token")

    def get(path, *, token, access, use_cache):
        assert access == "private" and use_cache is False
        store = source if token == "test-source-token" else destination
        if path not in store:
            raise BlobNotFoundError()
        return SimpleNamespace(content=store[path])

    def put(path, content, **options):
        assert options["token"] == "test-destination-token"
        assert options["access"] == "private"
        assert options["overwrite"] is False
        assert options["add_random_suffix"] is False
        assert options["multipart"] is False
        assert path not in destination
        destination[path] = content
        calls.append(path)

    monkeypatch.setattr("vercel.blob.get", get)
    monkeypatch.setattr("vercel.blob.put", put)
    monkeypatch.setattr("vercel.blob.iter_objects", Mock(side_effect=AssertionError("Unexpected Blob listing")))
    return source, destination, calls


def test_blob_migration_dry_run_never_uploads(blob_stores):
    source, destination, calls = blob_stores
    assert migrate_blob_store.main([]) == 0
    assert source and destination == {} and calls == []


def test_blob_migration_preserves_credentials_and_skips_completed_copy(blob_stores):
    source, destination, calls = blob_stores
    original = dict(source)
    assert migrate_blob_store.main(["--apply"]) == 0
    assert source == original and destination == original
    assert len(calls) == 2
    assert migrate_blob_store.main(["--apply"]) == 0
    assert len(calls) == 2


def test_blob_conflict_prevents_all_uploads(blob_stores):
    source, destination, calls = blob_stores
    destination["catalogo/erp_products.json"] = b"different current destination data"
    before = dict(destination)
    assert migrate_blob_store.main(["--apply"]) == 1
    assert destination == before and calls == []
    assert source["catalogo/representative_users.json"]


def test_blob_partial_copy_can_resume_without_overwriting(blob_stores):
    source, destination, calls = blob_stores
    destination["catalogo/representative_users.json"] = source["catalogo/representative_users.json"]
    assert migrate_blob_store.main(["--apply"]) == 0
    assert destination == source
    assert calls == ["catalogo/erp_products.json"]


def test_blocked_source_never_changes_destination(blob_stores, monkeypatch):
    source, destination, calls = blob_stores
    before = dict(source)
    monkeypatch.setattr("vercel.blob.get", Mock(side_effect=PermissionError("store blocked")))
    assert migrate_blob_store.main(["--apply"]) == 1
    assert source == before and destination == {} and calls == []


def test_provider_errors_never_print_token_values(blob_stores, monkeypatch, capsys):
    monkeypatch.setattr("vercel.blob.get", Mock(side_effect=ValueError("invalid token test-source-token")))
    assert migrate_blob_store.main([]) == 1
    assert "test-source-token" not in capsys.readouterr().err
