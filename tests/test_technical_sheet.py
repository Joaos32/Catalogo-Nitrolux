from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
import pytest

from app import app
from catalog import erp_catalog
from catalog.services import catalog_service
from catalog.technical_sheet import read_technical_sheet
from catalog.technical_sheet_layout import NITROLUX_HEADERS


MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BASE = "/catalog/erp/technical-sheet"


def excel(rows, *, second_rows=None, number_format=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Produtos"
    for row in rows:
        sheet.append(row)
    if number_format:
        sheet["A2"].number_format = number_format
    if second_rows:
        second = workbook.create_sheet("Outra aba")
        for row in second_rows:
            second.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


@pytest.fixture
def active_catalog(monkeypatch, tmp_path):
    path = tmp_path / "active.json"
    products = [
        {"Codigo": "1234", "Nome": "Pendente", "Categoria": "PENDENTE", "Descricao": "Original", "Especificacoes": "Potência: 5 W", "FotoBranco": "https://example.com/foto.jpg", "campo_extra": "preservado"},
        {"Codigo": "5678", "Nome": "Arandela", "Categoria": "ARANDELA", "Especificacoes": "Inalterado"},
        {"Codigo": "0012", "Nome": "Código com zeros", "Categoria": "PENDENTE", "Especificacoes": "Antigo"},
    ]
    path.write_text(json.dumps({"source": "fixture", "products": products}), encoding="utf-8")
    monkeypatch.setenv("CATALOG_ERP_JSON_PATH", str(path))
    monkeypatch.setattr(catalog_service, "list_catalog_products", lambda: list(products))
    return path


def post(client, action, content, **params):
    return client.post(f"{BASE}/{action}", params={"filename": "ficha.xlsx", **params}, content=content, headers={"Content-Type": MIME})


def test_preview_and_apply_preserve_other_products_and_fields(active_catalog):
    before = active_catalog.read_bytes()
    content = excel([["Código", "Nome", "Potência", "Tensão"], [1234, "Nome que não deve substituir", "12 W", "Bivolt"], [5678, "", "", ""]])
    client = TestClient(app)
    response = post(client, "preview", content)
    assert response.status_code == 200
    preview = response.json()
    assert preview["updated_count"] == 1
    assert preview["invalid_count"] == 1
    assert active_catalog.read_bytes() == before
    assert preview["rows"][0]["previous_specs"] == "Potência: 5 W"
    applied = post(client, "import", content, preview_key=preview["preview_key"])
    assert applied.status_code == 200
    assert applied.json()["updated_count"] == 1
    saved = json.loads(active_catalog.read_text(encoding="utf-8"))
    products = {p["Codigo"]: p for p in saved["products"]}
    assert len(products) == 3
    assert products["1234"]["Especificacoes"] == "Potência: 12 W | Tensão: Bivolt"
    assert products["1234"]["Nome"] == "Pendente"
    assert products["1234"]["Descricao"] == "Original"
    assert products["1234"]["FotoBranco"] == "https://example.com/foto.jpg"
    assert products["1234"]["campo_extra"] == "preservado"
    assert products["5678"]["Especificacoes"] == "Inalterado"
    assert saved["source"] == "fixture"
    assert erp_catalog.load_erp_index()["1234"]["Especificacoes"] == products["1234"]["Especificacoes"]


def test_duplicate_unknown_blank_formula_and_unchanged_rows(active_catalog):
    content = excel([
        ["SKU", "Especificações"], [1234, "Duplicado 1"], [1234, "Duplicado 2"],
        [9999, "Desconhecido"], [5678, "Inalterado"], ["", "Sem código"],
        ["0012", "=1+1"], [None, None],
    ])
    preview = read_technical_sheet(content, "dados.xlsx")
    assert preview["total_rows"] == 6
    assert preview["updated_count"] == 0
    assert preview["unchanged_count"] == 1
    assert preview["invalid_count"] == 5
    assert all("duplicado" in row["issues"][0] for row in preview["rows"][:2])
    assert "não encontrado" in preview["rows"][2]["issues"][0]
    assert "fórmulas" in preview["rows"][-1]["issues"][0]


def test_import_requires_preview_and_rejects_stale_catalog(active_catalog):
    client = TestClient(app)
    content = excel([["Código", "Especificações"], [1234, "12 W"]])
    assert post(client, "import", content).status_code == 400
    preview = post(client, "preview", content).json()
    payload = json.loads(active_catalog.read_text(encoding="utf-8"))
    payload["products"][0]["Especificacoes"] = "Edição concorrente"
    active_catalog.write_text(json.dumps(payload), encoding="utf-8")
    before = active_catalog.read_bytes()
    assert post(client, "import", content, preview_key=preview["preview_key"]).status_code == 409
    assert active_catalog.read_bytes() == before


def test_import_rejects_changed_file_and_remote_write_conflict(active_catalog, monkeypatch):
    client = TestClient(app)
    content = excel([["Código", "Especificações"], [1234, "12 W"]])
    preview = post(client, "preview", content).json()
    changed = excel([["Código", "Especificações"], [1234, "100 W"]])
    assert post(client, "import", changed, preview_key=preview["preview_key"]).status_code == 409
    def conflict(*args, **kwargs):
        raise erp_catalog.ERPWriteConflictError("Outra edição foi salva")
    monkeypatch.setattr(erp_catalog, "_write_erp_products", conflict)
    assert post(client, "import", content, preview_key=preview["preview_key"]).status_code == 409


def test_sheet_selection_header_detection_and_leading_zeros(active_catalog):
    content = excel([["Instruções"], ["Preencha a segunda aba"]], second_rows=[["Título"], ["Referência", "Material"], ["0012", "Vidro"]])
    preview = read_technical_sheet(content, "dados.xlsx")
    assert preview["sheet"] == "Outra aba"
    assert len(preview["sheets"]) == 2
    assert preview["rows"][0]["row"] == 3
    assert preview["rows"][0]["code"] == "0012"
    padded = excel([["Código", "Especificações"], [12, "Vidro"]], number_format="0000")
    assert read_technical_sheet(padded, "dados.xlsx")["rows"][0]["code"] == "0012"
    with pytest.raises(ValueError, match="não existe"):
        read_technical_sheet(content, "dados.xlsx", "Ausente")


def test_catalog_only_product_can_receive_specs_without_new_unknown_product(active_catalog, monkeypatch):
    monkeypatch.setattr(catalog_service, "list_catalog_products", lambda: [{"Codigo": "8888", "Nome": "Produto local", "Categoria": "PENDENTE", "Especificacoes": "Antigo", "FotoBranco": "https://example.com/local.jpg"}])
    content = excel([["Código", "Especificações"], [8888, "Novo"], [9999, "Não cadastrar"]])
    preview = read_technical_sheet(content, "dados.xlsx")
    result = read_technical_sheet(content, "dados.xlsx", preview_key=preview["preview_key"])
    assert result["updated_count"] == 1
    index = erp_catalog.load_erp_index()
    assert len(index) == 4
    assert index["8888"]["Nome"] == "Produto local"
    assert index["8888"]["FotoBranco"] == "https://example.com/local.jpg"
    assert "9999" not in index


@pytest.mark.parametrize("rows", [[], [["Código", "Nome"], [1234, "Produto"]], [["Código", "Especificações", "Especificações"], [1234, "a", "b"]]])
def test_invalid_headers_rejected(active_catalog, rows):
    with pytest.raises(ValueError):
        read_technical_sheet(excel(rows), "dados.xlsx")


def test_invalid_files_limits_and_authentication(active_catalog, monkeypatch):
    client = TestClient(app)
    content = excel([["Código", "Especificações"], [1234, "12 W"]])
    assert post(client, "preview", b"broken").status_code == 400
    assert client.post(f"{BASE}/preview?filename=antigo.xls", content=content, headers={"Content-Type": MIME}).status_code == 400
    assert client.post(f"{BASE}/preview", content=content, headers={"Content-Type": "text/plain"}).status_code == 415
    monkeypatch.setenv("CATALOG_ERP_MAX_UPLOAD_BYTES", "100")
    assert post(client, "preview", content).status_code == 413
    monkeypatch.setenv("CATALOG_ERP_MAX_UPLOAD_BYTES", "1000000")
    monkeypatch.setenv("CATALOG_ERP_ADMIN_TOKEN", "test-secret")
    assert post(client, "preview", content).status_code == 401
    assert post(client, "import", content, preview_key="fake").status_code == 401


def test_compressed_content_limit_is_checked_before_parsing(active_catalog):
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        for i in range(1001):
            archive.writestr(str(i), "")
    with pytest.raises(ValueError, match="limite de conteúdo"):
        read_technical_sheet(content.getvalue(), "dados.xlsx")


def nitrolux_excel(values=None, *, header_row=3, changed_header=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Planilha1"
    sheet["C1"] = "CADASTRO DE PRODUTOS"
    sheet["Y2"], sheet["AD2"], sheet["AI2"] = "PRODUTO", "EMBALAGEM", "CAIXA MASTER"
    for index, header in enumerate(NITROLUX_HEADERS, 1):
        sheet.cell(header_row, index, header)
    if changed_header:
        sheet[changed_header[0]] = changed_header[1]
    for address, value in (values or {}).items():
        sheet[address] = value
    # The supplied file has formatting-only columns out to FB.
    sheet["FB4"].number_format = "0.00"
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_nitrolux_layout_groups_and_photo_errors(active_catalog):
    content = nitrolux_excel({
        "A4": "Categoria que deve ser preservada", "B4": 1234, "C4": "Outro nome",
        "D4": "8539.52.00", "E4": 0.065, "F4": "900100", "G4": "004696/2019",
        "H4": "Outro título", "I4": "Descrição do comércio", "J4": "palavra-chave",
        "K4": "Descrição comercial", "L4": "Frequência: 60 Hz", "M4": "12 W", "N4": "3000 K",
        "Y4": 6, "Z4": 11, "AC4": 0.037, "AD4": 0.043, "AE4": 12,
        "AH4": 7896688160487, "AI4": 2.88, "AJ4": 1.78, "AK4": 50, "AN4": 20,
        "AO4": 78966881604878, "AP4": "#VALUE!", "AQ4": "=1+1", "AR4": "#REF!",
        "AS4": 0.000396, "P4": "***", "B6": "0012", "L6": "Vidro",
    })
    client = TestClient(app)
    response = post(client, "preview", content)
    assert response.status_code == 200
    preview = response.json()
    assert preview["updated_count"] == 2
    assert preview["invalid_count"] == 0
    assert [row["row"] for row in preview["rows"]] == [4, 6]
    specs = preview["rows"][0]["specs"]
    for part in ("Código Inmetro: 004696/2019", "Potência (W): 12 W", "Produto - Largura (cm): 6",
                 "Produto - Peso líquido (kg): 0.037", "Embalagem - Peso bruto (kg): 0.043",
                 "Embalagem - Altura (cm): 12", "Caixa master - Peso bruto (kg): 2.88",
                 "Caixa master - Altura (cm): 20", "Código de barras EAN: 7896688160487",
                 "Código de barras DUN: 78966881604878", "Cubagem: 0.000396", "Frequência: 60 Hz"):
        assert part in specs
    assert specs.index("Potência") < specs.index("Frequência")
    for excluded in ("8539.52.00", "900100", "Outro nome", "Outro título", "palavra-chave",
                     "Descrição comercial", "#VALUE!", "#REF!", "***", "=1+1"):
        assert excluded not in specs
    assert post(client, "import", content, preview_key=preview["preview_key"]).status_code == 200
    saved = {p["Codigo"]: p for p in json.loads(active_catalog.read_text(encoding="utf-8"))["products"]}
    assert saved["1234"]["Nome"] == "Pendente"
    assert saved["1234"]["Categoria"] == "PENDENTE"
    assert saved["1234"]["Descricao"] == "Original"
    assert saved["1234"]["FotoBranco"] == "https://example.com/foto.jpg"


@pytest.mark.parametrize("column", ["B", "L", "M", "AS"])
def test_nitrolux_used_cell_errors_are_not_ignored(active_catalog, column):
    content = nitrolux_excel({"B4": 1234, "L4": "Vidro", f"{column}4": "=1+1"})
    preview = read_technical_sheet(content, "dados.xlsx")
    assert preview["invalid_count"] == 1
    assert any("fórmulas" in issue for issue in preview["rows"][0]["issues"])


def test_nitrolux_requires_expected_column_positions(active_catalog):
    content = nitrolux_excel({"B4": 1234, "L4": "Vidro"}, changed_header=("AD3", "Outro peso"))
    with pytest.raises(ValueError, match="coluna AD"):
        read_technical_sheet(content, "dados.xlsx")
    shifted = nitrolux_excel({"B5": 1234, "L5": "Vidro"}, header_row=4)
    with pytest.raises(ValueError, match="linha 3"):
        read_technical_sheet(shifted, "dados.xlsx")


def test_nitrolux_blank_technical_values_and_duplicate_codes(active_catalog):
    content = nitrolux_excel({"B4": 1234, "M4": "***", "AP4": "#VALUE!",
                             "B5": "0012", "L5": "Vidro", "B6": "0012", "L6": "Metal"})
    preview = read_technical_sheet(content, "dados.xlsx")
    assert preview["invalid_count"] == 3
    assert any("Nenhum dado técnico" in issue for issue in preview["rows"][0]["issues"])
    assert all(any("duplicado" in issue for issue in row["issues"]) for row in preview["rows"][1:])


def test_download_template_can_be_filled_without_rearranging_columns(active_catalog):
    template = Path(__file__).resolve().parents[1] / "frontend/public/modelo-dados-tecnicos.xlsx"
    workbook = load_workbook(template)
    sheet = workbook.active
    assert sheet["B3"].value == "CÓDIGO"
    assert sheet["L3"].value == "FICHA TÉCNICA"
    assert sheet["Y2"].value == "PRODUTO"
    assert sheet["AD2"].value == "EMBALAGEM"
    assert sheet["AI2"].value == "CAIXA MASTER"
    assert sheet["B4"].value is None
    sheet["B4"] = "0012"
    sheet["M4"] = "9 W"
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    preview = read_technical_sheet(output.getvalue(), "novo-cadastro.xlsx")
    assert preview["updated_count"] == 1
    assert preview["rows"][0]["row"] == 4
    assert preview["rows"][0]["code"] == "0012"
    assert preview["rows"][0]["specs"] == "Potência (W): 9 W"
