import json
from io import BytesIO
from types import SimpleNamespace

import pytest

from fastapi.testclient import TestClient
from vercel.blob import BlobNotFoundError
from botocore.exceptions import ClientError

from catalog.bootstrap import create_app
from catalog import representative_registry


def test_representative_registry_persists_in_private_s3(monkeypatch):
    stored_payload: bytes | None = None

    class FakeS3Client:
        def get_object(self, *, Bucket, Key):
            assert Bucket == "registry-bucket"
            assert Key == "private/representative_users.json"
            if stored_payload is None:
                raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
            return {"Body": BytesIO(stored_payload), "ETag": "test"}

        def put_object(self, *, Bucket, Key, Body, **kwargs):
            nonlocal stored_payload
            assert Bucket == "registry-bucket"
            assert Key == "private/representative_users.json"
            assert kwargs["ServerSideEncryption"] == "AES256"
            stored_payload = Body
            return {"ETag": "test"}

    monkeypatch.setenv("CATALOG_REPRESENTATIVE_S3_BUCKET", "registry-bucket")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_S3_ACCESS_KEY_ID", "limited-access-key")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_S3_SECRET_ACCESS_KEY", "limited-secret-key")
    monkeypatch.setattr(representative_registry, "_s3_registry_client", lambda: FakeS3Client())

    created, _ = representative_registry.upsert_managed_representative(
        "persist@example.com", "Persistente", "secure-password"
    )
    users = representative_registry.list_representative_login_users()

    assert created is True
    assert [user["email"] for user in users] == ["persist@example.com"]


def test_environment_login_is_denied_during_temporary_blob_failure(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "blob-token")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", "fallback@example.com")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", "fallback-password")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_NAME", "Fallback")
    monkeypatch.setattr(
        representative_registry,
        "_load_blob_payload",
        lambda **_: (_ for _ in ()).throw(PermissionError("blob suspended")),
    )

    users = representative_registry.list_representative_login_users()

    assert users == []


@pytest.mark.parametrize("explicit_blob", [False, True])
def test_representative_registry_uses_private_vercel_blob(monkeypatch, explicit_blob):
    if explicit_blob:
        monkeypatch.setenv("CATALOG_STATE_BACKEND", "blob")
        monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://unused-local-database")
        monkeypatch.setenv("CATALOG_REPRESENTATIVE_S3_BUCKET", "unused-bucket")
        monkeypatch.setenv("CATALOG_REPRESENTATIVE_S3_ACCESS_KEY_ID", "unused-access-key")
        monkeypatch.setenv("CATALOG_REPRESENTATIVE_S3_SECRET_ACCESS_KEY", "unused-secret-key")
    stored_payload: bytes | None = None

    def fake_get(path, *, access, token, use_cache):
        assert path == "catalogo/representative_users.json"
        assert access == "private"
        assert token == "blob-test-token"
        assert use_cache is False
        if stored_payload is None:
            raise BlobNotFoundError()
        return SimpleNamespace(content=stored_payload, etag="version-1")

    def fake_put(path, body, *, token, expected_etag, expected_missing):
        nonlocal stored_payload
        assert path == "catalogo/representative_users.json"
        assert token == "blob-test-token"
        assert expected_missing is (stored_payload is None)
        assert expected_etag is None if expected_missing else expected_etag == "version-1"
        stored_payload = body
        return "version-1"

    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "blob-test-token")
    monkeypatch.setattr("vercel.blob.get", fake_get)
    monkeypatch.setattr("catalog.representative_registry.put_versioned", fake_put)

    client = TestClient(create_app())
    created = client.put(
        "/catalog/representatives/blob@example.com",
        json={
            "email": "blob@example.com",
            "name": "Representante Blob",
            "password": "blob-secret",
        },
    )

    assert created.status_code == 200
    assert created.json()["created"] is True
    assert stored_payload is not None
    persisted = json.loads(stored_payload.decode("utf-8"))
    assert persisted["users"][0]["email"] == "blob@example.com"
    assert persisted["users"][0]["password_hash"].startswith("pbkdf2_sha256$")
    assert "password" not in persisted["users"][0]

    login = client.post(
        "/auth/representative/login",
        json={"email": "blob@example.com", "password": "blob-secret"},
    )
    assert login.status_code == 200
    assert login.json()["authenticated"] is True


def test_blocked_blob_reports_login_outage_instead_of_bad_password(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "blocked-test-token")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", "fallback@example.com")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", "fallback-password")
    monkeypatch.setattr(
        representative_registry, "_load_blob_payload",
        lambda **_: (_ for _ in ()).throw(PermissionError("store blocked")),
    )
    client = TestClient(create_app())
    unavailable = client.post(
        "/auth/representative/login", json={"email": "managed@example.com", "password": "current-password"},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "Representative storage is temporarily unavailable"

    contingency = client.post(
        "/auth/representative/login", json={"email": "fallback@example.com", "password": "fallback-password"},
    )
    assert contingency.status_code == 503
    assert client.get("/auth/representative/session").json()["authenticated"] is False
