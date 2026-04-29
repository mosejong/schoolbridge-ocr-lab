from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ocr_quality_gate import AUTO_PASS_THRESHOLD, run_quality_gate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate OCR result.json and decide whether it can produce verified_text automatically.",
    )
    parser.add_argument("--result-json", required=True, help="Path to OCR experiment result.json.")
    parser.add_argument("--output", required=True, help="Output directory for quality gate artifacts.")
    parser.add_argument("--ground-truth", default=None, help="Optional ground truth text for CER/F1 metrics.")
    parser.add_argument("--threshold", type=float, default=AUTO_PASS_THRESHOLD, help="Auto-pass threshold.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_quality_gate(
        result_json_path=args.result_json,
        output_dir=args.output,
        ground_truth_path=args.ground_truth,
        threshold=args.threshold,
    )
    report = result.quality_report
    output_dir = Path(args.output)
    print(f"[OK] quality report: {output_dir / 'quality_report.json'}")
    print(f"[OK] key patterns: {output_dir / 'key_patterns.json'}")
    print(f"[OK] verified text: {output_dir / 'verified_text.txt'}")
    print(f"[OK] review text: {output_dir / 'review_text.txt'}")
    print(f"[RESULT] auto_pass={report['auto_pass']} overall_score={report['overall_score']:.4f}")
    if report["reasons"]:
        print("[REASONS]")
        for reason in report["reasons"]:
            print(f"- {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
