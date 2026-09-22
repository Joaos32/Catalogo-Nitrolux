import json

from fastapi.testclient import TestClient

from app import app
from catalog import cdn_media


def _configure_manifest(monkeypatch, tmp_path):
    manifest = tmp_path / "media_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "images": [
                    {"key": "produtos/1234_2.jpg", "name": "1234_2.jpg", "size": 20},
                    {"key": "produtos/1234_1.jpg", "name": "1234_1.jpg", "size": 10},
                    {"key": "produtos/9999_1.jpg", "name": "9999_1.jpg", "size": 10},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CATALOG_MEDIA_CDN_BASE_URL", "https://media.example.cloudfront.net")
    monkeypatch.setenv("CATALOG_MEDIA_MANIFEST_PATH", str(manifest))
    cdn_media._load_index.cache_clear()


def test_cdn_manifest_serves_product_gallery(monkeypatch, tmp_path):
    _configure_manifest(monkeypatch, tmp_path)
    monkeypatch.setattr("catalog.onedrive.find_local_images_for_code", lambda code: [])
    monkeypatch.setattr("catalog.onedrive.resolve_local_products_root", lambda: None)

    response = TestClient(app).get("/catalog/produtos/1234/imagens")

    assert response.status_code == 200
    images = response.json()["imagens"]
    assert [image["variant"] for image in images] == [1, 2]
    assert images[0]["url"] == "https://media.example.cloudfront.net/produtos/1234_1.jpg"


def test_cdn_manifest_enriches_product_cover(monkeypatch, tmp_path):
    _configure_manifest(monkeypatch, tmp_path)

    products = cdn_media.enrich_products_with_photos([{"Codigo": "1234", "Nome": "Produto"}])

    assert products[0]["URLFoto"].startswith("https://media.example.cloudfront.net/")
    assert products[0]["FotoBranco"].endswith("1234_1.jpg")


def test_catalog_service_reuses_merged_products_on_vercel(monkeypatch):
    from catalog import onedrive, vercel_blob_media
    from catalog.services import catalog_service

    calls = {"products": 0}

    def list_products():
        calls["products"] += 1
        return [{"Codigo": "3009"}]

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(onedrive, "list_local_products", list_products)
    monkeypatch.setattr(cdn_media, "enrich_products_with_photos", lambda products: products)
    monkeypatch.setattr(vercel_blob_media, "enrich_products_with_photos", lambda products: products)
    monkeypatch.setattr(catalog_service, "_load_prebuilt_catalog", lambda: None)
    catalog_service._cached_catalog_products.cache_clear()
    try:
        assert catalog_service.list_catalog_products() == [{"Codigo": "3009"}]
        assert catalog_service.list_catalog_products() == [{"Codigo": "3009"}]
        assert calls["products"] == 1
    finally:
        catalog_service._cached_catalog_products.cache_clear()


def test_prebuilt_catalog_replaces_local_photo_urls_with_runtime_cdn(monkeypatch):
    from catalog import vercel_blob_media
    from catalog.services import catalog_service

    local_product = {
        "Codigo": "3009",
        "URLFoto": "/catalog/local/asset?path=3009_2.jpg",
        "FotoBranco": "/catalog/local/asset?path=3009_1.jpg",
        "FotoAmbient": "/catalog/local/asset?path=3009_3.jpg",
    }

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(catalog_service, "_load_prebuilt_catalog", lambda: [local_product])
    monkeypatch.setattr(
        cdn_media,
        "enrich_products_with_photos",
        lambda products: [
            {
                **products[0],
                "URLFoto": "https://media.example.cloudfront.net/produtos/3009_2.jpg",
                "FotoBranco": "https://media.example.cloudfront.net/produtos/3009_1.jpg",
            }
        ],
    )
    monkeypatch.setattr(vercel_blob_media, "enrich_products_with_photos", lambda products: products)
    catalog_service._cached_catalog_products.cache_clear()
    try:
        product = catalog_service.list_catalog_products()[0]
        assert product["URLFoto"].startswith("https://media.example.cloudfront.net/")
        assert product["FotoBranco"].startswith("https://media.example.cloudfront.net/")
        assert product["FotoAmbient"] == ""
    finally:
        catalog_service._cached_catalog_products.cache_clear()
