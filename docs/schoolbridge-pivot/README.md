# SchoolBridge OCR Pivot Archive

날짜: 2026-05-07  
목적: SchoolBridge 메인 파이프라인에서 OCR 전략을 드랍한 결정과, 그 전까지 진행한 OCR 연구/PoC 기록을 OCR 전용 레포에 보존한다.

## 현재 결론

```text
OCR main pipeline: drop
OCR research: keep
Highlight UX: keep as PDF text-layer / original text comparison candidate
```

OCR은 메인 문서 이해 엔진에서 제외한다. 다만 OCR 실험은 실패 기록이 아니라, 실제 문서 입력 전략을 조정하게 된 근거로 보존한다.

## 보존 문서

- `2026-05-01-ocr-mlkit-korean-results.md`
- `worklog-2026-05-06-ocr-pivot-bbox.md`
- `worklog-2026-05-07-android-ocr-smoke.md`
- `worklog-2026-05-07-ocr-slot-correction.md`
- `2026-05-07-ocr-slot-correction-eval.md`
- `2026-05-07-ocr-drop-highlight-strategy.md`

## 보존 코드 스냅샷

코드는 `archive/schoolbridge-integration/`에 보존한다.

- `ocr_slot_corrector.py`
- `test_ocr_slot_corrector.py`
- `highlight_mapper.py`
- `test_highlight_mapper.py`

## 번역 레포와의 분리

번역/TTS 실험은 `translation-tts-lab`에서 관리한다. OCR 관련 기록과 PoC 코드는 이 레포에서 관리한다.

```text
translation-tts-lab: NLLB / glossary / slot protected translation / template translation
ocr_lab_schoolbridge: OCR engine comparison / bbox / OCR slot correction / highlight PoC records
```

## 후속 후보

- PDF text-layer bbox 기반 highlight PoC
- Gemini Vision 결과와 PDF bbox sentence matching 비교
- OCR fallback이 필요한 환경에서 ML Kit Korean 재검토
- confusable character correction을 실제 OCR 샘플로 재평가
