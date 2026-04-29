# OCR Experiment Reference

This note summarizes useful context imported from the local `OCR실험` folder. It is reference material only; the phase-1 pipeline remains focused on local image OCR with OpenCV preprocessing and pytesseract.

## Useful Takeaways

- OCR output is not ground truth.
- Camera/PDF OCR results need human review before downstream analysis.
- Prior comparison used CER, WER, jamo CER, line accuracy, and character-level precision/recall/F1.
- Prior broad OCR experiments included ML Kit Korean, EasyOCR, Tesseract, and PaddleOCR.
- PaddleOCR was not stable in the tested Python 3.13/numpy 2.x environment and should remain TODO for now.
- PDF parsing, table crop, CER/WER pipeline integration, Android/FastAPI integration, and translation/TTS handoff are outside phase 1.

## Optional Local Evaluation

The clean evaluation helper lives at:

```text
tools/eval_ocr.py
```

Example:

```powershell
python tools\eval_ocr.py `
  --ground-truth data\reference\ocr_ground_truth.txt `
  --ocr-result outputs\ocr_experiment\sample01\ocr_results\warped.txt
```

This helper is not part of the required OCR run. Use it only when a human-reviewed reference text exists.
