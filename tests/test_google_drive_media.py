from fastapi.testclient import TestClient

from app import app


def test_google_drive_images_route_matches_product_code(monkeypatch):
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_FOLDER_ID", "drive-folder")
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_API_KEY", "test-key")
    monkeypatch.setattr(
        "catalog.google_drive.list_google_drive_images",
        lambda folder_id=None: [
            {
                "id": "file-1",
                "name": "1234 (1).jpg",
                "mimeType": "image/jpeg",
                "url": "https://drive.google.com/uc?export=view&id=file-1",
            },
            {
                "id": "file-2",
                "name": "1234 (2).jpg",
                "mimeType": "image/jpeg",
                "url": "https://drive.google.com/uc?export=view&id=file-2",
            },
            {
                "id": "file-3",
                "name": "9999.jpg",
                "mimeType": "image/jpeg",
                "url": "https://drive.google.com/uc?export=view&id=file-3",
            },
        ],
    )

    client = TestClient(app)
    response = client.get("/catalog/google-drive/produtos/1234/imagens")

    assert response.status_code == 200
    payload = response.json()
    assert payload["codigo"] == "1234"
    assert [item["name"] for item in payload["imagens"]] == ["1234 (1).jpg", "1234 (2).jpg"]
    assert payload["imagens"][0]["variant"] == 1


def test_google_drive_photos_route_categorizes_variants(monkeypatch):
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_FOLDER_ID", "drive-folder")
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_API_KEY", "test-key")
    monkeypatch.setattr(
        "catalog.google_drive.list_google_drive_images",
        lambda folder_id=None: [
            {
                "id": "white",
                "name": "1234 (1).jpg",
                "mimeType": "image/jpeg",
                "url": "https://drive.google.com/uc?export=view&id=white",
            },
            {
                "id": "measure",
                "name": "1234 (2).jpg",
                "mimeType": "image/jpeg",
                "url": "https://drive.google.com/uc?export=view&id=measure",
            },
            {
                "id": "ambient",
                "name": "1234 ambiente.jpg",
                "mimeType": "image/jpeg",
                "url": "https://drive.google.com/uc?export=view&id=ambient",
            },
        ],
    )

    client = TestClient(app)
    response = client.get("/catalog/google-drive/photos", params={"code": "1234"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["white_background"].endswith("id=white")
    assert payload["measures"].endswith("id=measure")
    assert payload["ambient"].endswith("id=ambient")


def test_product_images_uses_google_drive_when_local_is_empty(monkeypatch):
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_FOLDER_ID", "drive-folder")
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_API_KEY", "test-key")
    monkeypatch.setattr("catalog.onedrive.find_local_images_for_code", lambda code: [])
    monkeypatch.setattr("catalog.onedrive.resolve_local_products_root", lambda: "D:/catalogo/fotos")
    monkeypatch.setattr(
        "catalog.google_drive.find_images_for_code",
        lambda code: [{"name": f"{code}.jpg", "variant": 0, "url": "https://drive.google.com/uc?export=view&id=file"}],
    )

    client = TestClient(app)
    response = client.get("/catalog/produtos/1234/imagens")

    assert response.status_code == 200
    payload = response.json()
    assert payload["codigo"] == "1234"
    assert payload["imagens"][0]["url"].endswith("id=file")


def test_google_drive_is_disabled_without_api_key(monkeypatch):
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_FOLDER_ID", "drive-folder")
    monkeypatch.delenv("CATALOG_GOOGLE_DRIVE_API_KEY", raising=False)

    from catalog import google_drive

    assert google_drive.is_configured() is False


def test_google_drive_media_proxy_serves_image(monkeypatch):
    monkeypatch.setattr(
        "catalog.api.endpoints.media.fetch_google_drive_image",
        lambda file_id, size="detail": (b"fake-image", "image/jpeg"),
    )

    client = TestClient(app)
    response = client.get("/catalog/media/google-drive/file-123")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.headers["cache-control"] == "public, max-age=86400, s-maxage=86400"
    assert response.content == b"fake-image"


def test_photos_batch_returns_each_product_once(monkeypatch):
    monkeypatch.setattr(
        "catalog.api.endpoints.media.get_product_photos_payload",
        lambda code=None, share_url=None: {
            "white_background": f"white-{code}",
            "ambient": f"ambient-{code}",
            "measures": None,
        },
    )

    client = TestClient(app)
    response = client.get("/catalog/photos/batch?codes=1234,5678,1234")

    assert response.status_code == 200
    assert response.json() == {
        "1234": {"white_background": "white-1234", "ambient": "ambient-1234", "measures": None},
        "5678": {"white_background": "white-5678", "ambient": "ambient-5678", "measures": None},
    }


def test_google_drive_falls_back_to_recursive_lookup_when_direct_query_is_empty(monkeypatch):
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_FOLDER_ID", "drive-folder")
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_API_KEY", "test-key")
    monkeypatch.setattr(
        "catalog.google_drive._request_named_images",
        lambda codes, folder_id=None: {str(code): [] for code in codes},
    )
    monkeypatch.setattr(
        "catalog.google_drive.list_google_drive_images",
        lambda folder_id=None: [
            {
                "id": "nested-file",
                "name": "1234_1.jpg",
                "mimeType": "image/jpeg",
                "url": "https://drive.google.com/thumbnail?id=nested-file&sz=w1000",
            }
        ],
    )

    from catalog.google_drive import find_images_for_codes

    payload = find_images_for_codes(["1234"])

    assert [item["name"] for item in payload["1234"]] == ["1234_1.jpg"]


def test_photos_batch_falls_back_when_drive_has_no_photo_for_a_code(monkeypatch):
    monkeypatch.setattr(
        "catalog.api.endpoints.media.get_google_drive_photos_batch_payload",
        lambda codes: {code: {"white_background": None, "ambient": None, "measures": None} for code in codes},
    )
    monkeypatch.setattr(
        "catalog.api.endpoints.media.get_product_photos_payload",
        lambda code=None, share_url=None: {
            "white_background": f"white-{code}",
            "ambient": f"ambient-{code}",
            "measures": None,
        },
    )

    client = TestClient(app)
    response = client.get("/catalog/photos/batch?codes=6566")

    assert response.status_code == 200
    assert response.json() == {
        "6566": {"white_background": "white-6566", "ambient": "ambient-6566", "measures": None}
    }
