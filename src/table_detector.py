from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .image_preprocess import PreprocessImage
from .utils import ensure_dir


@dataclass(frozen=True)
class TableCrop:
    table_id: str
    bbox: tuple[int, int, int, int]
    area: int
    relative_area: float
    aspect_ratio: float
    text_density_estimate: float
    is_too_small: bool
    is_too_large: bool
    is_header_like: bool
    is_low_text_density: bool
    filter_reason: str | None
    candidate_priority_score: float
    is_candidate: bool
    image_path: Path
    zoom2x_path: Path
    zoom3x_path: Path


@dataclass(frozen=True)
class TableDetectionResult:
    tables: list[TableCrop]
    ocr_images: list[PreprocessImage]
    warnings: list[str]
    horizontal_lines_path: Path
    vertical_lines_path: Path
    table_line_mask_path: Path
    table_boxes_path: Path
    crop_images: dict[str, np.ndarray]


def detect_table_crops(
    image: np.ndarray,
    table_crops_dir: Path,
    debug_dir: Path,
    padding: int = 20,
    min_width: int = 100,
    min_height: int = 40,
) -> TableDetectionResult:
    ensure_dir(table_crops_dir)
    ensure_dir(debug_dir)

    warnings: list[str] = []
    horizontal, vertical, line_mask = _build_table_line_masks(image)

    horizontal_path = debug_dir / "09_horizontal_lines.png"
    vertical_path = debug_dir / "10_vertical_lines.png"
    line_mask_path = debug_dir / "11_table_line_mask.png"
    boxes_path = debug_dir / "12_table_boxes.png"

    _write_image(horizontal_path, horizontal)
    _write_image(vertical_path, vertical)
    _write_image(line_mask_path, line_mask)

    boxes = _find_table_boxes(
        line_mask=line_mask,
        image_shape=image.shape,
        min_width=min_width,
        min_height=min_height,
    )

    if not boxes:
        warnings.append("No table or box candidates were detected.")

    annotated = image.copy()
    crops: list[TableCrop] = []
    ocr_images: list[PreprocessImage] = []
    crop_images: dict[str, np.ndarray] = {}

    for index, bbox in enumerate(boxes, start=1):
        table_id = f"table_{index:03d}"
        x, y, width, height = _apply_padding(bbox, image.shape, padding)
        crop = image[y : y + height, x : x + width]
        candidate_info = _score_candidate_geometry(
            bbox=(x, y, width, height),
            crop=crop,
            image_shape=image.shape,
            min_width=min_width,
            min_height=min_height,
        )

        image_path = table_crops_dir / f"{table_id}.png"
        zoom2x_path = table_crops_dir / f"{table_id}_zoom2x.png"
        zoom3x_path = table_crops_dir / f"{table_id}_zoom3x.png"

        zoom2x = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        zoom3x = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

        _write_image(image_path, crop)
        _write_image(zoom2x_path, zoom2x)
        _write_image(zoom3x_path, zoom3x)

        crop_images[table_id] = crop

        crops.append(
            TableCrop(
                table_id=table_id,
                bbox=(x, y, width, height),
                area=candidate_info["area"],
                relative_area=candidate_info["relative_area"],
                aspect_ratio=candidate_info["aspect_ratio"],
                text_density_estimate=candidate_info["text_density_estimate"],
                is_too_small=candidate_info["is_too_small"],
                is_too_large=candidate_info["is_too_large"],
                is_header_like=candidate_info["is_header_like"],
                is_low_text_density=candidate_info["is_low_text_density"],
                filter_reason=candidate_info["filter_reason"],
                candidate_priority_score=candidate_info["candidate_priority_score"],
                is_candidate=candidate_info["is_candidate"],
                image_path=image_path,
                zoom2x_path=zoom2x_path,
                zoom3x_path=zoom3x_path,
            )
        )
        ocr_images.extend(
            [
                PreprocessImage(name=table_id, image=crop, path=image_path),
                PreprocessImage(name=f"{table_id}_psm6", image=crop, path=image_path, tesseract_config="--psm 6"),
                PreprocessImage(name=f"{table_id}_psm11", image=crop, path=image_path, tesseract_config="--psm 11"),
                PreprocessImage(
                    name=f"{table_id}_url_config",
                    image=crop,
                    path=image_path,
                    tesseract_config=(
                        "--psm 6 "
                        "-c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:/.-_"
                    ),
                ),
                PreprocessImage(name=f"{table_id}_zoom2x", image=zoom2x, path=zoom2x_path),
                PreprocessImage(name=f"{table_id}_zoom2x_psm6", image=zoom2x, path=zoom2x_path, tesseract_config="--psm 6"),
                PreprocessImage(name=f"{table_id}_zoom2x_psm11", image=zoom2x, path=zoom2x_path, tesseract_config="--psm 11"),
                PreprocessImage(
                    name=f"{table_id}_zoom2x_url_config",
                    image=zoom2x,
                    path=zoom2x_path,
                    tesseract_config=(
                        "--psm 6 "
                        "-c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:/.-_"
                    ),
                ),
                PreprocessImage(name=f"{table_id}_zoom3x", image=zoom3x, path=zoom3x_path),
            ]
        )

        cv2.rectangle(annotated, (x, y), (x + width, y + height), (0, 0, 255), 3)
        cv2.putText(
            annotated,
            table_id,
            (x, max(y - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    _write_image(boxes_path, annotated)

    return TableDetectionResult(
        tables=crops,
        ocr_images=ocr_images,
        warnings=warnings,
        horizontal_lines_path=horizontal_path,
        vertical_lines_path=vertical_path,
        table_line_mask_path=line_mask_path,
        table_boxes_path=boxes_path,
        crop_images=crop_images,
    )


def _build_table_line_masks(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )

    height, width = binary.shape[:2]
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 25, 30), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(height // 25, 30)))

    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    line_mask = cv2.add(horizontal, vertical)
    line_mask = cv2.dilate(
        line_mask,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        iterations=2,
    )
    return horizontal, vertical, line_mask


def _score_candidate_geometry(
    bbox: tuple[int, int, int, int],
    crop: np.ndarray,
    image_shape: tuple[int, ...],
    min_width: int,
    min_height: int,
) -> dict:
    x, y, width, height = bbox
    image_height, image_width = image_shape[:2]
    image_area = image_width * image_height
    area = width * height
    relative_area = area / image_area if image_area else 0.0
    aspect_ratio = width / height if height else 0.0
    text_density = _estimate_text_density(crop)

    is_too_small = width < min_width or height < min_height or relative_area < 0.003
    is_too_large = relative_area > 0.8
    is_header_like = y < image_height * 0.20 and text_density < 0.08
    is_low_text_density = text_density < 0.015

    reasons: list[str] = []
    if is_too_small:
        reasons.append("too_small")
    if is_too_large:
        reasons.append("too_large")
    if is_header_like:
        reasons.append("header_or_logo_like")
    if is_low_text_density:
        reasons.append("low_text_density")

    score = 0.0
    score += min(relative_area * 100, 8)
    score += min(text_density * 80, 8)
    if 1.2 <= aspect_ratio <= 8:
        score += 2
    if is_header_like:
        score -= 4
    if is_too_small:
        score -= 5
    if is_too_large:
        score -= 6
    if is_low_text_density:
        score -= 3

    return {
        "area": area,
        "relative_area": relative_area,
        "aspect_ratio": aspect_ratio,
        "text_density_estimate": text_density,
        "is_too_small": is_too_small,
        "is_too_large": is_too_large,
        "is_header_like": is_header_like,
        "is_low_text_density": is_low_text_density,
        "filter_reason": ", ".join(reasons) if reasons else None,
        "candidate_priority_score": score,
        "is_candidate": not (is_too_small or is_too_large or is_header_like or is_low_text_density),
    }


def _estimate_text_density(crop: np.ndarray) -> float:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )
    return float(cv2.countNonZero(binary)) / float(binary.size) if binary.size else 0.0


def _find_table_boxes(
    line_mask: np.ndarray,
    image_shape: tuple[int, ...],
    min_width: int,
    min_height: int,
) -> list[tuple[int, int, int, int]]:
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_height, image_width = image_shape[:2]
    image_area = image_width * image_height

    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = width * height
        if width < min_width or height < min_height:
            continue
        if area < image_area * 0.003:
            continue
        if area > image_area * 0.8:
            continue
        boxes.append((x, y, width, height))

    boxes = _merge_overlapping_boxes(boxes)
    boxes = _remove_contained_boxes(boxes)
    return sorted(boxes, key=lambda box: (box[1], box[0]))[:10]


def _merge_overlapping_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    for box in sorted(boxes, key=lambda item: item[2] * item[3], reverse=True):
        did_merge = False
        for index, existing in enumerate(merged):
            if _iou(box, existing) > 0.25 or _nearby(box, existing):
                merged[index] = _union(box, existing)
                did_merge = True
                break
        if not did_merge:
            merged.append(box)
    return merged


def _remove_contained_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    result: list[tuple[int, int, int, int]] = []
    for box in boxes:
        if any(_contains(other, box) for other in boxes if other != box):
            continue
        result.append(box)
    return result


def _apply_padding(
    bbox: tuple[int, int, int, int],
    image_shape: tuple[int, ...],
    padding: int,
) -> tuple[int, int, int, int]:
    x, y, width, height = bbox
    image_height, image_width = image_shape[:2]
    left = max(x - padding, 0)
    top = max(y - padding, 0)
    right = min(x + width + padding, image_width)
    bottom = min(y + height + padding, image_height)
    return left, top, right - left, bottom - top


def _contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return ox <= ix and oy <= iy and ox + ow >= ix + iw and oy + oh >= iy + ih


def _nearby(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    expanded_a = (ax - 12, ay - 12, aw + 24, ah + 24)
    return _iou(expanded_a, b) > 0.05


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x_left = max(ax, bx)
    y_top = max(ay, by)
    x_right = min(ax + aw, bx + bw)
    y_bottom = min(ay + ah, by + bh)
    if x_right <= x_left or y_bottom <= y_top:
        return 0.0
    intersection = (x_right - x_left) * (y_bottom - y_top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union else 0.0


def _union(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x = min(ax, bx)
    y = min(ay, by)
    right = max(ax + aw, bx + bw)
    bottom = max(ay + ah, by + bh)
    return x, y, right - x, bottom - y


def _write_image(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image):
        raise ValueError(f"OpenCV could not write image: {path}")
