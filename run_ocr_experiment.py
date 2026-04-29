from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.image_preprocess import build_preprocessed_images, load_image
from src.json_builder import build_result, save_result_json
from src.ocr_runner import OcrEnvironmentError, run_ocr_for_images
from src.table_cell_extractor import extract_cells
from src.table_detector import detect_table_crops
from src.utils import ensure_dir, safe_stem


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local SchoolBridge OCR preprocessing experiments."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to a JPG or PNG image.",
    )
    parser.add_argument(
        "--lang",
        default="kor+eng",
        help="Tesseract language code. Default: kor+eng",
    )
    parser.add_argument(
        "--output-root",
        default="outputs/ocr_experiment",
        help="Directory where experiment outputs are saved.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_root = Path(args.output_root)

    try:
        original_image = load_image(input_path)
    except FileNotFoundError:
        print(f"[ERROR] Input image not found: {input_path}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    experiment_dir = output_root / safe_stem(input_path)
    debug_dir = ensure_dir(experiment_dir / "debug_images")
    ocr_results_dir = ensure_dir(experiment_dir / "ocr_results")
    table_crops_dir = ensure_dir(experiment_dir / "table_crops")

    preprocessed = build_preprocessed_images(original_image, debug_dir, lang=args.lang)
    base_image = next(item.image for item in preprocessed.images if item.name == "original")

    table_detection = None
    table_warnings: list[str] = []
    try:
        table_detection = detect_table_crops(
            image=base_image,
            table_crops_dir=table_crops_dir,
            debug_dir=debug_dir,
        )
        table_warnings.extend(table_detection.warnings)
    except Exception as exc:
        table_warnings.append(f"Table detection failed: {exc}")

    cell_extraction_results: dict = {}
    cell_crops_dir = ensure_dir(experiment_dir / "table_cell_crops")
    if table_detection and table_detection.crop_images:
        for table_id, crop_image in table_detection.crop_images.items():
            try:
                cell_result = extract_cells(
                    table_id=table_id,
                    crop_image=crop_image,
                    cell_crops_dir=cell_crops_dir,
                    lang=args.lang,
                )
                cell_extraction_results[table_id] = cell_result
            except Exception as exc:
                table_warnings.append(f"Cell extraction failed for {table_id}: {exc}")

    try:
        ocr_results = run_ocr_for_images(
            preprocessed.images + (table_detection.ocr_images if table_detection else []),
            ocr_results_dir=ocr_results_dir,
            lang=args.lang,
        )
    except OcrEnvironmentError as exc:
        print("[ERROR] Tesseract OCR execution is not ready.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("", file=sys.stderr)
        print("Windows quick check:", file=sys.stderr)
        print("  1. Install Tesseract OCR for Windows.", file=sys.stderr)
        print("  2. Add tesseract.exe to PATH.", file=sys.stderr)
        print("  3. Reopen PowerShell and run: tesseract --version", file=sys.stderr)
        print("  4. If Korean OCR is needed, install the 'kor' language data.", file=sys.stderr)
        return 2

    result_payload = build_result(
        input_path=input_path,
        experiment_dir=experiment_dir,
        preprocess_result=preprocessed,
        ocr_results=ocr_results,
        lang=args.lang,
        table_detection=table_detection,
        warnings=table_warnings,
        cell_extraction_results=cell_extraction_results,
    )
    result_json_path = save_result_json(experiment_dir / "result.json", result_payload)

    print(f"[OK] OCR experiment finished: {experiment_dir}")
    print(f"[OK] Debug images: {debug_dir}")
    print(f"[OK] OCR text files: {ocr_results_dir}")
    print(f"[OK] Result JSON: {result_json_path}")
    print("[NOTE] OCR output is an experiment artifact, not ground truth data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
