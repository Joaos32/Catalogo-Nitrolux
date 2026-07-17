import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


LOCAL_TMP_ROOT = ROOT_DIR / "reports" / ".pytest_tmp_local"
LOCAL_TMP_ROOT.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("CATALOG_SKIP_DOTENV", "true")
os.environ.setdefault("CATALOG_ADMIN_USERS_FILE", str(LOCAL_TMP_ROOT / "disabled-admin-users.json"))
os.environ.setdefault("CATALOG_REPRESENTATIVE_USERS_FILE", str(LOCAL_TMP_ROOT / "disabled-representative-users.json"))
os.environ.setdefault("CATALOG_SESSION_SECRET", "pytest-session-secret")

# Mantem os temporarios do pytest dentro do proprio projeto para evitar
# problemas com diretorios globais bloqueados em ambientes Windows.
for env_key in ("TMP", "TEMP", "TMPDIR", "PYTEST_DEBUG_TEMPROOT"):
    os.environ.setdefault(env_key, str(LOCAL_TMP_ROOT))


@pytest.fixture
def tmp_path():
    path = LOCAL_TMP_ROOT / f"case-{uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolate_runtime_environment(monkeypatch, tmp_path):
    for env_key in (
        "CATALOG_LOCAL_PRODUCTS_PATH",
        "CATALOG_CADASTRO_HTML",
        "CATALOG_STOCK_REPORT_PATH",
        "CATALOG_STOCK_PHOTOS_ROOT",
        "CATALOG_S3_MEDIA_BUCKET",
        "CATALOG_S3_MEDIA_PREFIX",
        "CATALOG_S3_MEDIA_PUBLIC_BASE_URL",
        "CATALOG_S3_MEDIA_PRESIGNED_URLS",
        "CATALOG_S3_MEDIA_PRESIGNED_EXPIRES_SECONDS",
        "CATALOG_GOOGLE_DRIVE_FOLDER_ID",
        "CATALOG_GOOGLE_DRIVE_API_KEY",
        "CATALOG_GOOGLE_DRIVE_RECURSIVE",
        "CATALOG_GOOGLE_DRIVE_MAX_DEPTH",
        "CATALOG_ERP_JSON_PATH",
        "CATALOG_ERP_INBOX_DIR",
        "CATALOG_ERP_SOURCE_DIRS",
        "CATALOG_ERP_ADMIN_TOKEN",
        "CATALOG_ALLOW_OPEN_ADMIN",
        "CATALOG_ERP_MAX_UPLOAD_BYTES",
        "CATALOG_ADMIN_USERS_FILE",
        "CATALOG_ADMIN_LOGIN_EMAIL",
        "CATALOG_ADMIN_LOGIN_PASSWORD",
        "CATALOG_REPRESENTATIVE_LOGIN_EMAIL",
        "CATALOG_REPRESENTATIVE_LOGIN_PASSWORD",
        "CATALOG_REPRESENTATIVE_LOGIN_NAME",
        "CATALOG_REPRESENTATIVE_USERS_JSON",
        "CATALOG_REPRESENTATIVE_USERS_FILE",
        "CATALOG_REPRESENTATIVE_JWT_SECRET",
        "CATALOG_REPRESENTATIVE_JWT_EXPIRES_MINUTES",
        "CATALOG_SESSION_SECRET",
        "CATALOG_SESSION_MAX_AGE_SECONDS",
        "CATALOG_NITROLUX_DB_ENABLED",
        "CATALOG_NITROLUX_DB_URL",
        "CATALOG_NITROLUX_DB_HOST",
        "CATALOG_NITROLUX_DB_PORT",
        "CATALOG_NITROLUX_DB_NAME",
        "CATALOG_NITROLUX_DB_USER",
        "CATALOG_NITROLUX_DB_PASSWORD",
        "CATALOG_NITROLUX_DB_SSLMODE",
        "CATALOG_NITROLUX_DB_SCHEMA",
        "CATALOG_NITROLUX_DB_TABLE",
        "CATALOG_NITROLUX_DB_CODE_COLUMN",
        "CATALOG_NITROLUX_DB_PACKAGE_COLUMN",
        "CATALOG_NITROLUX_DB_MASTER_BOX_COLUMN",
        "CATALOG_ENABLE_API_DOCS",
        "CATALOG_EXPORT_MAX_REMOTE_IMAGE_BYTES",
        "OneDrive",
        "OneDriveCommercial",
        "OneDriveConsumer",
    ):
        monkeypatch.delenv(env_key, raising=False)

    monkeypatch.setenv("CATALOG_ERP_AUTO_DISCOVERY", "false")
    monkeypatch.setenv("CATALOG_ALLOW_OPEN_ADMIN", "true")
    monkeypatch.setenv("CATALOG_SKIP_DOTENV", "true")
    monkeypatch.setenv("CATALOG_ADMIN_USERS_FILE", str(tmp_path / "disabled-admin-users.json"))
    monkeypatch.setenv("CATALOG_REPRESENTATIVE_USERS_FILE", str(tmp_path / "disabled-representative-users.json"))
    monkeypatch.setenv("CATALOG_SESSION_SECRET", "pytest-session-secret")
    monkeypatch.setenv("CATALOG_STOCK_REPORT_AUTO_DISCOVERY", "false")
    monkeypatch.setenv("CATALOG_LOCAL_PRODUCTS_HOME_FALLBACK", "false")
    monkeypatch.setenv("CATALOG_STOCK_PHOTOS_HOME_FALLBACK", "false")
    monkeypatch.setenv(
        "CATALOG_ERP_JSON_PATH",
        str(LOCAL_TMP_ROOT / "disabled-erp.json"),
    )

    from catalog.cache import cache
    from catalog.auth import _AUTH_FAILURES

    cache.store.clear()
    _AUTH_FAILURES.clear()
    yield
    cache.store.clear()
    _AUTH_FAILURES.clear()
