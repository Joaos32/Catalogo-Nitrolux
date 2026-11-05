"""Copy current users and ERP between private Blob stores; dry-run by default."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migrate_blob_state import validate_objects  # noqa: E402


class CopyValidationError(ValueError):
    """A safe, locally generated migration validation message."""


def _path(variable: str, default: str) -> str:
    return str(os.getenv(variable) or default).strip().strip("/")


def _read(token: str, pathname: str, *, allow_missing: bool = False) -> bytes | None:
    from vercel.blob import BlobNotFoundError, get

    try:
        response = get(pathname, access="private", token=token, use_cache=False)
    except BlobNotFoundError:
        if allow_missing:
            return None
        raise CopyValidationError("A required source object is missing") from None
    if response is None:
        if allow_missing:
            return None
        raise CopyValidationError("A required source object is missing")
    return bytes(response.content)


def copy_state(*, apply: bool = False) -> int:
    source = str(os.getenv("CATALOG_SOURCE_BLOB_READ_WRITE_TOKEN") or "").strip()
    destination = str(os.getenv("BLOB_READ_WRITE_TOKEN") or "").strip()
    if not source or not destination:
        raise CopyValidationError("Configure source and destination Blob tokens")
    if secrets.compare_digest(source, destination):
        raise CopyValidationError("Source and destination tokens must identify different stores")

    users = _read(source, _path("CATALOG_SOURCE_REPRESENTATIVE_BLOB_PATH", "catalogo/representative_users.json"))
    erp = _read(source, _path("CATALOG_SOURCE_ERP_BLOB_PATH", "catalogo/erp_products.json"))
    try:
        objects = validate_objects(users, erp)
    except (ValueError, UnicodeError):
        raise CopyValidationError("Source snapshots are invalid; restore valid current source data before copying") from None
    destinations = {
        _path("CATALOG_REPRESENTATIVE_BLOB_PATH", "catalogo/representative_users.json"): objects["representative_users.json"],
        _path("CATALOG_ERP_BLOB_PATH", "catalogo/erp_products.json"): objects["erp_products.json"],
    }
    if len(destinations) != 2:
        raise CopyValidationError("Destination paths must be distinct")

    pending = []
    # Check both destinations before any upload. An interrupted copy can be
    # resumed only when previously copied objects still match the source.
    for pathname, content in destinations.items():
        existing = _read(destination, pathname, allow_missing=True)
        if existing is not None:
            if hashlib.sha256(existing).digest() != hashlib.sha256(content).digest():
                raise CopyValidationError("Destination contains different data; refusing to overwrite")
        else:
            pending.append((pathname, content))
        print(f"Validated {pathname}: {len(content)} bytes")
    print(f"Pending uploads: {len(pending)}; matching existing objects: {2 - len(pending)}")
    if not apply:
        print("Dry-run complete. No Blob uploads, listings or deletions performed.")
        return 0

    from vercel.blob import put

    for pathname, content in pending:
        put(
            pathname, content, access="private", token=destination,
            content_type="application/json; charset=utf-8", add_random_suffix=False,
            overwrite=False, cache_control_max_age=0, multipart=False,
        )
        print(f"Copied {pathname}")
    print("Copy complete. Source objects preserved; existing destination objects were not overwritten.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Upload only missing destination objects")
    args = parser.parse_args(argv)
    try:
        return copy_state(apply=args.apply)
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        kind = type(exc).__name__ + (f", HTTP {status}" if isinstance(status, int) else "")
        # Driver errors can expose token-bearing URLs; print only known safe fields.
        reason = str(exc) if isinstance(exc, CopyValidationError) else "Check source access, destination and token configuration"
        print(f"Copy aborted ({kind}): {reason}", file=sys.stderr)
        print("Sources were preserved. If an upload was interrupted, retry after resolving the error; matching objects are skipped.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
    raise SystemExit(main())
