from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_input_builder import (  # noqa: E402
    build_from_text,
    collect_text_from_result_json,
    save_build_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build model_input_text.txt from PDF text or OCR result.json."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", type=Path, help="Path to extracted text file.")
    source.add_argument("--result-json", type=Path, help="Path to OCR result.json.")
    parser.add_argument("--output", required=True, type=Path, help="Output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.text:
        if not args.text.exists():
            print(f"[ERROR] Text file not found: {args.text}", file=sys.stderr)
            return 1
        raw_text = args.text.read_text(encoding="utf-8", errors="replace")
        input_type = "text"
    else:
        if not args.result_json.exists():
            print(f"[ERROR] result.json not found: {args.result_json}", file=sys.stderr)
            return 1
        raw_text = collect_text_from_result_json(args.result_json)
        input_type = "result_json"

    result = build_from_text(raw_text, input_type=input_type)
    paths = save_build_result(result, args.output)

    print(f"[OK] review text: {paths['review_text']}")
    print(f"[OK] model input text compatibility copy: {paths['model_input_text']}")
    print(f"[OK] key patterns: {paths['key_patterns']}")
    print(f"[OK] normalization report: {paths['normalization_report']}")
    print("[NOTE] This is review text for human confirmation, not verified_text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
