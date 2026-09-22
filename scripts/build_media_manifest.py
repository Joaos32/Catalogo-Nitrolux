"""Gera o manifesto de imagens usado pelo catalogo e pelo CDN."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
ROOT_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--prefix", default="produtos/")
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "reports" / "media_manifest.json")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"Pasta de fotos nao encontrada: {source}")
    prefix = f"{args.prefix.replace('\\', '/').strip('/')}/"
    images = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        images.append(
            {
                "key": prefix + path.relative_to(source).as_posix(),
                "name": path.name,
                "size": path.stat().st_size,
            }
        )

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"version": 1, "images": images}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Manifesto: {output}")
    print(f"Imagens: {len(images)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
