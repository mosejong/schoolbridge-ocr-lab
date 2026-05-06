"""Digital PDF layout probe for SchoolBridge highlight PoC.

This script extracts text lines with coordinates from text-based PDFs.
It is intentionally separate from OCR:

- text PDF: use embedded PDF coordinates via pdfplumber
- scanned PDF/photo: render or capture as image, then use OCR bounding boxes

Output schema is designed to be easy to hand off to backend/Android overlay work.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def merge_words_to_lines(words: list[dict], y_tolerance: float = 4.0) -> list[dict]:
    """Merge pdfplumber words into rough visual lines."""
    buckets: dict[int, list[dict]] = {}
    for word in words:
        key = int(round(float(word.get("top", 0.0)) / y_tolerance))
        buckets.setdefault(key, []).append(word)

    lines: list[dict] = []
    for group in buckets.values():
        group.sort(key=lambda w: (float(w["x0"]), float(w["top"])))
        text = " ".join(w["text"] for w in group).strip()
        if not text:
            continue

        x0 = min(float(w["x0"]) for w in group)
        y0 = min(float(w["top"]) for w in group)
        x1 = max(float(w["x1"]) for w in group)
        y1 = max(float(w["bottom"]) for w in group)
        lines.append({
            "text": text,
            "bbox": {
                "x": round(x0, 2),
                "y": round(y0, 2),
                "width": round(x1 - x0, 2),
                "height": round(y1 - y0, 2),
            },
            "source": "pdfplumber_line",
        })

    return sorted(lines, key=lambda item: (item["bbox"]["y"], item["bbox"]["x"]))


def extract_pdf_layout(pdf_path: Path) -> dict:
    import pdfplumber

    pages: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
                x_tolerance=2,
                y_tolerance=4,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            lines = merge_words_to_lines(words)
            for line in lines:
                line["page"] = page_number

            table_regions = []
            for table_index, table in enumerate(page.find_tables() or [], start=1):
                x0, top, x1, bottom = table.bbox
                table_regions.append({
                    "page": page_number,
                    "table_index": table_index,
                    "bbox": {
                        "x": round(float(x0), 2),
                        "y": round(float(top), 2),
                        "width": round(float(x1 - x0), 2),
                        "height": round(float(bottom - top), 2),
                    },
                    "source": "pdfplumber_table",
                })

            pages.append({
                "page": page_number,
                "width": round(float(page.width), 2),
                "height": round(float(page.height), 2),
                "lines": lines,
                "tables": table_regions,
            })

    return {
        "source_file": str(pdf_path),
        "mode": "digital_pdf_layout",
        "parser": "pdfplumber",
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Text-based PDF path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    result = extract_pdf_layout(Path(args.input))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    line_count = sum(len(page["lines"]) for page in result["pages"])
    table_count = sum(len(page["tables"]) for page in result["pages"])
    print(f"saved={output} pages={len(result['pages'])} lines={line_count} tables={table_count}")


if __name__ == "__main__":
    main()
