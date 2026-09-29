from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from catalog import cache as cache_module


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    cache_module.cache.store.clear()
    monkeypatch.setattr(cache_module.cache, "ttl", 3600)
    monkeypatch.setattr(cache_module.cache, "stale_seconds", 24 * 3600)
    yield
    cache_module.cache.store.clear()


def test_cached_decorator_serves_stale_read_only_result_after_provider_failure(monkeypatch):
    monkeypatch.setattr(cache_module.cache, "ttl", 0.01)
    calls = 0
    unavailable = False

    @cache_module.cached(stale_if_error=True)
    def provider_index():
        nonlocal calls
        calls += 1
        if unavailable:
            raise ConnectionError("provider temporarily unavailable")
        return [{"id": "cached-image"}]

    assert provider_index() == [{"id": "cached-image"}]
    time.sleep(0.02)
    unavailable = True

    assert provider_index() == [{"id": "cached-image"}]
    assert calls == 2


def test_cached_decorator_coalesces_concurrent_misses_for_the_same_key():
    calls = 0

    @cache_module.cached
    def provider_index(key):
        nonlocal calls
        calls += 1
        time.sleep(0.03)
        return {"key": key}

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(provider_index, ["same"] * 8))

    assert results == [{"key": "same"}] * 8
    assert calls == 1


def test_cache_keeps_independent_keys_concurrent():
    started = []
    gate = threading.Barrier(2)

    @cache_module.cached
    def provider_index(key):
        started.append(key)
        gate.wait(timeout=2)
        return {"key": key}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(provider_index, ["first", "second"]))

    assert sorted(started) == ["first", "second"]
    assert results == [{"key": "first"}, {"key": "second"}]


def test_cache_evicts_old_entries_when_the_size_limit_is_reached():
    bounded_cache = cache_module.TTLCache(ttl_seconds=60, stale_seconds=60, max_entries=2)
    bounded_cache.set("first", 1)
    bounded_cache.set("second", 2)

    assert bounded_cache.get("first") == 1
    bounded_cache.set("third", 3)

    assert bounded_cache.get("first") == 1
    assert bounded_cache.get("second") is None
    assert bounded_cache.get("third") == 3
