"""Process-local private Blob snapshots, bounded to five minutes without stale reads."""

from dataclasses import dataclass
import hashlib
from typing import Callable, TypeVar

from .cache import TTLCache


T = TypeVar("T")
SNAPSHOT_TTL_SECONDS = 300
snapshots = TTLCache(ttl_seconds=SNAPSHOT_TTL_SECONDS, stale_seconds=0, max_entries=16)


@dataclass(frozen=True)
class _Snapshot:
    # A missing object is a successful read too; cache it to avoid repeated 404s.
    content: bytes | None
    etag: str | None = None


def _key(token: str, pathname: str) -> tuple[str, str]:
    return hashlib.sha256(token.encode("utf-8")).hexdigest(), pathname


def read(token: str, pathname: str, loader: Callable[[], bytes | None], *, fresh: bool = False) -> bytes | None:
    return _read(token, pathname, lambda: _Snapshot(loader()), fresh=fresh).content


def read_versioned(token: str, pathname: str, loader: Callable[[], tuple[bytes | None, str | None]], *, fresh: bool = False) -> tuple[bytes | None, str | None]:
    snapshot = _read(token, pathname, lambda: _Snapshot(*loader()), fresh=fresh)
    return snapshot.content, snapshot.etag


def _read(token: str, pathname: str, loader: Callable[[], _Snapshot], *, fresh: bool) -> _Snapshot:
    key = _key(token, pathname)
    with snapshots.lock_for(key):
        cached = snapshots.get(key)
        if not fresh and cached is not None:
            return cached
        # An expired/forced refresh must never fall back to old credentials.
        snapshots.delete(key)
        snapshot = loader()
        snapshots.set(key, snapshot)
        return snapshot


def write_versioned(token: str, pathname: str, content: bytes, writer: Callable[[], str]) -> str:
    key = _key(token, pathname)
    with snapshots.lock_for(key):
        snapshots.delete(key)
        etag = writer()
        snapshots.set(key, _Snapshot(bytes(content), etag))
        return etag


def write(token: str, pathname: str, content: bytes, writer: Callable[[], T]) -> T:
    key = _key(token, pathname)
    with snapshots.lock_for(key):
        # Also discard on failure: a provider may have accepted an interrupted PUT.
        snapshots.delete(key)
        result = writer()
        snapshots.set(key, _Snapshot(bytes(content)))
        return result
