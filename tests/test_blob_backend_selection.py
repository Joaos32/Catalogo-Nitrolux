from types import SimpleNamespace
from unittest.mock import Mock

from catalog import erp_storage, state_database


def test_explicit_blob_erp_ignores_previous_postgres_and_s3(monkeypatch):
    monkeypatch.setenv("CATALOG_STATE_BACKEND", "blob")
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://unused-local-database")
    monkeypatch.setenv("CATALOG_ERP_S3_BUCKET", "unused-bucket")
    monkeypatch.setenv("CATALOG_ERP_BLOB_ENABLED", "true")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "synthetic-blob-token")
    monkeypatch.setattr(state_database, "_connect", Mock(side_effect=AssertionError("Unexpected PostgreSQL access")))
    monkeypatch.setattr("boto3.client", Mock(side_effect=AssertionError("Unexpected S3 access")))
    get = Mock(return_value=SimpleNamespace(content=b'current ERP', etag='version-1'))
    put = Mock(return_value="version-2")
    monkeypatch.setattr("vercel.blob.get", get)
    monkeypatch.setattr("catalog.erp_storage.put_versioned", put)

    assert erp_storage.storage_uri() == "vercel-blob://catalogo/erp_products.json"
    assert erp_storage.load_active().content == b'current ERP'
    get.assert_called_once_with("catalogo/erp_products.json", access="private", token="synthetic-blob-token", use_cache=False)
    erp_storage.write_active(b'new ERP', expected_etag="version-1", expected_missing=False)
    assert put.call_count == 1
    assert put.call_args.args == ("catalogo/erp_products.json", b'new ERP')
    assert put.call_args.kwargs["expected_etag"] == "version-1"
