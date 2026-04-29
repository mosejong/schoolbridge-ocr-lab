# SchoolBridge OCR Local Lab

SchoolBridge OCR 로컬 실험실입니다. 팀 메인 레포에 붙이는 기능이 아니라, 가정통신문 이미지 OCR 가능성을 확인하기 위한 별도 로컬 실험 코드입니다.

OCR 결과는 정답 데이터가 아닙니다. OCR은 입력 편의성을 위한 보조 기능이며, 최종 분석 전에 사용자 확인 또는 사람 검수가 필요합니다. OCR 결과를 바로 학습 데이터, 번역 입력, NLLB/TTS 입력으로 확정해서 사용하지 않습니다.

## 1차 구현 범위

- JPG/PNG/JPEG 이미지 입력
- 0도/90도/180도/270도 자동 회전 후보 생성 및 OCR 기반 방향 선택
- 표/박스 후보 영역 crop 및 zoom OCR 실험
- OpenCV 전처리 이미지 저장
- pytesseract OCR 실행
- 전처리별 OCR 결과 `.txt` 저장
- `result.json` 저장
- Tesseract 미설치 또는 언어팩 미설치 시 안내 메시지 출력

## Windows PowerShell 실행 방법

```powershell
cd C:\Users\user\Desktop\project\TEAM\ocr_lab_schoolbridge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-ocr.txt
python run_ocr_experiment.py --input data\samples\sample01.jpg
```

기본 OCR 언어는 `kor+eng`입니다. 영어만 확인하려면 다음처럼 실행합니다.

```powershell
python run_ocr_experiment.py --input data\samples\sample01.jpg --lang eng
```

## Tesseract 설치 및 PATH 설정

Python 패키지 `pytesseract`는 Tesseract OCR 프로그램을 호출하는 래퍼입니다. 따라서 Windows에 Tesseract 본체가 설치되어 있어야 합니다.

### 1. Windows에서 Tesseract 설치

1. Windows용 Tesseract 설치 파일을 내려받아 설치합니다.
2. 기본 설치 경로는 보통 다음 중 하나입니다.

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
C:\Program Files (x86)\Tesseract-OCR\tesseract.exe
```

3. 설치 옵션에서 language data를 선택할 수 있다면 English와 Korean을 포함합니다.
4. 설치 후 PowerShell을 새로 엽니다.

### 2. 설치 확인

```powershell
tesseract --version
```

정상 설치 및 PATH 설정이 되어 있으면 버전 정보가 출력됩니다. 실패하면 `tesseract`가 PATH에 잡히지 않은 상태입니다.

### 3. 한글/영어 언어팩 확인

설치된 언어팩 목록을 확인합니다.

```powershell
tesseract --list-langs
```

아래 항목이 보여야 기본 실행값인 `kor+eng`를 사용할 수 있습니다.

```text
eng
kor
```

`kor`가 없으면 한국어 OCR 실행 시 언어 데이터 로딩 에러가 납니다. 이 경우 Korean traineddata를 설치하거나 우선 영어만 테스트합니다.

```powershell
python run_ocr_experiment.py --input data\samples\sample01.jpg --lang eng
```

### 4. tessdata 경로 확인

언어팩 파일은 보통 아래 폴더에 있습니다.

```text
C:\Program Files\Tesseract-OCR\tessdata
```

다음 파일이 있는지 확인합니다.

```powershell
Get-ChildItem "C:\Program Files\Tesseract-OCR\tessdata" | Select-Object Name
```

기본 확인 대상:

```text
eng.traineddata
kor.traineddata
```

### 5. PATH가 안 잡혔을 때 .env fallback 사용

PATH 설정이 번거롭거나 `tesseract --version`이 계속 실패하면, 프로젝트 루트에 `.env` 파일을 만들어 Tesseract 경로를 직접 지정할 수 있습니다.

먼저 예시 파일을 복사합니다.

```powershell
Copy-Item .env.example .env
notepad .env
```

`.env` 내용 예시:

```text
OCR_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata
```

이 프로젝트는 실행 시 `.env`를 읽어서 내부적으로 다음 설정을 적용합니다.

```python
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

또한 `OCR_TESSDATA_PREFIX` 값은 `TESSDATA_PREFIX` 환경변수로 설정됩니다.

`.env`는 개인 PC 경로가 들어가는 로컬 설정 파일이므로 Git에 올리지 않습니다. `.gitignore`에 이미 포함되어 있습니다.

### 6. PowerShell 환경변수로 임시 지정

`.env` 대신 현재 PowerShell 세션에서만 지정할 수도 있습니다.

```powershell
$env:OCR_TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:OCR_TESSDATA_PREFIX="C:\Program Files\Tesseract-OCR\tessdata"
python run_ocr_experiment.py --input data\samples\sample01.jpg
```

### 7. 설치 전/후 예상 에러 차이

Tesseract 설치 전 또는 PATH/.env 설정 전:

```text
[ERROR] Tesseract OCR execution is not ready.
Tesseract executable was not found on PATH.
```

Tesseract는 찾았지만 한국어 언어팩이 없을 때:

```text
[ERROR] Tesseract OCR execution is not ready.
Tesseract language data could not be loaded for lang='kor+eng'.
Install the needed .traineddata files or choose another --lang value.
```

정상 설치 후:

```text
[OK] OCR experiment finished: outputs\ocr_experiment\sample01
[OK] Debug images: outputs\ocr_experiment\sample01\debug_images
[OK] OCR text files: outputs\ocr_experiment\sample01\ocr_results
[OK] Result JSON: outputs\ocr_experiment\sample01\result.json
```

## 출력 구조

입력 파일이 `data\samples\sample01.jpg`라면 다음 구조가 생성됩니다.

```text
outputs/ocr_experiment/sample01/
├── debug_images/
│   ├── rotation_0.png
│   ├── rotation_90_cw.png
│   ├── rotation_180.png
│   ├── rotation_90_ccw.png
│   ├── 01_original.png
│   ├── 02_grayscale.png
│   ├── 03_denoised.png
│   ├── 04_adaptive_threshold.png
│   ├── 05_otsu_threshold.png
│   ├── 06_contrast_enhanced.png
│   ├── 07_sharpened.png
│   └── 08_warped.png
├── ocr_results/
│   ├── original.txt
│   ├── grayscale.txt
│   ├── adaptive_threshold.txt
│   ├── otsu_threshold.txt
│   ├── contrast_enhanced.txt
│   ├── sharpened.txt
│   └── warped.txt
├── table_crops/
│   ├── table_001.png
│   ├── table_001_zoom2x.png
│   └── table_001_zoom3x.png
└── result.json
```

`08_warped.png`는 perspective transform을 시도한 결과입니다. 문서 외곽선을 안정적으로 찾지 못하면 원본 이미지를 fallback으로 저장합니다.

## 자동 회전 보정

입력 이미지에 대해 다음 4개 후보를 먼저 생성합니다.

- `rotation_0`
- `rotation_90_cw`
- `rotation_180`
- `rotation_90_ccw`

각 후보는 `debug_images/rotation_*.png`로 저장됩니다. 이후 빠른 pytesseract OCR을 실행하고 한글, 숫자, 날짜, 전화번호, URL 같은 유효 문자 점수를 계산해 `best_rotation`을 선택합니다. 선택된 방향의 이미지를 기준으로 grayscale, denoised, adaptive threshold, otsu threshold, contrast enhanced, sharpened, warped 전처리를 진행합니다.

`result.json`에는 다음 정보가 기록됩니다.

```json
{
  "preprocessing": {
    "rotation_candidates": [],
    "best_rotation": "rotation_90_cw",
    "rotation_score": 1118.4,
    "rotation_note": "Best rotation selected by quick OCR scoring."
  }
}
```

이 방향 선택은 정답 판정이 아니라 OCR 품질 개선 후보를 고르는 휴리스틱입니다. Tesseract 실행 또는 점수 계산이 실패하면 원본 방향인 `rotation_0`으로 fallback하며 전체 파이프라인은 중단하지 않습니다.

## 표/박스 Crop & Zoom OCR

가정통신문은 표 안에 날짜, 시간, 장소, 대상자, 문의처, URL 같은 핵심 정보가 들어가는 경우가 많습니다. 전체 문서를 한 번에 OCR하면 표 안의 항목-내용 관계와 줄 순서가 쉽게 깨지므로, 별도 실험으로 표/박스 후보를 crop하고 2배/3배 확대 OCR을 수행합니다.

OpenCV morphological operation으로 수평선과 수직선을 감지한 뒤 결합 mask에서 contour 기반 후보 박스를 찾습니다. 너무 작은 박스는 제외하고, 겹치는 bbox는 일부 병합/제거합니다.

생성되는 debug 이미지:

```text
debug_images/
├── 09_horizontal_lines.png
├── 10_vertical_lines.png
├── 11_table_line_mask.png
└── 12_table_boxes.png
```

생성되는 crop과 OCR 결과:

```text
table_crops/
├── table_001.png
├── table_001_zoom2x.png
└── table_001_zoom3x.png

ocr_results/
├── table_001.txt
├── table_001_zoom2x.txt
└── table_001_zoom3x.txt
```

`result.json`의 `tables`에는 `table_id`, `bbox`, crop 이미지 경로, zoom 이미지 경로, OCR txt 경로가 기록됩니다.

표 탐지는 완벽한 구조 분석이 아니라 품질 개선 가능성을 보기 위한 후보 탐지입니다. 표가 감지되지 않거나 crop OCR이 실패해도 일반 OCR 파이프라인은 계속 실행되며, 실패 내용은 `warnings`에 기록합니다.

## 표/박스 후보 필터링 + URL 전용 OCR 실험

기존 문제:

- 일반 OCR에서는 URL이 `wwewsarlang.com`처럼 깨질 수 있습니다.
- 상단 로고/장식 박스도 표 후보로 잡힐 수 있습니다.
- 신청 기간 날짜 범위가 완전히 복원되지 않고 일부 조각만 남을 수 있습니다.

개선 실험:

- 표 후보마다 `area`, `relative_area`, `aspect_ratio`, `text_density_estimate`를 계산합니다.
- 너무 작은 박스, 너무 큰 박스, header/logo로 보이는 박스, OCR 신호가 약한 박스는 `filter_reason`에 기록합니다.
- crop OCR 결과에서 URL, 전화번호, 날짜, 시간, 금액 패턴을 정규식으로 추출합니다.
- 각 표 후보에 `candidate_priority_score`와 `table_priority_score`를 기록합니다.
- table crop에 대해 기본 OCR 외에 `psm6`, `psm11`, `url_config`를 추가 실험합니다.
- `url_config`는 영문/숫자/URL 문자 whitelist를 사용하며, table crop 전용 실험입니다.

`result.json`의 `tables`에는 다음 정보가 포함됩니다.

```json
{
  "table_id": "table_002",
  "bbox": [140, 805, 790, 114],
  "patterns": {
    "urls": ["www.sarlang.com"],
    "phones": [],
    "dates": [],
    "times": [],
    "amounts": []
  },
  "best_table_ocr_variant": "zoom2x_psm6",
  "table_priority_score": 23.13,
  "is_candidate": true,
  "filter_reason": null
}
```

현재 확인된 결과:

- `table_002`가 가장 높은 우선순위를 받았고 `www.sarlang.com` URL이 탐지되었습니다.
- `table_003`에서는 `2023. 3. 6`, `3. 17` 같은 날짜 조각이 탐지되었습니다.
- `table_001`은 상단 로고/장식 영역으로 보이며 `low_ocr_signal`로 낮은 우선순위를 받았습니다.
- `bit.ly/sarlang`은 아직 안정적으로 복원되지 않았습니다.
- 전화번호, 시간, 금액 패턴은 이번 샘플의 table crop 결과에서는 안정적으로 탐지되지 않았습니다.

결론:

표 crop OCR은 URL과 날짜 같은 핵심 정보 보존에 도움 가능성이 있습니다. 다만 행/열 구조 복원, 항목-값 매칭, QR/URL 주변 노이즈 처리는 아직 미완성입니다. OCR 결과는 계속 실험 산출물이며 사용자 확인 또는 사람 검수가 필요합니다. MVP 핵심 파이프라인과는 분리해서 유지합니다.

## 실제 실행 확인 결과

2026-04-29 Windows 환경에서 Tesseract `5.4.0.20240606`, language data `eng`, `kor`, `osd`를 확인한 뒤 다음 명령으로 실행했습니다.

```powershell
python run_ocr_experiment.py --input data\samples\sample01.jpg
```

실행 결과 `debug_images/`, `ocr_results/`, `result.json` 생성이 확인되었습니다. 다만 `sample01.jpg`는 원본 이미지가 90도 돌아간 상태라 OCR 품질이 낮았습니다. 기준 텍스트와 비교했을 때 원본 방향에서는 `sharpened`가 상대적으로 가장 나았지만 CER가 약 `0.9540`으로 매우 높았습니다.

방향 문제를 확인하기 위해 로컬 ignore 대상 샘플 `sample01_rotated_cw.jpg`를 만들어 추가 실행했을 때는 `adaptive_threshold`가 가장 낮은 CER 약 `0.5358`을 보였습니다. 다음 단계에서는 자동 회전 보정 또는 촬영 방향 안내가 우선 TODO입니다.

자동 회전 보정 추가 후 `sample01.jpg`는 `best_rotation=rotation_90_cw`로 선택되었고, `adaptive_threshold` 기준 CER가 약 `0.5711`, F1이 약 `0.6174`로 개선되었습니다. 이미 회전된 `sample01_rotated_cw.jpg`는 `best_rotation=rotation_0`을 선택했고, `adaptive_threshold` 기준 CER 약 `0.5358`, F1 약 `0.6821`을 유지했습니다.

표/박스 crop 추가 후 `sample01.jpg`에서 3개 후보가 탐지되었습니다. `table_002`는 신청 사이트 미리보기 표를 잡았고, 일반 OCR에서는 `wwewsarlang.com`처럼 깨지던 URL이 crop OCR에서는 `www.sarlang.com`으로 더 잘 보존되었습니다. `bit.ly/sarlang`은 여전히 깨졌고, `table_003`의 신청 기간 박스는 `2023. 3. 6`, `17` 같은 일부 날짜 조각만 보존되었습니다. 즉, crop OCR은 URL/박스 내부 핵심 문자열 보존 가능성을 보여주지만, 표 구조와 날짜 범위 복원은 추가 개선이 필요합니다.

표 후보 필터링과 config별 OCR 실험 추가 후 `table_001`은 `low_ocr_signal`로 제외 후보가 되었고, `table_002`가 `best_table_id`로 선택되었습니다. `table_summary`에는 `detected_count=3`, `candidate_count=2`, `found_urls=["www.sarlang.com"]`, `found_dates=["2023. 3. 6", "3. 6", "3. 17"]`가 기록됩니다.

## 표 내부 셀 구조 복원

### 왜 필요한가

표 전체 OCR만으로는 항목과 값의 관계를 알 수 없습니다.

예시:
- `신청서 작성 온라인` ↔ `bit.ly/sarlang`
- `온라인 설명회` ↔ `2023. 3. 23.(목)` ↔ `19:00~20:00` ↔ `온라인 ZOOM`

URL과 날짜가 어느 항목의 값인지 연결하려면 표 내부 선 구조 분석이 필요합니다.

### 구현 방식

`src/table_cell_extractor.py`가 아래 순서로 동작합니다.

1. table crop 이미지 기준으로 grayscale → adaptiveThreshold 적용
2. 수평선/수직선 위치 감지 (morphologyEx MORPH_OPEN)
3. ±5px 중복 선 제거
4. 선 위치로 셀 bbox 생성
5. 각 셀 crop → 2배 이상 확대
6. `table_cell_crops/` 폴더에 셀 이미지 저장
7. 셀별 Tesseract OCR (`--psm 6`)
8. 셀별 패턴 추출 (URL/날짜/전화번호/시간/금액)
9. `rows[][]` 2D 배열 생성
10. `result.json tables[].cell_structure` 에 기록

선 감지가 충분하지 않으면 (`uniform_grid` fallback):
- 이미지 비율을 기준으로 2×2 / 4×3 / 3×2 균등 분할
- `method: "uniform_grid"` 로 기록

### 출력 구조

```text
outputs/ocr_experiment/sample01/
└── table_cell_crops/
    ├── cell_table_002_r0c0.png
    ├── cell_table_002_r0c1.png
    ├── cell_table_003_r0c0.png
    ├── cell_table_003_r0c1.png
    └── ...
```

`result.json` 추가 필드:

```json
{
  "tables": [
    {
      "table_id": "table_002",
      "cell_structure": {
        "method": "line_split",
        "row_count": 2,
        "col_count": 2,
        "rows": [
          ["신청서 작성 온라인", "bit.ly/sarlang"],
          ["학습 사이트 미리보기", "www.sarlang.com"]
        ],
        "cells": [
          {
            "row": 0, "col": 0,
            "bbox": [0, 0, 200, 50],
            "text": "신청서 작성 온라인",
            "patterns": {"urls": [], "phones": [], "dates": [], "times": [], "amounts": []}
          }
        ],
        "warnings": []
      }
    }
  ]
}
```

### 1차 구현 결과 (2026-04-29)

`sample01.jpg` (의정부신곡초 가정통신문) 기준:

- `table_002` (신청 사이트 표): `uniform_grid` fallback 사용 → 2×2로 분할 → `r1c1`에서 `www.sarlang.com` URL 탐지 성공
- `table_003` (일정 안내 표): `line_split` 성공 (2×3) → `r0c1`에서 `3. 17` 날짜 조각 탐지
- `table_001` (상단 로고/제호 박스): 셀 분리는 되나 의미 있는 OCR 결과 없음
- `bit.ly/sarlang`: 여전히 불안정 (QR 코드 노이즈 원인)
- `table_003` 실제 4행 구조가 2행으로 복원 → 일정표 행/열 복원 부족

### 셀 구조 복원 2차 개선 (2026-04-29)

1차 한계를 바탕으로 아래 항목을 개선했습니다.

**선 감지 파라미터 완화**:
- kernel ratio를 `[3, 5, 8]` 조합으로 시도
- threshold ratio를 `[0.25, 0.3, 0.4]` 조합으로 시도
- 선 감지 후 dilate 추가 (끊어진 선 연결)
- 가장 유효한 조합을 자동 선택, `line_detection.selected_params`에 기록

**하이브리드 분할**:
- h_lines만 탐지 → row는 선 기반, col은 비율 기반 (`line_split_rows_only`)
- v_lines만 탐지 → col은 선 기반, row는 비율 기반 (`line_split_cols_only`)
- 둘 다 없을 때만 `uniform_grid`

**grid 후보 비교**:
- `uniform_grid` 사용 시 여러 후보(예: 2×2 / 3×4 / 4×3 등)를 대상으로 빠른 OCR을 실행
- URL/날짜/시간 패턴이 가장 많이 탐지되는 구조를 자동 선택
- `grid_candidates`와 `selected_grid_reason`을 result.json에 기록

**셀별 OCR 멀티 variant**:
- `psm6` (기본) + `adaptive_psm6` (adaptive threshold 전처리) 중 best 선택
- 넓은 셀 (aspect ≥ 4): `psm7` 추가 시도
- URL 후보 셀 (col > 0): `url_config` 추가 시도
- 패턴 점수 + 유효 문자 수로 best variant 선택, `ocr_variant` 필드에 기록

**result.json 추가 필드**:
```json
"cell_structure": {
  "line_detection": {
    "h_lines": 1,
    "v_lines": 2,
    "selected_params": {
      "horizontal_kernel_ratio": 5,
      "vertical_kernel_ratio": 5,
      "threshold_ratio": 0.3
    }
  },
  "structure_hint": "url_table_candidate",
  "grid_candidates": [...],
  "selected_grid_reason": "grid_2x2 selected: pattern_count=2, score=10.5",
  "cells": [
    {"row": 0, "col": 1, "text": "www.sarlang.com", "ocr_variant": "url_config", ...}
  ]
}
```

### 현재 한계

- QR 코드 주변 셀은 OCR이 불안정하며 `bit.ly/sarlang` 복원이 어려울 수 있습니다.
- 표 선이 흐리거나 없는 경우 `uniform_grid` fallback이 사용되며 행/열 수가 정확하지 않을 수 있습니다.
- 셀 내부에 여러 줄이 있을 때 줄바꿈 처리는 Tesseract 출력 그대로입니다.
- OCR 결과는 사용자 확인/사람 검수 전제입니다.
- 셀 수가 30개를 초과하면 처음 30개만 처리합니다.
- grid 후보 비교 시 추가 OCR 실행으로 전체 실행 시간이 길어질 수 있습니다.

## 선택 참고 도구

상위 `OCR실험` 폴더에서 참고할 만한 CER/WER 계산 로직은 UTF-8로 정리해 `tools/eval_ocr.py`에 두었습니다. 이 도구는 1차 OCR 실행 파이프라인에 자동 연결하지 않습니다. 사람이 검수한 기준 텍스트가 있을 때만 별도로 사용하세요.

```powershell
python tools\eval_ocr.py `
  --ground-truth data\reference\ocr_ground_truth.txt `
  --ocr-result outputs\ocr_experiment\sample01\ocr_results\warped.txt
```

## 이번 단계에서 하지 않는 것

- PDF 처리 고도화
- 고급 이미지 전처리(구김/그림자/dewarping)
- CER/WER 평가 고도화
- FastAPI/Android 연결
- 팀 메인 레포 코드와 통합
- OCR 결과를 번역/NLLB/TTS로 바로 넘기는 기능
- OCR 결과를 학습 데이터로 저장하는 기능

## Git 관리

`.gitignore`는 다음 항목을 Git에서 제외합니다.

- `.env`
- `.venv/`, `venv/`, `env/`
- `outputs/`
- `data/samples/` 안의 실제 샘플 이미지/PDF
- `data/reference/` 안의 기준 텍스트
- `__pycache__/`, `*.pyc`

샘플 파일과 OCR 산출물은 대용량 또는 개인정보 가능성이 있으므로 Git에 올리지 않습니다.
