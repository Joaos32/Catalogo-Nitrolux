from fastapi.testclient import TestClient

from catalog.bootstrap import create_app


def test_integration_products_requires_configured_key(monkeypatch):
    monkeypatch.delenv("CATALOG_INTEGRATION_API_KEY", raising=False)
    client = TestClient(create_app())

    response = client.get("/catalog/integration/products")

    assert response.status_code == 503
    assert response.json() == {"detail": "Catalog integration is not configured"}


def test_integration_products_authenticates_api_key(monkeypatch):
    monkeypatch.setenv("CATALOG_INTEGRATION_API_KEY", "integration-test-secret")
    monkeypatch.setattr(
        "catalog.api.endpoints.integration._integration_catalog_products",
        lambda: (
            {"Codigo": "6419", "Nome": "Produto", "Categoria": "PENDENTE"},
            {"Codigo": "6000", "Nome": "Outro", "Categoria": "LAMPADA"},
        ),
    )
    client = TestClient(create_app())

    missing = client.get("/catalog/integration/products")
    invalid = client.get(
        "/catalog/integration/products",
        headers={"X-Catalog-Api-Key": "invalid"},
    )
    valid = client.get(
        "/catalog/integration/products",
        headers={"X-Catalog-Api-Key": "integration-test-secret"},
    )
    assert missing.status_code == 401
    assert invalid.status_code == 403
    assert valid.status_code == 200
    assert valid.json()[0]["Codigo"] == "6419"
    etag = valid.headers["etag"]

    cached = client.get(
        "/catalog/integration/products",
        headers={
            "X-Catalog-Api-Key": "integration-test-secret",
            "If-None-Match": etag,
        },
    )

    assert etag.startswith('"') and etag.endswith('"')
    assert cached.status_code == 304
    assert cached.content == b""

    filtered = client.get(
        "/catalog/integration/products?category=pendente",
        headers={"X-Catalog-Api-Key": "integration-test-secret"},
    )
    categories = client.get(
        "/catalog/integration/categories",
        headers={"X-Catalog-Api-Key": "integration-test-secret"},
    )

    assert filtered.status_code == 200
    assert [item["Codigo"] for item in filtered.json()] == ["6419"]
    assert categories.status_code == 200
    assert categories.json()["categories"] == [
        {"name": "LAMPADA", "total": 1},
        {"name": "PENDENTE", "total": 1},
    ]
