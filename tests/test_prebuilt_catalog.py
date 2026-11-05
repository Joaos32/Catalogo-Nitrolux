import hashlib
import json

from catalog.services import catalog_service


def _snapshot(monkeypatch, tmp_path, *, legacy_windows=False):
    source = tmp_path / "products.json"
    source.write_bytes(b'{\r\n  "products": [{"Codigo": "1", "Nome": "Original"}]\r\n}\r\n')
    snapshot = tmp_path / "runtime.json"
    monkeypatch.setattr(catalog_service, "PREBUILT_SOURCE_PATHS", {"products": source})
    monkeypatch.setattr(catalog_service, "PREBUILT_CATALOG_PATH", snapshot)
    products = [{"Codigo": "1", "Nome": "Original"}]
    hashes = {"products": hashlib.sha256(source.read_bytes()).hexdigest()} if legacy_windows else catalog_service.prebuilt_source_hashes()
    snapshot.write_text(json.dumps({"source_hashes": hashes, "products": products}), encoding="utf-8")
    return source, products


def test_prebuilt_catalog_survives_git_line_ending_conversion(monkeypatch, tmp_path):
    source, products = _snapshot(monkeypatch, tmp_path)
    source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
    assert catalog_service._load_prebuilt_catalog() == products


def test_old_windows_snapshot_survives_linux_git_checkout(monkeypatch, tmp_path):
    source, products = _snapshot(monkeypatch, tmp_path, legacy_windows=True)
    source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
    assert catalog_service._load_prebuilt_catalog() == products


def test_changed_product_still_invalidates_old_windows_snapshot(monkeypatch, tmp_path):
    source, _ = _snapshot(monkeypatch, tmp_path, legacy_windows=True)
    source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n").replace(b"Original", b"Updated"))
    assert catalog_service._load_prebuilt_catalog() is None


def test_missing_source_still_invalidates_prebuilt_catalog(monkeypatch, tmp_path):
    source, _ = _snapshot(monkeypatch, tmp_path)
    source.unlink()
    assert catalog_service._load_prebuilt_catalog() is None


def test_line_ending_normalization_handles_chunk_boundary_and_trailing_cr(tmp_path):
    source = tmp_path / "large.json"
    windows = b" " * (1024 * 1024 - 1) + b"\r\n{}\r"
    linux = windows.replace(b"\r\n", b"\n")
    source.write_bytes(windows)
    first = catalog_service._file_sha256(source)
    source.write_bytes(linux)
    assert catalog_service._file_sha256(source) == first
    assert catalog_service._file_sha256(source, windows_line_endings=True) == hashlib.sha256(windows).hexdigest()
