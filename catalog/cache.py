"""Thread-safe in-process TTL cache with optional stale-on-error reads."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Iterator, Tuple, TypeVar, overload


logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


class TTLCache:
    def __init__(
        self,
        ttl_seconds: int = 3600,
        stale_seconds: int = 24 * 3600,
        max_entries: int = 128,
    ):
        self.ttl = ttl_seconds
        self.stale_seconds = stale_seconds
        self.max_entries = max(1, max_entries)
        self.store: OrderedDict[Any, Tuple[Any, float, float]] = OrderedDict()
        self._store_lock = threading.RLock()
        self._key_locks: dict[Any, tuple[threading.Lock, int]] = {}

    def get(self, key: Any) -> Any:
        now = time.monotonic()
        with self._store_lock:
            entry = self.store.get(key)
            if not entry:
                return None
            value, expiry, stale_expiry = entry
            if expiry > now:
                self.store.move_to_end(key)
                return value
            if stale_expiry <= now:
                self.store.pop(key, None)
        return None

    def get_stale(self, key: Any) -> Any:
        """Return an expired value only while it remains inside its grace window."""
        now = time.monotonic()
        with self._store_lock:
            entry = self.store.get(key)
            if not entry:
                return None
            value, expiry, stale_expiry = entry
            if expiry <= now < stale_expiry:
                self.store.move_to_end(key)
                return value
            if stale_expiry <= now:
                self.store.pop(key, None)
        return None

    def set(self, key: Any, value: Any) -> None:
        now = time.monotonic()
        with self._store_lock:
            self.store[key] = (
                value,
                now + max(0, self.ttl),
                now + max(0, self.ttl) + max(0, self.stale_seconds),
            )
            self.store.move_to_end(key)
            while len(self.store) > self.max_entries:
                self.store.popitem(last=False)

    @contextmanager
    def lock_for(self, key: Any) -> Iterator[None]:
        """Coalesce concurrent cache misses for one key without blocking others."""
        with self._store_lock:
            lock, users = self._key_locks.get(key, (threading.Lock(), 0))
            self._key_locks[key] = (lock, users + 1)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._store_lock:
                current_lock, users = self._key_locks[key]
                if users <= 1:
                    self._key_locks.pop(key, None)
                else:
                    self._key_locks[key] = (current_lock, users - 1)


# These values are process-local. Stale reads are enabled only for read-only
# provider indexes, never for representative or ERP writes.
cache = TTLCache()


@overload
def cached(func: F, *, stale_if_error: bool = False) -> F: ...


@overload
def cached(*, stale_if_error: bool = False) -> Callable[[F], F]: ...


def cached(
    func: F | None = None,
    *,
    stale_if_error: bool = False,
) -> F | Callable[[F], F]:
    """Cache successful results and optionally serve stale data on provider errors.

    Stale fallback is bounded by ``TTLCache.stale_seconds`` and should be used
    only for read-only data whose last known value is more useful than an outage.
    """

    def decorate(target: F) -> F:
        @wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (target.__module__, target.__qualname__, args, tuple(sorted(kwargs.items())))
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value

            with cache.lock_for(key):
                cached_value = cache.get(key)
                if cached_value is not None:
                    return cached_value
                stale_value = cache.get_stale(key) if stale_if_error else None
                try:
                    value = target(*args, **kwargs)
                except Exception as exc:
                    if stale_value is not None:
                        logger.warning(
                            "Serving stale cached result for %s after %s",
                            target.__qualname__,
                            type(exc).__name__,
                        )
                        return stale_value
                    raise

                cache.set(key, value)
                return value

        return wrapper  # type: ignore[return-value]

    if func is None:
        return decorate
    return decorate(func)
