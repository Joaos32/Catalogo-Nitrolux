import pytest

from scripts.check_production_readiness import _validate_backend


def _configuration(database_url, *, vercel=False):
    return {
        "CATALOG_SESSION_SECRET": "a73f93b108d44921a5a925fcc81a524ffe651a93",
        "CATALOG_SESSION_COOKIE_SECURE": "true",
        "CATALOG_ENABLE_API_DOCS": "false",
        "CATALOG_ADMIN_LOGIN_PASSWORD": "synthetic-test-password",
        "CATALOG_REQUIRE_REPRESENTATIVE_LOGIN": "true",
        "CATALOG_STATE_DATABASE_URL": database_url,
        "VERCEL": "true" if vercel else "false",
    }


def test_postgresql_is_recognized_as_shared_representative_storage():
    errors, _ = _validate_backend(_configuration("postgresql://user:sample@database.example/catalogo", vercel=True))
    assert errors == []


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_vercel_cannot_use_database_on_workstation_localhost(host):
    errors, _ = _validate_backend(_configuration(f"postgresql://user:sample@{host}/catalogo", vercel=True))
    assert any("CATALOG_STATE_DATABASE_URL must use a remote host" in error for error in errors)
    assert all("sample" not in error for error in errors)


def test_self_hosted_backend_can_use_local_postgresql():
    errors, _ = _validate_backend(_configuration("postgresql://user:sample@127.0.0.1/catalogo"))
    assert errors == []


def test_blob_backend_ignores_leftover_local_database_configuration():
    values = _configuration("postgresql://user:sample@localhost/catalogo", vercel=True)
    values.update(CATALOG_STATE_BACKEND="blob", BLOB_READ_WRITE_TOKEN="synthetic-blob-token")
    errors, _ = _validate_backend(values)
    assert errors == []


def test_blob_backend_requires_its_own_registry_even_with_s3_or_postgres_configured():
    values = _configuration("postgresql://user:sample@localhost/catalogo", vercel=True)
    values.update(CATALOG_STATE_BACKEND="blob", CATALOG_REPRESENTATIVE_S3_BUCKET="unused-bucket")
    errors, _ = _validate_backend(values)
    assert any("Configure at least one representative" in error for error in errors)
