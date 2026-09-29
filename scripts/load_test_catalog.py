"""Bounded load runner for catalog reads, local searches, and export downloads.

The catalog is downloaded once per simulated user; product filtering is then
measured in-process because that is how the browser performs its searches.
Export requests exercise the API's actual download path.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import math
import os
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx


MAX_USERS = 200
REMOTE_USER_LIMIT = 20
SUPPORTED_FORMATS = {"csv", "xlsx", "json", "pdf", "ficha", "zip"}
CATALOG_PATH = "/catalog/local/produtos"
EXPORT_PATH = "/catalog/export"


@dataclass(frozen=True)
class Sample:
    operation: str
    elapsed_ms: float
    status_code: int
    response_bytes: int
    ok: bool
    matches: int = 0


def parse_user_levels(value: str) -> list[int]:
    try:
        levels = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError("user levels must be positive integers") from exc

    if not levels or any(level <= 0 for level in levels):
        raise ValueError("user levels must be positive integers")
    if levels != sorted(set(levels)):
        raise ValueError("user levels must be unique and strictly increasing")
    if levels[-1] > MAX_USERS:
        raise ValueError(f"the absolute maximum is {MAX_USERS} users")
    return levels


def _is_loopback(hostname: str) -> bool:
    normalized = hostname.strip("[]").casefold()
    if normalized in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def validate_target(
    base_url: str,
    levels: list[int],
    formats: list[str],
    *,
    allow_remote: bool,
    allow_high_load: bool,
    allow_remote_zip: bool,
) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("credentials must not be embedded in the base URL")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("base URL must contain only the scheme and host")

    loopback = _is_loopback(parsed.hostname)
    if not loopback and not allow_remote:
        raise ValueError("remote targets require --allow-remote")
    if not loopback and parsed.scheme != "https":
        raise ValueError("remote targets must use HTTPS")
    if not loopback and max(levels) > REMOTE_USER_LIMIT and not allow_high_load:
        raise ValueError(
            f"remote loads above {REMOTE_USER_LIMIT} users require --allow-high-load"
        )
    if not loopback and "zip" in formats and not allow_remote_zip:
        raise ValueError("remote ZIP downloads require --allow-remote-zip")


def _normalize_search_text(value: object) -> str:
    decomposed = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def local_search_count(products: list[dict], query: str) -> int:
    normalized_query = _normalize_search_text(query).strip()
    if not normalized_query:
        return len(products)

    fields = ("Nome", "Produto", "Codigo", "CODPROD", "Descricao", "Categoria")
    return sum(
        normalized_query
        in _normalize_search_text(" ".join(str(product.get(field) or "") for field in fields))
        for product in products
    )


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 2)


def _field(product: dict, names: tuple[str, ...]) -> str:
    for name in names:
        value = str(product.get(name) or "").strip()
        if value:
            return value
    return ""


async def _measured_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    operation: str,
    samples: list[Sample],
    params: dict[str, str] | None = None,
) -> httpx.Response | None:
    started = time.perf_counter()
    try:
        response = await client.get(path, params=params)
        samples.append(
            Sample(
                operation=operation,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                status_code=response.status_code,
                response_bytes=len(response.content),
                ok=response.status_code < 400,
            )
        )
        return response
    except httpx.HTTPError as exc:
        # Keep reports useful without recording URLs, credentials, or response bodies.
        samples.append(
            Sample(
                operation=operation,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                status_code=0,
                response_bytes=0,
                ok=False,
            )
        )
        print(f"{operation}: request failed ({type(exc).__name__})", file=sys.stderr)
        return None


def _search_terms(product: dict) -> list[str]:
    name = _field(product, ("Nome", "Produto", "Descricao"))
    category = _field(product, ("Categoria", "Tipo"))
    code = _field(product, ("Codigo", "CODPROD", "Code"))
    first_name_word = next(iter(name.split()), name)
    return [term for term in (first_name_word, category, code) if term]


async def _run_user(
    user_number: int,
    users: int,
    duration_seconds: float,
    think_time_seconds: float,
    formats: list[str],
    client: httpx.AsyncClient,
    samples: list[Sample],
) -> None:
    deadline = time.perf_counter() + duration_seconds
    response = await _measured_get(
        client,
        CATALOG_PATH,
        operation="catalog_load",
        samples=samples,
    )
    if response is None or response.status_code != 200:
        return

    try:
        products = response.json()
    except ValueError:
        samples.append(Sample("catalog_parse", 0, response.status_code, 0, False))
        return
    if not isinstance(products, list) or not products:
        samples.append(Sample("catalog_parse", 0, response.status_code, 0, False))
        return

    product = products[(user_number * 97) % len(products)]
    if not isinstance(product, dict):
        samples.append(Sample("catalog_parse", 0, response.status_code, 0, False))
        return

    code = _field(product, ("Codigo", "CODPROD", "Code"))
    terms = _search_terms(product)
    if not code or not terms:
        samples.append(Sample("catalog_selection", 0, response.status_code, 0, False))
        return

    cycle = 0
    while time.perf_counter() < deadline:
        cycle_started = time.perf_counter()
        for query in terms:
            started = time.perf_counter()
            matches = local_search_count(products, query)
            samples.append(
                Sample(
                    operation="client_search",
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                    status_code=200,
                    response_bytes=0,
                    ok=True,
                    matches=matches,
                )
            )

        selected_format = formats[(user_number + cycle) % len(formats)]
        await _measured_get(
            client,
            EXPORT_PATH,
            operation=f"download_{selected_format}",
            samples=samples,
            params={"format": selected_format, "code": code},
        )
        cycle += 1
        remaining = think_time_seconds - (time.perf_counter() - cycle_started)
        if remaining > 0:
            await asyncio.sleep(min(remaining, max(0, deadline - time.perf_counter())))


def _summarize_stage(users: int, elapsed: float, samples: list[Sample]) -> dict:
    grouped: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.operation].append(sample)

    operations = {}
    for operation, operation_samples in sorted(grouped.items()):
        latencies = [sample.elapsed_ms for sample in operation_samples]
        operations[operation] = {
            "count": len(operation_samples),
            "successes": sum(sample.ok for sample in operation_samples),
            "errors": sum(not sample.ok for sample in operation_samples),
            "statuses": {
                str(status): sum(sample.status_code == status for sample in operation_samples)
                for status in sorted({sample.status_code for sample in operation_samples})
            },
            "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
            "p99_ms": percentile(latencies, 0.99),
            "max_ms": round(max(latencies, default=0), 2),
            "response_bytes": sum(sample.response_bytes for sample in operation_samples),
            "search_matches": sum(sample.matches for sample in operation_samples),
        }

    http_samples = [sample for sample in samples if sample.operation != "client_search"]
    http_count = len(http_samples)
    return {
        "users": users,
        "elapsed_seconds": round(elapsed, 2),
        "http_requests": http_count,
        "http_requests_per_second": round(http_count / elapsed, 2) if elapsed else 0,
        "http_errors": sum(not sample.ok for sample in http_samples),
        "http_4xx": sum(400 <= sample.status_code < 500 for sample in http_samples),
        "http_5xx": sum(sample.status_code >= 500 for sample in http_samples),
        "downloaded_mb": round(sum(sample.response_bytes for sample in http_samples) / 1024**2, 3),
        "operations": operations,
    }


def _print_stage(report: dict) -> None:
    print(
        f"{report['users']:>3} users | {report['http_requests_per_second']:>6.2f} HTTP req/s | "
        f"{report['http_errors']} errors | {report['downloaded_mb']:.2f} MB received"
    )
    for operation, summary in report["operations"].items():
        if operation == "client_search":
            print(
                f"  {operation}: {summary['count']} searches, "
                f"p95 {summary['p95_ms']:.2f} ms, {summary['search_matches']} matches"
            )
        else:
            print(
                f"  {operation}: {summary['successes']}/{summary['count']} OK, "
                f"p95 {summary['p95_ms']:.2f} ms, {summary['response_bytes']} bytes"
            )


async def _authenticate(client: httpx.AsyncClient) -> None:
    token = os.getenv("CATALOG_LOAD_TOKEN", "").strip()
    email = os.getenv("CATALOG_LOAD_EMAIL", "").strip()
    password = os.getenv("CATALOG_LOAD_PASSWORD", "")
    if token and (email or password):
        raise ValueError("set either CATALOG_LOAD_TOKEN or CATALOG_LOAD_EMAIL/PASSWORD, not both")
    if bool(email) != bool(password):
        raise ValueError("set both CATALOG_LOAD_EMAIL and CATALOG_LOAD_PASSWORD")

    if not token and email and password:
        try:
            response = await client.post(
                "/auth/representative/login",
                json={"email": email, "password": password},
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"representative login request failed ({type(exc).__name__})") from exc
        if response.status_code != 200:
            raise RuntimeError(f"representative login failed: HTTP {response.status_code}")
        token = str(response.json().get("access_token") or "").strip()
        if not token:
            raise RuntimeError("representative login response did not contain an access token")

    if token:
        client.headers["Authorization"] = f"Bearer {token}"


async def run_benchmark(args: argparse.Namespace, levels: list[int], formats: list[str]) -> list[dict]:
    max_users = max(levels)
    limits = httpx.Limits(
        max_connections=max_users,
        max_keepalive_connections=max_users,
    )
    timeout = httpx.Timeout(args.timeout)
    reports = []

    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=timeout,
        limits=limits,
    ) as client:
        await _authenticate(client)
        try:
            preflight = await client.get(CATALOG_PATH)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"catalog preflight failed ({type(exc).__name__})") from exc
        if preflight.status_code == 401:
            raise RuntimeError(
                "catalog requires representative authentication; set CATALOG_LOAD_TOKEN "
                "or CATALOG_LOAD_EMAIL and CATALOG_LOAD_PASSWORD"
            )
        if preflight.status_code != 200:
            raise RuntimeError(f"catalog preflight failed: HTTP {preflight.status_code}")
        try:
            products = preflight.json()
        except ValueError as exc:
            raise RuntimeError("catalog preflight returned invalid JSON") from exc
        if not isinstance(products, list) or not products:
            raise RuntimeError("catalog preflight returned no products")

        print(f"Catalog loaded: {len(products)} products; formats: {', '.join(formats)}")
        for users in levels:
            samples: list[Sample] = []
            stage_started = time.perf_counter()
            tasks = [
                asyncio.create_task(
                    _run_user(
                        user_number,
                        users,
                        args.duration,
                        args.think_time,
                        formats,
                        client,
                        samples,
                    )
                )
                for user_number in range(users)
            ]
            await asyncio.gather(*tasks)
            elapsed = time.perf_counter() - stage_started
            report = _summarize_stage(users, elapsed, samples)
            reports.append(report)
            _print_stage(report)

    return reports


def _parse_formats(value: str) -> list[str]:
    formats = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not formats:
        raise ValueError("select at least one export format")
    invalid = sorted(set(formats) - SUPPORTED_FORMATS)
    if invalid:
        raise ValueError(f"unsupported export formats: {', '.join(invalid)}")
    return list(dict.fromkeys(formats))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="catalog API origin")
    parser.add_argument(
        "--users",
        default="1,5,10,20",
        help="increasing concurrency levels, e.g. 1,5,10,20",
    )
    parser.add_argument("--duration", type=float, default=10, help="seconds at each concurrency level (max 300)")
    parser.add_argument("--think-time", type=float, default=1, help="minimum seconds between downloads per user")
    parser.add_argument("--timeout", type=float, default=15, help="HTTP request timeout in seconds")
    parser.add_argument("--formats", default="csv,pdf", help="comma-separated export formats")
    parser.add_argument("--allow-remote", action="store_true", help="allow a non-loopback HTTPS target")
    parser.add_argument(
        "--allow-high-load",
        action="store_true",
        help=f"allow remote stages above {REMOTE_USER_LIMIT} users (max {MAX_USERS})",
    )
    parser.add_argument(
        "--allow-remote-zip",
        action="store_true",
        help="allow remote ZIP downloads, which can call external media providers",
    )
    parser.add_argument("--json-output", type=Path, help="optional path for a JSON report")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        levels = parse_user_levels(args.users)
        formats = _parse_formats(args.formats)
        validate_target(
            args.base_url,
            levels,
            formats,
            allow_remote=args.allow_remote,
            allow_high_load=args.allow_high_load,
            allow_remote_zip=args.allow_remote_zip,
        )
        if not 0 < args.duration <= 300:
            raise ValueError("duration must be greater than 0 and at most 300 seconds")
        if args.think_time < 0.1:
            raise ValueError("think time must be at least 0.1 seconds")
        if not 0 < args.timeout <= 60:
            raise ValueError("timeout must be greater than 0 and at most 60 seconds")
        reports = asyncio.run(run_benchmark(args, levels, formats))
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        print(f"JSON report written to {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
