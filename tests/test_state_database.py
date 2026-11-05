import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient

from catalog import erp_storage, online_users, representative_registry, state_database
from catalog.bootstrap import create_app
from scripts import migrate_blob_state, setup_catalog_database


@pytest.fixture
def database_state(monkeypatch):
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://private-test-database")
    objects = {}
    presence = {}

    def load(key):
        return objects.get(key)

    def write(key, content, *, expected_etag=None, expected_missing=False):
        previous = objects.get(key)
        if expected_missing and previous is not None:
            raise state_database.StateWriteConflictError()
        if expected_etag is not None and (previous is None or previous.etag != expected_etag):
            raise state_database.StateWriteConflictError()
        etag = str(int(previous.etag) + 1) if previous else "1"
        objects[key] = state_database.StateObject(content, etag, datetime.now(timezone.utc).isoformat())
        return etag

    def record(email, name, last_seen):
        presence[email] = {"email": email, "name": name, "last_seen_at": last_seen.isoformat()}

    monkeypatch.setattr(state_database, "load_object", load)
    monkeypatch.setattr(state_database, "write_object", write)
    monkeypatch.setattr(state_database, "record_activity", record)
    monkeypatch.setattr(state_database, "list_activity", lambda window: list(presence.values()))
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "unused-test-token")
    for method in ("get", "put", "iter_objects"):
        monkeypatch.setattr("vercel.blob." + method, Mock(side_effect=AssertionError("Unexpected Blob access")))
    return objects, presence


def test_database_login_presence_and_password_revocation(database_state):
    client = TestClient(create_app())
    email = "database@example.com"
    created = client.put(
        f"/catalog/representatives/{email}",
        json={"email": email, "name": "Database User", "password": "database-password"},
    )
    assert created.status_code == 200
    stored = json.loads(database_state[0][state_database.REPRESENTATIVES_KEY].content)
    assert stored["users"][0]["password_hash"].startswith("pbkdf2_sha256$")
    assert "password" not in stored["users"][0]

    login = client.post("/auth/representative/login", json={"email": email, "password": "database-password"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    for _ in range(3):
        session = client.get("/auth/representative/session")
        assert session.json()["authenticated"] is True
        assert session.json()["activity_tracking_available"] is True
    online = client.get("/catalog/online-users")
    assert online.status_code == 200
    assert online.json()["total_online"] == 1
    assert online.json()["users"][0]["email"] == email

    representative_registry.upsert_managed_representative(email, "Database User", "changed-password")
    client.cookies.clear()
    revoked = client.get("/auth/representative/session", headers={"Authorization": f"Bearer {token}"})
    assert revoked.status_code == 200
    assert revoked.json()["authenticated"] is False
    protected = client.get("/catalog/local/produtos", headers={"Authorization": f"Bearer {token}"})
    assert protected.status_code == 403


def test_database_erp_conflicts_preserve_newer_snapshot(monkeypatch, database_state):
    monkeypatch.setenv("CATALOG_ERP_BLOB_ENABLED", "true")
    monkeypatch.setenv("CATALOG_ERP_S3_BUCKET", "unused-bucket")
    assert erp_storage.storage_uri() == "postgres-state://erp_products.json"
    initial = erp_storage.write_active(b'{"products": []}', expected_etag=None, expected_missing=True)
    second = erp_storage.write_active(b'{"products": [1]}', expected_etag=initial, expected_missing=False)
    with pytest.raises(erp_storage.ERPWriteConflictError):
        erp_storage.write_active(b"stale", expected_etag=initial, expected_missing=False)
    with pytest.raises(erp_storage.ERPWriteConflictError):
        erp_storage.write_active(b"overwrite", expected_etag=None, expected_missing=True)
    with pytest.raises(erp_storage.ERPWriteConflictError):
        erp_storage.write_active(b"unguarded", expected_etag=None, expected_missing=False)
    assert erp_storage.load_active().content == b'{"products": [1]}'
    assert erp_storage.load_active().etag == second


def test_database_unavailable_does_not_use_old_blob_registry(monkeypatch):
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://private-test-database")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "unused-token")
    monkeypatch.setattr(state_database, "load_object", Mock(side_effect=OSError("database unavailable")))
    old_storage = Mock(side_effect=AssertionError("Unexpected Blob fallback"))
    monkeypatch.setattr(representative_registry, "_load_blob_payload", old_storage)
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        representative_registry._load_managed_users_payload()
    assert representative_registry.list_representative_login_users() == []
    old_storage.assert_not_called()


def test_serverless_presence_without_database_never_uses_blob(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("CATALOG_STATE_BACKEND", "blob")
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://unused-local-database")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "unused-token")
    blob_put = Mock(side_effect=AssertionError("Unexpected heartbeat write"))
    monkeypatch.setattr("vercel.blob.put", blob_put)
    monkeypatch.setattr(online_users, "list_representative_login_users", Mock(side_effect=AssertionError("Unexpected read")))
    for _ in range(100):
        online_users.record_representative_activity({"email": "user@example.com"})
    summary = online_users.list_online_representatives()
    assert summary["tracking_available"] is False
    assert summary["total_online"] == 0
    blob_put.assert_not_called()


class FakeConnection:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.calls = []
        self.exit_exception = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.exit_exception = exc

    def execute(self, query, parameters):
        self.calls.append((query, parameters))
        return SimpleNamespace(fetchone=lambda: next(self.rows))


def test_adapter_conflict_raises_inside_transaction(monkeypatch):
    connection = FakeConnection([None])
    monkeypatch.setattr(state_database, "_connect", lambda: connection)
    with pytest.raises(state_database.StateWriteConflictError):
        state_database.write_object("erp_products.json", b"new", expected_etag="stale-version")
    assert isinstance(connection.exit_exception, state_database.StateWriteConflictError)
    query, parameters = connection.calls[0]
    assert "AND version = %s" in query
    assert parameters[-1] == "stale-version"


def test_seed_conflict_aborts_entire_transaction(monkeypatch):
    connection = FakeConnection([("new-version",), None])
    monkeypatch.setattr(state_database, "_connect", lambda: connection)
    with pytest.raises(state_database.StateWriteConflictError):
        state_database.seed_objects({"representative_users.json": b"users", "erp_products.json": b"erp"})
    assert isinstance(connection.exit_exception, state_database.StateWriteConflictError)
    assert len(connection.calls) == 2
    assert all("DO NOTHING" in query for query, _ in connection.calls)


def test_pooler_connection_requires_tls_and_disables_prepared_statements(monkeypatch):
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://private-test-database")
    connect = Mock()
    monkeypatch.setattr("psycopg.connect", connect)
    state_database._connect()
    connect.assert_called_once_with(
        "postgresql://private-test-database", sslmode="require", connect_timeout=5, prepare_threshold=None,
    )


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_desktop_database_can_connect_without_server_tls(monkeypatch, host):
    url = f"postgresql://catalog_user:sample-password@{host}:5432/catalogo"
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", url)
    connect = Mock()
    monkeypatch.setattr("psycopg.connect", connect)
    state_database._connect()
    connect.assert_called_once_with(url, sslmode="prefer", connect_timeout=5, prepare_threshold=None)


@pytest.mark.parametrize("url", [
    "postgresql://catalog_user@database.example/catalogo?sslmode=disable",
    "postgresql://catalog_user@localhost/catalogo?hostaddr=192.0.2.1&sslmode=disable",
])
def test_remote_database_cannot_disable_tls(monkeypatch, url):
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", url)
    connect = Mock()
    monkeypatch.setattr("psycopg.connect", connect)
    with pytest.raises(ValueError, match="require TLS"):
        state_database._connect()
    connect.assert_not_called()


def test_local_database_preserves_explicit_tls_verification(monkeypatch):
    url = "postgresql://catalog_user@localhost/catalogo?sslmode=verify-full"
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", url)
    connect = Mock()
    monkeypatch.setattr("psycopg.connect", connect)
    state_database._connect()
    connect.assert_called_once_with(url, sslmode="verify-full", connect_timeout=5, prepare_threshold=None)


def test_inherited_remote_hostaddr_keeps_tls_required(monkeypatch):
    url = "postgresql://catalog_user@localhost/catalogo"
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", url)
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    connect = Mock()
    monkeypatch.setattr("psycopg.connect", connect)
    state_database._connect()
    connect.assert_called_once_with(url, sslmode="require", connect_timeout=5, prepare_threshold=None)


def test_database_setup_check_never_creates_or_changes_tables(monkeypatch):
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://private-test-database")
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = ("catalog_private.objects", "catalog_private.presence")
    connection.execute.return_value.fetchall.return_value = []
    monkeypatch.setattr(state_database, "_connect", lambda: connection)
    assert setup_catalog_database.main([]) == 0
    assert all(call.args[0].strip().startswith("SELECT") for call in connection.execute.call_args_list)


def test_database_setup_hides_connection_credentials_on_failure(monkeypatch, capsys):
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://private-test-database")
    monkeypatch.setattr(state_database, "_connect", Mock(side_effect=OSError("secret password inside driver error")))
    assert setup_catalog_database.main(["--apply"]) == 1
    output = capsys.readouterr().err
    assert "OSError" in output
    assert "secret password" not in output


def test_migration_dry_run_preserves_credentials_and_never_writes(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    erp = tmp_path / "erp.json"
    users.write_text(json.dumps({"users": [{"email": "admin@example.com", "password_hash": "original-hash", "is_admin": True}]}))
    erp.write_text(json.dumps({"products": [{"Codigo": "1234", "Nome": "Produto"}]}))
    seed = Mock(side_effect=AssertionError("Dry-run wrote to destination"))
    monkeypatch.setattr(state_database, "seed_objects", seed)
    assert migrate_blob_state.main(["--users-file", str(users), "--erp-file", str(erp)]) == 0
    objects = migrate_blob_state.prepare_objects(users, erp)
    assert json.loads(objects[state_database.REPRESENTATIVES_KEY])["users"][0]["password_hash"] == "original-hash"
    assert json.loads(objects[state_database.REPRESENTATIVES_KEY])["users"][0]["is_admin"] is True
    seed.assert_not_called()


def test_migration_refuses_empty_source_before_any_writes(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    erp = tmp_path / "erp.json"
    users.write_text('{"users": []}')
    erp.write_text('{"products": []}')
    seed = Mock()
    monkeypatch.setattr(state_database, "seed_objects", seed)
    assert migrate_blob_state.main(["--users-file", str(users), "--erp-file", str(erp), "--apply"]) == 1
    seed.assert_not_called()
