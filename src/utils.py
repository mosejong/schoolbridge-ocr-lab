from __future__ import annotations

import re
from pathlib import Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_stem(path: Path) -> str:
    stem = path.stem.strip() or "image"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem)


def write_text(path: Path, text: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    return path


def relative_or_absolute(path: Path, base: Path | None = None) -> str:
    try:
        if base is not None:
            return str(path.resolve().relative_to(base.resolve()))
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())
