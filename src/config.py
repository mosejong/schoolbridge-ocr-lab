from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytesseract


@dataclass(frozen=True)
class OcrConfig:
    tesseract_cmd: str | None = None
    tessdata_prefix: str | None = None


def load_ocr_config(env_path: Path | None = None) -> OcrConfig:
    values = _read_env_file(env_path or Path.cwd() / ".env")

    tesseract_cmd = (
        os.environ.get("OCR_TESSERACT_CMD")
        or values.get("OCR_TESSERACT_CMD")
        or None
    )
    tessdata_prefix = (
        os.environ.get("OCR_TESSDATA_PREFIX")
        or values.get("OCR_TESSDATA_PREFIX")
        or None
    )

    if tessdata_prefix:
        os.environ["TESSDATA_PREFIX"] = tessdata_prefix

    return OcrConfig(
        tesseract_cmd=tesseract_cmd,
        tessdata_prefix=tessdata_prefix,
    )


def configure_tesseract(env_path: Path | None = None) -> OcrConfig:
    config = load_ocr_config(env_path)

    if config.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
        return config

    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    return config


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
