"""Preview and merge technical specifications from Excel without replacing products."""

from __future__ import annotations

from collections import Counter
from contextlib import nullcontext
import hashlib
from io import BytesIO
import json
import re
import unicodedata
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from . import erp_catalog as erp
from .file_lock import document_lock
from .technical_sheet_layout import NITROLUX_HEADERS, NITROLUX_TECHNICAL_COLUMNS

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_ROWS = 10000
MAX_COLUMNS = 100
CODE_HEADERS = {"codigo", "cod", "codprod", "codproduto", "codigoproduto", "codigodoproduto", "sku", "referencia", "productcode"}
SPECS_HEADERS = {"especificacoes", "especificacao", "specs", "fichatecnica", "dadostecnicos", "caracteristicastecnicas"}
IDENTITY_HEADERS = {"nome", "produto", "descricao", "descricaodoproduto", "categoria", "marca", "urlfoto", "fotobranco", "fotoambient", "fotomedidas", "codepto", "codsec"}


class StaleTechnicalPreview(ValueError):
    pass


def _key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _nitrolux_header(values: list[str], row_number: int) -> bool:
    keys = [_key(value) for value in values]
    if len(keys) < 12 or keys[0] != "categoria" or keys[1] != "codigo" or keys[11] != "fichatecnica":
        return False
    if row_number != 3:
        raise ValueError("No modelo Nitrolux, mantenha os cabeçalhos na linha 3 e os produtos a partir da linha 4.")
    for index, expected in enumerate(NITROLUX_HEADERS):
        if index >= len(keys) or keys[index] != _key(expected):
            raise ValueError(f"Modelo Nitrolux: mantenha a coluna {get_column_letter(index + 1)} com o cabeçalho {expected} na linha 3.")
    return True


def _read_rows(content: bytes, filename: str, sheet_name: str | None) -> tuple[list[str], str, list[dict]]:
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("Selecione um arquivo Excel .xlsx. Para arquivos .xls, salve uma cópia como .xlsx.")
    if not content:
        raise ValueError("O arquivo está vazio.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("A planilha deve ter no máximo 4 MB.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(item.file_size for item in entries) > 32 * 1024 * 1024:
                raise ValueError("A planilha excede o limite de conteúdo. Divida o arquivo em planilhas menores.")
    except BadZipFile as exc:
        raise ValueError("Arquivo Excel inválido. Abra o arquivo no Excel e salve novamente como .xlsx.") from exc
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
    except Exception as exc:
        raise ValueError("Não foi possível abrir a planilha. Verifique se o arquivo .xlsx está íntegro e sem senha.") from exc
    try:
        sheets = workbook.sheetnames
        if len(sheets) > 20:
            raise ValueError("Use uma pasta de trabalho com no máximo 20 abas.")
        selected = sheet_name or sheets[0]
        if sheet_name is None:
            for candidate in workbook:
                candidate.reset_dimensions()
                if any(_key(cell.value) in CODE_HEADERS for cells in candidate.iter_rows(max_row=20, max_col=MAX_COLUMNS) for cell in cells):
                    selected = candidate.title
                    break
        if selected not in sheets:
            raise ValueError("A aba selecionada não existe nesta planilha.")
        sheet = workbook[selected]
        # Do not trust worksheet dimensions: some generators report A1 for full sheets.
        sheet.reset_dimensions()
        header = None
        nitrolux = False
        rows = []
        for row_number, cells in enumerate(sheet.iter_rows(), start=1):
            if row_number > MAX_ROWS + 20:
                raise ValueError("Use no máximo 10.000 linhas de produtos por aba.")
            # Excel keeps empty styled cells far beyond the actual table.
            last_value = next((i + 1 for i in range(len(cells) - 1, -1, -1) if cells[i].value is not None), 0)
            cells = cells[:last_value]
            if len(cells) > MAX_COLUMNS:
                raise ValueError("Use no máximo 100 colunas por aba.")
            values = [_text(cell.value) for cell in cells]
            if any(len(value) > 8000 for value in values):
                raise ValueError(f"Linha {row_number}: uma célula excede 8.000 caracteres.")
            if header is None:
                keys = [_key(value) for value in values]
                if any(key in CODE_HEADERS for key in keys):
                    nitrolux = _nitrolux_header(values, row_number)
                    populated = [key for key in keys if key]
                    if not nitrolux and (len(populated) != len(set(populated)) or sum(key in CODE_HEADERS for key in keys) != 1):
                        raise ValueError("Use cabeçalhos únicos e apenas uma coluna de código do produto.")
                    header = values
                    code_column = 1 if nitrolux else next(i for i, key in enumerate(keys) if key in CODE_HEADERS)
                    technical_columns = list(NITROLUX_TECHNICAL_COLUMNS) if nitrolux else [i for i, key in enumerate(keys) if key and key not in CODE_HEADERS | IDENTITY_HEADERS]
                    if not technical_columns:
                        raise ValueError("Inclua uma coluna Especificações ou colunas técnicas, como Potência e Tensão.")
                elif row_number >= 20:
                    raise ValueError("Não foi encontrada uma coluna Código, SKU ou Referência nas primeiras 20 linhas.")
                continue
            if not any(values):
                continue
            if len(rows) >= MAX_ROWS:
                raise ValueError("Use no máximo 10.000 linhas de produtos por aba.")
            padded = values + [""] * max(0, len(header) - len(values))
            code = padded[code_column]
            code_cell = cells[code_column] if code_column < len(cells) else None
            if code_cell is not None and isinstance(code_cell.value, (int, float)) and re.fullmatch(r"0+", code_cell.number_format or ""):
                code = code.zfill(len(code_cell.number_format))
            issues = []
            if not re.fullmatch(r"\d{1,12}", code):
                issues.append("Informe um código numérico válido, com até 12 dígitos.")
            used_columns = [code_column, *technical_columns]
            if any(i < len(cells) and cells[i].data_type in {"f", "e"} for i in used_columns):
                issues.append("Substitua fórmulas e erros por valores antes de importar.")
            if any(value and (i >= len(header) or not header[i]) for i, value in enumerate(values)):
                issues.append("Há dados em uma coluna sem cabeçalho.")
            if nitrolux:
                parts = [padded[i] if label is None else f"{label}: {padded[i]}"
                         for i, label in NITROLUX_TECHNICAL_COLUMNS.items()
                         if padded[i] and padded[i].strip() not in {"***", "-", "--"}]
            else:
                parts = [padded[i] if _key(header[i]) in SPECS_HEADERS else f"{header[i]}: {padded[i]}" for i in technical_columns if padded[i]]
            specs = " | ".join(parts)
            if not specs:
                issues.append("Nenhum dado técnico preenchido.")
            if len(specs) > 16000:
                issues.append("Os dados técnicos excedem 16.000 caracteres.")
            rows.append({"row": row_number, "code": code, "specs": specs, "issues": issues})
        if header is None:
            raise ValueError("Inclua uma linha de cabeçalho com Código e Especificações ou outras colunas técnicas.")
        if not rows:
            raise ValueError("A aba selecionada não contém linhas de produtos.")
        return sheets, selected, rows
    finally:
        workbook.close()


def _preview(rows: list[dict], products: dict, sheets: list[str], selected: str, filename: str) -> dict:
    counts = Counter(row["code"] for row in rows if row["code"])
    result_rows = []
    for row in rows:
        product = products.get(row["code"])
        issues = list(row["issues"])
        if counts[row["code"]] > 1:
            issues.append("Código duplicado na aba. Mantenha uma linha por produto.")
        if not product:
            issues.append("Código não encontrado no catálogo.")
        previous = _text((product or {}).get("Especificacoes"))
        status = "invalid" if issues else "unchanged" if previous == row["specs"] else "updated"
        result_rows.append({**row, "issues": issues, "name": _text((product or {}).get("Nome")), "previous_specs": previous, "status": status})
    fingerprint = hashlib.sha256(json.dumps(result_rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {
        "filename": filename, "sheets": sheets, "sheet": selected, "preview_key": fingerprint,
        "total_rows": len(result_rows),
        **{f"{status}_count": sum(row["status"] == status for row in result_rows) for status in ("updated", "unchanged", "invalid")},
        "rows": result_rows,
    }


def read_technical_sheet(content: bytes, filename: str, sheet_name: str | None = None, *, preview_key: str | None = None) -> dict:
    sheets, selected, rows = _read_rows(content, filename, sheet_name)
    from .services.catalog_service import list_catalog_products

    catalog = {str(product.get("Codigo")): product for product in list_catalog_products()}
    with erp._ERP_MUTATION_LOCK, (nullcontext() if erp.storage_uri() else document_lock(erp._resolve_json_target_path())):
        payload, etag, missing, _, _ = erp._load_active_erp_snapshot(fresh=True)
        index = erp._build_index(payload) if payload else {}
        products = {**catalog, **index}
        preview = _preview(rows, products, sheets, selected, filename)
        if preview_key is None:
            return preview
        if not preview_key or preview_key != preview["preview_key"]:
            raise StaleTechnicalPreview("O catálogo ou a planilha mudou. Leia a planilha novamente e confira a nova prévia.")
        if not preview["updated_count"]:
            raise ValueError("Não há dados técnicos válidos para atualizar.")
        for row in preview["rows"]:
            if row["status"] == "updated":
                index[row["code"]] = {**products[row["code"]], "Especificacoes": row["specs"]}
        result = erp._write_erp_products(list(index.values()), base_payload=payload, expected_remote_etag=etag, expected_remote_missing=missing)
        return {**result, "updated_count": preview["updated_count"], "unchanged_count": preview["unchanged_count"], "invalid_count": preview["invalid_count"]}
