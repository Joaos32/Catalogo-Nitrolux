"""Importacao e mesclagem de produtos vindos de arquivo JSON do ERP."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading
import tempfile
import unicodedata
from urllib.parse import quote
from typing import Any, Dict, List

from .technical_specs import resolve_technical_specs
from .erp_storage import ERPWriteConflictError, load_active as load_remote_erp, storage_uri, write_active as write_remote_erp


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ERP_JSON_PATH = BASE_DIR / "reports" / "erp_products.json"
DEFAULT_ERP_INBOX_DIR = BASE_DIR / "reports" / "erp_inbox"
DEFAULT_ERP_DROP_DIR = BASE_DIR / "catalog" / "json"
CATALOG_META_KEY = "catalog_meta"
_ERP_MUTATION_LOCK = threading.RLock()
PRODUCT_CONTAINER_KEYS = (
    "produtos",
    "products",
    "itens",
    "items",
    "registros",
    "records",
    "data",
)
CODE_PATTERN = re.compile(r"\d{3,12}")
NUMERIC_TEXT_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
DISCOVERY_PATTERNS = (
    "erp*.json",
    "pcprodut*.json",
    "*produto*.json",
    "*produt*.json",
    "*catalog*.json",
)
JSON_TEXT_ENCODINGS = ("utf-8-sig", "utf-16", "latin-1")
PREVIEW_SAMPLE_SIZE = 8
PREVIEW_CHANGE_SAMPLE_SIZE = 8
CATALOG_RESPONSE_CACHES = {
    "catalog.api.endpoints.catalog": ("_cached_vercel_catalog_payload",),
    "catalog.api.endpoints.export": ("_cached_export",),
    "catalog.api.endpoints.integration": (
        "_integration_catalog_products",
        "_integration_catalog_payload",
        "_pienza_products_payload",
    ),
    "catalog.services.catalog_service": ("_cached_catalog_products",),
}
CHANGE_FIELD_LABELS = {
    "nome": "Nome",
    "categoria": "Categoria",
    "descricao": "Descricao",
    "especificacoes": "Especificacoes",
    "urlfoto": "Foto principal",
    "fotobranco": "Foto branco",
    "fotoambient": "Foto ambientada",
    "fotomedidas": "Foto medidas",
    "codepto": "CODEPTO",
    "codsec": "CODSEC",
}


def _atomic_write_bytes(target: Path, content: bytes) -> None:
    """Replace a file only after its complete contents are safely written."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _invalidate_catalog_response_caches() -> None:
    """Clear process-local catalog snapshots after a successful ERP write."""
    for module_name, function_names in CATALOG_RESPONSE_CACHES.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for function_name in function_names:
            cached_function = getattr(module, function_name, None)
            clear_cache = getattr(cached_function, "cache_clear", None)
            if clear_cache:
                clear_cache()

CODE_ALIASES = (
    "Codigo",
    "Code",
    "SKU",
    "cod",
    "id",
    "codigo_produto",
    "CODPROD",
    "CODIGO",
    "CODPRODPRINC",
)
NAME_ALIASES = (
    "Nome",
    "Name",
    "Produto",
    "Descricao",
    "Description",
    "Titulo",
    "title",
    "DESCRICAO",
)
DESCRIPTION_ALIASES = ("Descricao", "Description", "Resumo", "Detalhes", "DescricaoCurta", "DESCRICAO")
CATEGORY_ALIASES = (
    "Categoria",
    "Category",
    "Grupo",
    "Familia",
    "Linha",
    "Tipo",
    "Department",
    "Departamento",
    "Secao",
)
SPECS_ALIASES = ("Especificacoes", "Especificacao", "Specs", "FichaTecnica", "Atributos")
WHITE_IMAGE_ALIASES = ("FotoBranco", "white_background", "WhiteBackground", "ImagemBranca")
AMBIENT_IMAGE_ALIASES = ("FotoAmbient", "ambient", "Ambient", "ImagemAmbient")
MEASURES_IMAGE_ALIASES = ("FotoMedidas", "measures", "Measures", "ImagemMedidas")
COVER_IMAGE_ALIASES = (
    "URLFoto",
    "Imagem",
    "Image",
    "Foto",
    "URL",
    "Capa",
    "Cover",
    "FotoPrincipal",
)
DEPT_ALIASES = ("CODEPTO", "CODDEPTO", "DEPTO", "DEPARTAMENTO")
SECTION_ALIASES = ("CODSEC", "CODSECAO", "SEC", "SECAO")
DEPT_SECTION_CATEGORY_MAP: Dict[tuple[str, str], str] = {
    ("101", "107"): "MANGUEIRAS E DECORATIVOS LED",
    ("102", "105"): "ACESSORIOS ELETRICOS",
    ("102", "108"): "CONECTORES E EMENDAS",
    ("102", "120"): "RELES E SENSORES",
    ("103", "112"): "LAMPADAS BULBO",
    ("103", "115"): "ILUMINACAO PUBLICA",
    ("104", "116"): "TARTARUGAS LED",
    ("104", "121"): "SPOTS EXTERNOS",
    ("105", "117"): "MOVEIS E UTILIDADES",
    ("106", "122"): "RODIZIOS E MOVIMENTACAO",
    ("107", "123"): "SUPRIMENTOS E OPERACAO",
}
DEPT_CATEGORY_MAP: Dict[str, str] = {
    "101": "ILUMINACAO INTERNA",
    "102": "ACESSORIOS ELETRICOS",
    "103": "LAMPADAS E ILUMINACAO PUBLICA",
    "104": "ILUMINACAO EXTERNA",
    "105": "MOVEIS E UTILIDADES",
    "106": "RODIZIOS E MOVIMENTACAO",
    "107": "SUPRIMENTOS E OPERACAO",
}
BUSINESS_CATEGORY_MAP: Dict[str, str] = {
    "iluminacao decorativa": "ILUMINACAO DECORATIVA",
    "iluminacao tecnica": "ILUMINACAO TECNICA",
    "iluminacao externa e publica": "ILUMINACAO EXTERNA E PUBLICA",
    "lampadas e fitas": "LAMPADAS E FITAS",
    "componentes e acessorios": "COMPONENTES E ACESSORIOS",
    "utilidades e operacao": "UTILIDADES E OPERACAO",
    "outros itens erp": "OUTROS ITENS ERP",
    "abajur": "ILUMINACAO DECORATIVA",
    "arandela": "ILUMINACAO DECORATIVA",
    "espelho": "ILUMINACAO DECORATIVA",
    "lustre": "ILUMINACAO DECORATIVA",
    "pendente": "ILUMINACAO DECORATIVA",
    "painel": "ILUMINACAO TECNICA",
    "plafon": "ILUMINACAO TECNICA",
    "perfil": "ILUMINACAO TECNICA",
    "trilho": "ILUMINACAO TECNICA",
    "luminaria": "ILUMINACAO TECNICA",
    "balizador": "ILUMINACAO EXTERNA E PUBLICA",
    "espeto": "ILUMINACAO EXTERNA E PUBLICA",
    "spots externos": "ILUMINACAO EXTERNA E PUBLICA",
    "tartarugas led": "ILUMINACAO EXTERNA E PUBLICA",
    "iluminacao publica": "ILUMINACAO EXTERNA E PUBLICA",
    "refletor": "ILUMINACAO EXTERNA E PUBLICA",
    "lampadas bulbo": "LAMPADAS E FITAS",
    "lampada": "LAMPADAS E FITAS",
    "fita led": "LAMPADAS E FITAS",
    "mangueiras e decorativos led": "LAMPADAS E FITAS",
    "componentes eletricos": "COMPONENTES E ACESSORIOS",
    "acessorios eletricos": "COMPONENTES E ACESSORIOS",
    "conectores e emendas": "COMPONENTES E ACESSORIOS",
    "reles e sensores": "COMPONENTES E ACESSORIOS",
    "driver/fonte": "COMPONENTES E ACESSORIOS",
    "utilidades e operacao": "UTILIDADES E OPERACAO",
    "moveis e utilidades": "UTILIDADES E OPERACAO",
    "rodizios e movimentacao": "UTILIDADES E OPERACAO",
    "suprimentos e operacao": "UTILIDADES E OPERACAO",
}
NAME_KEYWORD_PRIORITY: List[tuple[str, set[str]]] = [
    (
        "ILUMINACAO DECORATIVA",
        {"pendente", "pendentes", "lustre", "lustres", "arandela", "arandelas", "abajur", "espelho"},
    ),
    (
        "ILUMINACAO EXTERNA E PUBLICA",
        {
            "refletor",
            "refletores",
            "publica",
            "publico",
            "balizador",
            "balizadores",
            "espeto",
            "espeto",
            "tartaruga",
            "tartarugas",
        },
    ),
    (
        "ILUMINACAO TECNICA",
        {"luminaria", "luminarias", "plafon", "plafons", "trilho", "trilhos", "perfil", "perfis", "painel", "paineis", "spot", "spots"},
    ),
    (
        "LAMPADAS E FITAS",
        {"lampada", "lampadas", "fita", "fitas", "mangueira", "mangueiras", "bulbo", "bulbos"},
    ),
    (
        "COMPONENTES E ACESSORIOS",
        {
            "rele",
            "reles",
            "sensor",
            "sensores",
            "conector",
            "conectores",
            "emenda",
            "emendas",
            "driver",
            "drivers",
            "fonte",
            "fontes",
            "bocal",
            "bocais",
            "rabicho",
            "rabichos",
            "base",
            "bases",
            "fotocelula",
            "fotocelulas",
        },
    ),
    (
        "UTILIDADES E OPERACAO",
        {
            "rodizio",
            "rodizios",
            "cadeira",
            "cadeiras",
            "paleteira",
            "paleteiras",
            "suprimento",
            "suprimentos",
            "operacao",
            "operacoes",
        },
    ),
]


def _env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def get_max_upload_size_bytes() -> int:
    value = os.getenv("CATALOG_ERP_MAX_UPLOAD_BYTES", "").strip()
    if not value:
        return 10 * 1024 * 1024
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError("CATALOG_ERP_MAX_UPLOAD_BYTES must be an integer") from exc
    if parsed <= 0:
        raise ValueError("CATALOG_ERP_MAX_UPLOAD_BYTES must be positive")
    return parsed


def _normalized_tokens(text: str) -> List[str]:
    normalized = re.sub(r"[^a-z0-9\s]", " ", _normalize_text(text or ""))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.split() if normalized else []


def _token_to_category(token: str, next_token: str = "") -> str | None:
    token_upper = (token or "").upper()
    next_upper = (next_token or "").upper()
    if not token_upper:
        return None

    if token_upper.startswith("ARANDEL"):
        return "ARANDELA"
    if token_upper.startswith("ABAJUR"):
        return "ABAJUR"
    if token_upper.startswith("PENDENTE"):
        return "PENDENTE"
    if token_upper.startswith("LUSTRE"):
        return "LUSTRE"
    if token_upper.startswith("PAINEL"):
        return "PAINEL"
    if token_upper.startswith("PLAFON"):
        return "PLAFON"
    if token_upper == "MINI" and next_upper.startswith("TRILHO"):
        return "TRILHO"
    if token_upper.startswith("TRILHO"):
        return "TRILHO"
    if token_upper.startswith("PERFIL"):
        return "PERFIL"
    if token_upper.startswith("SPOT"):
        return "SPOT"
    if token_upper.startswith("SENSOR"):
        return "SENSOR"
    if token_upper.startswith("RELE") or token_upper.startswith("FOTOCEL"):
        return "RELE"
    if token_upper.startswith("BOCAL"):
        return "BOCAL"
    if token_upper.startswith("RABICHO"):
        return "RABICHO"
    if token_upper.startswith("BASE"):
        return "BASE"
    if token_upper.startswith("CONECT") or token_upper.startswith("CONEX"):
        return "CONECTOR"
    if token_upper.startswith("EMENDA"):
        return "EMENDA"
    if token_upper.startswith("ADAPTADOR"):
        return "ADAPTADOR"
    if token_upper.startswith("ESPETO"):
        return "ESPETO"
    if token_upper.startswith("BALIZADOR"):
        return "BALIZADOR"
    if token_upper.startswith("TARTARUGA"):
        return "TARTARUGA"
    if token_upper.startswith("ESPELHO"):
        return "ESPELHO"
    if token_upper.startswith("PISCA") or token_upper.startswith("CORTINA"):
        return "PISCA LED"
    if token_upper.startswith("REFLET") or token_upper.startswith("HOLOFOTE"):
        return "REFLETOR"
    if token_upper.startswith("LAMP"):
        return "LAMPADA"
    if token_upper.startswith("DRIVER") or token_upper.startswith("FONTE"):
        return "DRIVER/FONTE"
    if token_upper == "FITA" or token_upper.startswith("MANG"):
        return "FITA LED"
    if token_upper.startswith("LUMINARIA") or token_upper in {"LUMI", "LUM", "LUMIN"}:
        return "LUMINARIA"
    if token_upper.startswith("CADEIRA"):
        return "CADEIRA"
    if token_upper.startswith("RODA") or token_upper.startswith("RODIZ"):
        return "RODA E RODIZIO"
    if token_upper.startswith("PALETEIR") or token_upper.startswith("TRANSPALETE"):
        return "PALETEIRA"
    return None


def _is_numeric_text(value: str) -> bool:
    return bool(NUMERIC_TEXT_PATTERN.fullmatch(value or ""))


def _build_dept_category(dept_code: str, sec_code: str) -> str:
    dept = str(dept_code or "").strip()
    sec = str(sec_code or "").strip()
    mapped_pair = DEPT_SECTION_CATEGORY_MAP.get((dept, sec))
    if mapped_pair:
        return mapped_pair
    mapped_dept = DEPT_CATEGORY_MAP.get(dept)
    if mapped_dept:
        return mapped_dept
    if dept and sec:
        return f"DEPTO {dept} / SEC {sec}"
    if dept:
        return f"DEPTO {dept}"
    if sec:
        return f"SEC {sec}"
    return "Sem categoria"


def _infer_category(
    name: str,
    description: str,
    fallback_category: str,
    dept_code: str,
    sec_code: str,
) -> str:
    fallback = str(fallback_category or "").strip()
    if fallback and fallback.lower() != "sem categoria" and not _is_numeric_text(fallback):
        return fallback

    for candidate in (name, description):
        tokens = _normalized_tokens(candidate)
        if not tokens:
            continue
        if "iluminacao" in tokens and "publica" in tokens:
            return "ILUMINACAO PUBLICA"
        if "fita" in tokens and "led" in tokens:
            return "FITA LED"

        for idx, token in enumerate(tokens):
            mapped = _token_to_category(token, tokens[idx + 1] if idx + 1 < len(tokens) else "")
            if mapped:
                return mapped

    return _build_dept_category(dept_code, sec_code)


def _to_business_category(category: str, name: str = "", description: str = "") -> str:
    def _clean_category_label(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).upper()

    def _is_generic_category(value: str) -> bool:
        normalized_value = _normalize_text(value).strip()
        if not normalized_value:
            return True
        if normalized_value == "sem categoria":
            return True
        if normalized_value in BUSINESS_CATEGORY_MAP:
            return True
        if normalized_value in {_normalize_text(item) for item in DEPT_CATEGORY_MAP.values()}:
            return True
        if normalized_value in {_normalize_text(item) for item in DEPT_SECTION_CATEGORY_MAP.values()}:
            return True
        return normalized_value.startswith("depto ") or normalized_value.startswith("sec ")

    def _specific_category_from_tokens(tokens: List[str]) -> str | None:
        if not tokens:
            return None

        token_set = set(tokens)
        if ("iluminacao" in token_set and "publica" in token_set) or (
            ("publica" in token_set or "pub" in token_set)
            and any(token in token_set for token in {"luminaria", "lum", "lumi", "lumin", "poste", "fotocel", "fotocelula"})
        ):
            return "ILUMINACAO PUBLICA"

        if "filamento" in token_set:
            return "LAMPADA FILAMENTO"

        luminaria_candidate: str | None = None
        for idx, token in enumerate(tokens):
            mapped = _token_to_category(token, tokens[idx + 1] if idx + 1 < len(tokens) else "")
            if not mapped:
                continue
            if mapped == "LUMINARIA":
                luminaria_candidate = mapped
                continue
            return mapped

        return luminaria_candidate

    for candidate in (name, description, category):
        mapped = _specific_category_from_tokens(_normalized_tokens(candidate))
        if mapped:
            return mapped

    normalized_category = _normalize_text(category).strip()
    cleaned_category = _clean_category_label(category)
    if _is_generic_category(category):
        if (
            normalized_category in {"", "sem categoria"}
            or normalized_category.startswith("depto ")
            or normalized_category.startswith("sec ")
        ):
            return "OUTROS ITENS ERP"
        return cleaned_category or "OUTROS ITENS ERP"

    if (
        cleaned_category
        and not _is_numeric_text(cleaned_category)
        and not normalized_category.startswith("grupo ")
        and not normalized_category.startswith("depto ")
        and not normalized_category.startswith("sec ")
    ):
        return cleaned_category

    return "OUTROS ITENS ERP"


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    without_accents = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_accents.lower()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize_text(value or ""))


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _preferred_cover_url(ambient_url: Any, white_url: Any, measures_url: Any, cover_url: Any) -> str:
    for candidate in (ambient_url, white_url, measures_url, cover_url):
        rendered = _stringify(candidate)
        if rendered:
            return rendered
    return ""


def _safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _extract_catalog_meta(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    raw_meta = payload.get(CATALOG_META_KEY)
    meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}

    for key in ("imported_at", "updated_at", "source_path", "source_name", "source_updated_at"):
        value = payload.get(key)
        if key not in meta and isinstance(value, str) and value.strip():
            meta[key] = value.strip()

    if "source_size_bytes" not in meta:
        parsed_size = _safe_int(payload.get("source_size_bytes"))
        if parsed_size is not None:
            meta["source_size_bytes"] = parsed_size

    parsed_meta_size = _safe_int(meta.get("source_size_bytes"))
    if parsed_meta_size is not None:
        meta["source_size_bytes"] = parsed_meta_size
    elif "source_size_bytes" in meta:
        meta.pop("source_size_bytes", None)

    return meta


def _build_source_metadata(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "source_path": str(path),
        "source_name": path.name,
        "source_size_bytes": stat.st_size,
        "source_updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _resolve_deployed_source_path(meta: Dict[str, Any]) -> Path | None:
    source_path = str(meta.get("source_path") or "").strip()
    if not source_path:
        return None
    return Path(source_path)


def resolve_erp_inbox_dir() -> Path:
    configured = os.getenv("CATALOG_ERP_INBOX_DIR", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = BASE_DIR / candidate
        return candidate
    return DEFAULT_ERP_INBOX_DIR


def _resolve_erp_source_dirs() -> List[Path]:
    configured = os.getenv("CATALOG_ERP_SOURCE_DIRS", "").strip()
    source_dirs: List[Path] = [BASE_DIR, BASE_DIR / "reports", resolve_erp_inbox_dir(), DEFAULT_ERP_DROP_DIR]

    if configured:
        for item in configured.split(","):
            value = item.strip()
            if not value:
                continue
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = BASE_DIR / candidate
            source_dirs.append(candidate)

    unique_dirs: dict[Path, Path] = {}
    for directory in source_dirs:
        unique_dirs[directory.resolve(strict=False)] = directory
    return list(unique_dirs.values())


def _resolve_json_target_path() -> Path:
    configured = os.getenv("CATALOG_ERP_JSON_PATH", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = BASE_DIR / candidate
        return candidate
    return DEFAULT_ERP_JSON_PATH


def _resolve_json_path() -> Path:
    target = _resolve_json_target_path()
    configured = os.getenv("CATALOG_ERP_JSON_PATH", "").strip()
    if configured and target.is_file():
        return target

    if not configured and target.is_file():
        return target

    if not _env_flag("CATALOG_ERP_AUTO_DISCOVERY", default=True):
        return target

    candidates: List[Path] = []
    for root in _resolve_erp_source_dirs():
        if not root.is_dir():
            continue
        for pattern in DISCOVERY_PATTERNS:
            candidates.extend(
                item
                for item in root.glob(pattern)
                if item.is_file()
            )

    if candidates:
        unique_candidates = {item.resolve(): item for item in candidates}
        ordered = sorted(
            unique_candidates.values(),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return ordered[0]

    return target


def _build_lookup(record: Dict[str, Any]) -> Dict[str, Any]:
    lookup: Dict[str, Any] = {}
    for key, value in record.items():
        lookup[_normalize_key(str(key))] = value
    return lookup


def _pick_value(lookup: Dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        value = lookup.get(_normalize_key(alias))
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _normalize_code(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value).strip()

    if not text:
        return None

    if re.fullmatch(r"\d+(?:\.0+)?", text):
        return text.split(".")[0]

    match = CODE_PATTERN.search(text)
    if not match:
        return None
    return match.group(0)


def _extract_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in PRODUCT_CONTAINER_KEYS:
            values = payload.get(key)
            if isinstance(values, list):
                return [item for item in values if isinstance(item, dict)]

        if payload and all(isinstance(value, dict) for value in payload.values()):
            records: List[Dict[str, Any]] = []
            for fallback_code, value in payload.items():
                item = dict(value)
                item.setdefault("Codigo", fallback_code)
                records.append(item)
            return records

    raise ValueError("invalid ERP payload: expected array or object with product list")


def _normalize_erp_record(record: Dict[str, Any]) -> Dict[str, Any] | None:
    lookup = _build_lookup(record)

    code = _normalize_code(_pick_value(lookup, CODE_ALIASES))
    if not code:
        return None

    name = _stringify(_pick_value(lookup, NAME_ALIASES)) or f"Produto {code}"
    description = _stringify(_pick_value(lookup, DESCRIPTION_ALIASES))
    dept_code = _stringify(_pick_value(lookup, DEPT_ALIASES))
    sec_code = _stringify(_pick_value(lookup, SECTION_ALIASES))
    category = _infer_category(
        name=name,
        description=description,
        fallback_category=_stringify(_pick_value(lookup, CATEGORY_ALIASES)),
        dept_code=dept_code,
        sec_code=sec_code,
    )
    specs = resolve_technical_specs(
        code=code,
        current_specs=_pick_value(lookup, SPECS_ALIASES),
        name=name,
        description=description,
        category=category,
        extra_fields=record,
    )

    cover_url = _stringify(_pick_value(lookup, COVER_IMAGE_ALIASES))
    white_url = _stringify(_pick_value(lookup, WHITE_IMAGE_ALIASES)) or cover_url
    ambient_url = _stringify(_pick_value(lookup, AMBIENT_IMAGE_ALIASES))
    measures_url = _stringify(_pick_value(lookup, MEASURES_IMAGE_ALIASES))
    preferred_cover = _preferred_cover_url(ambient_url, white_url, measures_url, cover_url)

    normalized: Dict[str, Any] = {
        "Codigo": code,
        "Nome": name,
        "Descricao": description,
        "Categoria": category,
        "Especificacoes": specs,
        "URLFoto": preferred_cover,
        "FotoBranco": white_url or preferred_cover,
        "FotoAmbient": ambient_url,
        "FotoMedidas": measures_url,
    }

    for key, value in record.items():
        if key in normalized:
            continue
        rendered = _stringify(value)
        if not rendered:
            continue
        normalized[key] = value

    return normalized


def _build_index(payload: Any) -> Dict[str, Dict[str, Any]]:
    records = _extract_records(payload)
    index: Dict[str, Dict[str, Any]] = {}
    for record in records:
        normalized = _normalize_erp_record(record)
        if not normalized:
            continue
        index[str(normalized["Codigo"])] = normalized
    return index


def _change_field_label(key: str) -> str:
    return CHANGE_FIELD_LABELS.get(_normalize_key(key), key)


def _product_sort_key(product: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        _normalize_text(_stringify(product.get("Categoria"))),
        _normalize_text(_stringify(product.get("Nome"))),
        _stringify(product.get("Codigo")),
    )


def _detect_changed_fields(
    next_product: Dict[str, Any],
    current_product: Dict[str, Any],
) -> List[str]:
    changed_fields: List[str] = []
    seen_labels: set[str] = set()
    all_keys = list(next_product.keys()) + [key for key in current_product.keys() if key not in next_product]

    for key in all_keys:
        if _stringify(next_product.get(key)) == _stringify(current_product.get(key)):
            continue
        label = _change_field_label(key)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        changed_fields.append(label)

    return changed_fields


def _build_change_summary(
    next_index: Dict[str, Dict[str, Any]],
    current_index: Dict[str, Dict[str, Any]],
    *,
    compared_to_path: str = "",
    compared_to_name: str = "",
) -> Dict[str, Any]:
    added_changes: List[Dict[str, Any]] = []
    updated_changes: List[Dict[str, Any]] = []
    removed_changes: List[Dict[str, Any]] = []
    unchanged_count = 0

    for code, product in sorted(next_index.items(), key=lambda item: _product_sort_key(item[1])):
        current_product = current_index.get(code)
        name = _stringify(product.get("Nome")) or f"Produto {code}"
        category = _stringify(product.get("Categoria")) or "Sem categoria"

        if current_product is None:
            added_changes.append(
                {
                    "change_type": "added",
                    "code": code,
                    "name": name,
                    "category": category,
                    "previous_name": None,
                    "previous_category": None,
                    "changed_fields": [],
                }
            )
            continue

        changed_fields = _detect_changed_fields(product, current_product)
        if not changed_fields:
            unchanged_count += 1
            continue

        updated_changes.append(
            {
                "change_type": "updated",
                "code": code,
                "name": name,
                "category": category,
                "previous_name": _stringify(current_product.get("Nome")) or None,
                "previous_category": _stringify(current_product.get("Categoria")) or None,
                "changed_fields": changed_fields,
            }
        )

    for code, product in sorted(
        ((code, product) for code, product in current_index.items() if code not in next_index),
        key=lambda item: _product_sort_key(item[1]),
    ):
        removed_changes.append(
            {
                "change_type": "removed",
                "code": code,
                "name": _stringify(product.get("Nome")) or f"Produto {code}",
                "category": _stringify(product.get("Categoria")) or "Sem categoria",
                "previous_name": None,
                "previous_category": None,
                "changed_fields": [],
            }
        )

    sampled_changes = (updated_changes + added_changes + removed_changes)[:PREVIEW_CHANGE_SAMPLE_SIZE]

    return {
        "compared_to_path": compared_to_path or None,
        "compared_to_name": compared_to_name or None,
        "added_count": len(added_changes),
        "updated_count": len(updated_changes),
        "removed_count": len(removed_changes),
        "unchanged_count": unchanged_count,
        "changes": sampled_changes,
    }


def _build_preview_summary(
    payload: Any,
    *,
    source_path: str = "",
    source_name: str = "",
    source_size_bytes: int | None = None,
    source_updated_at: str | None = None,
    is_active: bool = False,
    is_deployed_source: bool = False,
    current_index: Dict[str, Dict[str, Any]] | None = None,
    compared_to_path: str = "",
    compared_to_name: str = "",
) -> Dict[str, Any]:
    records = _extract_records(payload)
    index = _build_index(payload)
    products = sort_products_by_category(list(index.values()))
    category_counts: Dict[str, int] = {}
    sample_products: List[Dict[str, str]] = []

    for product in products:
        category = _stringify(product.get("Categoria")) or "Sem categoria"
        category_counts[category] = category_counts.get(category, 0) + 1

        if len(sample_products) < PREVIEW_SAMPLE_SIZE:
            sample_products.append(
                {
                    "Codigo": _stringify(product.get("Codigo")),
                    "Nome": _stringify(product.get("Nome")) or f"Produto {_stringify(product.get('Codigo'))}",
                    "Categoria": category,
                }
            )

    categories = [
        {"name": name, "count": count}
        for name, count in sorted(category_counts.items(), key=lambda item: (-item[1], _normalize_text(item[0])))
    ]

    meta = _extract_catalog_meta(payload)
    resolved_name = source_name or (Path(source_path).name if source_path else "")

    return {
        "path": source_path,
        "name": resolved_name,
        "size_bytes": source_size_bytes or 0,
        "updated_at": source_updated_at or None,
        "is_active": is_active,
        "is_deployed_source": is_deployed_source,
        "products_loaded": len(products),
        "records_detected": len(records),
        "ignored_records": max(len(records) - len(products), 0),
        "imported_at": _stringify(meta.get("imported_at")) or None,
        "payload_updated_at": _stringify(meta.get("updated_at")) or None,
        "categories": categories,
        "sample_products": sample_products,
        "change_summary": _build_change_summary(
            index,
            current_index or {},
            compared_to_path=compared_to_path,
            compared_to_name=compared_to_name,
        ),
    }


def _parse_json_bytes(content: bytes) -> Any:
    if not content:
        raise ValueError("empty ERP JSON content")

    parse_error: Exception | None = None
    for encoding in JSON_TEXT_ENCODINGS:
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError as exc:
            parse_error = exc
            continue

        try:
            return json.loads(decoded)
        except json.JSONDecodeError as exc:
            parse_error = exc

    raise ValueError(f"invalid ERP JSON content: {parse_error}")


def _load_json_file(path: Path) -> Any:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"unable to read ERP file: {exc}") from exc
    return _parse_json_bytes(content)


def _sanitize_json_filename(filename: str) -> str:
    base_name = Path(filename or "").name.strip()
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", base_name)
    if not safe_name:
        raise ValueError("filename is required")
    if not safe_name.lower().endswith(".json"):
        safe_name = f"{safe_name}.json"
    return safe_name


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _resolve_candidate_file_path(file_path: str) -> Path:
    raw_path = Path(file_path or "").expanduser()
    if not str(raw_path).strip():
        raise ValueError("file_path is required")

    search_roots = tuple(_resolve_erp_source_dirs())

    if raw_path.is_absolute():
        if raw_path.is_file() and any(_is_within(raw_path, root) for root in search_roots):
            return raw_path
        raise ValueError("ERP file not found inside allowed directories")

    if ".." in raw_path.parts:
        raise ValueError("file_path must not contain parent directory traversal")

    for root in search_roots:
        candidate = root / raw_path
        if candidate.is_file():
            return candidate

    raise ValueError("ERP file not found")


def import_erp_payload(payload: Any, deployment_source: Dict[str, Any] | None = None) -> Dict[str, Any]:
    index = _build_index(payload)
    if not index:
        raise ValueError("no valid product records with code found in ERP payload")

    with _ERP_MUTATION_LOCK:
        imported_at = datetime.now(timezone.utc).isoformat()
        base_payload, etag, remote_expected_missing, _, _ = _load_active_erp_snapshot()
        return _write_erp_products(
            list(index.values()),
            base_payload=base_payload,
            imported_at=imported_at,
            deployment_source=deployment_source,
            persist_change_summary=True,
            expected_remote_etag=etag,
            expected_remote_missing=remote_expected_missing,
        )


def import_erp_file(file_path: str) -> Dict[str, Any]:
    source = _resolve_candidate_file_path(file_path)
    payload = _load_json_file(source)
    source_metadata = _build_source_metadata(source)
    result = import_erp_payload(payload, deployment_source=source_metadata)
    result.update(source_metadata)
    return result


def _store_uploaded_file(filename: str, content: bytes) -> Dict[str, Any]:
    if len(content) > get_max_upload_size_bytes():
        raise ValueError("ERP upload too large")
    _parse_json_bytes(content)
    safe_filename = _sanitize_json_filename(filename)
    inbox_dir = resolve_erp_inbox_dir()
    inbox_dir.mkdir(parents=True, exist_ok=True)

    target = inbox_dir / safe_filename
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target = inbox_dir / f"{target.stem}_{stamp}{target.suffix}"

    _atomic_write_bytes(target, content)
    stored = _build_source_metadata(target)
    return {
        "path": str(target),
        "name": target.name,
        "size_bytes": stored["source_size_bytes"],
        "updated_at": stored["source_updated_at"],
    }


def stage_erp_file(filename: str, content: bytes) -> Dict[str, Any]:
    stored = _store_uploaded_file(filename, content)
    preview = preview_erp_file(stored["path"])
    preview["staged"] = True
    return preview


def receive_erp_file(filename: str, content: bytes) -> Dict[str, Any]:
    stored = _store_uploaded_file(filename, content)
    result = import_erp_file(stored["path"])
    result["uploaded_path"] = stored["path"]
    result["uploaded_size_bytes"] = stored["size_bytes"]
    result["uploaded_updated_at"] = stored["updated_at"]
    return result


def preview_erp_file(file_path: str) -> Dict[str, Any]:
    source = _resolve_candidate_file_path(file_path)
    payload = _load_json_file(source)
    active_path = _resolve_json_path()
    active = active_path.resolve(strict=False)
    active_payload = _load_existing_erp_payload()
    active_meta = _extract_catalog_meta(active_payload)
    deployed_source = _resolve_deployed_source_path(_extract_catalog_meta(_load_existing_erp_payload()))
    resolved_source = source.resolve(strict=False)
    active_source = _stringify(active_meta.get("source_path"))
    source_stat = source.stat()
    compared_to_path = _stringify(active_meta.get("source_path"))
    compared_to_name = _stringify(active_meta.get("source_name"))

    if not compared_to_path and active_path.is_file():
        compared_to_path = str(active_path)
    if not compared_to_name and active_path.is_file():
        compared_to_name = active_path.name

    return _build_preview_summary(
        payload,
        source_path=str(source),
        source_name=source.name,
        source_size_bytes=source_stat.st_size,
        source_updated_at=datetime.fromtimestamp(source_stat.st_mtime, tz=timezone.utc).isoformat(),
        is_active=resolved_source == active
        or bool(active_source and Path(active_source).resolve(strict=False) == resolved_source),
        is_deployed_source=bool(deployed_source and resolved_source == deployed_source.resolve(strict=False)),
        current_index=load_erp_index(),
        compared_to_path=compared_to_path,
        compared_to_name=compared_to_name,
    )


def list_erp_files() -> List[Dict[str, Any]]:
    active_path = _resolve_json_path()
    active = active_path.resolve(strict=False)
    deployed_source = _resolve_deployed_source_path(_extract_catalog_meta(_load_existing_erp_payload()))
    seen: dict[Path, Path] = {}

    for root in _resolve_erp_source_dirs():
        if not root.is_dir():
            continue
        for pattern in DISCOVERY_PATTERNS:
            for item in root.glob(pattern):
                if not item.is_file():
                    continue
                seen[item.resolve(strict=False)] = item

    if active_path.is_file():
        seen[active] = active_path
    if deployed_source and deployed_source.is_file():
        seen[deployed_source.resolve(strict=False)] = deployed_source

    files: List[Dict[str, Any]] = []
    for resolved, item in seen.items():
        stat = item.stat()
        files.append(
            {
                "path": str(item),
                "name": item.name,
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "is_active": resolved == active,
                "is_deployed_source": bool(
                    deployed_source and resolved == deployed_source.resolve(strict=False)
                ),
            }
        )

    active_payload, _, remote_missing, active_uri, remote_updated_at = _load_active_erp_snapshot()
    if active_uri and not remote_missing:
        active_meta = _extract_catalog_meta(active_payload)
        files.append(
            {
                "path": active_uri,
                "name": active_uri.rsplit("/", 1)[-1],
                "size_bytes": int(active_meta.get("source_size_bytes") or 0),
                "updated_at": remote_updated_at or _stringify(active_meta.get("updated_at")) or "",
                "is_active": True,
                "is_deployed_source": False,
                "source_path": _stringify(active_meta.get("source_path")) or None,
            }
        )

    files.sort(key=lambda entry: entry["updated_at"], reverse=True)
    return files


def _normalize_active_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    return {"products": _extract_records(payload)}


def _load_active_erp_snapshot() -> tuple[Dict[str, Any], str | None, bool, str | None, str | None]:
    """Return active payload, remote ETag, remote-missing flag, URI, and update time."""
    active_uri = storage_uri()
    if active_uri:
        remote = load_remote_erp()
        if remote is not None:
            return (
                _normalize_active_payload(_parse_json_bytes(remote.content)),
                remote.etag,
                False,
                active_uri,
                remote.updated_at,
            )

    source = _resolve_json_path()
    if source.is_file():
        payload = _normalize_active_payload(_load_json_file(source))
        updated_at = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc).isoformat()
        return payload, None, bool(active_uri), active_uri, updated_at
    return {}, None, bool(active_uri), active_uri, None


def _load_existing_erp_payload() -> Dict[str, Any]:
    payload, _, _, _, _ = _load_active_erp_snapshot()
    return payload


def _write_erp_products(
    products: List[Dict[str, Any]],
    base_payload: Dict[str, Any] | None = None,
    *,
    imported_at: str | None = None,
    deployment_source: Dict[str, Any] | None = None,
    persist_change_summary: bool = False,
    expected_remote_etag: str | None = None,
    expected_remote_missing: bool = False,
) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    stored_payload: Dict[str, Any] = {}

    for key, value in (base_payload or {}).items():
        if key in PRODUCT_CONTAINER_KEYS or key == CATALOG_META_KEY:
            continue
        stored_payload[key] = value

    existing_meta = _extract_catalog_meta(base_payload or {})
    catalog_meta = dict(existing_meta)
    current_index = load_erp_index() if persist_change_summary else {}
    next_index = {str(product.get("Codigo")): product for product in products if _stringify(product.get("Codigo"))}
    catalog_meta["imported_at"] = imported_at or _stringify(existing_meta.get("imported_at")) or timestamp
    catalog_meta["updated_at"] = timestamp
    if deployment_source:
        catalog_meta.update(
            {
                "source_path": str(deployment_source.get("source_path") or "").strip(),
                "source_name": str(deployment_source.get("source_name") or "").strip(),
                "source_updated_at": str(deployment_source.get("source_updated_at") or "").strip(),
            }
        )
        parsed_size = _safe_int(deployment_source.get("source_size_bytes"))
        if parsed_size is not None:
            catalog_meta["source_size_bytes"] = parsed_size
    if persist_change_summary:
        current_path = _stringify(existing_meta.get("source_path"))
        current_name = _stringify(existing_meta.get("source_name"))
        active_path = _resolve_json_path()
        if not current_path and active_path.is_file():
            current_path = str(active_path)
        if not current_name and active_path.is_file():
            current_name = active_path.name
        catalog_meta["last_change_summary"] = _build_change_summary(
            next_index,
            current_index,
            compared_to_path=current_path,
            compared_to_name=current_name,
        )

    stored_payload["imported_at"] = catalog_meta["imported_at"]
    stored_payload["updated_at"] = timestamp
    stored_payload["products"] = sort_products_by_category(products)
    stored_payload[CATALOG_META_KEY] = catalog_meta

    serialized_payload = json.dumps(stored_payload, ensure_ascii=False, indent=2).encode("utf-8")
    remote_uri = storage_uri()
    if remote_uri:
        write_remote_erp(
            serialized_payload,
            expected_etag=expected_remote_etag,
            expected_missing=expected_remote_missing,
        )
        target_label = remote_uri
    else:
        target = _resolve_json_target_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_bytes(target, serialized_payload)
        target_label = str(target)
    _invalidate_catalog_response_caches()

    return {
        "path": target_label,
        "products_imported": len(stored_payload["products"]),
        "products_loaded": len(stored_payload["products"]),
        "imported_at": stored_payload["imported_at"],
        "updated_at": timestamp,
        "source_path": _stringify(catalog_meta.get("source_path")),
        "source_name": _stringify(catalog_meta.get("source_name")),
        "source_size_bytes": catalog_meta.get("source_size_bytes"),
        "source_updated_at": _stringify(catalog_meta.get("source_updated_at")) or None,
        "last_change_summary": catalog_meta.get("last_change_summary"),
    }


def list_erp_products() -> Dict[str, Any]:
    payload, _, _, active_uri, remote_updated_at = _load_active_erp_snapshot()
    products = sort_products_by_category(list(load_erp_index().values()))
    meta = _extract_catalog_meta(payload)
    source = _resolve_json_path()
    active_path = active_uri or str(source)
    exists = bool(payload)
    updated_at = remote_updated_at or _stringify(meta.get("updated_at")) or None
    return {
        "path": active_path,
        "exists": exists,
        "products_loaded": len(products),
        "imported_at": _stringify(meta.get("imported_at")) or None,
        "updated_at": updated_at,
        "source_path": _stringify(meta.get("source_path")) or None,
        "source_name": _stringify(meta.get("source_name")) or None,
        "source_size_bytes": meta.get("source_size_bytes"),
        "source_updated_at": _stringify(meta.get("source_updated_at")) or None,
        "last_change_summary": meta.get("last_change_summary"),
        "products": products,
    }


def upsert_erp_product(product: Dict[str, Any], code: str | None = None) -> Dict[str, Any]:
    if not isinstance(product, dict):
        raise ValueError("invalid ERP product payload")

    payload = dict(product)
    normalized_code = _normalize_code(code) or _normalize_code(payload.get("Codigo"))
    if not normalized_code:
        raise ValueError("product code is required")

    payload["Codigo"] = normalized_code
    normalized = _normalize_erp_record(payload)
    if not normalized:
        raise ValueError("invalid ERP product payload")

    with _ERP_MUTATION_LOCK:
        existing_payload, etag, remote_expected_missing, _, _ = _load_active_erp_snapshot()
        try:
            index = _build_index(existing_payload)
        except ValueError:
            index = {}
        created = normalized_code not in index
        index[normalized_code] = normalized

        result = _write_erp_products(
            list(index.values()),
            base_payload=existing_payload,
            expected_remote_etag=etag,
            expected_remote_missing=remote_expected_missing,
        )
    result["code"] = normalized_code
    result["created"] = created
    result["product"] = normalized
    return result


def load_erp_index() -> Dict[str, Dict[str, Any]]:
    try:
        payload = _load_existing_erp_payload()
    except Exception:
        return {}

    try:
        return _build_index(payload)
    except ValueError:
        return {}


def get_erp_status() -> Dict[str, Any]:
    payload, _, _, active_uri, remote_updated_at = _load_active_erp_snapshot()
    index = load_erp_index()
    meta = _extract_catalog_meta(payload)
    source = _resolve_json_path()
    return {
        "path": active_uri or str(source),
        "exists": bool(payload),
        "products_loaded": len(index),
        "imported_at": _stringify(meta.get("imported_at")) or None,
        "updated_at": remote_updated_at or _stringify(meta.get("updated_at")) or None,
        "source_path": _stringify(meta.get("source_path")) or None,
        "source_name": _stringify(meta.get("source_name")) or None,
        "source_size_bytes": meta.get("source_size_bytes"),
        "source_updated_at": _stringify(meta.get("source_updated_at")) or None,
        "last_change_summary": meta.get("last_change_summary"),
    }


def _placeholder_urls(code: str) -> tuple[str, str]:
    safe_code = quote(str(code), safe="")
    return (
        f"https://placehold.co/900x700?text=Sem+Imagem+{safe_code}",
        f"https://placehold.co/240x240?text=Sem+foto+{safe_code}",
    )


def _merge_single_product(base: Dict[str, Any], erp: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    code = str(erp.get("Codigo") or base.get("Codigo") or "").strip()

    for field in ("Nome", "Descricao", "Especificacoes"):
        value = _stringify(erp.get(field))
        if value:
            merged[field] = value

    base_category = _stringify(merged.get("Categoria"))
    erp_category = _infer_category(
        name=_stringify(erp.get("Nome")),
        description=_stringify(erp.get("Descricao")),
        fallback_category=_stringify(erp.get("Categoria")),
        dept_code=_stringify(erp.get("CODEPTO")),
        sec_code=_stringify(erp.get("CODSEC")),
    )
    if base_category and base_category.lower() != "sem categoria":
        if erp_category and not erp_category.startswith("DEPTO "):
            merged["Categoria"] = _to_business_category(
                erp_category,
                _stringify(merged.get("Nome")),
                _stringify(merged.get("Descricao")),
            )
    else:
        merged["Categoria"] = _to_business_category(
            erp_category or "Sem categoria",
            _stringify(merged.get("Nome")),
            _stringify(merged.get("Descricao")),
        )

    for field in ("URLFoto", "FotoBranco", "FotoAmbient", "FotoMedidas"):
        value = _stringify(erp.get(field))
        if value:
            merged[field] = value

    for key, value in erp.items():
        if key in merged and _stringify(merged.get(key)):
            continue
        merged[key] = value

    preferred_cover = _preferred_cover_url(
        merged.get("FotoAmbient"),
        merged.get("FotoBranco"),
        merged.get("FotoMedidas"),
        merged.get("URLFoto"),
    )
    if preferred_cover:
        merged["URLFoto"] = preferred_cover
    if not _stringify(merged.get("FotoBranco")) and preferred_cover:
        merged["FotoBranco"] = preferred_cover

    merged["Codigo"] = code
    if not _stringify(merged.get("Especificacoes")):
        merged["Especificacoes"] = resolve_technical_specs(
            code=code,
            name=_stringify(merged.get("Nome")),
            description=_stringify(merged.get("Descricao")),
            category=_stringify(merged.get("Categoria")),
            extra_fields=merged,
        )
    return merged


def _create_product_from_erp(erp: Dict[str, Any]) -> Dict[str, Any]:
    code = str(erp.get("Codigo") or "").strip()
    if not code:
        return {}

    cover_url, thumb_url = _placeholder_urls(code)
    inferred_category = _infer_category(
        name=_stringify(erp.get("Nome")),
        description=_stringify(erp.get("Descricao")),
        fallback_category=_stringify(erp.get("Categoria")),
        dept_code=_stringify(erp.get("CODEPTO")),
        sec_code=_stringify(erp.get("CODSEC")),
    )
    raw_cover_url = _stringify(erp.get("URLFoto")) or cover_url
    white_url = _stringify(erp.get("FotoBranco")) or _stringify(erp.get("URLFoto")) or thumb_url
    ambient_url = _stringify(erp.get("FotoAmbient"))
    measures_url = _stringify(erp.get("FotoMedidas"))
    preferred_cover = _preferred_cover_url(ambient_url, white_url, measures_url, raw_cover_url)

    created = {
        "Codigo": code,
        "Nome": _stringify(erp.get("Nome")) or f"Produto {code}",
        "Descricao": _stringify(erp.get("Descricao")),
        "Categoria": _to_business_category(
            inferred_category,
            _stringify(erp.get("Nome")),
            _stringify(erp.get("Descricao")),
        ),
        "Especificacoes": resolve_technical_specs(
            code=code,
            current_specs=erp.get("Especificacoes"),
            name=_stringify(erp.get("Nome")),
            description=_stringify(erp.get("Descricao")),
            category=inferred_category,
            extra_fields=erp,
        ),
        "URLFoto": preferred_cover,
        "FotoBranco": white_url or preferred_cover,
        "FotoAmbient": ambient_url,
        "FotoMedidas": measures_url,
    }

    for key, value in erp.items():
        if key not in created:
            created[key] = value

    return created


def _code_sort_key(code: str) -> tuple[int, Any]:
    text = str(code or "").strip()
    return (0, int(text)) if text.isdigit() else (1, text)


def _product_sort_key(product: Dict[str, Any]) -> tuple[Any, ...]:
    category = _stringify(product.get("Categoria")) or "Sem categoria"
    sem_categoria = _normalize_text(category) == "sem categoria"
    name = _stringify(product.get("Nome"))
    code = _normalize_code(product.get("Codigo")) or _stringify(product.get("Codigo"))
    return (
        sem_categoria,
        _normalize_text(category),
        _code_sort_key(code),
        _normalize_text(name),
    )


def sort_products_by_category(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(products, key=_product_sort_key)


def merge_products_with_erp(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    erp_index = load_erp_index()
    if not erp_index:
        return products

    strict_mode = os.getenv("CATALOG_ERP_STRICT_MODE", "true").strip().lower() not in {"0", "false", "no"}
    merged_products: List[Dict[str, Any]] = []
    seen_codes: set[str] = set()

    for product in products:
        code = _normalize_code(product.get("Codigo"))
        if code and code in erp_index:
            merged_products.append(_merge_single_product(product, erp_index[code]))
            seen_codes.add(code)
        else:
            if not strict_mode:
                merged_products.append(product)
            if code:
                seen_codes.add(code)

    missing_codes = sorted((code for code in erp_index.keys() if code not in seen_codes), key=_code_sort_key)
    for code in missing_codes:
        created = _create_product_from_erp(erp_index[code])
        if created:
            merged_products.append(created)

    normalized_categories: List[Dict[str, Any]] = []
    for item in merged_products:
        normalized = dict(item)
        normalized["Categoria"] = _to_business_category(
            _stringify(normalized.get("Categoria")),
            _stringify(normalized.get("Nome")),
            _stringify(normalized.get("Descricao")),
        )
        normalized_categories.append(normalized)

    return sort_products_by_category(normalized_categories)
