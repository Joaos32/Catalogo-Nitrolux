from fastapi.testclient import TestClient

from catalog.bootstrap import create_app


def _configure_representatives(monkeypatch):
    monkeypatch.setenv(
        "CATALOG_REPRESENTATIVE_USERS_JSON",
        '[{"email":"rep@example.com","password":"rep-secret","name":"Representante"}]',
    )
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_JWT_SECRET", "security-test-jwt-secret")
    monkeypatch.setenv("CATALOG_REQUIRE_REPRESENTATIVE_LOGIN", "true")


def test_catalog_search_data_and_download_require_representative_auth(monkeypatch):
    _configure_representatives(monkeypatch)
    client = TestClient(create_app())

    search_data = client.get("/catalog/local/produtos")
    download = client.get("/catalog/export", params={"format": "csv"})

    assert search_data.status_code == 401
    assert download.status_code == 401


def test_invalid_representative_token_cannot_download_catalog(monkeypatch):
    _configure_representatives(monkeypatch)
    client = TestClient(create_app())

    response = client.get(
        "/catalog/export",
        params={"format": "csv"},
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid representative token"}


def test_product_data_and_exports_use_private_auth_aware_cache_headers(monkeypatch):
    from catalog.api.endpoints import catalog as catalog_endpoint
    from catalog.api.endpoints import export as export_endpoint

    monkeypatch.setattr(catalog_endpoint, "_catalog_payload", lambda: (b"[]", '"catalog-etag"'))
    monkeypatch.setattr(
        export_endpoint,
        "_build_export",
        lambda **_: (b"Codigo;Nome\n1;Produto\n", "text/csv; charset=utf-8", "catalogo.csv"),
    )
    client = TestClient(create_app())

    responses = (
        client.get("/catalog/local/produtos"),
        client.get("/catalog/export", params={"format": "csv"}),
    )

    for response in responses:
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-cache"
        vary_headers = {value.strip().lower() for value in response.headers["vary"].split(",")}
        assert {"authorization", "cookie", "accept-encoding"} <= vary_headers
