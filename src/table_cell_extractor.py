from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from .config import configure_tesseract
from .table_analysis import analyze_table_text, extract_patterns, score_patterns
from .utils import ensure_dir


_CELL_MIN_SIZE = 20
_MAX_CELLS = 30
_MAX_GRID_CELLS_FOR_SCORING = 20

_H_KERNEL_RATIOS = [3, 5, 8]
_V_KERNEL_RATIOS = [3, 5, 8]
# Fraction of image width (h) or height (v) that must be covered.
# Relative threshold avoids detecting short text runs as table lines.
_THRESHOLD_FRACS = [0.40, 0.30, 0.20]


@dataclass(frozen=True)
class CellOcrResult:
    row: int
    col: int
    bbox: tuple[int, int, int, int]  # x, y, w, h relative to crop image
    text: str
    patterns: dict[str, list[str]]
    ocr_variant: str = "psm6"


@dataclass(frozen=True)
class TableCellStructure:
    table_id: str
    row_count: int
    col_count: int
    cells: list[CellOcrResult]
    rows: list[list[str]]
    warnings: list[str]
    method: str  # "line_split" | "line_split_rows_only" | "line_split_cols_only" | "uniform_grid"
    line_detection: dict | None = None
    structure_hint: str | None = None
    grid_candidates: list | None = None
    selected_grid_reason: str | None = None


def extract_cells(
    table_id: str,
    crop_image: np.ndarray,
    cell_crops_dir: Path,
    lang: str = "kor+eng",
) -> TableCellStructure:
    configure_tesseract()
    ensure_dir(cell_crops_dir)

    warnings: list[str] = []
    height, width = crop_image.shape[:2]

    gray = cv2.cvtColor(crop_image, cv2.COLOR_BGR2GRAY) if len(crop_image.shape) == 3 else crop_image
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )

    h_positions, v_positions, line_params = _find_best_line_detection(binary, height, width)

    line_detection = {
        "h_lines": len(h_positions),
        "v_lines": len(v_positions),
        "selected_params": line_params,
    }

    row_boundaries = _to_boundaries(h_positions, 0, height)
    col_boundaries = _to_boundaries(v_positions, 0, width)

    h_ok = len(row_boundaries) >= 3
    v_ok = len(col_boundaries) >= 3

    method = "line_split"
    grid_candidates: list | None = None
    selected_grid_reason: str | None = None

    if h_ok and v_ok:
        method = "line_split"
    elif h_ok and not v_ok:
        n_cols = _estimate_cols_from_aspect(height, width)
        col_boundaries = [round(width * i / n_cols) for i in range(n_cols + 1)]
        method = "line_split_rows_only"
        warnings.append(
            f"Only h_lines detected ({len(h_positions)}). "
            f"Using uniform {n_cols} columns."
        )
    elif not h_ok and v_ok:
        n_rows = _estimate_rows_from_aspect(height, width)
        row_boundaries = [round(height * i / n_rows) for i in range(n_rows + 1)]
        method = "line_split_cols_only"
        warnings.append(
            f"Only v_lines detected ({len(v_positions)}). "
            f"Using uniform {n_rows} rows."
        )
    else:
        n_rows, n_cols, selected_grid_reason, grid_candidates = _best_uniform_grid(
            crop_image, height, width, lang
        )
        row_boundaries = [round(height * i / n_rows) for i in range(n_rows + 1)]
        col_boundaries = [round(width * i / n_cols) for i in range(n_cols + 1)]
        method = "uniform_grid"
        warnings.append(
            f"No interior lines detected (h={len(h_positions)}, v={len(v_positions)}). "
            f"Best grid: {n_rows}x{n_cols}."
        )

    row_count = len(row_boundaries) - 1
    col_count = len(col_boundaries) - 1

    if row_count * col_count > _MAX_CELLS:
        warnings.append(
            f"Cell count ({row_count * col_count}) exceeds limit ({_MAX_CELLS}). Truncating."
        )

    cells: list[CellOcrResult] = []
    rows: list[list[str]] = []
    cell_index = 0

    for r in range(row_count):
        y1 = row_boundaries[r]
        y2 = row_boundaries[r + 1]
        row_texts: list[str] = []

        for c in range(col_count):
            x1 = col_boundaries[c]
            x2 = col_boundaries[c + 1]
            cell_w = x2 - x1
            cell_h = y2 - y1

            if cell_index >= _MAX_CELLS:
                row_texts.append("")
                continue

            if cell_w < _CELL_MIN_SIZE or cell_h < _CELL_MIN_SIZE:
                warnings.append(
                    f"Cell {table_id}_r{r}c{c} too small ({cell_w}x{cell_h}), skipping."
                )
                cells.append(CellOcrResult(
                    row=r, col=c,
                    bbox=(x1, y1, cell_w, cell_h),
                    text="",
                    patterns=_empty_patterns(),
                    ocr_variant="skipped",
                ))
                row_texts.append("")
                cell_index += 1
                continue

            cell_crop = crop_image[y1:y2, x1:x2]
            scale = max(2.0, min(80.0 / min(cell_w, cell_h), 4.0))
            enlarged = cv2.resize(
                cell_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )

            cell_path = cell_crops_dir / f"cell_{table_id}_r{r}c{c}.png"
            try:
                cv2.imwrite(str(cell_path), enlarged)
            except Exception as exc:
                warnings.append(f"Save failed for cell_{table_id}_r{r}c{c}: {exc}")

            # Non-first columns are URL candidates (label is typically in col 0)
            is_url_candidate = c > 0
            text, variant = _ocr_cell_best(enlarged, lang, is_url_candidate)

            patterns = extract_patterns(text)
            cells.append(CellOcrResult(
                row=r, col=c,
                bbox=(x1, y1, cell_w, cell_h),
                text=text,
                patterns=patterns,
                ocr_variant=variant,
            ))
            row_texts.append(text)
            cell_index += 1

        rows.append(row_texts)

    structure_hint = _generate_structure_hint(cells)

    return TableCellStructure(
        table_id=table_id,
        row_count=row_count,
        col_count=col_count,
        cells=cells,
        rows=rows,
        warnings=warnings,
        method=method,
        line_detection=line_detection,
        structure_hint=structure_hint,
        grid_candidates=grid_candidates,
        selected_grid_reason=selected_grid_reason,
    )


# ---------------------------------------------------------------------------
# Line detection
# ---------------------------------------------------------------------------

def _find_best_line_detection(
    binary: np.ndarray, height: int, width: int
) -> tuple[list[int], list[int], dict]:
    best_h: list[int] = []
    best_v: list[int] = []
    best_params: dict = {
        "horizontal_kernel_ratio": 3,
        "vertical_kernel_ratio": 3,
        "threshold_ratio": 0.4,
    }
    best_score = -1.0

    for h_ratio in _H_KERNEL_RATIOS:
        for v_ratio in _V_KERNEL_RATIOS:
            for t_frac in _THRESHOLD_FRACS:
                h_pos = _detect_h_lines(binary, width, h_ratio, t_frac)
                v_pos = _detect_v_lines(binary, height, v_ratio, t_frac)
                h_pos = _deduplicate(h_pos)
                v_pos = _deduplicate(v_pos)
                score = _score_line_counts(len(h_pos), len(v_pos))
                if score > best_score:
                    best_score = score
                    best_h = h_pos
                    best_v = v_pos
                    best_params = {
                        "horizontal_kernel_ratio": h_ratio,
                        "vertical_kernel_ratio": v_ratio,
                        "threshold_fraction": t_frac,
                    }

    return best_h, best_v, best_params


def _score_line_counts(h: int, v: int) -> float:
    def side(n: int) -> float:
        if n == 0:
            return 0.0
        return float(min(n, 5)) - max(0, n - 5) * 0.5

    both_bonus = 2.0 if h > 0 and v > 0 else 0.0
    return side(h) + side(v) + both_bonus


def _detect_h_lines(binary: np.ndarray, width: int, ratio: int, t_frac: float) -> list[int]:
    kernel_w = max(width // ratio, 15)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, 1))
    mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)), iterations=1)
    row_counts = np.sum(mask > 0, axis=1).astype(float)
    # Relative threshold: require t_frac of image width to be covered.
    # Real table lines span most of the width; text runs are much shorter.
    threshold = max(width * t_frac, 20.0)
    return _find_run_centers(row_counts, threshold)


def _detect_v_lines(binary: np.ndarray, height: int, ratio: int, t_frac: float) -> list[int]:
    kernel_h = max(height // ratio, 12)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_h))
    mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5)), iterations=1)
    col_counts = np.sum(mask > 0, axis=0).astype(float)
    threshold = max(height * t_frac, 15.0)
    return _find_run_centers(col_counts, threshold)


# ---------------------------------------------------------------------------
# Grid candidate selection (uniform_grid fallback)
# ---------------------------------------------------------------------------

def _best_uniform_grid(
    crop_image: np.ndarray, height: int, width: int, lang: str
) -> tuple[int, int, str, list[dict]]:
    aspect = width / height if height > 0 else 1.0

    if aspect >= 2.5:
        # Wide schedule-style table: include 4-column candidates
        candidates = [(2, 2), (2, 3), (3, 4), (4, 4), (3, 3)]
    elif aspect >= 1.2:
        candidates = [(3, 3), (3, 4), (4, 3), (4, 4)]
    elif aspect >= 0.8:
        candidates = [(3, 2), (3, 3), (2, 3)]
    else:
        candidates = [(4, 2), (3, 2), (5, 2)]

    scored: list[dict] = []
    for n_rows, n_cols in candidates:
        if n_rows * n_cols > _MAX_GRID_CELLS_FOR_SCORING:
            continue
        row_b = [round(height * i / n_rows) for i in range(n_rows + 1)]
        col_b = [round(width * i / n_cols) for i in range(n_cols + 1)]

        total_patterns = 0
        total_score = 0.0
        for r in range(n_rows):
            for c in range(n_cols):
                cell = crop_image[row_b[r]:row_b[r + 1], col_b[c]:col_b[c + 1]]
                cw = col_b[c + 1] - col_b[c]
                ch = row_b[r + 1] - row_b[r]
                if cw < _CELL_MIN_SIZE or ch < _CELL_MIN_SIZE:
                    continue
                try:
                    sc = max(2.0, min(60.0 / min(cw, ch), 3.0))
                    enlarged = cv2.resize(cell, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
                    text = pytesseract.image_to_string(
                        _to_rgb(enlarged), lang=lang, config="--psm 6"
                    ).strip()
                    analysis = analyze_table_text(text)
                    total_patterns += sum(len(v) for v in analysis.patterns.values())
                    total_score += analysis.score
                except Exception:
                    pass

        scored.append({
            "grid": [n_rows, n_cols],
            "score": round(total_score, 2),
            "pattern_count": total_patterns,
        })

    if not scored:
        return 2, 2, "fallback_default", []

    best = max(scored, key=lambda x: (x["pattern_count"], x["score"]))
    n_rows, n_cols = best["grid"]
    reason = (
        f"grid_{n_rows}x{n_cols} selected: "
        f"pattern_count={best['pattern_count']}, score={best['score']}"
    )
    return n_rows, n_cols, reason, scored


# ---------------------------------------------------------------------------
# Cell OCR — multi-variant, pick best
# ---------------------------------------------------------------------------

def _ocr_cell_best(
    enlarged: np.ndarray, lang: str, is_url_candidate: bool
) -> tuple[str, str]:
    aspect = enlarged.shape[1] / enlarged.shape[0] if enlarged.shape[0] > 0 else 1.0

    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY) if len(enlarged.shape) == 3 else enlarged
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    thresh_bgr = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

    variants: list[tuple[str, np.ndarray, str]] = [
        ("psm6", enlarged, "--psm 6"),
        ("adaptive_psm6", thresh_bgr, "--psm 6"),
    ]

    if aspect >= 4.0:
        variants.append(("psm7", enlarged, "--psm 7"))

    if is_url_candidate:
        url_cfg = (
            "--psm 6 "
            "-c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:/.-_"
        )
        variants.append(("url_config", enlarged, url_cfg))

    best_text = ""
    best_variant = "psm6"
    best_combined = -1.0

    for variant_name, img, cfg in variants:
        try:
            text = pytesseract.image_to_string(_to_rgb(img), lang=lang, config=cfg).strip()
        except Exception:
            continue
        patterns = extract_patterns(text)
        pat_score = score_patterns(text, patterns)
        meaningful = sum(1 for ch in text if ch.isalpha() or ch.isdigit())
        combined = pat_score * 10.0 + meaningful * 0.1
        if combined > best_combined:
            best_combined = combined
            best_text = text
            best_variant = variant_name

    return best_text, best_variant


# ---------------------------------------------------------------------------
# Structure hint
# ---------------------------------------------------------------------------

def _generate_structure_hint(cells: list[CellOcrResult]) -> str | None:
    all_urls: list[str] = []
    all_dates: list[str] = []
    all_times: list[str] = []
    all_phones: list[str] = []

    for cell in cells:
        all_urls.extend(cell.patterns.get("urls", []))
        all_dates.extend(cell.patterns.get("dates", []))
        all_times.extend(cell.patterns.get("times", []))
        all_phones.extend(cell.patterns.get("phones", []))

    if len(all_urls) >= 2:
        return "multi_url_table_candidate"
    if len(all_urls) == 1 and len(all_dates) >= 2:
        return "url_and_schedule_table"
    if len(all_urls) == 1:
        return "url_table_candidate"
    if len(all_dates) >= 3 or len(all_times) >= 2:
        return "schedule_table_candidate"
    if len(all_phones) >= 1:
        return "contact_table_candidate"
    if len(all_dates) >= 1 or len(all_times) >= 1:
        return "date_or_time_table_candidate"
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_cols_from_aspect(height: int, width: int) -> int:
    aspect = width / height if height > 0 else 1.0
    if aspect >= 3.0:
        return 3
    return 2


def _estimate_rows_from_aspect(height: int, width: int) -> int:
    aspect = width / height if height > 0 else 1.0
    if aspect < 0.5:
        return 4
    if aspect < 1.0:
        return 3
    return 2


def _find_run_centers(sums: np.ndarray, threshold: float) -> list[int]:
    positions: list[int] = []
    in_run = False
    run_start = 0
    for i, val in enumerate(sums):
        if val >= threshold and not in_run:
            in_run = True
            run_start = i
        elif val < threshold and in_run:
            in_run = False
            positions.append((run_start + i) // 2)
    if in_run:
        positions.append((run_start + len(sums)) // 2)
    return positions


def _deduplicate(positions: list[int], tolerance: int = 5) -> list[int]:
    if not positions:
        return []
    result = [positions[0]]
    for pos in sorted(positions)[1:]:
        if pos - result[-1] > tolerance:
            result.append(pos)
    return result


def _to_boundaries(positions: list[int], start: int, end: int) -> list[int]:
    raw = [start] + sorted(positions) + [end]
    result: list[int] = []
    for b in raw:
        if not result or b - result[-1] > 5:
            result.append(b)
    if not result or result[-1] != end:
        result.append(end)
    return result


def _to_rgb(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 3 and img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    return img


def _empty_patterns() -> dict[str, list[str]]:
    return {"urls": [], "phones": [], "dates": [], "times": [], "amounts": []}
