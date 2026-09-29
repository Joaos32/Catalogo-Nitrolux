from pathlib import Path

import pytest

from catalog import erp_catalog


def test_atomic_write_replaces_target_after_full_write(tmp_path):
    target = tmp_path / "erp.json"
    target.write_bytes(b"old")

    erp_catalog._atomic_write_bytes(target, b"new complete value")

    assert target.read_bytes() == b"new complete value"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_keeps_previous_file_if_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "erp.json"
    target.write_bytes(b"valid previous data")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated disk interruption")

    monkeypatch.setattr(erp_catalog.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        erp_catalog._atomic_write_bytes(target, b"partial new data")

    assert target.read_bytes() == b"valid previous data"
    assert list(tmp_path.iterdir()) == [target]
