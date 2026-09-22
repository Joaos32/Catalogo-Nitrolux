from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import app


def test_blob_images_are_used_as_remote_fallback(monkeypatch):
    monkeypatch.setenv("CATALOG_MEDIA_BLOB_ENABLED", "true")
    monkeypatch.setenv("CATALOG_MEDIA_BLOB_TOKEN", "test-token")
    monkeypatch.setattr("catalog.onedrive.find_local_images_for_code", lambda code: [])
    monkeypatch.setattr("catalog.onedrive.resolve_local_products_root", lambda: None)
    monkeypatch.setattr(
        "vercel.blob.iter_objects",
        lambda **kwargs: iter(
            [
                SimpleNamespace(pathname="catalogo/media/fotos/1234 (2).jpg", size=20),
                SimpleNamespace(pathname="catalogo/media/fotos/1234 (1).jpg", size=10),
                SimpleNamespace(pathname="catalogo/representative_users.json", size=1),
            ]
        ),
    )

    response = TestClient(app).get("/catalog/produtos/1234/imagens")

    assert response.status_code == 200
    assert [item["variant"] for item in response.json()["imagens"]] == [1, 2]
    assert response.json()["imagens"][0]["url"].startswith("/catalog/blob/asset?blobPath=")


def test_blob_is_checked_when_an_empty_local_root_exists(monkeypatch):
    monkeypatch.setenv("CATALOG_MEDIA_BLOB_ENABLED", "true")
    monkeypatch.setenv("CATALOG_MEDIA_BLOB_TOKEN", "test-token")
    monkeypatch.setattr("catalog.onedrive.find_local_images_for_code", lambda code: [])
    monkeypatch.setattr("catalog.onedrive.resolve_local_products_root", lambda: "D:/catalogo/fotos")
    monkeypatch.setattr(
        "catalog.vercel_blob_media.find_images_for_code",
        lambda code: [{"name": f"{code}.jpg", "variant": 0, "url": "/catalog/blob/asset?blobPath=foto"}],
    )

    response = TestClient(app).get("/catalog/produtos/1234/imagens")

    assert response.status_code == 200
    assert response.json()["imagens"][0]["name"] == "1234.jpg"


def test_blob_asset_is_private_and_restricted_to_media_prefix(monkeypatch):
    monkeypatch.setenv("CATALOG_MEDIA_BLOB_ENABLED", "true")
    monkeypatch.setenv("CATALOG_MEDIA_BLOB_TOKEN", "test-token")
    monkeypatch.setattr(
        "vercel.blob.get",
        lambda *args, **kwargs: SimpleNamespace(content=b"image", content_type="image/jpeg"),
    )

    client = TestClient(app)
    response = client.get("/catalog/blob/asset?blobPath=catalogo/media/fotos/1234.jpg")
    assert response.status_code == 200
    assert response.content == b"image"
    assert response.headers["content-type"] == "image/jpeg"

    forbidden = client.get("/catalog/blob/asset?blobPath=catalogo/representative_users.json")
    assert forbidden.status_code == 404
