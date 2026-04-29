from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path


def levenshtein(a: list[str], b: list[str]) -> int:
    rows = len(a)
    cols = len(b)
    dp = list(range(cols + 1))

    for row in range(1, rows + 1):
        previous = dp[:]
        dp[0] = row
        for col in range(1, cols + 1):
            if a[row - 1] == b[col - 1]:
                dp[col] = previous[col - 1]
            else:
                dp[col] = 1 + min(previous[col], dp[col - 1], previous[col - 1])
    return dp[cols]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def cer(ground_truth: str, hypothesis: str) -> float:
    expected = list(ground_truth.replace(" ", "").replace("\n", ""))
    actual = list(hypothesis.replace(" ", "").replace("\n", ""))
    if not expected:
        return 0.0 if not actual else 1.0
    return levenshtein(expected, actual) / len(expected)


def wer(ground_truth: str, hypothesis: str) -> float:
    expected = ground_truth.split()
    actual = hypothesis.split()
    if not expected:
        return 0.0 if not actual else 1.0
    return levenshtein(expected, actual) / len(expected)


def jamo_cer(ground_truth: str, hypothesis: str) -> float:
    expected = _decompose_hangul(ground_truth)
    actual = _decompose_hangul(hypothesis)
    if not expected:
        return 0.0 if not actual else 1.0
    return levenshtein(expected, actual) / len(expected)


def line_accuracy(ground_truth: str, hypothesis: str) -> float:
    expected = [line.strip() for line in ground_truth.splitlines() if line.strip()]
    actual = [line.strip() for line in hypothesis.splitlines() if line.strip()]
    total = max(len(expected), len(actual))
    if total == 0:
        return 1.0
    correct = sum(1 for left, right in zip(expected, actual) if left == right)
    return correct / total


def char_precision_recall_f1(ground_truth: str, hypothesis: str) -> dict[str, float]:
    expected = [char for char in ground_truth if char not in (" ", "\n")]
    actual = [char for char in hypothesis if char not in (" ", "\n")]

    expected_counts = _count_chars(expected)
    actual_counts = _count_chars(actual)

    true_positive = sum(
        min(expected_counts.get(char, 0), count)
        for char, count in actual_counts.items()
    )
    precision = true_positive / len(actual) if actual else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate(ground_truth_path: Path, ocr_result_path: Path) -> dict[str, float]:
    ground_truth = normalize(ground_truth_path.read_text(encoding="utf-8-sig"))
    hypothesis = normalize(ocr_result_path.read_text(encoding="utf-8-sig"))

    prf = char_precision_recall_f1(ground_truth, hypothesis)
    return {
        "cer": cer(ground_truth, hypothesis),
        "wer": wer(ground_truth, hypothesis),
        "jamo_cer": jamo_cer(ground_truth, hypothesis),
        "line_accuracy": line_accuracy(ground_truth, hypothesis),
        **prf,
    }


def _decompose_hangul(text: str) -> list[str]:
    result: list[str] = []
    for char in text:
        if "가" <= char <= "힣":
            code = ord(char) - 0xAC00
            jong = code % 28
            jung = (code // 28) % 21
            cho = code // 28 // 21
            result.extend([str(cho), str(jung), str(jong)])
        elif char not in (" ", "\n"):
            result.append(char)
    return result


def _count_chars(chars: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for char in chars:
        counts[char] = counts.get(char, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate OCR text against human-reviewed text.")
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--ocr-result", required=True, type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    metrics = evaluate(args.ground_truth, args.ocr_result)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
