"""Check the real installed SDK, without monkeypatching away missing exports."""

import inspect
from importlib.metadata import version
from pathlib import Path


def test_deployed_blob_sdk_contract_matches_pinned_dependency():
    from vercel.blob import get, put, BlobNotFoundError
    from vercel.blob.types import GetBlobResult

    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert "vercel==0.8.1" in requirements.splitlines()
    assert version("vercel") == "0.8.1"
    assert callable(get) and callable(put)
    assert issubclass(BlobNotFoundError, Exception)
    assert {"access", "token", "use_cache"} <= inspect.signature(get).parameters.keys()
    assert {"content", "etag", "status_code"} <= GetBlobResult.__dataclass_fields__.keys()


def test_flattened_runtime_pins_match_audited_snapshot():
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    root = Path(__file__).resolve().parents[1]
    def packages(filename):
        entries = [Requirement(line) for line in (root / filename).read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
        assert all(str(entry.specifier).startswith("==") for entry in entries)
        return {canonicalize_name(entry.name):str(entry.specifier) for entry in entries}
    assert packages("requirements.txt") == packages("requirements.lock")
