"""Catalog identity regressions: repeated spreadsheet/ERP rows must not multiply products."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from catalog.product_identity import deduplicate_products, normalize_product_code
from catalog.services import catalog_service


@pytest.mark.parametrize("value,expected", [(5160, "5160"), (5160.0, "5160"), (" 5160.00 ", "5160"), ("005160", "005160"), ("SKU-5160", "SKU-5160"), (None, ""), (False, ""), (float("nan"), "")])
def test_code_identity(value, expected):
    assert normalize_product_code(value) == expected


def test_repetitions_fill_missing_fields_without_changing_first_record_or_summing_sales():
    rows = [
        {"Codigo": "5160", "Nome": "TARTARUGA LED 10W", "VendaMes": 0, "Ativo": False, "FotoBranco": "https://placehold.co/240x240", "Especificacoes": "", "Fotos": []},
        {"Codigo": 5160.0, "Nome": "Conflicting name", "VendaMes": 30, "Ativo": True, "FotoBranco": "/photos/5160.jpg", "Especificacoes": "10W | 6500K", "Fotos": ["/photos/5160.jpg"]},
        {"Codigo": "5160.00", "FotoAmbient": "/photos/5160-ambient.jpg"},
    ]
    before = deepcopy(rows)
    result = deduplicate_products(rows)
    assert len(result) == 1
    assert result[0] == {**rows[0], "FotoBranco": "/photos/5160.jpg", "Especificacoes": "10W | 6500K", "Fotos": ["/photos/5160.jpg"], "FotoAmbient": "/photos/5160-ambient.jpg"}
    assert rows == before
    assert deduplicate_products(result) == result


def test_shared_names_and_photos_do_not_merge_different_codes_or_missing_codes():
    rows = [{"Codigo": code, "Nome": "TARTARUGA", "FotoBranco": "same.jpg"} for code in ["1641", "2371", "005160", "5160", "SKU-5160"]]
    rows += [{"Nome": "No code"}, {"Nome": "No code"}]
    assert deduplicate_products(rows) == rows


def test_code_aliases_are_recognized():
    result = deduplicate_products([{"COD_PROD": "5160"}, {"code": 5160}, {"sku": "5160.0"}])
    assert len(result) == 1
    assert result[0]["Codigo"] == "5160"


@pytest.mark.parametrize("with_erp", [False, True])
def test_erp_merge_has_one_record_per_code(monkeypatch, with_erp):
    from catalog import erp_catalog
    erp = {"5160": {"Codigo": "5160", "Nome": "TARTARUGA LED 10W", "Categoria": "TARTARUGA", "CODMARCA": "1"}} if with_erp else {}
    monkeypatch.setattr(erp_catalog, "load_erp_index", lambda: erp)
    result = erp_catalog.merge_products_with_erp([{"Codigo": "5160", "Nome": "TARTARUGA LED 10W"}, {"Codigo": "5160", "FotoAmbient": "photo.jpg"}])
    assert [row["Codigo"] for row in result] == ["5160"]
    assert result[0]["FotoAmbient"] == "photo.jpg"


def test_legacy_prebuilt_catalog_is_cleaned_on_read(monkeypatch, tmp_path):
    snapshot = tmp_path / "runtime.json"
    snapshot.write_text(json.dumps({"source_hashes": {}, "products": [{"Codigo": "5160"}, {"Codigo": "5160"}]}), encoding="utf-8")
    monkeypatch.setattr(catalog_service, "PREBUILT_SOURCE_PATHS", {})
    monkeypatch.setattr(catalog_service, "PREBUILT_CATALOG_PATH", snapshot)
    assert catalog_service._load_prebuilt_catalog() == [{"Codigo": "5160"}]


@pytest.mark.parametrize("serverless", [False, True])
def test_public_catalog_and_exports_share_unique_products(monkeypatch, serverless):
    from catalog import exporter
    rows = [{"Codigo": "5160"}, {"Codigo": "5160"}, {"Codigo": "5161"}]
    monkeypatch.setenv("VERCEL", "1" if serverless else "0")
    monkeypatch.setattr(catalog_service, "_build_catalog_products", lambda: rows)
    monkeypatch.setattr(catalog_service, "_cached_catalog_products", lambda: tuple(rows))
    monkeypatch.setattr(catalog_service, "_catalog_cache_refreshed_at", 10**20)
    expected = [{"Codigo": "5160"}, {"Codigo": "5161"}]
    assert catalog_service.list_catalog_products() == expected
    assert exporter._load_products() == expected


def test_sheet_input_is_deduplicated(monkeypatch):
    monkeypatch.setattr(catalog_service, "fetch_sheet", lambda _: [{"Codigo": "5160"}, {"Codigo": "5160"}])
    assert catalog_service.fetch_sheet_or_local_products("fixture") == [{"Codigo": "5160"}]


def test_runtime_builder_prevents_repeated_rows(monkeypatch, tmp_path):
    from scripts import build_runtime_catalog
    target = tmp_path / "runtime.json"
    monkeypatch.setattr(build_runtime_catalog, "PREBUILT_CATALOG_PATH", target)
    monkeypatch.setattr(build_runtime_catalog, "prebuilt_source_hashes", lambda: {})
    monkeypatch.setattr(build_runtime_catalog, "_build_catalog_products_from_sources", lambda: [{"Codigo": "5160"}, {"Codigo": "5160"}])
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer", "USERPROFILE", "CATALOG_LOCAL_PRODUCTS_HOME_FALLBACK"):
        monkeypatch.setenv(name, "fixture")
    build_runtime_catalog.main()
    assert json.loads(target.read_text(encoding="utf-8"))["products"] == [{"Codigo": "5160"}]


def test_bundled_catalog_retains_every_erp_code_once():
    root = Path(__file__).resolve().parents[1]
    products = json.loads((root / "reports/catalog_runtime.json").read_text(encoding="utf-8"))["products"]
    erp = json.loads((root / "reports/erp_products.json").read_text(encoding="utf-8"))["products"]
    codes = [row["Codigo"] for row in products]
    assert len(codes) == len(set(codes))
    assert set(codes) == {row["Codigo"] for row in erp}
    for code in ("5160", "5161", "5162", "1641", "2371"):
        assert codes.count(code) == 1
