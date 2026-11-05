"""Build the public blank template using the recurring Nitrolux column layout."""

from pathlib import Path
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from catalog.technical_sheet_layout import NITROLUX_HEADERS  # noqa: E402


def main() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Planilha1"
    sheet["C1"] = "CADASTRO DE PRODUTOS"
    sheet["C1"].font = Font(size=16, bold=True, color="1E4070")
    for address, end, label in (("Y2", "AC2", "PRODUTO"), ("AD2", "AH2", "EMBALAGEM"), ("AI2", "AO2", "CAIXA MASTER")):
        sheet.merge_cells(f"{address}:{end}")
        sheet[address] = label
        sheet[address].font = Font(bold=True, color="1E4070")
    for index, header in enumerate(NITROLUX_HEADERS, 1):
        cell = sheet.cell(3, index, header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2256A5")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.column_dimensions[get_column_letter(index)].width = 20
    sheet.column_dimensions["L"].width = 55
    sheet.column_dimensions["B"].number_format = "@"
    sheet["B4"].number_format = "@"
    sheet.row_dimensions[3].height = 44
    sheet.freeze_panes = "C4"
    sheet.auto_filter.ref = "A3:AS3"
    target = ROOT / "frontend/public/modelo-dados-tecnicos.xlsx"
    workbook.save(target)
    workbook.close()
    print(target)


if __name__ == "__main__":
    main()
