from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PatternScore:
    patterns: dict[str, list[str]]
    score: float


def analyze_table_text(text: str) -> PatternScore:
    patterns = extract_patterns(text)
    score = score_patterns(text, patterns)
    return PatternScore(patterns=patterns, score=score)


def extract_patterns(text: str) -> dict[str, list[str]]:
    urls = _unique(
        re.findall(
            r"(?:https?://)?(?:www\.)?[A-Za-z0-9][A-Za-z0-9.-]*\.(?:com|net|org|kr)(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
            text,
            flags=re.IGNORECASE,
        )
        + re.findall(r"bit\.ly/[A-Za-z0-9._-]+", text, flags=re.IGNORECASE)
    )
    phones = _unique(re.findall(r"\b0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4}\b", text))
    dates = _unique(
        re.findall(r"\b\d{4}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,2}\b", text)
        + re.findall(r"\b\d{1,2}\s*[.\-/]\s*\d{1,2}\b", text)
    )
    times = _unique(re.findall(r"\b\d{1,2}\s*:\s*\d{2}\s*(?:~|-)\s*\d{1,2}\s*:\s*\d{2}\b", text))
    amounts = _unique(re.findall(r"\b\d{1,3}(?:,\d{3})+\s*원\b|\b\d+\s*원\b", text))
    return {
        "urls": urls,
        "phones": phones,
        "dates": dates,
        "times": times,
        "amounts": amounts,
    }


def score_patterns(text: str, patterns: dict[str, list[str]]) -> float:
    meaningful_chars = re.findall(r"[\uac00-\ud7a3A-Za-z0-9]", text)
    non_space_chars = [char for char in text if not char.isspace()]
    special_chars = [
        char
        for char in non_space_chars
        if not re.match(r"[\uac00-\ud7a3A-Za-z0-9]", char)
    ]
    special_ratio = len(special_chars) / len(non_space_chars) if non_space_chars else 1.0

    score = 0.0
    score += len(patterns["urls"]) * 5
    score += len(patterns["phones"]) * 5
    score += len(patterns["dates"]) * 3
    score += len(patterns["times"]) * 3
    score += len(patterns["amounts"]) * 3

    if len(meaningful_chars) >= 120:
        score += 3
    elif len(meaningful_chars) >= 50:
        score += 2
    elif len(meaningful_chars) >= 15:
        score += 1
    else:
        score -= 3

    if special_ratio > 0.55:
        score -= 2

    return score


def merge_patterns(pattern_sets: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    merged = {"urls": [], "phones": [], "dates": [], "times": [], "amounts": []}
    for patterns in pattern_sets:
        for key in merged:
            merged[key].extend(patterns.get(key, []))
    return {key: _unique(values) for key, values in merged.items()}


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
