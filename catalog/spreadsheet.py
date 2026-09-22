"""Utilitarios para acessar dados de planilhas online.

Atualmente suporta Google Sheets publicas por exportacao em CSV.
"""

import csv
import re
import requests
from io import StringIO
from typing import Dict, List


def _extract_sheet_id(url: str) -> str:
    """Retorna o ID da planilha a partir de uma URL do Google Sheets."""
    # Exemplo: https://docs.google.com/spreadsheets/d/ID/edit...
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError("Invalid Google Sheets URL")
    return m.group(1)


def fetch_sheet(sheet_url: str) -> List[Dict[str, str]]:
    """Busca dados de uma Google Sheet publica e retorna registros.

    Parametros:
        sheet_url: URL completa da planilha.

    Excecoes:
        ValueError: se a URL nao for um link valido do Google Sheets.
        requests.HTTPError: se a busca do CSV falhar.
    """
    sheet_id = _extract_sheet_id(sheet_url)
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    try:
        resp = requests.get(export_url, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise ValueError("Google Sheets server timed out (10s)")
    except requests.exceptions.ConnectionError as e:
        raise ValueError(f"Network error connecting to Google Sheets: {e}")
    except requests.exceptions.HTTPError as e:
        raise ValueError(
            f"Google Sheets returned HTTP {resp.status_code}. "
            "The sheet may not be public or the URL may be invalid."
        )
    
    try:
        reader = csv.DictReader(StringIO(resp.text))
        if not reader.fieldnames:
            raise ValueError("Google Sheets returned an empty CSV")
        return [dict(row) for row in reader]
    except (csv.Error, UnicodeError) as e:
        raise ValueError(f"Failed to parse CSV from Google Sheets: {e}")
