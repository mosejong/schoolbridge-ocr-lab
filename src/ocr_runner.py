from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from pytesseract import TesseractNotFoundError

from .config import configure_tesseract
from .image_preprocess import PreprocessImage
from .utils import ensure_dir, write_text


class OcrEnvironmentError(RuntimeError):
    """Raised when Tesseract or pytesseract cannot run locally."""


@dataclass(frozen=True)
class OcrResult:
    name: str
    text: str
    text_path: Path
    image_path: Path
    status: str
    error: str | None = None


def run_ocr_for_images(
    images: list[PreprocessImage],
    ocr_results_dir: Path,
    lang: str,
) -> list[OcrResult]:
    ensure_dir(ocr_results_dir)
    _ensure_tesseract_available()

    results: list[OcrResult] = []
    for item in images:
        if not item.run_ocr:
            continue

        text_path = ocr_results_dir / f"{item.name}.txt"
        try:
            text = pytesseract.image_to_string(
                _prepare_for_tesseract(item.image),
                lang=lang,
                config=item.tesseract_config,
            )
        except TesseractNotFoundError as exc:
            raise OcrEnvironmentError(_tesseract_help_message()) from exc
        except RuntimeError as exc:
            message = str(exc)
            if "Failed loading language" in message or "Error opening data file" in message:
                raise OcrEnvironmentError(
                    f"Tesseract language data could not be loaded for lang='{lang}'.\n"
                    "Install the needed .traineddata files or choose another --lang value.\n"
                    "For Korean OCR, make sure kor.traineddata exists in tessdata.\n"
                    "If tessdata is in a custom location, set OCR_TESSDATA_PREFIX in .env."
                ) from exc
            text = ""
            write_text(text_path, f"[OCR_RUNTIME_ERROR]\n{message}\n")
            results.append(
                OcrResult(
                    name=item.name,
                    text=text,
                    text_path=text_path,
                    image_path=item.path,
                    status="runtime_error",
                    error=message,
                )
            )
            continue

        write_text(text_path, text)
        results.append(
            OcrResult(
                name=item.name,
                text=text,
                text_path=text_path,
                image_path=item.path,
                status="ok",
            )
        )
    return results


def _ensure_tesseract_available() -> None:
    config = configure_tesseract()
    if config.tesseract_cmd:
        configured_path = Path(config.tesseract_cmd)
        if not configured_path.exists():
            raise OcrEnvironmentError(
                "OCR_TESSERACT_CMD is set, but the file does not exist:\n"
                f"  {configured_path}\n\n"
                + _tesseract_help_message()
            )
        pytesseract.pytesseract.tesseract_cmd = str(configured_path)
        return

    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        return

    if os.environ.get("TESSDATA_PREFIX") and shutil.which("tesseract") is None:
        raise OcrEnvironmentError(_tesseract_help_message())

    raise OcrEnvironmentError(_tesseract_help_message())


def _prepare_for_tesseract(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return image


def _tesseract_help_message() -> str:
    return (
        "Tesseract executable was not found on PATH.\n"
        "Install Tesseract OCR, add the install directory to PATH, then reopen PowerShell.\n"
        "After setup, verify with: tesseract --version\n\n"
        "If PATH is not available, create a local .env file like this:\n"
        "  OCR_TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe\n"
        "  OCR_TESSDATA_PREFIX=C:\\Program Files\\Tesseract-OCR\\tessdata"
    )
