from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BuildResult:
    model_input_text: str
    key_patterns: dict[str, list[str]]
    normalization_report: dict[str, Any]


def normalize_text(text: str) -> str:
    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = _join_broken_korean_spacing(text)
    text = _normalize_common_ocr_spacing(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_duplicate_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    seen_exact: set[str] = set()
    seen_compact: set[str] = set()

    for line in lines:
        normalized = line.strip()
        if not normalized:
            if result and result[-1] != "":
                result.append("")
            continue

        compact = re.sub(r"\s+", "", normalized)
        if normalized in seen_exact or compact in seen_compact:
            continue
        if _is_meaningless_short_repeat(normalized) and compact in seen_compact:
            continue

        result.append(normalized)
        seen_exact.add(normalized)
        if len(compact) >= 2:
            seen_compact.add(compact)

    while result and result[-1] == "":
        result.pop()
    return result


def extract_key_patterns(text: str) -> dict[str, list[str]]:
    nutrition_numbers = _unique(
        re.findall(r"\b\d+(?:\.\d+)?/\d+(?:\.\d+)?/\d+(?:\.\d+)?/\d+(?:\.\d+)?\b", text)
    )
    allergy_numbers = _unique(re.findall(r"\((?:\d{1,2}\.){2,}\d{1,2}\)", text))

    masked = text
    for value in nutrition_numbers + allergy_numbers:
        masked = masked.replace(value, " ")

    meal_date_pattern = (
        r"(?<![\d.])"
        r"(?:[1-9]|1[0-2])\s*/\s*(?:[1-9]|[12]\d|3[01])"
        r"(?:\([^)]+\))?"
        r"(?![\d.])"
    )
    meal_dates = _filter_meal_dates_by_dominant_month(_unique(re.findall(meal_date_pattern, masked)))
    full_dates = _unique(
        re.findall(
            r"\b20\d{2}\s*[.]\s*(?:[1-9]|1[0-2])\s*[.]\s*(?:[1-9]|[12]\d|3[01])\s*[.]?",
            masked,
        )
        + re.findall(r"\b20\d{2}\s*년\s*(?:[1-9]|1[0-2])\s*월(?:\s*(?:[1-9]|[12]\d|3[01])\s*일)?", masked)
    )
    dates = _unique(meal_dates + full_dates)

    phones = _normalize_phone_values(
        re.findall(r"(?<!\d)0\d{1,2}\s*[-\s]\s*\d{3,4}\s*[-\s]\s*\d{4}\b", text)
    )

    return {
        "dates": dates,
        "times": _unique(re.findall(r"\b\d{1,2}\s*:\s*\d{2}(?:\s*[~-]\s*\d{1,2}\s*:\s*\d{2})?\b", text)),
        "amounts": _unique(re.findall(r"\b\d{1,3}(?:,\d{3})+\s*원\b|\b\d+\s*원\b", text)),
        "phones": phones,
        "urls": _unique(
            re.findall(
                r"(?:https?://)?(?:www\.)?[A-Za-z0-9][A-Za-z0-9.-]*\.(?:com|net|org|kr)(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
                text,
                flags=re.IGNORECASE,
            )
            + re.findall(r"bit\.ly/[A-Za-z0-9._-]+", text, flags=re.IGNORECASE)
        ),
        "meal_dates": meal_dates,
        "nutrition_numbers": nutrition_numbers,
        "allergy_numbers": allergy_numbers,
    }


def detect_sections(text: str) -> dict[str, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sections = {
        "title": "",
        "notice": "",
        "meal_table": "",
        "origin_info": "",
        "public_report_info": "",
    }

    title_index = _find_first_index(lines, [r"학교\s*급식\s*안내", r"급식\s*안내"])
    if title_index is not None:
        sections["title"] = lines[title_index]
    elif lines:
        sections["title"] = lines[0]

    meal_start = _find_first_index(lines, [r"예정\s*식단", r"\d{1,2}/\d{1,2}", r"급식\s*식단"])
    origin_start = _find_first_index(lines, [r"원산지", r"식재료"])
    public_start = _find_first_index(lines, [r"공익\s*제보", r"상담\s*전화", r"신고"])

    sections["notice"] = "\n".join(_slice_until(lines, 0, [meal_start, origin_start, public_start], max_lines=30))
    if meal_start is not None:
        sections["meal_table"] = "\n".join(_slice_until(lines, meal_start, [origin_start, public_start], max_lines=120))
    if origin_start is not None:
        sections["origin_info"] = "\n".join(_slice_until(lines, origin_start, [public_start], max_lines=80))
    if public_start is not None:
        sections["public_report_info"] = "\n".join(lines[public_start : public_start + 30])

    return sections


def build_model_input_text(sections: dict[str, str], patterns: dict[str, list[str]]) -> str:
    blocks: list[str] = []
    title = _clean_block(sections.get("title", ""))
    notice = _clean_block(sections.get("notice", ""))
    meal_table = _clean_block(sections.get("meal_table", ""))
    origin_info = _clean_block(sections.get("origin_info", ""))
    public_report_info = _clean_block(sections.get("public_report_info", ""))

    if title:
        blocks.append("[문서 제목]\n" + title)
    if notice:
        blocks.append("[주요 안내]\n" + _limit_lines(notice, 20))
    if meal_table:
        blocks.append("[급식 일정/메뉴]\n" + _limit_lines(meal_table, 80))

    key_lines: list[str] = []
    for label, key in [
        ("날짜", "dates"),
        ("급식 날짜", "meal_dates"),
        ("금액", "amounts"),
        ("전화번호", "phones"),
        ("URL", "urls"),
    ]:
        values = patterns.get(key, [])
        if values:
            key_lines.append(f"{label}: {', '.join(values[:20])}")
    if key_lines:
        blocks.append("[추출 패턴]\n" + "\n".join(key_lines))

    if patterns.get("nutrition_numbers"):
        blocks.append("[영양성분 수치 후보]\n" + "\n".join(patterns["nutrition_numbers"][:30]))
    if patterns.get("allergy_numbers"):
        blocks.append("[알레르기/식품 코드 후보]\n" + "\n".join(patterns["allergy_numbers"][:30]))
    if origin_info:
        blocks.append("[원산지 정보]\n" + _limit_lines(origin_info, 40))
    if public_report_info:
        blocks.append("[공익제보/문의]\n" + _limit_lines(public_report_info, 30))

    blocks.append("[주의]\nOCR/PDF 변환 결과 기반 정제 후보입니다. 사용자 확인이 필요합니다.")
    return "\n\n".join(blocks).strip() + "\n"


def build_from_text(text: str, input_type: str) -> BuildResult:
    normalized = normalize_text(text)
    lines_before = [line for line in normalized.splitlines()]
    deduped_lines = remove_duplicate_lines(lines_before)
    deduped_text = "\n".join(deduped_lines).strip()
    patterns = extract_key_patterns(deduped_text)
    sections = detect_sections(deduped_text)
    model_input_text = build_model_input_text(sections, patterns)

    return BuildResult(
        model_input_text=model_input_text,
        key_patterns=patterns,
        normalization_report={
            "input_type": input_type,
            "original_length": len(text),
            "normalized_length": len(deduped_text),
            "line_count_before": len([line for line in lines_before if line.strip()]),
            "line_count_after": len([line for line in deduped_lines if line.strip()]),
            "removed_duplicate_lines": max(
                len([line for line in lines_before if line.strip()])
                - len([line for line in deduped_lines if line.strip()]),
                0,
            ),
            "warnings": [],
        },
    )


def collect_text_from_result_json(result_json_path: Path) -> str:
    payload = json.loads(result_json_path.read_text(encoding="utf-8"))
    base_dir = result_json_path.parent
    paths: list[Path] = []

    for item in payload.get("ocr_results", []):
        text_path = item.get("text_path")
        if text_path:
            paths.append(_resolve_output_path(base_dir, Path(text_path)))

    for table in payload.get("tables", []):
        for value in table.get("ocr_variants", {}).values():
            text_path = value.get("text_path")
            if text_path:
                paths.append(_resolve_output_path(base_dir, Path(text_path)))

    chunks: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(chunks)


def save_build_result(result: BuildResult, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_input_path = output_dir / "model_input_text.txt"
    review_text_path = output_dir / "review_text.txt"
    key_patterns_path = output_dir / "key_patterns.json"
    report_path = output_dir / "normalization_report.json"

    model_input_path.write_text(result.model_input_text, encoding="utf-8")
    review_text_path.write_text(result.model_input_text, encoding="utf-8")
    key_patterns_path.write_text(
        json.dumps(result.key_patterns, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(result.normalization_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "model_input_text": model_input_path,
        "review_text": review_text_path,
        "key_patterns": key_patterns_path,
        "normalization_report": report_path,
    }


def _join_broken_korean_spacing(text: str) -> str:
    text = re.sub(r"(\d{4})\s*학\s*년\s*도", r"\1학년도", text)
    text = re.sub(r"(\d{1,2})\s*월", r"\1월", text)
    text = re.sub(r"학\s*교\s*급\s*식", "학교급식", text)
    text = re.sub(r"급\s*식\s*안\s*내", "급식 안내", text)
    return text


def _normalize_common_ocr_spacing(text: str) -> str:
    text = re.sub(r"(\d)\s*/\s*(\d)", r"\1/\2", text)
    text = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", text)
    text = re.sub(r"(\d)\s*,\s*(\d{3})", r"\1,\2", text)
    text = re.sub(r"\s+원", "원", text)
    return text


def _is_meaningless_short_repeat(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    if re.search(r"\d{1,2}/\d{1,2}|\d{4}|[가-힣]{2,}", compact):
        return False
    return len(compact) <= 2


def _find_first_index(lines: list[str], patterns: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if any(re.search(pattern, line) for pattern in patterns):
            return index
    return None


def _slice_until(
    lines: list[str],
    start: int,
    possible_ends: list[int | None],
    max_lines: int,
) -> list[str]:
    ends = [end for end in possible_ends if end is not None and end > start]
    end = min(ends) if ends else min(start + max_lines, len(lines))
    return lines[start:end]


def _clean_block(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if _is_noise_line(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    meaningful = re.findall(r"[\uac00-\ud7a3A-Za-z0-9]", stripped)
    if len(stripped) >= 8 and len(meaningful) / len(stripped) < 0.25:
        return True
    return False


def _limit_lines(text: str, max_lines: int) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", value.strip())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_phone_values(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 10 and digits.startswith("02"):
            normalized = f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
        elif len(digits) == 10:
            normalized = f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11:
            normalized = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        else:
            normalized = re.sub(r"\s+", "", value.strip())
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _filter_meal_dates_by_dominant_month(values: list[str]) -> list[str]:
    month_counts: dict[str, int] = {}
    parsed: list[tuple[str, str]] = []
    for value in values:
        match = re.match(r"\s*(\d{1,2})\s*/", value)
        if not match:
            continue
        month = match.group(1)
        parsed.append((value, month))
        month_counts[month] = month_counts.get(month, 0) + 1

    if not month_counts:
        return values

    dominant_month, count = max(month_counts.items(), key=lambda item: item[1])
    if count < 3:
        return values
    return [value for value, month in parsed if month == dominant_month]


def _resolve_output_path(base_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    if path.exists():
        return path
    candidate = base_dir / path
    if candidate.exists():
        return candidate
    experiment_root = base_dir
    while experiment_root.name and experiment_root.name != "outputs":
        if (experiment_root / path).exists():
            return experiment_root / path
        if experiment_root.parent == experiment_root:
            break
        experiment_root = experiment_root.parent
    return path
