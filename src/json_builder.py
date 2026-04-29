from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .image_preprocess import PreprocessResult
from .ocr_runner import OcrResult
from .table_analysis import analyze_table_text, merge_patterns
from .table_detector import TableDetectionResult
from .utils import ensure_dir, relative_or_absolute


def build_result(
    input_path: Path,
    experiment_dir: Path,
    preprocess_result: PreprocessResult,
    ocr_results: list[OcrResult],
    lang: str,
    table_detection: TableDetectionResult | None = None,
    warnings: list[str] | None = None,
    cell_extraction_results: dict | None = None,
) -> dict[str, Any]:
    ocr_result_by_name = {result.name: result for result in ocr_results}

    tables = _build_table_results(table_detection, ocr_result_by_name, cell_extraction_results or {})
    table_summary = _build_table_summary(tables, warnings or [])

    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "path": relative_or_absolute(input_path),
            "file_name": input_path.name,
        },
        "experiment_dir": relative_or_absolute(experiment_dir),
        "ocr_engine": {
            "name": "pytesseract",
            "lang": lang,
        },
        "preprocessing": {
            "rotation_candidates": [
                {
                    "name": candidate.name,
                    "debug_image_path": relative_or_absolute(candidate.debug_image_path),
                    "score": candidate.score,
                    "text_length": candidate.text_length,
                    "error": candidate.error,
                }
                for candidate in preprocess_result.rotation_candidates
            ],
            "best_rotation": preprocess_result.best_rotation,
            "rotation_score": preprocess_result.rotation_score,
            "rotation_note": preprocess_result.rotation_note,
            "perspective_applied": preprocess_result.perspective_applied,
            "perspective_note": preprocess_result.perspective_note,
            "variants": [
                {
                    "name": item.name,
                    "debug_image_path": relative_or_absolute(item.path),
                }
                for item in preprocess_result.images
            ],
        },
        "ocr_results": [
            {
                "name": result.name,
                "status": result.status,
                "debug_image_path": relative_or_absolute(result.image_path),
                "text_path": relative_or_absolute(result.text_path),
                "text_length": len(result.text),
                "error": result.error,
            }
            for result in ocr_results
        ],
        "tables": tables,
        "table_summary": table_summary,
        "warnings": warnings or [],
        "cautions": [
            "OCR text is an experiment artifact, not ground truth.",
            "Do not use OCR output directly as training data without human review.",
        ],
        "todo": [
            "PDF input handling",
            "Table crop improvement",
            "CER/WER evaluation",
        ],
    }


def save_result_json(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _build_table_results(
    table_detection: TableDetectionResult | None,
    ocr_result_by_name: dict[str, OcrResult],
    cell_extraction_results: dict,
) -> list[dict[str, Any]]:
    if table_detection is None:
        return []

    tables: list[dict[str, Any]] = []
    for table in table_detection.tables:
        table_id = table.table_id
        variant_names = [
            ("default", table_id),
            ("psm6", f"{table_id}_psm6"),
            ("psm11", f"{table_id}_psm11"),
            ("url_config", f"{table_id}_url_config"),
            ("zoom2x", f"{table_id}_zoom2x"),
            ("zoom2x_psm6", f"{table_id}_zoom2x_psm6"),
            ("zoom2x_psm11", f"{table_id}_zoom2x_psm11"),
            ("zoom2x_url_config", f"{table_id}_zoom2x_url_config"),
            ("zoom3x", f"{table_id}_zoom3x"),
        ]
        ocr_variants = _build_ocr_variant_results(variant_names, ocr_result_by_name)
        best_variant_name = _select_best_variant(ocr_variants)
        best_variant = ocr_variants.get(best_variant_name, {})
        best_patterns = best_variant.get("patterns", {"urls": [], "phones": [], "dates": [], "times": [], "amounts": []})
        best_score = float(best_variant.get("score", 0))
        table_priority_score = table.candidate_priority_score + best_score
        has_patterns = any(best_patterns.get(key) for key in ["urls", "phones", "dates", "times", "amounts"])
        best_text_length = int(best_variant.get("text_length", 0)) if best_variant else 0
        filter_reasons = [table.filter_reason] if table.filter_reason else []
        if not has_patterns and best_text_length < 100:
            filter_reasons.append("low_ocr_signal")
            table_priority_score -= 4
        effective_filter_reason = ", ".join(filter_reasons) if filter_reasons else None
        effective_is_candidate = table.is_candidate and not effective_filter_reason

        cell_structure = cell_extraction_results.get(table_id)
        tables.append(
            {
                "table_id": table_id,
                "bbox": list(table.bbox),
                "area": table.area,
                "relative_area": table.relative_area,
                "aspect_ratio": table.aspect_ratio,
                "text_density_estimate": table.text_density_estimate,
                "is_too_small": table.is_too_small,
                "is_too_large": table.is_too_large,
                "is_header_like": table.is_header_like,
                "is_low_text_density": table.is_low_text_density,
                "candidate_priority_score": table.candidate_priority_score,
                "is_candidate": effective_is_candidate,
                "filter_reason": effective_filter_reason,
                "image_path": relative_or_absolute(table.image_path),
                "zoom2x_path": relative_or_absolute(table.zoom2x_path),
                "zoom3x_path": relative_or_absolute(table.zoom3x_path),
                "ocr_text_path": _variant_text_path(ocr_variants, "default"),
                "zoom2x_ocr_text_path": _variant_text_path(ocr_variants, "zoom2x"),
                "zoom3x_ocr_text_path": _variant_text_path(ocr_variants, "zoom3x"),
                "ocr_variants": ocr_variants,
                "best_table_ocr_variant": best_variant_name,
                "patterns": best_patterns,
                "table_priority_score": table_priority_score,
                "cell_structure": _build_cell_structure_block(cell_structure),
            }
        )
    return tables


def _build_ocr_variant_results(
    variant_names: list[tuple[str, str]],
    ocr_result_by_name: dict[str, OcrResult],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for variant_label, result_name in variant_names:
        result = ocr_result_by_name.get(result_name)
        if result is None:
            continue
        text = result.text
        if not text and result.text_path.exists():
            text = result.text_path.read_text(encoding="utf-8")
        analysis = analyze_table_text(text)
        results[variant_label] = {
            "text_path": relative_or_absolute(result.text_path),
            "patterns": analysis.patterns,
            "score": analysis.score,
            "text_length": len(text),
            "status": result.status,
            "error": result.error,
        }
    return results


def _select_best_variant(ocr_variants: dict[str, dict[str, Any]]) -> str | None:
    if not ocr_variants:
        return None
    return max(
        ocr_variants.items(),
        key=lambda item: (float(item[1].get("score", 0)), int(item[1].get("text_length", 0))),
    )[0]


def _variant_text_path(ocr_variants: dict[str, dict[str, Any]], variant: str) -> str | None:
    item = ocr_variants.get(variant)
    return item.get("text_path") if item else None


def _build_cell_structure_block(cell_structure) -> dict[str, Any] | None:
    if cell_structure is None:
        return None
    return {
        "method": cell_structure.method,
        "row_count": cell_structure.row_count,
        "col_count": cell_structure.col_count,
        "rows": cell_structure.rows,
        "line_detection": cell_structure.line_detection,
        "structure_hint": cell_structure.structure_hint,
        "grid_candidates": cell_structure.grid_candidates,
        "selected_grid_reason": cell_structure.selected_grid_reason,
        "cells": [
            {
                "row": cell.row,
                "col": cell.col,
                "bbox": list(cell.bbox),
                "text": cell.text,
                "patterns": cell.patterns,
                "ocr_variant": cell.ocr_variant,
            }
            for cell in cell_structure.cells
        ],
        "warnings": cell_structure.warnings,
    }


def _build_table_summary(tables: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    candidate_tables = [table for table in tables if table.get("is_candidate")]
    best_table = max(
        tables,
        key=lambda table: float(table.get("table_priority_score", 0)),
        default=None,
    )
    merged_patterns = merge_patterns([table.get("patterns", {}) for table in tables])

    summary_warnings = list(warnings)
    for table in tables:
        if table.get("filter_reason"):
            summary_warnings.append(
                f"{table.get('table_id')} flagged: {table.get('filter_reason')}"
            )

    best_reason = None
    if best_table:
        patterns = best_table.get("patterns", {})
        if patterns.get("urls"):
            best_reason = "URL pattern detected"
        elif patterns.get("phones"):
            best_reason = "Phone pattern detected"
        elif patterns.get("dates"):
            best_reason = "Date pattern detected"
        else:
            best_reason = "Highest table priority score"

    return {
        "detected_count": len(tables),
        "candidate_count": len(candidate_tables),
        "best_table_id": best_table.get("table_id") if best_table else None,
        "best_table_reason": best_reason,
        "found_urls": merged_patterns["urls"],
        "found_phones": merged_patterns["phones"],
        "found_dates": merged_patterns["dates"],
        "found_times": merged_patterns["times"],
        "found_amounts": merged_patterns["amounts"],
        "warnings": summary_warnings,
    }
