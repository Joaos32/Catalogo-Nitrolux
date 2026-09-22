import pytest

from catalog.spreadsheet import _extract_sheet_id, fetch_sheet


def test_extract_sheet_id():
    url = "https://docs.google.com/spreadsheets/d/ABC123xyz/edit?usp=sharing"
    assert _extract_sheet_id(url) == "ABC123xyz"


def test_extract_sheet_id_invalid():
    with pytest.raises(ValueError):
        _extract_sheet_id("https://example.com/not-a-sheet")


def test_fetch_sheet_parses_csv_without_pandas(monkeypatch):
    class Response:
        text = "Codigo,Nome\n3009,Pendente\n"

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr("catalog.spreadsheet.requests.get", lambda *args, **kwargs: Response())

    assert fetch_sheet("https://docs.google.com/spreadsheets/d/ABC123xyz/edit") == [
        {"Codigo": "3009", "Nome": "Pendente"}
    ]
