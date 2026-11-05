import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from vercel.blob import BlobNotFoundError

from catalog import blob_cache, erp_storage, representative_registry as registry
from catalog.bootstrap import create_app


USERS = "catalogo/representative_users.json"
ERP = "catalogo/erp_products.json"


@pytest.fixture
def stores(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "cache-test-store")
    monkeypatch.setenv("CATALOG_STATE_BACKEND", "blob")
    monkeypatch.setenv("CATALOG_ERP_BLOB_ENABLED", "true")
    monkeypatch.setenv("CATALOG_REQUIRE_REPRESENTATIVE_LOGIN", "true")
    monkeypatch.setenv("VERCEL", "1")
    password_hash = registry.hash_representative_password("original-password")
    data = {USERS: json.dumps({"users":[{"email":"cached@example.com", "name":"Cached user", "password_hash":password_hash}]}).encode(), ERP:b'{"products":[{"Codigo":"1234","Nome":"Original"}]}'}

    def fetch(path, *, access, token, use_cache):
        assert access == "private" and use_cache is False
        assert token == "cache-test-store"
        if path not in data:
            raise BlobNotFoundError()
        return SimpleNamespace(content=data[path], etag="version-1")

    def upload(path, content, **kwargs):
        data[path] = content
        return "version-2"

    get = Mock(side_effect=fetch)
    put = Mock(side_effect=upload)
    monkeypatch.setattr("vercel.blob.get", get)
    monkeypatch.setattr("catalog.representative_registry.put_versioned", put)
    monkeypatch.setattr("catalog.erp_storage.put_versioned", put)
    return data, get, put


@pytest.fixture
def clock(monkeypatch):
    value = [1_000.0]
    monkeypatch.setattr("catalog.cache.time", SimpleNamespace(monotonic=lambda: value[0]))
    return value


def test_thousand_registry_reads_and_erp_reads_fetch_each_object_once(stores):
    _, get, put = stores
    for _ in range(1_000):
        assert registry.list_representative_login_users()[0]["email"] == "cached@example.com"
        assert erp_storage.load_active().content
    assert get.call_count == 2
    put.assert_not_called()


def test_repeated_missing_objects_are_cached(stores):
    data, get, put = stores
    data.clear()
    for _ in range(100):
        assert registry.list_representative_login_users() == []
        assert erp_storage.load_active() is None
    assert get.call_count == 2
    put.assert_not_called()


def test_session_validation_bypasses_snapshot_and_revokes_deleted_user(stores, clock):
    data, get, _ = stores
    client = TestClient(create_app())
    login = client.post("/auth/representative/login", json={"email":"cached@example.com", "password":"original-password"})
    assert login.status_code == 200
    for _ in range(3):
        assert client.get("/auth/representative/session").json()["authenticated"] is True
    assert get.call_count == 4  # One fresh identity/revocation read per request.
    data[USERS] = b'{"users":[]}'
    assert client.get("/auth/representative/session").json()["authenticated"] is False
    assert get.call_count == 5


def test_expired_credentials_are_never_served_after_blob_outage(stores, clock):
    _, get, _ = stores
    client = TestClient(create_app())
    assert client.post("/auth/representative/login", json={"email":"cached@example.com", "password":"original-password"}).status_code == 200
    clock[0] += 300
    get.side_effect = PermissionError("store unavailable")
    assert client.get("/auth/representative/session").json()["authenticated"] is False


def test_mutation_refreshes_external_users_and_updates_local_snapshot(stores):
    data, get, put = stores
    registry.list_representative_login_users()
    payload = json.loads(data[USERS])
    payload["users"].append({"email":"external@example.com","name":"External user","password":"external-password"})
    data[USERS] = json.dumps(payload).encode()
    registry.upsert_managed_representative("new@example.com","New user","new-user-password")
    assert {u["email"] for u in json.loads(data[USERS])["users"]} == {"cached@example.com","external@example.com","new@example.com"}
    assert get.call_count == 2 and put.call_count == 1
    assert len(registry.list_representative_login_users()) == 3
    assert get.call_count == 2


def test_password_change_and_delete_revoke_existing_session_immediately(stores):
    client = TestClient(create_app())
    assert client.post("/auth/representative/login", json={"email":"cached@example.com","password":"original-password"}).status_code == 200
    registry.upsert_managed_representative("cached@example.com","Cached user","changed-password")
    assert client.get("/auth/representative/session").json()["authenticated"] is False
    assert client.post("/auth/representative/login",json={"email":"cached@example.com","password":"changed-password"}).status_code == 200
    registry.delete_managed_representative("cached@example.com")
    assert client.get("/auth/representative/session").json()["authenticated"] is False


def test_failed_fresh_read_never_overwrites_registry_with_empty_fallback(stores):
    data, get, put = stores
    registry.list_representative_login_users()
    original = data[USERS]
    get.side_effect = PermissionError("store unavailable")
    with pytest.raises(RuntimeError):
        registry.upsert_managed_representative("new@example.com","New user","new-user-password")
    assert data[USERS] == original
    put.assert_not_called()


def test_erp_fresh_read_and_successful_write_replace_snapshot(stores):
    data, get, _ = stores
    original = erp_storage.load_active().content
    data[ERP] = b'changed externally'
    assert erp_storage.load_active().content == original
    assert erp_storage.load_active(fresh=True).content == b'changed externally'
    erp_storage.write_active(b'new ERP',expected_etag='version-1',expected_missing=False)
    assert erp_storage.load_active().content == b'new ERP'
    assert get.call_count == 2


def test_concurrent_cache_misses_share_the_same_fetch():
    barrier, entered, release = Barrier(8), Event(), Event()

    def load():
        entered.set()
        assert release.wait(timeout=5)
        return b'shared snapshot'

    loader = Mock(side_effect=load)

    def read():
        barrier.wait(timeout=5)
        return blob_cache.read("test-token","private.json",loader)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(read) for _ in range(8)]
        assert entered.wait(timeout=5)
        release.set()
        assert [f.result(timeout=5) for f in futures] == [b'shared snapshot'] * 8
    assert loader.call_count == 1


def test_cache_separates_store_credentials_and_paths():
    assert blob_cache.read("first-token","users.json",lambda:b'first') == b'first'
    assert blob_cache.read("second-token","users.json",lambda:b'second') == b'second'
    assert blob_cache.read("first-token","erp.json",lambda:b'erp') == b'erp'


def test_failed_write_discards_previous_snapshot():
    blob_cache.read("test-token","users.json",lambda:b'old')
    with pytest.raises(PermissionError):
        blob_cache.write("test-token","users.json",b'new',Mock(side_effect=PermissionError()))
    assert blob_cache.read("test-token","users.json",lambda:b'actual') == b'actual'


def test_cached_registry_dictionaries_cannot_be_mutated_by_a_caller(stores):
    payload = registry._load_blob_payload()
    payload["users"].clear()
    assert registry.list_representative_login_users()[0]["email"] == "cached@example.com"


def test_reset_password_refreshes_and_invalidates_previous_credentials(stores):
    client = TestClient(create_app())
    assert client.post("/auth/representative/login",json={"email":"cached@example.com","password":"original-password"}).status_code == 200
    reset = registry.create_representative_password_reset("cached@example.com")
    registry.reset_representative_password_with_code("cached@example.com",reset["reset_code"],"reset-password-new")
    assert client.get("/auth/representative/session").json()["authenticated"] is False
    assert client.post("/auth/representative/login",json={"email":"cached@example.com","password":"reset-password-new"}).status_code == 200
    with pytest.raises(ValueError):
        registry.reset_representative_password_with_code("cached@example.com",reset["reset_code"],"another-password")
