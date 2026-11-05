"""Keep product-source discovery separate from deployment reports and snapshots."""
import json
import os
from pathlib import Path

from catalog import erp_catalog


def _product(path, code="1001"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"products": [{"Codigo": code, "Nome": "Produto válido"}]}), encoding="utf-8")
    return path


def _isolated_tree(monkeypatch, tmp_path):
    reports = tmp_path / "reports"
    inbox = reports / "erp_inbox"
    drop = tmp_path / "catalog" / "json"
    for folder in (reports, inbox, drop):
        folder.mkdir(parents=True)
    monkeypatch.setattr(erp_catalog, "BASE_DIR", tmp_path)
    monkeypatch.setattr(erp_catalog, "DEFAULT_ERP_JSON_PATH", reports / "erp_products.json")
    monkeypatch.setattr(erp_catalog, "DEFAULT_ERP_DROP_DIR", drop)
    monkeypatch.setenv("CATALOG_ERP_JSON_PATH", str(reports / "erp_products.json"))
    monkeypatch.setenv("CATALOG_ERP_INBOX_DIR", str(inbox))
    return reports, inbox, drop


def test_file_list_ignores_diagnostic_json_even_when_newer_than_products(monkeypatch, tmp_path):
    reports, inbox, drop = _isolated_tree(monkeypatch, tmp_path)
    active = _product(reports / "erp_products.json")
    review = _product(inbox / "novo.json", "1002")
    source = _product(drop / "pcprodut_antigo.json", "1003")
    _product(reports / "catalog_runtime.json", "1004")
    for name in ("erp-review-counts-browser-evidence-2026-10-29.json", "erp_products_diagnostic.json", "pcprodut_report.json"):
        report = reports / name
        report.write_text(json.dumps({"scenarios": [{"width": 1440, "passed": True}]}), encoding="utf-8")
        os.utime(report, (2_000_000_000, 2_000_000_000))
    (inbox / "broken.json").write_text("broken JSON", encoding="utf-8")
    (drop / "empty.json").write_text('{"products": []}', encoding="utf-8")
    files = erp_catalog.list_erp_files()
    assert {row["path"] for row in files} == {str(active), str(review), str(source)}
    assert next(row for row in files if row["path"] == str(review))["is_review"] is True
    assert next(row for row in files if row["path"] == str(source))["is_review"] is False
    assert next(row for row in files if row["path"] == str(active))["is_active"] is True


def test_automatic_active_discovery_skips_newer_invalid_reports(monkeypatch, tmp_path):
    reports, inbox, drop = _isolated_tree(monkeypatch, tmp_path)
    monkeypatch.setenv("CATALOG_ERP_AUTO_DISCOVERY", "true")
    actual = _product(drop / "pcprodut_valido.json")
    diagnostic = reports / "erp-review-counts-browser-evidence-2026-10-29.json"
    diagnostic.write_text('{"scenarios": []}', encoding="utf-8")
    malformed = drop / "pcprodut_broken.json"
    malformed.write_text("broken", encoding="utf-8")
    os.utime(diagnostic, (2_000_000_000, 2_000_000_000))
    os.utime(malformed, (2_000_000_000, 2_000_000_000))
    assert erp_catalog._resolve_json_path() == actual


def test_explicit_source_directory_lists_only_valid_products(monkeypatch, tmp_path):
    reports, inbox, drop = _isolated_tree(monkeypatch, tmp_path)
    _product(reports / "erp_products.json")
    extra = tmp_path / "imports"
    product = _product(extra / "custom.json", "1005")
    (extra / "audit.json").write_text('{"scenarios": []}', encoding="utf-8")
    monkeypatch.setenv("CATALOG_ERP_SOURCE_DIRS", str(extra))
    found = erp_catalog._discover_erp_source_files()
    assert product in found
    assert extra / "audit.json" not in found


def test_packaging_rules_keep_only_the_runtime_json_allowlist():
    root = Path(__file__).resolve().parents[1]
    rules = (root / ".vercelignore").read_text(encoding="utf-8").splitlines()
    assert "reports/*.json" in rules
    for required in ("erp_products.json", "media_manifest.json", "catalog_runtime.json"):
        assert "!reports/" + required in rules
        assert rules.index("reports/*.json") < rules.index("!reports/" + required)
        assert (root / "reports" / required).is_file()
