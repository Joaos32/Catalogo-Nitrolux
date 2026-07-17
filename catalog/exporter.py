"""Geracao de exportacoes do catalogo em multiplos formatos."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
import textwrap
from typing import Any, Dict, Iterable, List, Sequence
import unicodedata
from urllib.parse import parse_qs, unquote, urlparse
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests

from . import onedrive


SUPPORTED_EXPORT_FORMATS = {"csv", "json", "xlsx", "xls", "pdf", "ficha", "zip"}
PREFERRED_COLUMNS = (
    "Codigo",
    "Nome",
    "Categoria",
    "Descricao",
    "Especificacoes",
    "URLFoto",
    "FotoBranco",
    "FotoAmbient",
    "FotoMedidas",
    "CODPROD",
    "CODAUXILIAR",
    "NBM",
    "PERCIPIVENDA",
)
PHOTO_FIELDS: tuple[tuple[str, str], ...] = (
    ("Capa", "URLFoto"),
    ("Fundo branco", "FotoBranco"),
    ("Ambientada", "FotoAmbient"),
    ("Medidas", "FotoMedidas"),
)
PAGE_SIZE = (1240, 1754)
PAGE_MARGIN = 80
BASE_DIR = Path(__file__).resolve().parents[1]
BRAND_BANNER_CANDIDATES = (
    BASE_DIR / "frontend" / "legacy" / "assets" / "azul-nitro.jpg",
    BASE_DIR / "Azul nitro.jpg",
)
DISPLAY_LABEL_MAP = {
    "Codigo": "Codigo",
    "Nome": "Produto",
    "Categoria": "Categoria",
    "Descricao": "Descricao",
    "Especificacoes": "Especificacoes",
    "CODPROD": "Codigo",
    "CODAUXILIAR": "Codigo de barras",
    "NBM": "NCM",
    "PERCIPIVENDA": "IPI",
    "EMBALAGEM": "Embalagem",
    "UNIDADE": "Unidade",
    "PESOLIQ": "Peso liquido",
    "PESOBRUTO": "Peso bruto",
    "CODEPTO": "Departamento",
    "CODSEC": "Secao",
}
FEATURED_ATTRIBUTE_KEYS = (
    "CODPROD",
    "CODAUXILIAR",
    "NBM",
    "PERCIPIVENDA",
    "EMBALAGEM",
    "UNIDADE",
    "PESOLIQ",
    "PESOBRUTO",
    "CODEPTO",
    "CODSEC",
)


def _normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    without_accents = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_accents.lower().strip()


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _slugify(value: str, fallback: str = "catalogo") -> str:
    normalized = _normalize_text(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or fallback


def _load_products() -> List[Dict[str, Any]]:
    return onedrive.list_local_products()


def _max_remote_image_bytes() -> int:
    raw_value = os.getenv("CATALOG_EXPORT_MAX_REMOTE_IMAGE_BYTES", "").strip()
    if not raw_value:
        return 5 * 1024 * 1024
    try:
        parsed = int(raw_value)
    except ValueError:
        return 5 * 1024 * 1024
    return parsed if parsed > 0 else 5 * 1024 * 1024


def _is_public_ip_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _is_permitted_remote_image_url(url: str) -> bool:
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
        return False

    if _is_public_ip_address(hostname):
        return True

    try:
        resolved = socket.getaddrinfo(
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return False
    except OSError:
        return False

    addresses = {item[4][0] for item in resolved if item and len(item) >= 5 and item[4]}
    if not addresses:
        return False
    return all(_is_public_ip_address(address) for address in addresses)


def _download_remote_image_bytes(url: str) -> tuple[bytes | None, str]:
    if not _is_permitted_remote_image_url(url):
        return None, ""

    max_bytes = _max_remote_image_bytes()

    try:
        response = requests.get(
            url,
            timeout=8,
            stream=True,
            allow_redirects=False,
            headers={"Accept": "image/*"},
        )
        response.raise_for_status()
    except Exception:
        return None, ""

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and not content_type.startswith("image/"):
        response.close()
        return None, ""

    declared_length = response.headers.get("content-length", "").strip()
    if declared_length:
        try:
            if int(declared_length) > max_bytes:
                response.close()
                return None, ""
        except ValueError:
            pass

    payload = bytearray()
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            payload.extend(chunk)
            if len(payload) > max_bytes:
                return None, ""
    finally:
        response.close()

    extension = Path(urlparse(url).path).suffix.lower()
    if not extension and content_type:
        extension = mimetypes.guess_extension(content_type) or ""
    return bytes(payload), extension


def _filter_products(
    products: Sequence[Dict[str, Any]],
    *,
    query: str = "",
    category: str = "",
    code: str = "",
    brand: str = "",
) -> List[Dict[str, Any]]:
    normalized_query = _normalize_text(query)
    normalized_category = _normalize_text(category)
    normalized_code = str(code or "").strip()
    normalized_brand = _normalize_text(brand)
    filtered: List[Dict[str, Any]] = []

    for product in products:
        product_code = _stringify(product.get("Codigo"))
        if normalized_code and product_code != normalized_code:
            continue

        if normalized_brand:
            product_brand_code = _stringify(product.get("CODMARCA"))
            product_brand = "pienza" if product_brand_code == "2" else "nitrolux"
            if product_brand != normalized_brand:
                continue

        if normalized_category and normalized_category != "todas":
            product_category = _normalize_text(product.get("Categoria"))
            if product_category != normalized_category:
                continue

        if normalized_query:
            blob = _normalize_text(
                " ".join(
                    (
                        _stringify(product.get("Codigo")),
                        _stringify(product.get("Nome")),
                        _stringify(product.get("Descricao")),
                        _stringify(product.get("Categoria")),
                    )
                )
            )
            if normalized_query not in blob:
                continue

        filtered.append(dict(product))

    return filtered


def _ordered_columns(products: Sequence[Dict[str, Any]]) -> List[str]:
    columns = {key for product in products for key in product.keys()}
    ordered = [column for column in PREFERRED_COLUMNS if column in columns]
    extra = sorted((column for column in columns if column not in ordered), key=_normalize_text)
    return ordered + extra


def _tabular_rows(products: Sequence[Dict[str, Any]]) -> tuple[List[str], List[Dict[str, str]]]:
    columns = _ordered_columns(products)
    rows: List[Dict[str, str]] = []
    for product in products:
        rows.append({column: _stringify(product.get(column)) for column in columns})
    return columns, rows


def _build_csv_bytes(products: Sequence[Dict[str, Any]]) -> bytes:
    columns, rows = _tabular_rows(products)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def _build_json_bytes(
    products: Sequence[Dict[str, Any]],
    *,
    query: str,
    category: str,
    code: str,
) -> bytes:
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "query": query,
            "category": category,
            "code": code,
        },
        "products": list(products),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _build_xlsx_bytes(products: Sequence[Dict[str, Any]]) -> bytes:
    columns, rows = _tabular_rows(products)
    dataframe = pd.DataFrame(rows, columns=columns)
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Produtos", index=False)
        worksheet = writer.sheets["Produtos"]
        worksheet.freeze_panes = "A2"
        for index, column in enumerate(dataframe.columns, start=1):
            values = [column, *dataframe[column].astype(str).tolist()]
            width = min(max((len(value) for value in values), default=10) + 2, 60)
            worksheet.column_dimensions[worksheet.cell(row=1, column=index).column_letter].width = width

    return output.getvalue()


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_names = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=font)
    return right - left, bottom - top


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    if not text:
        return [""]

    wrapped_lines: List[str] = []
    for paragraph in str(text).splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            candidate = word if not current else f"{current} {word}"
            width, _ = _measure_text(draw, candidate, font)
            if width <= max_width:
                current = candidate
                continue
            if current:
                wrapped_lines.append(current)
            current = word
        wrapped_lines.append(current or "")
    return wrapped_lines or [""]


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    font: ImageFont.ImageFont,
    x: int,
    y: int,
    max_width: int,
    fill: str = "#102845",
    line_spacing: int = 8,
) -> int:
    lines = _wrap_text(draw, text, font, max_width)
    _, line_height = _measure_text(draw, "Ag", font)
    for line in lines:
        draw.text((x, y), line, fill=fill, font=font)
        y += line_height + line_spacing
    return y


def _new_pdf_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    page = Image.new("RGB", PAGE_SIZE, "#f3f6fb")
    return page, ImageDraw.Draw(page)


def _display_label(key: str) -> str:
    if key in DISPLAY_LABEL_MAP:
        return DISPLAY_LABEL_MAP[key]
    cleaned = re.sub(r"[_\-]+", " ", key or "").strip()
    return cleaned.title() if cleaned else "Campo"


def _load_brand_banner() -> Image.Image | None:
    for path in BRAND_BANNER_CANDIDATES:
        if not path.is_file():
            continue
        try:
            with Image.open(path) as image:
                if image.mode != "RGB":
                    image = image.convert("RGB")
                return image.copy()
        except Exception:
            continue
    return None


def _rounded_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str | None = None,
    radius: int = 28,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _paste_fitted_image(
    page: Image.Image,
    image: Image.Image,
    box: tuple[int, int, int, int],
    *,
    background: str = "white",
) -> None:
    left, top, right, bottom = box
    available = (max(1, right - left), max(1, bottom - top))
    fitted = ImageOps.contain(image, available)
    canvas = Image.new("RGB", available, background)
    offset = ((available[0] - fitted.width) // 2, (available[1] - fitted.height) // 2)
    canvas.paste(fitted, offset)
    page.paste(canvas, (left, top))


def _paste_cover_image(
    page: Image.Image,
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    available = (max(1, right - left), max(1, bottom - top))
    fitted = ImageOps.fit(image, available, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    page.paste(fitted, (left, top))


def _paste_cutout_image(
    page: Image.Image,
    image: Image.Image,
    box: tuple[int, int, int, int],
    *,
    background_threshold: int = 238,
) -> None:
    left, top, right, bottom = box
    available = (max(1, right - left), max(1, bottom - top))
    fitted = ImageOps.contain(image.convert("RGB"), available)
    rgba = fitted.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if red >= background_threshold and green >= background_threshold and blue >= background_threshold:
                pixels[x, y] = (red, green, blue, 0)
            else:
                pixels[x, y] = (red, green, blue, alpha)
    offset = (left + (available[0] - fitted.width) // 2, top + (available[1] - fitted.height) // 2)
    page.paste(rgba, offset, rgba)


def _strip_power_unit(value: str) -> str:
    normalized = _stringify(value).upper()
    match = re.search(r"\d+(?:[.,]\d+)?", normalized)
    return match.group(0).replace(",", ".") if match else normalized


def _field_lookup(product: Dict[str, Any]) -> Dict[str, str]:
    return {re.sub(r"[^a-z0-9]+", "", _normalize_text(key)): _stringify(value) for key, value in product.items()}


def _parse_specs_pairs(specs: str) -> List[tuple[str, str]]:
    pairs: List[tuple[str, str]] = []
    for part in re.split(r"[|\n;]+", str(specs or "")):
        clean = part.strip()
        if not clean:
            continue
        match = re.match(r"^([^:=-]+)\s*[:=-]\s*(.+)$", clean)
        if not match:
            continue
        label = match.group(1).strip()
        value = match.group(2).strip()
        if label and value:
            pairs.append((label, value))
    return pairs


def _normalize_lookup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize_text(value))


def _spec_lookup(product: Dict[str, Any], specs: str) -> Dict[str, str]:
    lookup = _field_lookup(product)
    for label, value in _parse_specs_pairs(specs):
        lookup.setdefault(_normalize_lookup_key(label), value)
    return lookup


def _pick_spec_value(lookup: Dict[str, str], aliases: Sequence[str]) -> str:
    for alias in aliases:
        normalized_alias = _normalize_lookup_key(alias)
        if lookup.get(normalized_alias):
            return lookup[normalized_alias]
    for alias in aliases:
        normalized_alias = _normalize_lookup_key(alias)
        if len(normalized_alias) <= 3:
            continue
        for key, value in lookup.items():
            if value and normalized_alias in key:
                return value
    return ""


def _regex_value(text: str, patterns: Sequence[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip().upper()
    return ""


def _technical_sheet_rows(product: Dict[str, Any], specs: str) -> List[tuple[str, str]]:
    lookup = _spec_lookup(product, specs)
    search_text = " | ".join(
        _stringify(value)
        for value in (
            product.get("Nome"),
            product.get("Descricao"),
            product.get("Categoria"),
            specs,
        )
        if _stringify(value)
    )

    rows = [
        ("Potencia", _pick_spec_value(lookup, ("potencia", "potencia(w)", "watt", "watts")) or _regex_value(search_text, (r"\b\d+(?:[.,]\d+)?\s*W(?:/M)?\b",))),
        ("Tensao", _pick_spec_value(lookup, ("tensao", "tensao(v)", "voltagem", "voltagem(v)")) or _regex_value(search_text, (r"\b(?:AC|DC)?\s*\d+(?:[.,]\d+)?(?:\s*[-/]\s*\d+(?:[.,]\d+)?)?\s*V\b", r"\bBIVOLT\b"))),
        ("Temperatura de cor", _pick_spec_value(lookup, ("temperatura de cor", "temp. cor(k)", "temp cor", "cct", "kelvin")) or _regex_value(search_text, (r"\b\d{4,5}\s*K\b",))),
        ("Fluxo luminoso", _pick_spec_value(lookup, ("fluxo luminoso", "lumens", "lumen")) or _regex_value(search_text, (r"\b\d+(?:[.,]\d+)?\s*LM\b",))),
        ("IRC", _pick_spec_value(lookup, ("irc", "cri")) or _regex_value(search_text, (r"\b(?:IRC|CRI)\s*[=:]?\s*[><=]*\s*\d{2,3}\b",))),
        ("Fator de potencia", _pick_spec_value(lookup, ("fator de potencia", "fp")) or _regex_value(search_text, (r"\b(?:FP|FATOR\s+DE\s+POTENCIA)\s*[=:]?\s*[><=]*\s*\d+(?:[.,]\d+)?\b",))),
        ("Angulo de abertura", _pick_spec_value(lookup, ("angulo de abertura", "angulo", "abertura"))),
        ("Grau de protecao", _pick_spec_value(lookup, ("indice de protecao", "grau de protecao", "ip")) or _regex_value(search_text, (r"\bIP\s*\d{2}\b",))),
        ("Material", _pick_spec_value(lookup, ("material", "materia prima"))),
        ("Acabamento", _pick_spec_value(lookup, ("acabamento", "cor", "cores disponiveis"))),
        ("Medidas", _pick_spec_value(lookup, ("dimensoes", "dimensao", "medidas")) or _regex_value(search_text, (r"(?:Ø\s*)?\d+(?:[.,]\d+)?(?:\s*[xX]\s*(?:Ø\s*)?\d+(?:[.,]\d+)?){1,3}\s*MM\b",))),
        ("Peso", _pick_spec_value(lookup, ("peso", "peso liquido", "pesoliq", "peso bruto", "pesobruto"))),
        ("Garantia", _pick_spec_value(lookup, ("garantia",)) or _regex_value(search_text, (r"\b\d+\s*(?:ANO|ANOS|MES|MESES)\b",))),
    ]

    return [(label, value) for label, value in rows if _stringify(value)]


def _draw_dotted_row(
    draw: ImageDraw.ImageDraw,
    *,
    label: str,
    value: str,
    x: int,
    y: int,
    width: int,
    label_font: ImageFont.ImageFont,
    value_font: ImageFont.ImageFont,
) -> int:
    label_width, label_height = _measure_text(draw, label, label_font)
    value_width, _ = _measure_text(draw, value, value_font)
    value_x = x + width - value_width
    line_y = y + label_height - 6
    dot_start = x + label_width + 14
    dot_end = value_x - 14
    draw.text((x, y), label, fill="#171717", font=label_font)
    if dot_end > dot_start:
        for dot_x in range(dot_start, dot_end, 9):
            draw.line((dot_x, line_y, min(dot_x + 4, dot_end), line_y), fill="#b6b1ab", width=1)
    draw.text((value_x, y), value, fill="#171717", font=value_font)
    return y + label_height + 18


def _fit_title_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, *, bold: bool = True) -> ImageFont.ImageFont:
    size = start_size
    while size >= 24:
        font = _load_font(size, bold=bold)
        if _measure_text(draw, text, font)[0] <= max_width:
            return font
        size -= 2
    return _load_font(24, bold=bold)


def _draw_metric_card(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    label_font: ImageFont.ImageFont,
    value_font: ImageFont.ImageFont,
) -> None:
    _rounded_box(draw, box, fill="#ffffff", outline="#d7e7ff", radius=22)
    left, top, right, bottom = box
    draw.text((left + 18, top + 16), label.upper(), fill="#5b7caa", font=label_font)
    y = top + 50
    max_width = right - left - 36
    _draw_wrapped_text(draw, text=value or "-", font=value_font, x=left + 18, y=y, max_width=max_width, fill="#123874", line_spacing=6)


def _draw_attribute_grid(
    draw: ImageDraw.ImageDraw,
    *,
    attributes: Sequence[tuple[str, str]],
    box: tuple[int, int, int, int],
    columns: int,
    section_font: ImageFont.ImageFont,
    label_font: ImageFont.ImageFont,
    value_font: ImageFont.ImageFont,
    title: str,
) -> int:
    _rounded_box(draw, box, fill="#ffffff", outline="#d7e7ff", radius=30)
    left, top, right, bottom = box
    draw.text((left + 24, top + 20), title, fill="#123874", font=section_font)
    header_y = top + 60
    cell_gap = 16
    usable_width = right - left - 48
    cell_width = (usable_width - (columns - 1) * cell_gap) // columns
    cell_height = 92
    row_y = header_y
    used = 0

    for index, (label, value) in enumerate(attributes):
        row = index // columns
        col = index % columns
        cell_left = left + 24 + col * (cell_width + cell_gap)
        cell_top = header_y + row * (cell_height + 12)
        cell_bottom = cell_top + cell_height
        if cell_bottom > bottom - 20:
            break

        draw.rounded_rectangle(
            (cell_left, cell_top, cell_left + cell_width, cell_bottom),
            radius=18,
            fill="#f7fbff",
            outline="#e4eefc",
            width=2,
        )
        draw.text((cell_left + 16, cell_top + 14), _display_label(label).upper(), fill="#5b7caa", font=label_font)
        _draw_wrapped_text(
            draw,
            text=value or "-",
            font=value_font,
            x=cell_left + 16,
            y=cell_top + 42,
            max_width=cell_width - 32,
            fill="#153662",
            line_spacing=6,
        )
        row_y = cell_bottom
        used = index + 1

    return used


def _product_attributes(product: Dict[str, Any]) -> List[tuple[str, str]]:
    base_keys = {"Codigo", "Nome", "Categoria", "Descricao", "Especificacoes"}
    attributes: List[tuple[str, str]] = []

    for key in FEATURED_ATTRIBUTE_KEYS:
        value = _stringify(product.get(key))
        if value:
            attributes.append((key, value))

    extra_keys = sorted((key for key in product.keys() if key not in base_keys and key not in FEATURED_ATTRIBUTE_KEYS), key=_normalize_text)
    for key in extra_keys:
        value = _stringify(product.get(key))
        if value:
            attributes.append((key, value))

    return attributes


def _photo_references(product: Dict[str, Any]) -> List[Dict[str, str]]:
    code = _stringify(product.get("Codigo"))
    references: List[Dict[str, str]] = []
    seen: set[str] = set()

    for label, key in PHOTO_FIELDS:
        url = _stringify(product.get(key))
        if url and url not in seen:
            references.append({"label": label, "url": url})
            seen.add(url)

    if code:
        try:
            for index, image in enumerate(onedrive.find_local_images_for_code(code), start=1):
                url = _stringify(image.get("url"))
                if not url or url in seen:
                    continue
                label = _stringify(image.get("name")) or f"Imagem {index}"
                references.append({"label": label, "url": url})
                seen.add(url)
        except Exception:
            pass

    return references


def _resolve_photo_bytes(url: str) -> tuple[bytes | None, str]:
    parsed = urlparse(url or "")
    path_value = parse_qs(parsed.query).get("path", [""])[0]

    if parsed.path.endswith("/catalog/local/asset") and path_value:
        asset_path = onedrive.resolve_local_asset_path(unquote(path_value))
        if not asset_path:
            return None, ""
        local_path = Path(asset_path)
        try:
            return local_path.read_bytes(), local_path.suffix.lower()
        except OSError:
            return None, local_path.suffix.lower()

    if parsed.scheme not in {"http", "https"}:
        return None, ""

    return _download_remote_image_bytes(url)


def _open_image_for_export(url: str) -> Image.Image | None:
    payload, _ = _resolve_photo_bytes(url)
    if not payload:
        return None

    try:
        with Image.open(BytesIO(payload)) as image:
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.split()[-1])
                image = background
            return image.copy()
    except Exception:
        return None


def _build_product_pdf_pages(product: Dict[str, Any]) -> List[Image.Image]:
    brand_font = _load_font(46, bold=True)
    document_font = _load_font(32, bold=True)
    title_font = _load_font(40, bold=True)
    section_font = _load_font(24, bold=True)
    body_font = _load_font(20)
    small_font = _load_font(16)
    tiny_font = _load_font(12, bold=True)
    table_font = _load_font(17)
    table_value_font = _load_font(17, bold=True)
    footer_font = _load_font(15)
    code = _stringify(product.get("Codigo"))
    name = _stringify(product.get("Nome")) or f"Produto {code}"
    category = _stringify(product.get("Categoria")) or "PRODUTO"
    description = _stringify(product.get("Descricao")) or _stringify(product.get("Categoria")) or "Produto para catálogo técnico."
    specs = _stringify(product.get("Especificacoes")) or "Sem especificações cadastradas."
    brand_code = _stringify(product.get("CODMARCA"))
    brand_name = "PIENZA" if brand_code in {"2", "2.0"} else "NITROLUX"
    brand_site = "pienza.com.br" if brand_name == "PIENZA" else "nitrolux.com.br"
    accent = "#b8892f" if brand_name == "PIENZA" else "#0f5da8"
    dark = "#172234"
    muted = "#667085"
    border = "#d9e2ec"
    footer_text = f"{brand_site} | Ficha técnica gerada pelo Catálogo"

    photo_map: Dict[str, Image.Image] = {}
    for label, key in PHOTO_FIELDS:
        url = _stringify(product.get(key))
        if url:
            image = _open_image_for_export(url)
            if image is not None:
                photo_map[key] = image
    if "URLFoto" not in photo_map:
        for reference in _photo_references(product):
            image = _open_image_for_export(reference["url"])
            if image is not None:
                photo_map["URLFoto"] = image
                break

    product_image = photo_map.get("FotoBranco") or photo_map.get("URLFoto") or photo_map.get("FotoAmbient")
    ambient_image = photo_map.get("FotoAmbient") or photo_map.get("URLFoto") or photo_map.get("FotoBranco")
    measures_image = photo_map.get("FotoMedidas")
    technical_rows = _technical_sheet_rows(product, specs)

    quick_lookup = _spec_lookup(product, specs)
    power = _pick_spec_value(quick_lookup, ("potencia", "potencia(w)", "watt", "watts")) or _regex_value(specs, (r"\b\d+(?:[.,]\d+)?\s*W(?:/M)?\b",))
    voltage = _pick_spec_value(quick_lookup, ("tensao", "tensao(v)", "voltagem")) or _regex_value(specs, (r"\b(?:AC|DC)?\s*\d+(?:[.,]\d+)?(?:\s*[-/]\s*\d+(?:[.,]\d+)?)?\s*V\b", r"\bBIVOLT\b"))
    protection = _pick_spec_value(quick_lookup, ("indice de protecao", "grau de protecao", "ip")) or _regex_value(specs, (r"\bIP\s*\d{2}\b",))
    base = _pick_spec_value(quick_lookup, ("base", "soquete", "bocal")) or _regex_value(specs, (r"\b(?:E27/E40|E27/40|E27|E14|E40|GU10|G9X\d+|G9|G13)\b",))
    color_temp = _pick_spec_value(quick_lookup, ("temperatura de cor", "temp. cor(k)", "cct")) or _regex_value(specs, (r"\b\d{4,5}\s*K\b",))
    finish = _pick_spec_value(quick_lookup, ("acabamento", "cor", "cores disponiveis"))
    material = _pick_spec_value(quick_lookup, ("material", "materia prima"))
    dimensions = _pick_spec_value(quick_lookup, ("dimensoes", "dimensao", "medidas"))

    highlight_candidates = [
        ("Potência", power),
        ("Tensão", voltage),
        ("Temperatura", color_temp),
        ("Proteção", protection),
        ("Base", base),
        ("Material", material),
        ("Acabamento", finish),
        ("Medidas", dimensions),
        ("Embalagem", _stringify(product.get("EMBALAGEM"))),
        ("NCM", _stringify(product.get("NBM"))),
        ("Categoria", category),
        ("Código", code),
    ]
    highlights: List[tuple[str, str]] = []
    seen_highlights: set[str] = set()
    for label, value in highlight_candidates:
        value = _stringify(value)
        if not value:
            continue
        normalized_label = _normalize_lookup_key(label)
        if normalized_label in seen_highlights:
            continue
        highlights.append((label, value))
        seen_highlights.add(normalized_label)
        if len(highlights) == 4:
            break

    enriched_rows = list(technical_rows)
    seen_rows = {_normalize_lookup_key(label) for label, _ in enriched_rows}
    for label, value in _parse_specs_pairs(specs):
        normalized_label = _normalize_lookup_key(label)
        if normalized_label in {"codigo", "cod"} or normalized_label in seen_rows:
            continue
        enriched_rows.append((label, value))
        seen_rows.add(normalized_label)
    for label, key in (
        ("Código de barras", "CODAUXILIAR"),
        ("NCM", "NBM"),
        ("IPI", "PERCIPIVENDA"),
        ("Categoria", "Categoria"),
    ):
        value = _stringify(product.get(key))
        normalized_label = _normalize_lookup_key(label)
        if value and normalized_label not in seen_rows:
            enriched_rows.append((label, value))
            seen_rows.add(normalized_label)

    pages: List[Image.Image] = []
    page = Image.new("RGB", PAGE_SIZE, "#f5f7fa")
    draw = ImageDraw.Draw(page)

    draw.rectangle((0, 0, PAGE_SIZE[0], 18), fill=accent)
    draw.rectangle((0, 18, PAGE_SIZE[0], 152), fill="#ffffff")
    draw.text((72, 58), brand_name, fill=dark, font=brand_font)
    draw.text((760, 52), "FICHA TÉCNICA", fill=dark, font=document_font)
    draw.text((762, 94), f"Código {code or '-'}", fill=muted, font=body_font)
    draw.line((72, 152, 1168, 152), fill=border, width=2)

    left_x = 72
    right_x = 660
    top_y = 194

    _rounded_box(draw, (left_x, top_y, 600, 760), fill="#ffffff", outline=border, radius=24, width=2)
    if product_image is not None:
        _paste_fitted_image(page, product_image, (104, top_y + 34, 568, 724), background="#ffffff")
    else:
        draw.rectangle((134, 360, 538, 596), fill="#f7f8fa", outline=border, width=2)
        draw.text((276, 462), "SEM FOTO", fill=muted, font=section_font)

    draw.text((right_x, top_y), category.upper(), fill=accent, font=_load_font(18, bold=True))
    title_y = top_y + 38
    product_title_font = _fit_title_font(draw, name.upper(), 500, 40)
    title_lines = _wrap_text(draw, name.upper(), product_title_font, 500)[:4]
    for line in title_lines:
        draw.text((right_x, title_y), line, fill=dark, font=product_title_font)
        title_y += _measure_text(draw, "Ag", product_title_font)[1] + 10

    code_label = f"COD. {code or '-'}"
    code_width, code_height = _measure_text(draw, code_label, _load_font(22, bold=True))
    draw.rounded_rectangle(
        (right_x, title_y + 12, right_x + code_width + 28, title_y + code_height + 32),
        radius=8,
        fill=accent,
    )
    draw.text((right_x + 14, title_y + 20), code_label, fill="#ffffff", font=_load_font(22, bold=True))

    summary_y = title_y + 86
    draw.text((right_x, summary_y), "Resumo do produto", fill=dark, font=section_font)
    desc_y = summary_y + 42
    desc_y = _draw_wrapped_text(draw, text=description, font=body_font, x=right_x, y=desc_y, max_width=500, fill="#344054", line_spacing=8)
    if material or finish:
        meta = " | ".join(value for value in (material, finish) if value)
        _draw_wrapped_text(draw, text=meta, font=small_font, x=right_x, y=desc_y + 16, max_width=500, fill=muted, line_spacing=6)

    card_y = 812
    card_gap = 18
    card_width = (PAGE_SIZE[0] - 144 - card_gap * 3) // 4
    for index, (label, value) in enumerate(highlights):
        card_left = 72 + index * (card_width + card_gap)
        _draw_metric_card(
            draw,
            box=(card_left, card_y, card_left + card_width, card_y + 118),
            label=label,
            value=value,
            label_font=tiny_font,
            value_font=_load_font(22, bold=True),
        )

    table_box = (72, 982, 738, 1570)
    _rounded_box(draw, table_box, fill="#ffffff", outline=border, radius=24, width=2)
    draw.text((104, 1014), "Informações técnicas", fill=dark, font=section_font)
    row_y = 1068
    table_rows = enriched_rows or [("Especificações", specs)]
    for index, (label, value) in enumerate(table_rows[:14]):
        row_fill = "#f8fafc" if index % 2 == 0 else "#ffffff"
        draw.rectangle((104, row_y - 8, 706, row_y + 34), fill=row_fill)
        draw.text((124, row_y), label, fill="#475467", font=table_font)
        value_lines = _wrap_text(draw, value, table_value_font, 276)[:2]
        value_y = row_y
        for line in value_lines:
            draw.text((420, value_y), line, fill=dark, font=table_value_font)
            value_y += 21
        row_y += 44 if len(value_lines) <= 1 else 62
        if row_y > 1518:
            break

    gallery_box = (778, 982, 1168, 1570)
    _rounded_box(draw, gallery_box, fill="#ffffff", outline=border, radius=24, width=2)
    draw.text((810, 1014), "Imagens de apoio", fill=dark, font=section_font)
    image_slots = [
        ("Ambientada", ambient_image),
        ("Medidas", measures_image),
    ]
    slot_y = 1068
    for label, image in image_slots:
        draw.text((810, slot_y), label, fill="#475467", font=small_font)
        if image is not None:
            _paste_fitted_image(page, image, (810, slot_y + 30, 1136, slot_y + 218), background="#ffffff")
        else:
            draw.rounded_rectangle((810, slot_y + 30, 1136, slot_y + 218), radius=16, fill="#f8fafc", outline=border, width=2)
            draw.text((916, slot_y + 108), "Não informado", fill=muted, font=small_font)
        slot_y += 246

    draw.rectangle((0, 1660, PAGE_SIZE[0], PAGE_SIZE[1]), fill=dark)
    draw.text((72, 1692), footer_text, fill="#ffffff", font=footer_font)
    disclaimer = "Dados sujeitos à conferência conforme cadastro e lote do produto."
    disclaimer_width, _ = _measure_text(draw, disclaimer, footer_font)
    draw.text((PAGE_SIZE[0] - 72 - disclaimer_width, 1692), disclaimer, fill="#cbd5e1", font=footer_font)
    pages.append(page)

    remaining_attributes = [
        (label, value)
        for label, value in _product_attributes(product)
        if label not in {"CODPROD", "CODAUXILIAR", "NBM", "PERCIPIVENDA"}
    ][18:]
    while remaining_attributes:
        extra_page, extra_draw = _new_pdf_page()
        header_box = (60, 56, 1180, 196)
        _rounded_box(extra_draw, header_box, fill="#123f87", radius=30)
        extra_draw.text((88, 96), f"DETALHES COMPLEMENTARES - PRODUTO {code or '-'}", fill="white", font=title_font)
        extra_draw.text((88, 136), name, fill="#dbe8ff", font=body_font)
        consumed = _draw_attribute_grid(
            extra_draw,
            attributes=remaining_attributes,
            box=(60, 236, 1180, 1648),
            columns=2,
            section_font=section_font,
            label_font=tiny_font,
            value_font=small_font,
            title="ATRIBUTOS ADICIONAIS",
        )
        extra_draw.text((60, 1688), footer_text, fill="#6d82a6", font=footer_font)
        pages.append(extra_page)
        remaining_attributes = remaining_attributes[consumed:]

    return pages


def _build_catalog_pdf_pages(
    products: Sequence[Dict[str, Any]],
    *,
    query: str,
    category: str,
    code: str,
) -> List[Image.Image]:
    title_font = _load_font(34, bold=True)
    subtitle_font = _load_font(20, bold=True)
    body_font = _load_font(18)
    small_font = _load_font(16)
    line_height = _measure_text(ImageDraw.Draw(Image.new("RGB", (10, 10), "white")), "Ag", body_font)[1] + 14

    pages: List[Image.Image] = []
    rows_per_page = 34
    exported_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    summary = [
        f"Itens: {len(products)}",
        f"Categoria: {category or 'Todas'}",
        f"Busca: {query or '-'}",
        f"Codigo: {code or '-'}",
        f"Exportado em: {exported_at}",
    ]

    for page_index, start in enumerate(range(0, len(products), rows_per_page), start=1):
        page, draw = _new_pdf_page()
        y = PAGE_MARGIN
        draw.text((PAGE_MARGIN, y), "Catalogo de Produtos", fill="#123874", font=title_font)
        y += 52
        for item in summary:
            draw.text((PAGE_MARGIN, y), item, fill="#37506e", font=small_font)
            y += 24
        y += 12
        draw.rectangle((PAGE_MARGIN, y, PAGE_SIZE[0] - PAGE_MARGIN, y + 42), fill="#ebf2ff")
        draw.text((PAGE_MARGIN + 14, y + 10), "Codigo", fill="#123874", font=subtitle_font)
        draw.text((PAGE_MARGIN + 170, y + 10), "Nome", fill="#123874", font=subtitle_font)
        draw.text((PAGE_MARGIN + 780, y + 10), "Categoria", fill="#123874", font=subtitle_font)
        y += 58

        for row_index, product in enumerate(products[start : start + rows_per_page], start=1):
            code_text = _stringify(product.get("Codigo"))
            name_text = textwrap.shorten(_stringify(product.get("Nome")), width=52, placeholder="...")
            category_text = textwrap.shorten(_stringify(product.get("Categoria")), width=28, placeholder="...")
            draw.text((PAGE_MARGIN + 14, y), code_text, fill="#102845", font=body_font)
            draw.text((PAGE_MARGIN + 170, y), name_text, fill="#102845", font=body_font)
            draw.text((PAGE_MARGIN + 780, y), category_text, fill="#37506e", font=body_font)
            draw.line((PAGE_MARGIN, y + line_height - 8, PAGE_SIZE[0] - PAGE_MARGIN, y + line_height - 8), fill="#ebf2ff")
            y += line_height

        draw.text(
            (PAGE_MARGIN, PAGE_SIZE[1] - PAGE_MARGIN),
            f"Pagina {page_index}",
            fill="#617892",
            font=small_font,
        )
        pages.append(page)

    return pages or [_new_pdf_page()[0]]


def _build_pdf_bytes(
    products: Sequence[Dict[str, Any]],
    *,
    query: str,
    category: str,
    code: str,
) -> bytes:
    pages = (
        _build_product_pdf_pages(products[0])
        if len(products) == 1
        else _build_catalog_pdf_pages(products, query=query, category=category, code=code)
    )
    output = BytesIO()
    first_page, *other_pages = pages
    first_page.save(output, format="PDF", save_all=True, append_images=other_pages)
    return output.getvalue()


def _build_photo_manifest_rows(products: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for product in products:
        code = _stringify(product.get("Codigo"))
        name = _stringify(product.get("Nome"))
        for reference in _photo_references(product):
            rows.append(
                {
                    "Codigo": code,
                    "Nome": name,
                    "Foto": reference["label"],
                    "URL": reference["url"],
                }
            )
    return rows


def _csv_from_rows(rows: Sequence[Dict[str, str]], columns: Sequence[str]) -> bytes:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def _build_zip_bytes(
    products: Sequence[Dict[str, Any]],
    *,
    query: str,
    category: str,
    code: str,
    base_name: str,
) -> bytes:
    output = BytesIO()
    photo_manifest: List[Dict[str, str]] = []

    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as zip_file:
        zip_file.writestr(f"{base_name}.csv", _build_csv_bytes(products))
        zip_file.writestr(f"{base_name}.json", _build_json_bytes(products, query=query, category=category, code=code))
        zip_file.writestr(
            "README.txt",
            (
                "Pacote de exportacao do catalogo.\n"
                "- Arquivos CSV/JSON contem os dados exportados.\n"
                "- A pasta fotos/ contem imagens locais ou remotas que puderam ser baixadas.\n"
                "- O manifesto_fotos.csv lista todas as referencias encontradas, mesmo quando a imagem nao foi baixada.\n"
            ).encode("utf-8"),
        )

        for product in products:
            product_code = _stringify(product.get("Codigo")) or "sem-codigo"
            for index, reference in enumerate(_photo_references(product), start=1):
                photo_label = reference["label"]
                photo_url = reference["url"]
                file_in_zip = ""
                payload, extension = _resolve_photo_bytes(photo_url)
                if payload:
                    safe_label = _slugify(photo_label, fallback=f"imagem-{index}")
                    resolved_extension = extension or ".bin"
                    file_in_zip = f"fotos/{product_code}/{index:02d}_{safe_label}{resolved_extension}"
                    zip_file.writestr(file_in_zip, payload)

                photo_manifest.append(
                    {
                        "Codigo": product_code,
                        "Nome": _stringify(product.get("Nome")),
                        "Foto": photo_label,
                        "URL": photo_url,
                        "ArquivoZip": file_in_zip,
                    }
                )

        zip_file.writestr(
            "manifesto_fotos.csv",
            _csv_from_rows(photo_manifest, ("Codigo", "Nome", "Foto", "URL", "ArquivoZip")),
        )

    return output.getvalue()


def _response_metadata(format_name: str, *, base_name: str) -> tuple[str, str]:
    normalized = format_name.lower()
    if normalized == "csv":
        return "text/csv; charset=utf-8", f"{base_name}.csv"
    if normalized in {"xlsx", "xls"}:
        return (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{base_name}.xlsx",
        )
    if normalized == "json":
        return "application/json; charset=utf-8", f"{base_name}.json"
    if normalized in {"pdf", "ficha"}:
        return "application/pdf", f"{base_name}.pdf"
    if normalized == "zip":
        return "application/zip", f"{base_name}.zip"
    raise ValueError("unsupported export format")


def build_catalog_export(
    *,
    format_name: str,
    query: str = "",
    category: str = "",
    code: str = "",
    brand: str = "",
) -> tuple[bytes, str, str]:
    normalized_format = format_name.lower().strip()
    if normalized_format not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError("unsupported export format")

    products = _filter_products(_load_products(), query=query, category=category, code=code, brand=brand)
    if not products:
        raise ValueError("no products available for the selected export")
    if normalized_format == "ficha" and not code:
        raise ValueError("technical sheet export requires a product code")

    if normalized_format == "ficha" and code:
        base_name = f"ficha-tecnica-{_slugify(code, fallback='produto')}"
    elif code:
        base_name = f"produto-{_slugify(code, fallback='item')}"
    elif brand:
        base_name = f"catalogo-{_slugify(brand)}"
    elif category and _normalize_text(category) != "todas":
        base_name = f"catalogo-{_slugify(category)}"
    else:
        base_name = "catalogo-produtos"

    if normalized_format == "csv":
        payload = _build_csv_bytes(products)
    elif normalized_format in {"xlsx", "xls"}:
        payload = _build_xlsx_bytes(products)
    elif normalized_format == "json":
        payload = _build_json_bytes(products, query=query, category=category, code=code)
    elif normalized_format in {"pdf", "ficha"}:
        payload = _build_pdf_bytes(products, query=query, category=category, code=code)
    else:
        payload = _build_zip_bytes(products, query=query, category=category, code=code, base_name=base_name)

    media_type, filename = _response_metadata(normalized_format, base_name=base_name)
    return payload, media_type, filename
