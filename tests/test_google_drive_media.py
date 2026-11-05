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
    assert payload["imagens"][0]["url"] == (
        "https://drive.google.com/thumbnail?id=file-1&sz=w1000"
    )


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
    assert payload["white_background"] == (
        "https://drive.google.com/thumbnail?id=white&sz=w1000"
    )
    assert payload["measures"] == (
        "https://drive.google.com/thumbnail?id=measure&sz=w1000"
    )
    assert payload["ambient"] == (
        "https://drive.google.com/thumbnail?id=ambient&sz=w1000"
    )


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
    assert response.headers["cache-control"] == "private, no-store"
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


def test_photos_batch_uses_images_visible_in_gallery_without_variant_names(monkeypatch):
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_FOLDER_ID", "drive-folder")
    monkeypatch.setenv("CATALOG_GOOGLE_DRIVE_API_KEY", "test-key")
    monkeypatch.setattr("catalog.onedrive.find_local_images_for_code", lambda code: [])
    monkeypatch.setattr("catalog.onedrive.resolve_local_products_root", lambda: None)
    for provider in ("cdn_media", "vercel_blob_media", "s3_media"):
        monkeypatch.setattr(f"catalog.{provider}.is_configured", lambda: False)
    def unexpected_fallback(**kwargs):
        raise AssertionError("A valid gallery photo should be returned directly by the Drive batch")
    monkeypatch.setattr("catalog.api.endpoints.media.get_product_photos_payload", unexpected_fallback)
    monkeypatch.setattr("catalog.google_drive.find_images_for_codes", lambda codes, folder_id=None: {
        code: [{"name": f"{code} - DRIVER PARA LUMINARIA.jpg", "variant": 0,
                "url": f"https://images.test/{code}.jpg"}] for code in codes
    })
    client = TestClient(app)
    gallery = client.get("/catalog/produtos/5093/imagens").json()
    response = client.get("/catalog/photos/batch?codes=5093")
    assert response.status_code == 200
    assert response.json()["5093"]["white_background"] == gallery["imagens"][0]["url"]


def test_google_drive_categorization_retains_numbered_photos_and_fills_distinct_fallbacks(monkeypatch):
    from catalog.google_drive import categorize_photos_for_codes

    monkeypatch.setattr("catalog.google_drive.find_images_for_codes", lambda codes, folder_id=None: {
        "5093": [
            {"name": "5093.jpg", "url": "generic"},
            {"name": "5093_1.jpg", "url": "primary"},
            {"name": "5093 (2).jpg", "url": "dimensions"},
            {"name": "5093 other.jpg", "url": "generic"},
        ],
        "5094": [{"name": "5094.jpg", "url": "only-image"}],
        "5098": [],
    })
    photos = categorize_photos_for_codes(["5093", "5094", "5098"])
    assert photos["5093"] == {"white_background": "primary", "ambient": "generic", "measures": "dimensions"}
    assert photos["5094"] == {"white_background": "only-image", "ambient": None, "measures": None}
    assert photos["5098"] == {"white_background": None, "ambient": None, "measures": None}


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
