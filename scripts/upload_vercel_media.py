"""Envia as fotos locais do catalogo ao Vercel Blob privado conectado ao projeto."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from vercel.blob import iter_objects, upload_file


ROOT_DIR = Path(__file__).resolve().parents[1]
MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _load_environment() -> None:
    load_dotenv(ROOT_DIR / ".env", override=False)
    load_dotenv(ROOT_DIR / ".env.local", override=True)


def _media_prefix() -> str:
    value = str(os.getenv("CATALOG_MEDIA_BLOB_PREFIX") or "catalogo/media/")
    return f"{value.replace('\\', '/').strip('/')}/"


def _source_files(source_root: Path, *, recursive: bool = True) -> list[Path]:
    candidates = source_root.rglob("*") if recursive else source_root.iterdir()
    return sorted(path for path in candidates if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Executa os uploads; sem isto apenas mostra o resumo.")
    parser.add_argument("--workers", type=int, default=4, help="Quantidade de uploads simultaneos.")
    parser.add_argument("--source", help="Substitui CATALOG_STOCK_PHOTOS_ROOT para esta execucao.")
    parser.add_argument(
        "--top-level-only",
        action="store_true",
        help="Envia apenas arquivos diretamente na raiz, ignorando subpastas.",
    )
    args = parser.parse_args()

    _load_environment()
    token = str(os.getenv("CATALOG_MEDIA_BLOB_TOKEN") or os.getenv("BLOB_READ_WRITE_TOKEN") or "").strip()
    source_value = str(args.source or os.getenv("CATALOG_STOCK_PHOTOS_ROOT") or "").strip()
    source_root = Path(source_value).expanduser().resolve() if source_value else None
    if not token:
        raise SystemExit("Token do Vercel Blob nao encontrado em .env.local.")
    if source_root is None or not source_root.is_dir():
        raise SystemExit("CATALOG_STOCK_PHOTOS_ROOT nao aponta para uma pasta valida.")

    files = _source_files(source_root, recursive=not args.top_level_only)
    total_bytes = sum(path.stat().st_size for path in files)
    print(f"Fonte: {source_root}")
    print(f"Arquivos: {len(files)} ({total_bytes / 1024 / 1024:.1f} MiB)")

    prefix = _media_prefix()
    existing = {str(blob.pathname): int(blob.size or 0) for blob in iter_objects(prefix=prefix, token=token, batch_size=1000)}
    pending: list[tuple[Path, str]] = []
    skipped = 0
    new_files = 0
    changed_files = 0
    for path in files:
        pathname = prefix + path.relative_to(source_root).as_posix()
        if existing.get(pathname) == path.stat().st_size:
            skipped += 1
        else:
            pending.append((path, pathname))
            if pathname in existing:
                changed_files += 1
            else:
                new_files += 1

    pending_bytes = sum(path.stat().st_size for path, _ in pending)
    print(
        f"Ja sincronizados: {skipped}; a enviar: {len(pending)} "
        f"({pending_bytes / 1024 / 1024:.1f} MiB)"
    )
    print(f"Novos: {new_files}; versoes diferentes a substituir: {changed_files}")
    if not args.apply:
        print("Simulacao concluida. Use --apply para enviar.")
        return 0

    def upload(item: tuple[Path, str]) -> str:
        local_path, pathname = item
        content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        upload_file(
            local_path,
            pathname,
            access="private",
            content_type=content_type,
            overwrite=True,
            cache_control_max_age=3600,
            token=token,
            multipart=local_path.stat().st_size > 4 * 1024 * 1024,
        )
        return pathname

    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(upload, item) for item in pending]
        for future in as_completed(futures):
            future.result()
            completed += 1
            if completed % 25 == 0 or completed == len(pending):
                print(f"Enviados: {completed}/{len(pending)}")

    print(f"Sincronizacao concluida: {skipped + completed}/{len(files)} arquivos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
