import json
from io import BytesIO
from types import SimpleNamespace

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
            return {"Body": BytesIO(stored_payload)}

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


def test_environment_login_survives_temporary_blob_failure(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "blob-token")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_EMAIL", "fallback@example.com")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_PASSWORD", "fallback-password")
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_LOGIN_NAME", "Fallback")
    monkeypatch.setattr(
        representative_registry,
        "_load_blob_payload",
        lambda: (_ for _ in ()).throw(PermissionError("blob suspended")),
    )

    users = representative_registry.list_representative_login_users()

    assert [user["email"] for user in users] == ["fallback@example.com"]


def test_representative_registry_uses_private_vercel_blob(monkeypatch):
    stored_payload: bytes | None = None

    def fake_get(path, *, access, token):
        assert path == "catalogo/representative_users.json"
        assert access == "private"
        assert token == "blob-test-token"
        if stored_payload is None:
            raise BlobNotFoundError()
        return SimpleNamespace(content=stored_payload)

    def fake_put(
        path,
        body,
        *,
        access,
        content_type,
        add_random_suffix,
        overwrite,
        token,
    ):
        nonlocal stored_payload
        assert path == "catalogo/representative_users.json"
        assert access == "private"
        assert content_type.startswith("application/json")
        assert add_random_suffix is False
        assert overwrite is True
        assert token == "blob-test-token"
        stored_payload = body
        return SimpleNamespace(pathname=path)

    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "blob-test-token")
    monkeypatch.setattr("vercel.blob.get", fake_get)
    monkeypatch.setattr("vercel.blob.put", fake_put)

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
