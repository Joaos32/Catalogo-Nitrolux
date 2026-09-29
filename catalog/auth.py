import base64
import hashlib
import hmac
import json
import os
import logging
import secrets
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from msal import ConfidentialClientApplication, SerializableTokenCache
from dotenv import load_dotenv

from catalog.core import load_settings
from catalog.admin_registry import list_admin_login_users, verify_admin_password
from catalog.admin_access import require_admin_host
from catalog.representative_registry import (
    list_representative_login_users,
    representative_login_storage_is_configured,
    reset_representative_password_with_code,
    verify_representative_password,
)

# Carrega variaveis de ambiente do .env, se existir.
if os.getenv("CATALOG_SKIP_DOTENV", "").strip().lower() not in {"1", "true", "yes", "on"}:
    load_dotenv()
logger = logging.getLogger(__name__)

# Constantes de ambiente.
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
REDIRECT_URI = os.getenv("AZURE_REDIRECT_URI")

# Determina se as credenciais sao realmente utilizaveis; valores de placeholder
# como "seu-tenant-id" ou vazios devem desabilitar a autenticacao.
AUTH_CONFIGURED = all([CLIENT_ID, CLIENT_SECRET, TENANT_ID, REDIRECT_URI])
if AUTH_CONFIGURED:
    # Validacao simples para evitar valores ficticios evidentes.
    for val in (CLIENT_ID, CLIENT_SECRET, TENANT_ID):
        if "seu" in val.lower() or val.lower() == "none":
            AUTH_CONFIGURED = False
            break

if not AUTH_CONFIGURED:
    # A autenticacao sera desativada; chamadores devem tratar EnvironmentError.
    AUTHORITY = None
else:
    AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

SCOPES = ["Files.Read", "offline_access"]
STATE_COOKIE_NAME = "catalog_oauth_state"
ADMIN_SESSION_KEY = "admin_auth"
POST_LOGIN_PATH_SESSION_KEY = "admin_post_login_path"
DEFAULT_ADMIN_REDIRECT_PATH = "/erp"
REPRESENTATIVE_ROLE = "representative"
REPRESENTATIVE_COOKIE_NAME = "catalog_rep_session"
AUTH_RATE_LIMIT_WINDOW_SECONDS = 300
AUTH_RATE_LIMIT_MAX_ATTEMPTS = 10
AUTH_RATE_LIMIT_MAX_KEYS = 4096
AUTH_RATE_LIMIT_GLOBAL_PRUNE_SECONDS = 30
_AUTH_FAILURES: OrderedDict[str, list[float]] = OrderedDict()
_AUTH_FAILURES_LOCK = threading.Lock()
_AUTH_FAILURES_LAST_PRUNE = 0.0


def _resolve_cache_file() -> str:
    explicit = os.getenv("CATALOG_TOKEN_CACHE_FILE", "").strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))

    app_data_root = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if app_data_root:
        return os.path.join(app_data_root, "catalogo", "token_cache.bin")
    return os.path.join(os.path.expanduser("~"), ".catalogo", "token_cache.bin")


def _ensure_cache_directory() -> None:
    cache_dir = os.path.dirname(CACHE_FILE)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)


def _cache_cookie_secure() -> bool:
    return bool(REDIRECT_URI and REDIRECT_URI.lower().startswith("https://"))


def _request_cookie_secure(request: Request) -> bool:
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"
    return request.url.scheme == "https"


def _sanitize_next_path(value: str | None) -> str:
    candidate = str(value or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return DEFAULT_ADMIN_REDIRECT_PATH
    return candidate


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def _client_rate_limit_ip(request: Request) -> str:
    if str(os.getenv("VERCEL") or "").strip().lower() in {"1", "true", "yes"}:
        try:
            from vercel.functions import ip_address

            platform_ip = str(ip_address(request) or "").strip()
            if platform_ip:
                return platform_ip
        except Exception:
            logger.debug("Vercel request IP helper is unavailable; using the ASGI client address")

    try:
        trusted_proxy_hops = max(0, int(os.getenv("CATALOG_AUTH_TRUSTED_PROXY_HOPS", "0")))
    except ValueError:
        trusted_proxy_hops = 0
    forwarded_for = [
        item.strip()
        for item in str(request.headers.get("x-forwarded-for") or "").split(",")
        if item.strip()
    ]
    if trusted_proxy_hops and len(forwarded_for) > trusted_proxy_hops:
        return forwarded_for[-trusted_proxy_hops - 1]
    return request.client.host if request.client else "unknown"


def _rate_limit_keys(request: Request, scope: str, identity: str) -> tuple[str, str]:
    normalized_identity = str(identity or "").strip().lower() or "unknown"
    client_ip = _client_rate_limit_ip(request)
    return (
        f"{scope}:ip:{client_ip}",
        f"{scope}:identity:{normalized_identity[:320]}",
    )


def _shared_rate_limit_bucket_key(key: str, bucket: int) -> str:
    message = f"{key}:{bucket}".encode("utf-8")
    return hmac.new(
        _representative_jwt_secret().encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def _prune_auth_failures(key: str, now: float | None = None) -> list[float]:
    global _AUTH_FAILURES_LAST_PRUNE
    timestamp = now if now is not None else time.time()
    cutoff = timestamp - AUTH_RATE_LIMIT_WINDOW_SECONDS
    with _AUTH_FAILURES_LOCK:
        if timestamp - _AUTH_FAILURES_LAST_PRUNE >= AUTH_RATE_LIMIT_GLOBAL_PRUNE_SECONDS:
            for stored_key, stored_attempts in list(_AUTH_FAILURES.items()):
                active_attempts = [item for item in stored_attempts if item >= cutoff]
                if active_attempts:
                    _AUTH_FAILURES[stored_key] = active_attempts
                else:
                    _AUTH_FAILURES.pop(stored_key, None)
            _AUTH_FAILURES_LAST_PRUNE = timestamp

        attempts = [item for item in _AUTH_FAILURES.get(key, []) if item >= cutoff]
        if attempts:
            _AUTH_FAILURES[key] = attempts
            _AUTH_FAILURES.move_to_end(key)
        else:
            _AUTH_FAILURES.pop(key, None)
        return attempts


def _check_auth_rate_limit(request: Request, scope: str, identity: str) -> tuple[str, str]:
    keys = _rate_limit_keys(request, scope, identity)
    table_name = str(os.getenv("CATALOG_AUTH_RATE_LIMIT_TABLE") or "").strip()
    if table_name:
        window = AUTH_RATE_LIMIT_WINDOW_SECONDS
        bucket = int(time.time()) // window
        try:
            import boto3

            client = boto3.client("dynamodb")
            for key in keys:
                result = client.get_item(
                    TableName=table_name,
                    Key={"bucket_key": {"S": _shared_rate_limit_bucket_key(key, bucket)}},
                    ConsistentRead=True,
                )
                attempts = int(result.get("Item", {}).get("attempts", {}).get("N", "0"))
                if attempts >= AUTH_RATE_LIMIT_MAX_ATTEMPTS:
                    raise HTTPException(status_code=429, detail="Too many authentication attempts")
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            logger.exception("Shared authentication rate-limit storage is unavailable")
            raise HTTPException(status_code=503, detail="Authentication is temporarily unavailable") from exc
        return keys

    if any(len(_prune_auth_failures(key)) >= AUTH_RATE_LIMIT_MAX_ATTEMPTS for key in keys):
        raise HTTPException(status_code=429, detail="Too many authentication attempts")
    return keys


def _record_auth_failure(keys: tuple[str, ...]) -> None:
    now = time.time()
    table_name = str(os.getenv("CATALOG_AUTH_RATE_LIMIT_TABLE") or "").strip()
    if table_name:
        window = AUTH_RATE_LIMIT_WINDOW_SECONDS
        bucket = int(now) // window
        try:
            import boto3

            client = boto3.client("dynamodb")
            for key in keys:
                client.update_item(
                    TableName=table_name,
                    Key={"bucket_key": {"S": _shared_rate_limit_bucket_key(key, bucket)}},
                    UpdateExpression="SET expires_at = :expires ADD attempts :one",
                    ConditionExpression="attribute_not_exists(attempts) OR attempts < :max",
                    ExpressionAttributeValues={
                        ":expires": {"N": str((bucket + 2) * window)},
                        ":one": {"N": "1"},
                        ":max": {"N": str(AUTH_RATE_LIMIT_MAX_ATTEMPTS)},
                    },
                )
        except Exception as exc:
            error_response = getattr(exc, "response", {})
            error_code = str(error_response.get("Error", {}).get("Code") or "")
            if error_code == "ConditionalCheckFailedException":
                raise HTTPException(status_code=429, detail="Too many authentication attempts") from exc
            logger.exception("Unable to record an authentication failure")
            raise HTTPException(status_code=503, detail="Authentication is temporarily unavailable") from exc
        return

    cutoff = now - AUTH_RATE_LIMIT_WINDOW_SECONDS
    with _AUTH_FAILURES_LOCK:
        for key in keys:
            attempts = [
                item
                for item in _AUTH_FAILURES.get(key, [])
                if item >= cutoff
            ]
            if len(attempts) >= AUTH_RATE_LIMIT_MAX_ATTEMPTS:
                raise HTTPException(status_code=429, detail="Too many authentication attempts")
            attempts.append(now)
            if key not in _AUTH_FAILURES and len(_AUTH_FAILURES) >= AUTH_RATE_LIMIT_MAX_KEYS:
                _AUTH_FAILURES.popitem(last=False)
            _AUTH_FAILURES[key] = attempts
            _AUTH_FAILURES.move_to_end(key)


def _clear_auth_failures(keys: tuple[str, ...]) -> None:
    table_name = str(os.getenv("CATALOG_AUTH_RATE_LIMIT_TABLE") or "").strip()
    if table_name:
        bucket = int(time.time()) // AUTH_RATE_LIMIT_WINDOW_SECONDS
        try:
            import boto3

            client = boto3.client("dynamodb")
            for key in keys:
                client.delete_item(
                    TableName=table_name,
                    Key={"bucket_key": {"S": _shared_rate_limit_bucket_key(key, bucket)}},
                )
        except Exception:
            logger.warning("Unable to clear an authentication rate-limit counter", exc_info=True)
        return
    with _AUTH_FAILURES_LOCK:
        for key in keys:
            _AUTH_FAILURES.pop(key, None)


def _admin_login_capabilities() -> dict[str, bool]:
    settings = load_settings()
    admin_users = _admin_password_users()
    return {
        "password_login_available": bool(admin_users),
        "password_login_requires_email": bool(admin_users and any(user["email"] != "admin" for user in admin_users)),
        "azure_login_available": AUTH_CONFIGURED,
        "protection_enabled": bool(admin_users or AUTH_CONFIGURED),
    }


def is_admin_login_configured() -> bool:
    return bool(_admin_password_users() or AUTH_CONFIGURED)


def _admin_password_users() -> list[dict[str, object]]:
    users_by_email: dict[str, dict[str, object]] = {}
    representative_users = list_representative_login_users()
    managed_representative_emails = {
        str(user["email"]).strip().lower()
        for user in representative_users
        if user.get("managed")
    }
    for user in representative_users:
        if not user.get("is_admin"):
            continue
        users_by_email[user["email"]] = {**user, "admin_source": "representative_registry"}
    for user in list_admin_login_users():
        if user["email"] in managed_representative_emails:
            continue
        users_by_email.setdefault(user["email"], {**user, "admin_source": "admin_registry"})
    return list(users_by_email.values())


def _request_session(request: Request) -> dict:
    if "session" not in request.scope:
        return {}
    return request.session


def is_admin_session_authenticated(request: Request) -> bool:
    session = _request_session(request)
    payload = session.get(ADMIN_SESSION_KEY)
    return bool(isinstance(payload, dict) and payload.get("authenticated"))


def _get_admin_session_payload(request: Request) -> dict:
    session = _request_session(request)
    payload = session.get(ADMIN_SESSION_KEY)
    return payload if isinstance(payload, dict) else {}


def _mark_admin_session(request: Request, provider: str, email: str = "") -> None:
    request.session[ADMIN_SESSION_KEY] = {
        "authenticated": True,
        "provider": provider,
        "email": email,
        "logged_in_at": datetime.now(timezone.utc).isoformat(),
    }


def _clear_admin_session(request: Request) -> None:
    request.session.pop(ADMIN_SESSION_KEY, None)
    request.session.pop(POST_LOGIN_PATH_SESSION_KEY, None)


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _parse_representative_users() -> list[dict[str, str]]:
    users = list_representative_login_users()
    return [
        {
            "email": str(user["email"]),
            "name": str(user["name"]),
            "password": str(user.get("password") or ""),
            "password_hash": str(user.get("password_hash") or ""),
        }
        for user in users
    ]


def is_representative_login_configured() -> bool:
    # A exigencia explicita de login deve proteger o catalogo mesmo quando o
    # cadastro de representantes estiver em um armazenamento externo ainda
    # indisponivel durante o cold start do deploy. Sem essa verificacao, um
    # deploy sem o arquivo local de usuarios acabava ficando aberto.
    settings = load_settings()
    return settings.representative_login_required or representative_login_storage_is_configured()


def _representative_login_capabilities() -> dict[str, bool]:
    login_available = representative_login_storage_is_configured()
    return {
        "login_available": login_available,
        "protection_enabled": is_representative_login_configured(),
    }


def _representative_jwt_secret() -> str:
    settings = load_settings()
    return settings.representative_jwt_secret or settings.session_secret


def _representative_jwt_expires_seconds() -> int:
    configured_idle_minutes = os.getenv("CATALOG_REPRESENTATIVE_IDLE_TIMEOUT_MINUTES", "").strip()
    minutes = max(
        int(configured_idle_minutes or load_settings().representative_jwt_expires_minutes),
        1,
    )
    return minutes * 60


def _sign_representative_token(message: str) -> str:
    digest = hmac.new(
        _representative_jwt_secret().encode("utf-8"),
        message.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _urlsafe_b64encode(digest)


def _build_representative_token(user: dict[str, str]) -> tuple[str, dict[str, object]]:
    now = int(time.time())
    expires_in = _representative_jwt_expires_seconds()
    claims: dict[str, object] = {
        "sub": user["email"],
        "email": user["email"],
        "name": user["name"],
        "role": REPRESENTATIVE_ROLE,
        "credential_version": str(
            user.get("_credential_version") or _representative_credential_version(user)
        ),
        "iat": now,
        "nbf": now,
        "exp": now + expires_in,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signed_message = f"{encoded_header}.{encoded_payload}"
    return f"{signed_message}.{_sign_representative_token(signed_message)}", claims


def _decode_representative_token(token: str) -> dict[str, object]:
    parts = str(token or "").split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("invalid token format")

    encoded_header, encoded_payload, provided_signature = parts
    signed_message = f"{encoded_header}.{encoded_payload}"
    expected_signature = _sign_representative_token(signed_message)
    if not secrets.compare_digest(provided_signature, expected_signature):
        raise ValueError("invalid token signature")

    try:
        header = json.loads(_urlsafe_b64decode(encoded_header))
        payload = json.loads(_urlsafe_b64decode(encoded_payload))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ValueError("invalid token payload") from exc

    if not isinstance(header, dict) or header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise ValueError("invalid token header")
    if not isinstance(payload, dict):
        raise ValueError("invalid token claims")
    if payload.get("role") != REPRESENTATIVE_ROLE:
        raise ValueError("invalid token role")
    if not isinstance(payload.get("credential_version"), str):
        raise ValueError("missing representative credential version")

    now = int(time.time())
    try:
        exp = int(payload.get("exp", 0))
        nbf = int(payload.get("nbf", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid token lifetime") from exc

    if exp <= now:
        raise ValueError("token expired")
    if nbf > now:
        raise ValueError("token not active")

    return payload


def _set_representative_cookie(response: JSONResponse, request: Request, token: str) -> None:
    response.set_cookie(
        key=REPRESENTATIVE_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_request_cookie_secure(request),
        max_age=_representative_jwt_expires_seconds(),
    )


def _clear_representative_cookie(response: JSONResponse, request: Request) -> None:
    response.delete_cookie(
        REPRESENTATIVE_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=_request_cookie_secure(request),
    )


def get_representative_claims(
    request: Request,
    authorization: str | None = None,
    *,
    raise_on_invalid: bool = False,
) -> dict[str, object] | None:
    cache_key = "_catalog_representative_claims_validation"
    cached_validation = getattr(request.state, cache_key, None)
    if cached_validation is not None:
        claims, validation_error = cached_validation
        if validation_error is not None and raise_on_invalid:
            raise ValueError(str(validation_error)) from validation_error
        return claims

    provided_token = _extract_bearer_token(authorization) or request.cookies.get(REPRESENTATIVE_COOKIE_NAME)
    if not provided_token:
        setattr(request.state, cache_key, (None, None))
        return None

    try:
        claims = _decode_representative_token(provided_token)
        if not _representative_credentials_are_current(claims):
            raise ValueError("representative credentials changed or account is inactive")
        setattr(request.state, cache_key, (claims, None))
        return claims
    except Exception as exc:
        validation_error = exc if isinstance(exc, ValueError) else ValueError("unable to validate representative session")
        setattr(request.state, cache_key, (None, validation_error))
        if raise_on_invalid:
            raise ValueError(str(validation_error)) from exc
        return None


def _representative_credential_version(user: dict[str, object]) -> str:
    email = str(user.get("email") or user.get("sub") or "").strip().lower()
    credential = str(user.get("password_hash") or user.get("password") or "")
    if not email or not credential:
        return ""
    message = f"{email}\0{credential}".encode("utf-8")
    digest = hmac.new(_representative_jwt_secret().encode("utf-8"), message, hashlib.sha256).digest()
    return _urlsafe_b64encode(digest)


def _representative_credentials_are_current(claims: dict[str, object]) -> bool:
    email = str(claims.get("email") or claims.get("sub") or "").strip().lower()
    provided_version = str(claims.get("credential_version") or "")
    if not email or not provided_version:
        return False
    users = list_representative_login_users()
    current_user = next((user for user in users if user["email"] == email), None)
    if current_user is None:
        return False
    current_version = _representative_credential_version(current_user)
    return bool(current_version) and secrets.compare_digest(provided_version, current_version)


def _representative_status_payload(claims: dict[str, object] | None) -> dict[str, object]:
    capabilities = _representative_login_capabilities()
    if not claims:
        return {
            "authenticated": False,
            "provider": None,
            "expires_at": None,
            "user": None,
            **capabilities,
        }

    expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc).isoformat()
    return {
        "authenticated": True,
        "provider": "jwt",
        "expires_at": expires_at,
        "user": {
            "email": str(claims.get("email") or claims.get("sub") or ""),
            "name": str(claims.get("name") or claims.get("email") or claims.get("sub") or "Representante"),
        },
        **capabilities,
    }


CACHE_FILE = _resolve_cache_file()

# Cache de token persistido em arquivo.
token_cache = SerializableTokenCache()
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as cache_handle:
            token_cache.deserialize(cache_handle.read())
    except Exception:
        # Ignora cache corrompido.
        logger.warning("Ignoring corrupted token cache at %s", CACHE_FILE, exc_info=True)
        token_cache = SerializableTokenCache()


def _save_cache():
    if token_cache.has_state_changed:
        _ensure_cache_directory()
        with open(CACHE_FILE, "w", encoding="utf-8") as cache_handle:
            cache_handle.write(token_cache.serialize())
        try:
            os.chmod(CACHE_FILE, 0o600)
        except OSError:
            # No Windows o chmod e limitado; mantemos best-effort.
            pass


def _build_msal_app() -> ConfidentialClientApplication:
    if not AUTH_CONFIGURED:
        raise OSError("Azure credentials not set or invalid")
    return ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=token_cache,
    )


def get_access_token(scopes: List[str] = SCOPES) -> str:
    """Retorna um access token valido, adquirindo silenciosamente ou gerando 401.

    Se a autenticacao estiver desativada (sem credenciais), gera OSError para
    que o chamador use fallback com placeholders em vez de poluir logs com
    erros do MSAL.
    """
    if not AUTH_CONFIGURED:
        raise OSError("Azure credentials not configured")
    app = _build_msal_app()
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]
    raise HTTPException(status_code=401, detail="User login required")


auth_router = APIRouter()


@auth_router.get("/auth/session", dependencies=[Depends(require_admin_host)])
def auth_session_status(request: Request):
    capabilities = _admin_login_capabilities()
    payload = _get_admin_session_payload(request)
    return {
        "authenticated": bool(payload.get("authenticated")),
        "provider": payload.get("provider"),
        "email": payload.get("email"),
        "logged_in_at": payload.get("logged_in_at"),
        **capabilities,
    }


@auth_router.get("/auth/representative/session")
def representative_session_status(
    request: Request,
    authorization: str | None = Header(default=None),
):
    claims = get_representative_claims(request, authorization)
    return _representative_status_payload(claims)


@auth_router.post("/auth/representative/login")
def representative_login(request: Request, payload: dict = Body(...)):
    provided_email = str(payload.get("email") or payload.get("login") or "").strip().lower()
    provided_password = str(payload.get("password") or "").strip()

    if not provided_email:
        raise HTTPException(status_code=400, detail="Missing email")
    if not provided_password:
        raise HTTPException(status_code=400, detail="Missing password")

    rate_limit_keys = _check_auth_rate_limit(request, "representative-login", provided_email)
    users = _parse_representative_users()
    if not users:
        raise HTTPException(status_code=503, detail="Representative login not configured")

    selected_user = next((user for user in users if secrets.compare_digest(user["email"], provided_email)), None)
    if not selected_user or not verify_representative_password(selected_user, provided_password):
        _record_auth_failure(rate_limit_keys)
        raise HTTPException(status_code=403, detail="Invalid representative credentials")
    _clear_auth_failures(rate_limit_keys)

    token, claims = _build_representative_token(selected_user)
    response_payload = _representative_status_payload(claims)
    response_payload.update(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": _representative_jwt_expires_seconds(),
        }
    )
    response = JSONResponse(response_payload)
    _set_representative_cookie(response, request, token)
    return response


@auth_router.post("/auth/representative/reset-password")
def representative_reset_password(request: Request, payload: dict = Body(...)):
    provided_email = str(payload.get("email") or payload.get("login") or "").strip().lower()
    reset_code = str(payload.get("reset_code") or payload.get("code") or "").strip()
    new_password = str(payload.get("new_password") or payload.get("password") or "").strip()
    rate_limit_keys = _check_auth_rate_limit(request, "representative-reset", provided_email)

    try:
        user = reset_representative_password_with_code(provided_email, reset_code, new_password)
    except KeyError:
        _record_auth_failure(rate_limit_keys)
        raise HTTPException(status_code=400, detail="Invalid email, reset code, or new password") from None
    except ValueError as exc:
        _record_auth_failure(rate_limit_keys)
        raise HTTPException(status_code=400, detail="Invalid email, reset code, or new password") from exc
    _clear_auth_failures(rate_limit_keys)

    return {
        "success": True,
        "user": {
            "email": user["email"],
            "name": user["name"],
        },
    }


@auth_router.post("/auth/representative/logout")
def representative_logout(request: Request):
    response = JSONResponse({"success": True, "authenticated": False})
    _clear_representative_cookie(response, request)
    return response


@auth_router.post("/auth/admin/login", dependencies=[Depends(require_admin_host)])
def admin_password_login(request: Request, payload: dict = Body(...)):
    admin_users = _admin_password_users()
    if not admin_users:
        raise HTTPException(status_code=503, detail="Admin password login not configured")

    provided_password = str(payload.get("password") or payload.get("token") or "").strip()
    provided_email = str(payload.get("email") or payload.get("login") or "").strip().lower()

    requires_email = any(user["email"] != "admin" for user in admin_users)
    if requires_email and not provided_email:
        raise HTTPException(status_code=400, detail="Missing email")
    if not provided_password:
        raise HTTPException(status_code=400, detail="Missing password")

    rate_limit_keys = _check_auth_rate_limit(request, "admin-login", provided_email or "admin")
    selected_user = None
    if provided_email:
        selected_user = next((user for user in admin_users if secrets.compare_digest(user["email"], provided_email)), None)
    elif len(admin_users) == 1:
        selected_user = admin_users[0]

    if not selected_user or not verify_admin_password(selected_user, provided_password):
        _record_auth_failure(rate_limit_keys)
        raise HTTPException(status_code=403, detail="Credenciais administrativas inválidas.")
    _clear_auth_failures(rate_limit_keys)

    _mark_admin_session(request, provider="password", email=selected_user["email"])
    return auth_session_status(request)


@auth_router.post("/auth/logout", dependencies=[Depends(require_admin_host)])
def logout(request: Request):
    _clear_admin_session(request)
    response = JSONResponse({"success": True, "authenticated": False})
    _clear_representative_cookie(response, request)
    response.delete_cookie(
        STATE_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=_cache_cookie_secure(),
    )
    response.delete_cookie("catalog_admin_session", samesite="lax")
    return response


@auth_router.get("/auth/login", dependencies=[Depends(require_admin_host)])
def login(request: Request, next: str | None = None):
    try:
        app = _build_msal_app()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Azure authentication not configured") from exc
    request.session[POST_LOGIN_PATH_SESSION_KEY] = _sanitize_next_path(next)
    state = secrets.token_urlsafe(32)
    auth_url = app.get_authorization_request_url(
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI,
    )
    response = RedirectResponse(auth_url)
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state,
        httponly=True,
        samesite="lax",
        secure=_cache_cookie_secure(),
        max_age=600,
    )
    return response


@auth_router.get("/auth/callback", dependencies=[Depends(require_admin_host)])
def callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
    cookie_state = request.cookies.get(STATE_COOKIE_NAME)
    if not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    try:
        app = _build_msal_app()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Azure authentication not configured") from exc
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    _save_cache()
    if "access_token" in result:
        _mark_admin_session(request, provider="azure")
        redirect_path = _sanitize_next_path(request.session.pop(POST_LOGIN_PATH_SESSION_KEY, DEFAULT_ADMIN_REDIRECT_PATH))
        response = RedirectResponse(redirect_path, status_code=303)
        response.delete_cookie(
            STATE_COOKIE_NAME,
            httponly=True,
            samesite="lax",
            secure=_cache_cookie_secure(),
        )
        return response
    logger.warning("OAuth token exchange failed: %s", result)
    raise HTTPException(status_code=400, detail="OAuth token exchange failed")
