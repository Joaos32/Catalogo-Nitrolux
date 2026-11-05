"""Resource budgets shared by uploads, image downloads and exports."""

from contextlib import contextmanager
from contextvars import ContextVar
import os
import time


VERCEL_BODY_LIMIT = 4 * 1024 * 1024  # Leave room below the provider's 4.5 MB ceiling.
_deadline: ContextVar[float | None] = ContextVar("export_deadline", default=None)


class ExportLimitError(ValueError):
    pass


def on_vercel() -> bool:
    return os.getenv("VERCEL", "").strip().lower() in {"1", "true", "yes"}


def positive_limit(name: str, default: int) -> int:
    value = int(os.getenv(name) or default)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def export_byte_limit() -> int:
    value = positive_limit("CATALOG_EXPORT_MAX_BYTES", 64 * 1024 * 1024)
    return min(value, VERCEL_BODY_LIMIT) if on_vercel() else value


def check_export_budget() -> None:
    deadline = _deadline.get()
    if deadline is not None and time.monotonic() >= deadline:
        raise ExportLimitError("A exportação excedeu o tempo disponível. Filtre menos produtos e tente novamente.")


def network_timeout(default: float) -> float:
    check_export_budget()
    deadline = _deadline.get()
    return max(.1, min(default, deadline - time.monotonic())) if deadline is not None else default


def check_export_size(size: int) -> None:
    check_export_budget()
    if size > export_byte_limit():
        raise ExportLimitError("A exportação excedeu o tamanho disponível. Filtre menos produtos e tente novamente.")


@contextmanager
def export_budget():
    seconds = positive_limit("CATALOG_EXPORT_MAX_SECONDS", 45)
    if on_vercel():
        seconds = min(seconds, 45)
    token = _deadline.set(time.monotonic() + seconds)
    try:
        yield
        check_export_budget()
    finally:
        _deadline.reset(token)
