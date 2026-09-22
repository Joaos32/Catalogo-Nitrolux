"""Busca de imagens de produtos em uma pasta do Google Drive."""

from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List

import requests

from .cache import cached
from .local_catalog import IMG_EXTENSIONS
from .product_media import _classify_variant, _match_filename


GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
GOOGLE_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_bool_env(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _parse_folder_id(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None

    folder_match = re.search(r"/folders/([A-Za-z0-9_-]+)", cleaned)
    if folder_match:
        return folder_match.group(1)

    query_match = re.search(r"[?&]id=([A-Za-z0-9_-]+)", cleaned)
    if query_match:
        return query_match.group(1)

    return cleaned


def is_configured() -> bool:
    return bool(
        _parse_folder_id(_optional_env("CATALOG_GOOGLE_DRIVE_FOLDER_ID"))
        and _optional_env("CATALOG_GOOGLE_DRIVE_API_KEY")
    )


def _build_file_url(file_id: str) -> str:
    # O arquivo ja e acessivel sem autenticacao no Drive (a listagem tambem
    # usa somente a API key). Entregar a miniatura diretamente evita que cada
    # card abra uma nova funcao da Vercel para fazer o mesmo download.
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"


def fetch_google_drive_image(file_id: str, size: str = "detail") -> tuple[bytes, str]:
    """Baixa uma imagem do Drive para ser servida pelo próprio catálogo."""
    cleaned_id = str(file_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,200}", cleaned_id):
        raise ValueError("invalid Google Drive file id")

    requested_size = str(size or "detail").strip().lower()
    thumbnail_widths = {"thumb": 320, "card": 640}
    if requested_size in thumbnail_widths:
        source_url = (
            "https://drive.google.com/thumbnail"
            f"?id={cleaned_id}&sz=w{thumbnail_widths[requested_size]}"
        )
    else:
        source_url = f"https://drive.google.com/uc?export=view&id={cleaned_id}"

    upstream = requests.get(source_url, timeout=20)
    upstream.raise_for_status()

    media_type = (upstream.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if not media_type.startswith("image/"):
        raise ValueError("Google Drive file is not an image")

    return upstream.content, media_type


def _is_image_file(item: Dict) -> bool:
    mime_type = str(item.get("mimeType") or "")
    if mime_type.startswith("image/"):
        return True
    name = str(item.get("name") or "").lower()
    return any(name.endswith(ext) for ext in IMG_EXTENSIONS)


def _matches_code(name: str, code: str) -> bool:
    if _match_filename(name, code) is not None:
        return True
    return re.search(rf"(?<!\d){re.escape(str(code))}(?!\d)", name or "") is not None


def _image_sort_key(item: Dict, code: str) -> tuple:
    name = str(item.get("name") or "")
    variant = _match_filename(name, code)
    if variant is None:
        variant = 99
    return (variant, name.lower())


def _request_children(folder_id: str, api_key: str | None) -> Iterable[Dict]:
    page_token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        if api_key:
            params["key"] = api_key

        response = requests.get(GOOGLE_DRIVE_FILES_URL, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("files") or []:
            if isinstance(item, dict):
                yield item

        page_token = payload.get("nextPageToken")
        if not page_token:
            break


def _escape_query_value(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("'", "\\'")


def _request_named_images(codes: List[str], folder_id: str | None = None) -> Dict[str, List[Dict]]:
    root_folder_id = _parse_folder_id(folder_id or _optional_env("CATALOG_GOOGLE_DRIVE_FOLDER_ID"))
    api_key = _optional_env("CATALOG_GOOGLE_DRIVE_API_KEY")
    normalized_codes = list(dict.fromkeys(str(code or "").strip() for code in codes if str(code or "").strip()))
    matches: Dict[str, List[Dict]] = {code: [] for code in normalized_codes}
    if not root_folder_id or not api_key or not normalized_codes:
        return matches

    name_terms = " or ".join(
        f"name contains '{_escape_query_value(code)}'" for code in normalized_codes
    )
    query = f"'{_escape_query_value(root_folder_id)}' in parents and trashed = false and ({name_terms})"
    page_token = None

    while True:
        params = {
            "q": query,
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(GOOGLE_DRIVE_FILES_URL, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("files") or []:
            if not isinstance(item, dict) or not _is_image_file(item):
                continue
            name = str(item.get("name") or "")
            file_id = str(item.get("id") or "").strip()
            if not file_id:
                continue
            for code in normalized_codes:
                if not _matches_code(name, code):
                    continue
                matches[code].append(
                    {
                        "id": file_id,
                        "name": name,
                        "mimeType": str(item.get("mimeType") or ""),
                        "url": _build_file_url(file_id),
                    }
                )

        page_token = payload.get("nextPageToken")
        if not page_token:
            break

    return matches


@cached
def _request_named_images_cached(
    codes: tuple[str, ...], folder_id: str | None = None
) -> Dict[str, List[Dict]]:
    """Mantem a busca por codigos no Drive durante o TTL do cache local."""
    return _request_named_images(list(codes), folder_id=folder_id)


@cached
def list_google_drive_images(folder_id: str | None = None, max_depth: int | None = None) -> List[Dict]:
    root_folder_id = _parse_folder_id(folder_id or _optional_env("CATALOG_GOOGLE_DRIVE_FOLDER_ID"))
    if not root_folder_id:
        return []

    api_key = _optional_env("CATALOG_GOOGLE_DRIVE_API_KEY")
    if not api_key:
        raise ValueError("missing CATALOG_GOOGLE_DRIVE_API_KEY configuration")

    recursive = _parse_bool_env("CATALOG_GOOGLE_DRIVE_RECURSIVE", default=True)
    depth_limit = max_depth
    if depth_limit is None:
        depth_limit = int(os.getenv("CATALOG_GOOGLE_DRIVE_MAX_DEPTH", "4"))

    images: List[Dict] = []
    pending: list[tuple[str, int]] = [(root_folder_id, 0)]
    visited: set[str] = set()

    while pending:
        current_folder_id, depth = pending.pop(0)
        if current_folder_id in visited:
            continue
        visited.add(current_folder_id)

        for item in _request_children(current_folder_id, api_key):
            mime_type = str(item.get("mimeType") or "")
            if mime_type == GOOGLE_DRIVE_FOLDER_MIME:
                if recursive and depth < depth_limit:
                    child_id = str(item.get("id") or "").strip()
                    if child_id:
                        pending.append((child_id, depth + 1))
                continue

            if _is_image_file(item):
                file_id = str(item.get("id") or "").strip()
                if not file_id:
                    continue
                images.append(
                    {
                        "id": file_id,
                        "name": str(item.get("name") or ""),
                        "mimeType": mime_type,
                        "url": _build_file_url(file_id),
                    }
                )

    return images


def find_images_for_code(code: str, folder_id: str | None = None) -> List[Dict]:
    return find_images_for_codes([code], folder_id=folder_id).get(str(code or "").strip(), [])


def find_images_for_codes(codes: List[str], folder_id: str | None = None) -> Dict[str, List[Dict]]:
    code_list = list(dict.fromkeys(str(code or "").strip() for code in codes if str(code or "").strip()))
    if not code_list:
        return {}

    try:
        cached_matches = _request_named_images_cached(tuple(code_list), folder_id=folder_id)
        matches_by_code = {
            code: list(cached_matches.get(code) or [])
            for code in code_list
        }
    except Exception:
        matches_by_code = {code: [] for code in code_list}

    # A successful Drive query can still return no direct-child match. This is
    # common for catalogs whose photos are organized in subfolders, so use the
    # recursive index for only the missing codes.
    missing_codes = [code for code in code_list if not matches_by_code.get(code)]
    if missing_codes:
        try:
            recursive_images = list_google_drive_images(folder_id=folder_id)
        except Exception:
            recursive_images = []
        for code in missing_codes:
            matches_by_code[code] = [
                item
                for item in recursive_images
                if _matches_code(str(item.get("name") or ""), code)
            ]

    result: Dict[str, List[Dict]] = {}
    for code in code_list:
        matches = matches_by_code.get(code, [])
        matches.sort(key=lambda item: _image_sort_key(item, code))
        result[code] = [
            {
                "name": str(item.get("name") or ""),
                "variant": _match_filename(str(item.get("name") or ""), code) or 0,
                "url": (
                    _build_file_url(str(item.get("id") or "").strip())
                    if str(item.get("id") or "").strip()
                    else str(item.get("url") or "")
                ),
            }
            for item in matches
        ]
    return result


def categorize_photos_for_code(code: str, folder_id: str | None = None) -> Dict[str, str | None]:
    return categorize_photos_for_codes([code], folder_id=folder_id).get(
        str(code or "").strip(),
        {"white_background": None, "ambient": None, "measures": None},
    )


def categorize_photos_for_codes(codes: List[str], folder_id: str | None = None) -> Dict[str, Dict[str, str | None]]:
    images_by_code = find_images_for_codes(codes, folder_id=folder_id)
    categorized: Dict[str, Dict[str, str | None]] = {}

    for code, images in images_by_code.items():
        photos: Dict[str, str | None] = {
            "white_background": None,
            "ambient": None,
            "measures": None,
        }

        for image in images:
            variant = _classify_variant(str(image.get("name") or ""), code)
            if variant in photos and not photos[variant]:
                photos[variant] = str(image.get("url") or "") or None
        categorized[code] = photos

    return categorized
