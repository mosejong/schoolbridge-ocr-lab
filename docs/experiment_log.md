# OCR 실험 로그 — SchoolBridge OCR Local Lab

**기준일:** 2026-04-30  
**실험자:** mosejong  
**환경:** Windows 11 / Python 3.x / Tesseract v5.4.0 / lang=kor+eng

---

## 1. 실험 목적

SchoolBridge 앱이 수신하는 학교 문서(가정통신문, 급식표)에 대해 로컬 OCR 파이프라인의 가능성과 한계를 측정한다.
Android ML Kit 기반 OCR(score_history.md 참조, overall ≈ 0.82)과 비교 가능한 baseline을 Tesseract로 확보하고,
표 내부 셀 구조 복원까지 확장하여 다음 단계 구현 판단 자료로 활용한다.

**비고:** OCR 결과는 실험 산출물이며 ground truth가 아님. 학습 데이터로 직접 사용 금지.

---

## 2. 공통 파이프라인

```
입력 이미지 (JPG/PNG)
  └─ image_preprocess.py
       ├─ 회전 후보 4개 평가 (rotation_0/90_cw/90_ccw/180)
       └─ 최고 점수 회전 선택 + perspective / threshold / deskew variant 생성
  └─ table_detector.py
       ├─ contour 기반 테이블 영역 탐지
       ├─ zoom2x / zoom3x 확대 crop 생성
       └─ IOU 기반 중첩 제거 + 후보 우선순위 점수 부여
  └─ table_cell_extractor.py  (2차 개선 후 추가)
       ├─ 27가지 파라미터 조합으로 수평/수직 선 탐지
       ├─ line_split / uniform_grid 하이브리드 결정
       └─ 셀별 멀티 variant OCR (psm6 / psm7 / url_config)
  └─ ocr_runner.py
       └─ 전처리 variant + 테이블 crop 전체 pytesseract 실행
  └─ json_builder.py
       └─ result.json 생성 (patterns / cell_structure / table_summary 포함)
```

출력: `outputs/ocr_experiment/<stem>/result.json`

---

## 3. 가정통신문 샘플 결과

> **참조 문서:** `data/reference/ocr_ground_truth.txt`  
> **평가 도구:** `tools/eval_ocr.py` (CER / WER / 자모CER / F1)

### 3-1. 전처리 단계별 CER 추이

| 단계 | 적용 기법 | CER | 비고 |
|---|---|---|---|
| 기준 (raw) | 없음 | 0.9540 | 회전 미보정 상태 |
| 회전 보정 | rotation_score 기반 자동 선택 | 0.7200 | 기울임 조건 개선 |
| perspective + deskew | warped variant | 0.5711 | 구겨짐 조건 최저 |

- **URL 탐지:** `table_summary.found_urls` — 학교 홈페이지 URL 1건 정확 추출
- **날짜 탐지:** 제출 마감일, 행사일 등 날짜 패턴 다수 추출 성공
- **cell OCR:** table_001 기준 URL이 포함된 셀(r0c1) 위치 특정 성공

### 3-2. 한계

- CER 0.57 수준 — ML Kit overall 0.82와 직접 비교 시 Tesseract가 열세
- line_accuracy ≈ 0 (줄 순서 불일치, 복수 열 텍스트 병합 오류)
- 소형 글자(주의사항 단락) 인식률 낮음

---

## 4. 급식표 샘플 결과

급식표 3개 샘플은 `data/samples/` 에 로컬 복사 후 실험. (파일 자체는 .gitignore 제외)

### 4-1. meal_table_sample01

| 항목 | 값 |
|---|---|
| 회전 보정 | rotation_0 (점수 1425) |
| 탐지 테이블 수 | 1 |
| cell 구조 복원 방법 | **line_split** (h_lines=4, v_lines=1) |
| 그리드 크기 | 5행 × 2열 |
| 저장 셀 수 | 10 |
| 최고 OCR 텍스트 | r1c1 — "2026학년도 5월 학교 급식 안내" |
| 주요 패턴 | date 다수 (영양성분 소수점값 오탐 포함) |

**특이사항:** 수직선 1개만 탐지되어 `line_split_cols_only` 대신 `line_split` 처리됨.
(h_lines 4개 기준으로 행 경계는 명확히 잡힘)

### 4-2. meal_table_sample02

| 항목 | 값 |
|---|---|
| 회전 보정 | **rotation_90_ccw** 자동 보정 성공 |
| 탐지 테이블 수 | 1 |
| cell 구조 복원 방법 | **uniform_grid** (h/v_lines 모두 0) |
| 그리드 크기 | 3행 × 2열 |
| 저장 셀 수 | 6 |
| 주요 패턴 | 탐지 없음 |

**특이사항:** 이미지 품질 낮음(저조도 촬영), 선 탐지 실패로 uniform_grid 폴백.
균등 분할로 셀 위치는 근사치 수준.

### 4-3. meal_table_sample03

| 항목 | 값 |
|---|---|
| 회전 보정 | rotation_0 (점수 1499) |
| 탐지 테이블 수 | 5 (candidates=2) |
| 최우선 테이블 | table_002 |
| cell 구조 복원 방법 | **line_split** (4행 × 3열) |
| 저장 셀 수 | 28 (table_004 포함 4행 × 7열) |
| 주요 패턴 | date, phone 탐지 |

**특이사항:** table_002의 수직선 4개(실제 1개) — QR 코드 박스 외곽선이 vertical line으로 오탐됨.
table_004는 주간 급식표 구조로 4×7 그리드 성공적 복원.

---

## 5. 비교 인사이트

### 가정통신문 vs 급식표

| 비교 항목 | 가정통신문 | 급식표 |
|---|---|---|
| 표 구조 복잡도 | 중간 (단일 테이블, 혼합 텍스트) | 높음 (복수 테이블, 주간 캘린더) |
| line_split 성공률 | 중간 (선명도 따라 다름) | **높음** (급식표는 명확한 격자선) |
| 날짜 패턴 정확도 | 높음 | **낮음** (영양성분 소수점 오탐) |
| 회전 보정 | 필요 시 자동 보정 | sample02 90도 보정 성공 |
| URL 탐지 | 학교 홈페이지 URL 포함 | 없음 |
| 셀 수 제한 _MAX_CELLS=30 | 영향 없음 | **영향 있음** (5주×5일 캘린더 = 25+ 날짜행) |

### PDF vs 사진 (로컬 실험 관측)

| 항목 | PDF | 사진 (JPG) |
|---|---|---|
| 해상도 | 원본 벡터 → 고해상도 변환 가능 | 촬영 조건 의존 |
| 회전 노이즈 | 없음 | 최대 90도 기울임 발생 |
| 표 선명도 | 항상 선명 | 저조도/원근 왜곡 영향 |
| OCR 파이프라인 | pdf2image + poppler 필요 | 현재 지원 |
| Tesseract CER 예상 | ≤ 0.15 (고품질 PDF 기준) | 0.27~0.54 |

> **결론:** PDF 경로가 가능하다면 OCR 품질은 사진 대비 2배 이상 개선 기대.

---

## 6. 다음 개선 후보

### 우선순위 높음

| 후보 | 내용 | 예상 효과 |
|---|---|---|
| **날짜 regex 강화** | 월≤12, 일≤31 범위 검증 추가 | 급식표 영양성분 오탐(`4.6`, `9.10`) 제거 |
| **`_MAX_CELLS` 조건부 확대** | 테이블 면적/비율 기준 상한 50~100으로 확장 | 5주 급식 캘린더 전체 복원 |
| **QR 코드 마스킹** | contour 중 정사각형 + 작은 크기 → 수직선 탐지 전 제외 | table_003 v_lines 오탐 제거 |

### 우선순위 중간

| 후보 | 내용 | 예상 효과 |
|---|---|---|
| **CLAHE / unsharp masking** | 저조도 이미지 대비 강화 | sample02처럼 uniform_grid 폴백 비율 감소 |
| **PDF 경로 실험** | `pdf2image` + poppler 설치 후 PDF → PNG 변환 후 파이프라인 통과 | CER ≤ 0.15 기대 |
| **line_split_rows_only 개선** | 행만 탐지 시 컬럼 균등 분할 대신 텍스트 위치 기반 열 추정 | 2열 이상 구조 복원율 향상 |

---

## 7. 결론

| 지표 | 결과 | 판단 |
|---|---|---|
| Tesseract CER (가정통신문) | 0.57 (warped) | ML Kit 0.82 overall 대비 열세. 보조 경로 적합 |
| 회전 자동 보정 | 3/3 성공 | 실사용 수준 |
| 테이블 탐지 | 5/5 케이스 1건 이상 탐지 | 실사용 수준 |
| line_split 성공 (급식표) | 2/3 성공 (1건 uniform_grid 폴백) | 선명한 표에 한해 사용 가능 |
| URL/날짜 패턴 추출 | URL 1건 정확, 날짜 오탐 있음 | regex 강화 필요 |
| cell 구조 복원 | 구조 확인 가능, _MAX_CELLS 한계 노출 | 추가 개선 후 판단 |

**전체 결론:** 사진 기반 Tesseract OCR은 F1 관점에서는 어떤 텍스트가 존재하는지 파악 가능한 수준(F1 0.90+)이나, 글자 정확도(CER) 관점에서는 ML Kit 대비 열세. PDF 입력이 확보되면 파이프라인 품질이 급상승할 것으로 예상됨. 현재 단계에서 OCR은 `review_required` 경로로 운용하고, 사용자 확인 UX 이후 downstream 처리가 적합하다.
