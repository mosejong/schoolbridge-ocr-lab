from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import cv2
import numpy as np
import pytesseract

from .config import configure_tesseract
from .utils import ensure_dir


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class PreprocessImage:
    name: str
    image: np.ndarray
    path: Path
    run_ocr: bool = True
    tesseract_config: str = ""


@dataclass(frozen=True)
class RotationCandidate:
    name: str
    debug_image_path: Path
    score: float
    text_length: int
    error: str | None = None


@dataclass(frozen=True)
class PreprocessResult:
    images: list[PreprocessImage]
    perspective_applied: bool
    perspective_note: str
    rotation_candidates: list[RotationCandidate]
    best_rotation: str
    rotation_score: float
    rotation_note: str


def load_image(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Only JPG and PNG images are supported in phase 1.")

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"OpenCV could not read image: {path}")
    return image


def build_preprocessed_images(
    image: np.ndarray,
    debug_dir: Path,
    lang: str = "kor+eng",
) -> PreprocessResult:
    ensure_dir(debug_dir)

    rotation_images = _build_rotation_images(image)
    rotation_candidates, best_rotation, rotation_note = _select_best_rotation(
        rotation_images=rotation_images,
        debug_dir=debug_dir,
        lang=lang,
    )
    base_image = rotation_images[best_rotation].copy()

    original = base_image.copy()
    gray = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    adaptive = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        11,
    )
    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contrast_enhanced = _enhance_contrast(gray)
    sharpened = _sharpen(contrast_enhanced)
    warped, perspective_applied, perspective_note = _try_perspective_transform(base_image)

    variants = [
        ("original", "01_original.png", original, True),
        ("grayscale", "02_grayscale.png", gray, True),
        ("denoised", "03_denoised.png", denoised, False),
        ("adaptive_threshold", "04_adaptive_threshold.png", adaptive, True),
        ("otsu_threshold", "05_otsu_threshold.png", otsu, True),
        ("contrast_enhanced", "06_contrast_enhanced.png", contrast_enhanced, True),
        ("sharpened", "07_sharpened.png", sharpened, True),
        ("warped", "08_warped.png", warped, True),
    ]

    saved_images: list[PreprocessImage] = []
    for name, filename, variant, run_ocr in variants:
        path = debug_dir / filename
        if not cv2.imwrite(str(path), variant):
            raise ValueError(f"OpenCV could not write debug image: {path}")
        saved_images.append(PreprocessImage(name=name, image=variant, path=path, run_ocr=run_ocr))

    return PreprocessResult(
        images=saved_images,
        perspective_applied=perspective_applied,
        perspective_note=perspective_note,
        rotation_candidates=rotation_candidates,
        best_rotation=best_rotation,
        rotation_score=max((candidate.score for candidate in rotation_candidates), default=0.0),
        rotation_note=rotation_note,
    )


def _build_rotation_images(image: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "rotation_0": image.copy(),
        "rotation_90_cw": cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
        "rotation_180": cv2.rotate(image, cv2.ROTATE_180),
        "rotation_90_ccw": cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
    }


def _select_best_rotation(
    rotation_images: dict[str, np.ndarray],
    debug_dir: Path,
    lang: str,
) -> tuple[list[RotationCandidate], str, str]:
    candidates: list[RotationCandidate] = []
    can_run_ocr = _prepare_rotation_ocr()

    for name, candidate_image in rotation_images.items():
        debug_path = debug_dir / f"{name}.png"
        if not cv2.imwrite(str(debug_path), candidate_image):
            raise ValueError(f"OpenCV could not write rotation candidate: {debug_path}")

        if not can_run_ocr:
            candidates.append(
                RotationCandidate(
                    name=name,
                    debug_image_path=debug_path,
                    score=0.0,
                    text_length=0,
                    error="Rotation OCR skipped because Tesseract is not configured.",
                )
            )
            continue

        try:
            text = pytesseract.image_to_string(
                _prepare_quick_ocr_image(candidate_image),
                lang=lang,
                config="--psm 6",
            )
            score = _score_rotation_text(text)
            candidates.append(
                RotationCandidate(
                    name=name,
                    debug_image_path=debug_path,
                    score=score,
                    text_length=len(text),
                )
            )
        except Exception as exc:  # Rotation selection must never stop the full pipeline.
            candidates.append(
                RotationCandidate(
                    name=name,
                    debug_image_path=debug_path,
                    score=0.0,
                    text_length=0,
                    error=str(exc),
                )
            )

    valid_candidates = [candidate for candidate in candidates if candidate.error is None]
    if not valid_candidates:
        return candidates, "rotation_0", "Rotation OCR failed; original orientation was used."

    best = max(valid_candidates, key=lambda candidate: candidate.score)
    if best.score <= 0:
        return candidates, "rotation_0", "Rotation scores were not useful; original orientation was used."
    return candidates, best.name, "Best rotation selected by quick OCR scoring."


def _prepare_rotation_ocr() -> bool:
    config = configure_tesseract()
    if config.tesseract_cmd:
        return Path(config.tesseract_cmd).exists()
    return bool(pytesseract.pytesseract.tesseract_cmd)


def _prepare_quick_ocr_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    max_side = max(height, width)
    if max_side > 1400:
        scale = 1400 / max_side
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return gray


def _score_rotation_text(text: str) -> float:
    hangul_count = len(re.findall(r"[\uac00-\ud7a3]", text))
    digit_count = len(re.findall(r"\d", text))
    date_count = len(re.findall(r"\d{4}\s*[.\-/]\s*\d{1,2}", text))
    phone_count = len(re.findall(r"\d{2,4}[-\s]\d{3,4}[-\s]\d{4}", text))
    url_count = len(re.findall(r"https?://|www\.|bit\.ly", text, flags=re.IGNORECASE))
    korean_word_count = len(re.findall(r"[\uac00-\ud7a3]{2,}", text))
    replacement_count = text.count("?")

    return (
        hangul_count * 2.0
        + korean_word_count * 3.0
        + digit_count * 0.8
        + date_count * 8.0
        + phone_count * 8.0
        + url_count * 12.0
        - replacement_count * 0.5
    )


def _sharpen(gray: np.ndarray) -> np.ndarray:
    kernel = np.array(
        [
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0],
        ],
        dtype=np.float32,
    )
    return cv2.filter2D(gray, -1, kernel)


def _enhance_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _try_perspective_transform(image: np.ndarray) -> tuple[np.ndarray, bool, str]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    image_area = image.shape[0] * image.shape[1]
    candidates = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

    for contour in candidates:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        area = cv2.contourArea(approx)
        if len(approx) == 4 and area > image_area * 0.15:
            warped = _four_point_transform(image, approx.reshape(4, 2))
            return warped, True, "Perspective transform applied."

    return image.copy(), False, "No reliable document quadrilateral found; original image was used."


def _four_point_transform(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    rect = _order_points(points.astype("float32"))
    top_left, top_right, bottom_right, bottom_left = rect

    width_a = np.linalg.norm(bottom_right - bottom_left)
    width_b = np.linalg.norm(top_right - top_left)
    max_width = max(int(width_a), int(width_b), 1)

    height_a = np.linalg.norm(top_right - bottom_right)
    height_b = np.linalg.norm(top_left - bottom_left)
    max_height = max(int(height_a), int(height_b), 1)

    destination = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype="float32",
    )

    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def _order_points(points: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    point_sum = points.sum(axis=1)
    point_diff = np.diff(points, axis=1)

    rect[0] = points[np.argmin(point_sum)]
    rect[2] = points[np.argmax(point_sum)]
    rect[1] = points[np.argmin(point_diff)]
    rect[3] = points[np.argmax(point_diff)]
    return rect
