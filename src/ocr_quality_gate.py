from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.model_input_builder import extract_key_patterns, normalize_text, remove_duplicate_lines


AUTO_PASS_THRESHOLD = 0.90
TARGET_F1 = 0.90
TARGET_CER = 0.10


@dataclass(frozen=True)
class QualityGateResult:
    verified_text: str
    review_text: str
    key_patterns: dict[str, list[str]]
    quality_report: dict[str, Any]


def collect_best_ocr_text(result_json: str | Path | dict[str, Any]) -> str:
    payload, base_dir = _load_result_json(result_json)

    chunks: list[str] = []
    chunks.extend(_collect_best_document_ocr(payload, base_dir))
    chunks.extend(_collect_priority_table_ocr(payload, base_dir))
    chunks.extend(_collect_pattern_cells(payload))
    chunks.extend(_collect_fallback_document_ocr(payload, base_dir))

    normalized = normalize_text("\n\n".join(chunk for chunk in chunks if chunk.strip()))
    lines = remove_duplicate_lines(normalized.splitlines())
    return "\n".join(lines).strip()


def extract_quality_patterns(text: str) -> dict[str, list[str]]:
    return extract_key_patterns(text)


def calculate_text_quality_score(text: str) -> dict[str, Any]:
    warnings: list[str] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    total_chars = max(len(text), 1)
    meaningful_chars = len(re.findall(r"[\uac00-\ud7a3A-Za-z0-9]", text))
    hangul_chars = len(re.findall(r"[\uac00-\ud7a3]", text))
    ascii_word_chars = len(re.findall(r"[A-Za-z0-9]", text))
    garbage_chars = len(re.findall(r"[^ \n\t\r\uac00-\ud7a3A-Za-z0-9.,:/()\-_%+~#@&=]", text))
    repeated_space_chars = len(re.findall(r"(?:\S\s){4,}\S", text))

    compact_seen: set[str] = set()
    duplicate_count = 0
    short_count = 0
    garbage_line_count = 0
    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if compact in compact_seen:
            duplicate_count += 1
        elif compact:
            compact_seen.add(compact)
        if len(compact) <= 3:
            short_count += 1
        meaningful_in_line = len(re.findall(r"[\uac00-\ud7a3A-Za-z0-9]", line))
        if len(line) >= 8 and meaningful_in_line / max(len(line), 1) < 0.35:
            garbage_line_count += 1

    line_count = max(len(lines), 1)
    meaningful_ratio = meaningful_chars / total_chars
    hangul_ratio = hangul_chars / total_chars
    alnum_ratio = ascii_word_chars / total_chars
    garbage_ratio = garbage_chars / total_chars
    short_line_ratio = short_count / line_count
    duplicate_line_ratio = duplicate_count / line_count
    spaced_char_ratio = repeated_space_chars / total_chars
    garbage_line_ratio = garbage_line_count / line_count

    penalty = (
        garbage_ratio * 1.7
        + short_line_ratio * 0.18
        + duplicate_line_ratio * 0.25
        + spaced_char_ratio * 0.45
        + garbage_line_ratio * 0.35
    )
    score = _clamp(meaningful_ratio * 1.05 - penalty)

    if len(text.strip()) < 120:
        warnings.append("OCR text is too short for automatic verification.")
        score = min(score, 0.45)
    if garbage_ratio > 0.10:
        warnings.append("Garbage character ratio is above 0.10.")
    if short_line_ratio > 0.35:
        warnings.append("Too many short OCR lines.")
    if spaced_char_ratio > 0.12:
        warnings.append("Excessive character spacing detected.")

    return {
        "score": round(score, 4),
        "meaningful_ratio": round(meaningful_ratio, 4),
        "hangul_ratio": round(hangul_ratio, 4),
        "alnum_ratio": round(alnum_ratio, 4),
        "garbage_ratio": round(garbage_ratio, 4),
        "short_line_ratio": round(short_line_ratio, 4),
        "duplicate_line_ratio": round(duplicate_line_ratio, 4),
        "spaced_char_ratio": round(spaced_char_ratio, 4),
        "garbage_line_ratio": round(garbage_line_ratio, 4),
        "line_count": len(lines),
        "warnings": warnings,
    }


def calculate_pattern_score(patterns: dict[str, list[str]], text: str = "") -> dict[str, Any]:
    doc_type = _detect_doc_type(text)
    found = {key: len(values) for key, values in patterns.items()}
    warnings: list[str] = []

    if doc_type == "meal_notice":
        score = 0.0
        score += min(found.get("meal_dates", 0) / 8, 1.0) * 0.32
        score += min(_count_menu_like_tokens(text) / 20, 1.0) * 0.24
        score += min(found.get("nutrition_numbers", 0) / 10, 1.0) * 0.16
        score += min(found.get("allergy_numbers", 0) / 12, 1.0) * 0.10
        score += min((found.get("amounts", 0) + found.get("phones", 0) + found.get("urls", 0)) / 3, 1.0) * 0.18
        if found.get("meal_dates", 0) == 0:
            warnings.append("No meal date pattern detected.")
        if _looks_like_nutrition_date_confusion(patterns):
            warnings.append("Nutrition-like numbers may still be mixed with date candidates.")
    else:
        core = found.get("dates", 0) + found.get("times", 0) + found.get("phones", 0) + found.get("urls", 0) + found.get("amounts", 0)
        score = min(core / 5, 1.0) * 0.72
        score += min(_count_notice_keywords(text) / 5, 1.0) * 0.28
        if core == 0:
            warnings.append("No core notice pattern detected.")

    suspicious_urls = _find_suspicious_urls(text, patterns.get("urls", []))
    suspicious_phones = _find_suspicious_phones(text, patterns.get("phones", []))
    if suspicious_urls:
        warnings.append("Suspicious broken URL candidates detected.")
    if suspicious_phones:
        warnings.append("Suspicious broken phone number candidates detected.")

    return {
        "doc_type": doc_type,
        "score": round(_clamp(score), 4),
        "found": found,
        "suspicious_urls": suspicious_urls[:10],
        "suspicious_phones": suspicious_phones[:10],
        "warnings": warnings,
    }


def calculate_table_score(result_json: str | Path | dict[str, Any]) -> dict[str, Any]:
    payload, _base_dir = _load_result_json(result_json)
    table_summary = payload.get("table_summary", {}) or {}
    tables = payload.get("tables", []) or []
    warnings: list[str] = []

    detected_count = int(table_summary.get("detected_count") or len(tables) or 0)
    candidate_count = int(table_summary.get("candidate_count") or len([t for t in tables if t.get("is_candidate")]) or 0)
    best_table_id = table_summary.get("best_table_id")
    best_priority = 0.0
    cells_total = 0
    cells_non_empty = 0
    cells_with_patterns = 0

    for table in tables:
        best_priority = max(best_priority, float(table.get("table_priority_score") or 0.0))
        cell_structure = table.get("cell_structure") or {}
        cells = cell_structure.get("cells") or []
        for cell in cells:
            cells_total += 1
            text = str(cell.get("text") or "").strip()
            if text:
                cells_non_empty += 1
            patterns = cell.get("patterns") or {}
            if any(patterns.get(key) for key in ["urls", "phones", "dates", "times", "amounts"]):
                cells_with_patterns += 1

    non_empty_cell_ratio = cells_non_empty / cells_total if cells_total else 0.0
    cell_pattern_ratio = cells_with_patterns / cells_total if cells_total else 0.0
    priority_score = min(best_priority / 100, 1.0)

    score = 0.0
    score += min(detected_count / 3, 1.0) * 0.18
    score += min(candidate_count / 2, 1.0) * 0.18
    score += (0.18 if best_table_id else 0.0)
    score += priority_score * 0.20
    score += non_empty_cell_ratio * 0.18
    score += cell_pattern_ratio * 0.08
    score = _clamp(score)

    if detected_count == 0:
        warnings.append("No table candidate detected.")
    if cells_total and non_empty_cell_ratio < 0.35:
        warnings.append("Table cell OCR density is low.")
    if not cells_total and tables:
        warnings.append("Table candidates exist, but cell_structure is missing.")

    return {
        "score": round(score, 4),
        "detected_count": detected_count,
        "candidate_count": candidate_count,
        "best_table_id": best_table_id,
        "best_table_priority_score": round(best_priority, 4),
        "cell_count": cells_total,
        "non_empty_cell_ratio": round(non_empty_cell_ratio, 4),
        "cell_pattern_ratio": round(cell_pattern_ratio, 4),
        "warnings": warnings,
    }


def decide_auto_pass(
    scores: dict[str, Any],
    threshold: float = AUTO_PASS_THRESHOLD,
    scoring_mode: str = "result_json",
) -> dict[str, Any]:
    text_score = float(scores["text_quality"].get("score", 0.0))
    pattern_score = float(scores["pattern"].get("score", 0.0))
    table_score = float(scores["table"].get("score", 0.0))
    has_table_signal = scoring_mode == "result_json" and scores["table"].get("detected_count", 0) > 0
    weights = (0.50, 0.35, 0.15) if has_table_signal else (0.62, 0.38, 0.0)
    overall_score = text_score * weights[0] + pattern_score * weights[1] + table_score * weights[2]

    reasons: list[str] = []
    if overall_score < threshold:
        reasons.append("overall_score below threshold")
    if float(scores["text_quality"].get("garbage_ratio", 1.0)) > 0.10:
        reasons.append("garbage_ratio above 0.10")
    for warning in scores["pattern"].get("warnings", []):
        if _is_soft_pattern_warning(warning, scores["pattern"]):
            continue
        reasons.append(warning)
    if scores["table"].get("warnings"):
        reasons.extend(scores["table"]["warnings"])
    if scores.get("reference_metrics"):
        metrics = scores["reference_metrics"]
        if metrics.get("f1", 0.0) < TARGET_F1:
            reasons.append("F1 below target 0.90")
        if metrics.get("cer", 1.0) > TARGET_CER:
            reasons.append("CER above target 0.10")

    return {
        "auto_pass": not reasons,
        "overall_score": round(_clamp(overall_score), 4),
        "threshold": threshold,
        "scoring_mode": scoring_mode,
        "weights": {
            "text_quality": weights[0],
            "pattern": weights[1],
            "table": weights[2],
        },
        "reasons": _unique_strings(reasons),
    }


def run_quality_gate(
    result_json_path: str | Path,
    output_dir: str | Path,
    ground_truth_path: str | Path | None = None,
    threshold: float = AUTO_PASS_THRESHOLD,
) -> QualityGateResult:
    result_path = Path(result_json_path)
    output_path = Path(output_dir)
    text = collect_best_ocr_text(result_path)
    table_score = calculate_table_score(result_path)

    report = {
        "input_type": "result_json",
        "scoring_mode": "result_json",
        "input": str(result_path),
        "source_text_path": None,
        "ground_truth": str(ground_truth_path) if ground_truth_path else None,
    }
    return _run_quality_gate_for_text(
        text=text,
        output_path=output_path,
        base_report=report,
        table_score=table_score,
        ground_truth_path=ground_truth_path,
        threshold=threshold,
    )


def run_quality_gate_for_text(
    text_path: str | Path,
    output_dir: str | Path,
    ground_truth_path: str | Path | None = None,
    threshold: float = AUTO_PASS_THRESHOLD,
) -> QualityGateResult:
    source_path = Path(text_path)
    raw_text = source_path.read_text(encoding="utf-8", errors="replace")
    normalized = normalize_text(raw_text)
    text = "\n".join(remove_duplicate_lines(normalized.splitlines())).strip()
    table_score = {
        "score": 0.0,
        "available": False,
        "reason": "No table structure available for raw text input",
        "warnings": [],
    }
    report = {
        "input_type": "raw_text",
        "scoring_mode": "raw_text",
        "input": str(source_path),
        "source_text_path": str(source_path),
        "ground_truth": str(ground_truth_path) if ground_truth_path else None,
    }
    return _run_quality_gate_for_text(
        text=text,
        output_path=Path(output_dir),
        base_report=report,
        table_score=table_score,
        ground_truth_path=ground_truth_path,
        threshold=threshold,
    )


def _run_quality_gate_for_text(
    text: str,
    output_path: Path,
    base_report: dict[str, Any],
    table_score: dict[str, Any],
    ground_truth_path: str | Path | None,
    threshold: float,
) -> QualityGateResult:
    patterns = extract_quality_patterns(text)
    text_quality = calculate_text_quality_score(text)
    pattern_score = calculate_pattern_score(patterns, text)
    scores: dict[str, Any] = {
        "text_quality": text_quality,
        "pattern": pattern_score,
        "table": table_score,
    }
    if ground_truth_path:
        gt_text = Path(ground_truth_path).read_text(encoding="utf-8", errors="replace")
        scores["reference_metrics"] = calculate_reference_metrics(text, gt_text)

    scoring_mode = str(base_report.get("scoring_mode") or base_report.get("input_type") or "result_json")
    decision = decide_auto_pass(scores, threshold=threshold, scoring_mode=scoring_mode)
    verified_text = text + "\n" if decision["auto_pass"] else ""
    review_text = "" if decision["auto_pass"] else text + "\n"
    report = {
        **base_report,
        "doc_type": pattern_score["doc_type"],
        "auto_pass": decision["auto_pass"],
        "threshold": threshold,
        "overall_score": decision["overall_score"],
        "scoring_mode": decision["scoring_mode"],
        "scoring_weights": decision["weights"],
        "scores": scores,
        "patterns": patterns,
        "outputs": {
            "verified_text": "verified_text.txt",
            "review_text": "review_text.txt",
            "key_patterns": "key_patterns.json",
            "quality_report": "quality_report.json",
        },
        "reasons": decision["reasons"],
        "target": {
            "f1": TARGET_F1,
            "cer": TARGET_CER,
        },
    }

    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "verified_text.txt").write_text(verified_text, encoding="utf-8")
    (output_path / "review_text.txt").write_text(review_text, encoding="utf-8")
    (output_path / "key_patterns.json").write_text(
        json.dumps(patterns, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_path / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return QualityGateResult(
        verified_text=verified_text,
        review_text=review_text,
        key_patterns=patterns,
        quality_report=report,
    )


def calculate_reference_metrics(prediction: str, ground_truth: str) -> dict[str, float]:
    pred_norm = normalize_text(prediction)
    gt_norm = normalize_text(ground_truth)
    distance = _levenshtein(pred_norm, gt_norm)
    cer = distance / max(len(gt_norm), 1)

    pred_tokens = re.findall(r"[\uac00-\ud7a3A-Za-z0-9:/._-]+", pred_norm)
    gt_tokens = re.findall(r"[\uac00-\ud7a3A-Za-z0-9:/._-]+", gt_norm)
    pred_counts = _counts(pred_tokens)
    gt_counts = _counts(gt_tokens)
    overlap = sum(min(pred_counts.get(token, 0), gt_counts.get(token, 0)) for token in gt_counts)
    precision = overlap / max(len(pred_tokens), 1)
    recall = overlap / max(len(gt_tokens), 1)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "cer": round(cer, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _collect_best_document_ocr(payload: dict[str, Any], base_dir: Path) -> list[str]:
    document_items = [
        item
        for item in payload.get("ocr_results", [])
        if item.get("status") == "ok" and not str(item.get("name", "")).startswith(("table_", "cell_"))
    ]
    scored: list[tuple[float, str]] = []
    for item in document_items:
        text = _read_text_path(base_dir, item.get("text_path"))
        if not text.strip():
            continue
        quality = calculate_text_quality_score(normalize_text(text))
        scored.append((float(quality["score"]), text))
    if not scored:
        return []
    scored.sort(key=lambda item: item[0], reverse=True)
    return [scored[0][1]]


def _collect_priority_table_ocr(payload: dict[str, Any], base_dir: Path) -> list[str]:
    tables = sorted(
        payload.get("tables", []) or [],
        key=lambda table: float(table.get("table_priority_score") or table.get("candidate_priority_score") or 0.0),
        reverse=True,
    )
    chunks: list[str] = []
    for table in tables[:5]:
        variants = table.get("ocr_variants") or {}
        best_variant = table.get("best_table_ocr_variant")
        if best_variant and best_variant in variants:
            chunks.append(_read_text_path(base_dir, variants[best_variant].get("text_path")))
        elif table.get("ocr_text_path"):
            chunks.append(_read_text_path(base_dir, table.get("ocr_text_path")))
        for key in ["default", "psm6", "psm11", "url_config"]:
            if key in variants:
                chunks.append(_read_text_path(base_dir, variants[key].get("text_path")))
    return chunks


def _collect_pattern_cells(payload: dict[str, Any]) -> list[str]:
    chunks: list[str] = []
    for table in payload.get("tables", []) or []:
        cells = ((table.get("cell_structure") or {}).get("cells") or [])
        for cell in cells:
            patterns = cell.get("patterns") or {}
            if any(patterns.get(key) for key in ["urls", "phones", "dates", "times", "amounts"]):
                text = str(cell.get("text") or "").strip()
                if text:
                    chunks.append(text)
    return chunks


def _collect_fallback_document_ocr(payload: dict[str, Any], base_dir: Path) -> list[str]:
    chunks: list[str] = []
    for item in payload.get("ocr_results", []):
        name = str(item.get("name", ""))
        if item.get("status") == "ok" and name in {"adaptive_threshold", "contrast_enhanced", "sharpened", "warped", "original"}:
            chunks.append(_read_text_path(base_dir, item.get("text_path")))
    return chunks


def _read_text_path(base_dir: Path, value: str | None) -> str:
    if not value:
        return ""
    path = _resolve_output_path(base_dir, Path(value))
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_result_json(result_json: str | Path | dict[str, Any]) -> tuple[dict[str, Any], Path]:
    if isinstance(result_json, dict):
        return result_json, Path(".")
    path = Path(result_json)
    return json.loads(path.read_text(encoding="utf-8")), path.parent


def _resolve_output_path(base_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    if path.exists():
        return path
    if (base_dir / path).exists():
        return base_dir / path
    current = base_dir
    while current.parent != current:
        candidate = current / path
        if candidate.exists():
            return candidate
        current = current.parent
    return path


def _detect_doc_type(text: str) -> str:
    if re.search(r"학교\s*급식|급식|식단|알레르기", text):
        return "meal_notice"
    return "general_notice"


def _count_menu_like_tokens(text: str) -> int:
    keywords = [
        "밥",
        "국",
        "김치",
        "우유",
        "샐러드",
        "볶음",
        "구이",
        "찜",
        "탕",
        "면",
        "떡",
        "과일",
        "핫도그",
        "만두",
    ]
    return sum(len(re.findall(keyword, text)) for keyword in keywords)


def _count_notice_keywords(text: str) -> int:
    keywords = ["안내", "신청", "기간", "문의", "대상", "장소", "시간", "참여", "제출"]
    return sum(1 for keyword in keywords if keyword in text)


def _looks_like_nutrition_date_confusion(patterns: dict[str, list[str]]) -> bool:
    dates = patterns.get("dates", [])
    nutrition_count = len(patterns.get("nutrition_numbers", []))
    dot_heavy_dates = [value for value in dates if re.search(r"\d+\.\d+", value)]
    return nutrition_count >= 3 and bool(dot_heavy_dates)


def _find_suspicious_urls(text: str, valid_urls: list[str]) -> list[str]:
    candidates = re.findall(r"\b(?:www|http|bit|w{2,}|[A-Za-z0-9.-]+)\S{0,40}\b", text, flags=re.IGNORECASE)
    valid = {_normalize_url_for_compare(value) for value in valid_urls}
    return _unique_strings(
        [
            value
            for value in candidates
            if _normalize_url_for_compare(value) not in valid
            and re.search(r"www|http|bit\.?|\.com|\.kr", value, flags=re.IGNORECASE)
        ]
    )


def _find_suspicious_phones(text: str, valid_phones: list[str]) -> list[str]:
    candidates = re.findall(r"\b0\d[\d\s.-]{6,14}\d\b", text)
    valid = {_normalize_phone_for_compare(value) for value in valid_phones}
    return _unique_strings([value for value in candidates if _normalize_phone_for_compare(value) not in valid])


def _is_soft_pattern_warning(warning: str, pattern_score: dict[str, Any]) -> bool:
    found = pattern_score.get("found", {})
    if warning == "Suspicious broken URL candidates detected." and found.get("urls", 0) > 0:
        return True
    if warning == "Suspicious broken phone number candidates detected." and found.get("phones", 0) > 0:
        return True
    return False


def _normalize_url_for_compare(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"^https?://", "", normalized)
    normalized = normalized.rstrip(".,;:)]}")
    return normalized


def _normalize_phone_for_compare(value: str) -> str:
    return re.sub(r"\D", "", value)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def _counts(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", str(value).strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
