# PDF 텍스트 변환 vs 사진 OCR 비교 실험

## Executive Summary

| 항목 | 결론 |
|---|---|
| PDF 원본 입력 | `clean_text` 후보로 가장 안정적 |
| 사진 OCR 입력 | 실제 사용자 촬영 환경 대응 가능성 확인 |
| 자동 회전 보정 | 급식표 sample02에서 `rotation_90_ccw` 자동 선택 성공 |
| 표 탐지 | 급식표 sample03에서 `detected_count` 5, `candidate_count` 2 |
| 셀 OCR | `cell_crops` 최대 28개 생성, 다만 메뉴 셀 복원은 아직 부족 |
| 주요 한계 | 영양성분 수치가 날짜로 오탐, 흐린 사진 품질 저하 |
| 품질 게이트 | 목표는 F1 0.9 이상, CER 0.1 이하이며 현재는 기준 미달 시 review fallback |
| 결론 | MVP는 PDF/HWP/text 우선, 사진 OCR은 quality gate를 통과한 경우만 자동 처리 후보 |

## 1. 실험 목적

SchoolBridge OCR Lab에서 확인한 두 입력 경로를 비교한다. 하나는 급식표 PDF 원본을 텍스트로 변환한 결과이고, 다른 하나는 급식표 사진을 OCR Lab의 이미지 OCR 파이프라인에 넣은 결과다.

목적은 어떤 입력이 후속 정제와 모델 입력에 더 적합한지, 그리고 사진 OCR을 어디까지 입력 보조 기능으로 볼 수 있는지 정리하는 것이다. 이 문서는 기능 연결 계획이 아니라 실험 비교 노트다. FastAPI, Android, NLLB, TTS와 연결하지 않으며, OCR 결과를 학습 데이터나 번역 입력으로 바로 쓰지 않는다.

SchoolBridge의 실제 주 대상은 가정통신문/학교 안내문이다. 급식표는 표가 많은 문서에서 OCR/PDF 텍스트 정제 로직을 검증하기 위한 테스트 샘플이다. 따라서 이 문서의 급식표 결과는 표 구조가 많은 안내문에서 생기는 문제를 보기 위한 실험 근거로만 해석한다.

태수님 파트는 HWP/PDF/text를 `clean_text(str)`로 변환하는 단계까지 담당한다. model input builder와 OCR quality gate는 이 변환 로직을 대체하지 않는다. 사진/image 입력 경로에서는 OCR `result.json`을 받아 품질을 평가하고, 기준을 통과한 경우에만 `verified_text.txt`를 자동 생성한다. 기준 미달이면 `review_text.txt`로 fallback하고, 실패 이유를 `quality_report.json`에 남긴다.

## 2. 비교 대상

### 2.1 PDF 텍스트 변환 결과

태수님 파이프라인에서 급식표 PDF를 텍스트로 변환한 결과다. PDF 원본 기반이라 급식표 제목, 본문, 날짜별 메뉴, 영양성분, 원산지, 안내문이 비교적 많이 보존되었다.

보존된 정보 예시는 다음과 같다.

- `2026학년도 5월 학교급식 안내`
- `담당: 인성체육부`
- `급식비: 4,402원 × 17회 = 74,834원`
- `5/6(수다날)`
- `베트남쌀국수`
- `소세지핫도그`
- `파파야샐러드`
- `배추김치`
- `급식우유`
- `569.36/21.02/274.41/2.7` 같은 영양성분 수치
- 원산지 표
- 공익제보센터 안내

PDF 변환 결과에는 이번 비교에서 CER/F1 같은 정량 지표를 계산하지 않았다. 따라서 PDF 쪽은 보존된 정보 유형, 문제 유형, 후속 입력 적합도 중심으로 판단한다.

### 2.2 사진 OCR 결과

SchoolBridge OCR Lab에서 급식표 사진 3개를 실행한 결과다.

실행 샘플:

```text
meal_table_sample01.jpg
meal_table_sample02.jpg
meal_table_sample03.jpg
```

실행 명령:

```powershell
python run_ocr_experiment.py --input data/samples/meal_table_sample01.jpg
python run_ocr_experiment.py --input data/samples/meal_table_sample02.jpg
python run_ocr_experiment.py --input data/samples/meal_table_sample03.jpg
```

3개 모두 정상 완료했다. 자동 회전 보정, 전체 OCR, 표/박스 crop, cell OCR 실험, `result.json` 저장까지 확인되었다.

## 3. 비교 요약표

| 비교 항목 | PDF 텍스트 변환 | 사진 OCR |
|---|---|---|
| 입력 형태 | PDF 원본 | 직접 촬영/카카오톡 이미지 |
| 텍스트 보존 | 높음 | 중간~낮음 |
| 표 구조 보존 | 일부 보존 | 표 선 탐지는 가능하나 셀 OCR 불안정 |
| 날짜/메뉴 보존 | 비교적 좋음 | 일부 메뉴명만 보존 |
| 영양성분 숫자 처리 | 텍스트는 보존되나 정제 필요 | 날짜 패턴으로 오탐 많음 |
| 회전/기울어짐 대응 | 필요 없음 | 자동 회전 보정 필요 |
| 실제 사용자 사진 대응 | 낮음 | 높음 |
| 후속 모델 입력 적합성 | `clean_text` 후보로 적합 | 사용자 확인/정제 후 가능 |
| 주요 한계 | 중복/줄바꿈/표 구조 | 흐림/각도/셀 복원/오탐 |

## 4. 사진 OCR 샘플별 정량 결과

| 샘플 | best_rotation | rotation_score | detected_count | candidate_count | best_table_id | best_table_reason | cell_crops |
|---|---|---:|---:|---:|---|---|---:|
| meal_table_sample01 | `rotation_0` | 1425.1 | 1 | 1 | `table_001` | Date pattern detected | 10 |
| meal_table_sample02 | `rotation_90_ccw` | 399.0 | 1 | 1 | `table_001` | Date pattern detected | 6 |
| meal_table_sample03 | `rotation_0` | 1498.7 | 5 | 2 | `table_002` | Highest table priority score | 28 |

- sample02는 촬영 방향이 틀어진 이미지였지만 자동 회전 보정이 작동했다.
- sample03은 표 후보가 5개 탐지되어 표 구조가 가장 많이 잡힌 샘플이다.
- `cell_crops` 수가 많다고 OCR 품질이 무조건 좋은 것은 아니며, 실제 메뉴명 복원 여부는 별도 확인이 필요하다.

## 5. PDF 변환 vs 사진 OCR 비교 요약

| 비교 항목 | PDF 텍스트 변환 | 사진 OCR |
|---|---|---|
| 입력 품질 | 디지털 원본 기반 | 촬영 품질에 크게 의존 |
| 회전 보정 필요 | 거의 없음 | 필요함, sample02에서 `rotation_90_ccw` 자동 선택 |
| 표 탐지 수치 | 별도 탐지 수치 없음 | sample01: 1개, sample02: 1개, sample03: 5개 |
| 후보 표 수 | 별도 후보 수 없음 | sample01: 1개, sample02: 1개, sample03: 2개 |
| 셀 crop 수 | 해당 없음 | sample01: 10개, sample02: 6개, sample03: 28개 |
| 메뉴 텍스트 보존 | 비교적 높음 | 전체 OCR에서는 일부 보존, cell OCR에서는 부족 |
| 날짜/숫자 처리 | 날짜와 영양성분이 함께 보존되나 정제 필요 | 영양성분 수치가 날짜로 오탐 |
| 후속 모델 입력 적합성 | 높음, 단 normalization 필요 | 낮음~중간, 사용자 확인/정제 필요 |
| 권장 사용 위치 | MVP 기본 입력 경로 | 향후 image 입력 확장 후보 |

## 6. 내부 실험 기준 점수화

> 아래 점수는 CER/F1 같은 공식 성능 지표가 아니라, 현재 샘플 기준의 실험적 판단이다.

| 평가 항목 | PDF 텍스트 변환 | 사진 OCR |
|---|---:|---:|
| 텍스트 보존 | 4/5 | 2/5 |
| 표 구조 유지 | 3/5 | 2/5 |
| 실제 사용자 촬영 대응 | 1/5 | 4/5 |
| 후속 모델 입력 안정성 | 4/5 | 2/5 |
| 추가 정제 필요도 | 3/5 | 5/5 |

PDF 변환은 텍스트 보존과 후속 모델 입력 안정성에서는 유리하지만, 실제 종이 문서를 촬영하는 상황에는 대응하지 못한다.

사진 OCR은 실사용 입력 형태를 다룰 수 있다는 장점이 있지만, 촬영 품질과 표 구조에 따라 결과가 크게 흔들려 사용자 확인과 정제 단계가 필수다.

## 7. PDF 텍스트 변환 결과 분석

### 장점

PDF 원본이 있는 경우에는 사진 OCR보다 텍스트 보존률이 훨씬 좋다. 제목, 날짜, 메뉴, 영양성분, 원산지, 안내문까지 많은 정보가 남아 있기 때문에 후속 `clean_text` 입력 후보로 쓰기 좋다.

급식표처럼 표와 숫자가 많은 문서에서도 PDF 기반 텍스트 변환은 문자의 손실이 상대적으로 적다. 사진 OCR에서 자주 발생하는 회전, 흔들림, 그림자, 구겨짐 문제도 없다.

### 한계

PDF 변환도 완성된 구조화 결과는 아니다. 표 구조가 행/열로 완벽히 복원되지 않고, 일부 텍스트 오탈자가 있다. 예를 들면 `칼슠` 같은 잘못된 문자 조합이 남을 수 있다.

또한 표 내용이 중복으로 풀리거나, `2 5/27(수다날)`처럼 숫자 잡음이 섞이는 부분이 있다. 영양성분 수치와 날짜 패턴이 섞일 가능성도 있어서 윤정님 모델에 넣기 전에는 줄바꿈, 중복, 숫자, 날짜/영양성분 구분을 정리해야 한다.

## 8. 사진 OCR 결과 분석

### 장점

사진 OCR은 실제 사용자가 종이 안내문을 촬영해 올리는 상황을 다룰 수 있다. PDF 원본이 없거나, 카카오톡으로 이미지가 전달되는 경우를 생각하면 사진 OCR은 입력 보조 기능으로 의미가 있다.

이번 급식표 실험에서는 자동 회전 보정이 동작했다. 특히 `meal_table_sample02.jpg`는 `rotation_90_ccw`가 자동 선택되었다. 급식표는 표 선이 비교적 명확해서 일반 가정통신문보다 line split과 표 후보 탐지가 잘 되는 편이었다.

전체 OCR에서는 일부 메뉴명이 살아났다.

- `2026 학년도`
- `5월 학교 급식 안내`
- `급식비`
- `무상급식비`
- `베트남쌀국수`
- `소세지핫도그`
- `파파야샐러드`
- `배추김치`
- `급식우유`
- `만두국`
- `잡곡밥`
- `쇠고기미역국`

### 한계

사진 OCR 품질은 PDF 텍스트 변환보다 낮다. 글자 간격, 한글 깨짐, 메뉴 섞임이 많고 표 안의 행/열 관계도 안정적으로 복원되지 않는다.

가장 눈에 띄는 문제는 영양성분 숫자가 날짜로 오탐되는 것이다. 예를 들어 `13.16`, `1.5`, `6.10` 같은 영양성분 또는 알레르기 숫자가 날짜 패턴으로 잡히면서 `found_dates`가 과도하게 늘어난다.

급식표는 셀 수가 많다. 5주 × 5일 구조에 메뉴와 영양성분까지 포함되면 실제 복원해야 할 셀이 많아진다. 현재 cell OCR 실험의 `_MAX_CELLS = 30` 제한으로는 전체 복원이 어렵다.

`meal_table_sample02.jpg`는 회전은 잡았지만 흐림과 각도 문제로 OCR 품질이 낮았다. 표 선 분석에서도 `h_lines=0`, `v_lines=0`이었고, uniform grid fallback을 사용했다. 즉 자동 회전만으로는 흐림/기울어짐 문제를 해결하지 못한다.

## 9. 급식표 샘플별 결과

### meal_table_sample01

- `best_rotation`: `rotation_0`
- `rotation_score`: 1425.1
- `detected_count`: 1
- `candidate_count`: 1
- `best_table_id`: `table_001`
- `best_table_reason`: Date pattern detected
- `cell_crops`: 10

전체 OCR에서 급식표 제목, 급식비, 일부 메뉴명이 보존되었다. `베트남쌀국수`, `소세지핫도그`, `파파야샐러드`, `배추김치`, `급식우유` 같은 메뉴가 일부 확인되었다.

다만 cell OCR만으로 날짜별 메뉴 전체를 안정적으로 복원하기에는 부족했다. 영양성분 숫자가 날짜처럼 잡히는 오탐도 있었다.

### meal_table_sample02

- `best_rotation`: `rotation_90_ccw`
- `rotation_score`: 399.0
- `detected_count`: 1
- `candidate_count`: 1
- `best_table_id`: `table_001`
- `best_table_reason`: Date pattern detected
- `cell_crops`: 6

자동 회전 보정은 성공했다. 하지만 사진 자체가 흐리거나 각도가 좋지 않아 OCR 품질이 낮았다. 표 선이 충분히 잡히지 않아 `h_lines=0`, `v_lines=0` 상태였고, uniform grid fallback을 사용했다.

이 샘플은 사진 OCR에서 입력 품질 관리가 필요하다는 점을 보여준다. 촬영 방향뿐 아니라 초점, 흔들림, 그림자, 기울어짐까지 영향을 준다.

### meal_table_sample03

- `best_rotation`: `rotation_0`
- `rotation_score`: 1498.7
- `detected_count`: 5
- `candidate_count`: 2
- `best_table_id`: `table_002`
- `best_table_reason`: Highest table priority score
- `cell_crops`: 28

표 후보와 cell crop이 가장 많이 생성된 샘플이다. 급식표 선이 비교적 잘 잡혀서 표 분할 가능성은 보였지만, 셀 단위 OCR 품질은 아직 충분하지 않다.

후속 실험에서는 급식 달력 테이블과 영양성분/원산지 테이블을 구분하는 parser가 필요하다. 단순히 셀을 많이 자르는 것만으로는 메뉴 구조를 안정적으로 복원하기 어렵다.

## 10. 발견된 주요 문제

| 문제 | 발생 위치 | 근거 |
|---|---|---|
| 영양성분 수치의 날짜 오탐 | 사진 OCR | `13.16`, `1.5`, `6.10` 같은 수치가 날짜 후보로 잡힘 |
| 급식표 셀 수 초과 | 사진 OCR | 5주 × 5일 × 메뉴행 구조로 실제 셀 수가 많아 `_MAX_CELLS = 30` 한계 발생 |
| 흐린 사진 OCR 품질 저하 | `meal_table_sample02` | `rotation_90_ccw`는 성공했지만 `h_lines=0`, `v_lines=0`으로 uniform grid fallback |
| 표 중복/줄바꿈 문제 | PDF 변환 | 표 내용이 문단형 텍스트와 표 형태로 중복 추출됨 |
| 메뉴 셀 단위 복원 부족 | 사진 OCR | 전체 OCR에서는 메뉴 일부가 보이나 cell OCR에서는 안정적 복원 부족 |

## 11. 주요 인사이트

PDF 원본이 있는 경우에는 PDF 텍스트 변환 방식이 우선이다. 텍스트 보존률이 높고, 후속 정제 대상으로 삼기 쉽다.

사진 OCR은 실제 사용자가 종이 안내문을 촬영해 올리는 상황을 위한 확장 후보로 보는 것이 맞다. 가능성은 있지만 MVP 핵심 기능으로 바로 넣기에는 품질 변동이 크다.

두 방식 모두 결과를 그대로 정답으로 쓰면 안 된다. PDF 변환 결과도 중복, 줄바꿈, 숫자 섞임이 있고, 사진 OCR 결과는 회전, 흐림, 셀 복원, 날짜 오탐 문제가 있다.

급식표처럼 표 선이 명확한 문서에서도 OCR은 가능성이 있지만, 메뉴 셀 복원과 영양성분 숫자 오탐은 추가 개선이 필요하다.

## 12. 후속 모델 입력 관점

윤정님 모델에 넣기 전에는 두 경로 모두 `clean_text` normalization이 필요하다.

PDF 텍스트 변환 결과는 후속 모델 입력 후보로 더 적합하다. 다만 줄바꿈, 중복, 숫자 오탐, 표 구조 깨짐을 정리해야 한다. 특히 급식표는 날짜/메뉴/영양성분/원산지/안내문이 섞여 있으므로 문서 목적에 맞는 섹션 분리가 필요하다.

사진 OCR의 최종 목표는 사용자 확인 없이 자동 처리 가능한 수준까지 품질을 끌어올리는 것이다. 내부 목표는 F1 `0.9` 이상, CER `0.1` 이하, 핵심 패턴(URL/전화번호/날짜/시간/금액) 누락 최소화다.

다만 현재 상태에서는 OCR 원문을 바로 모델 입력으로 넣으면 메뉴명과 숫자 정보가 섞이거나 잘못 해석될 위험이 크다. 따라서 사진/image 경로에는 OCR quality gate가 필요하다. quality gate는 `result.json`에서 텍스트 품질, 핵심 패턴 보존, 표/셀 OCR 신호를 점수화하고, 기준을 통과한 샘플만 `verified_text.txt`로 자동 생성한다. 대부분의 현재 샘플은 자동 통과보다 `review_text.txt` fallback이 정상이며, `quality_report.json`으로 자동 통과 실패 이유를 기록한다.

## 13. 다음 개선 후보

### PDF 변환 결과 개선

- 표 중복 제거
- 줄바꿈 정리
- 날짜/메뉴 단위 정리
- 영양성분 수치와 날짜 구분
- `model_input_text.txt` 생성

### 사진 OCR 개선

- 날짜 regex 필터 강화
- 영양성분 숫자와 날짜 분리
- `_MAX_CELLS` 조건부 확대
- 급식표 특화 parser
- OCR quality gate 추가
  - 목표: F1 0.9 이상, CER 0.1 이하
  - `text_quality`, `pattern`, `table` 점수 계산
  - 기준 통과 시 `verified_text.txt` 생성
  - 기준 미달 시 `review_text.txt` fallback
  - `quality_report.json`에 실패 이유 기록
- 흐린 사진 대응 전처리
  - CLAHE
  - unsharp masking
  - shadow reduction
- 사진 OCR 결과를 quality gate로 평가한 뒤 자동 통과 또는 review fallback 분기

### 공통 개선

- OCR/PDF 변환 결과 통합 정제본 생성
- `key_patterns.json` 생성
- 사용자 확인용 `review_text.txt` 생성
- 호환용 후속 입력 후보 `model_input_text.txt` 생성
- 다음 기능 업데이트로 model input builder를 추가한다. 이 도구는 태수님 `clean_text` 경로를 대체하지 않고, 사진/image OCR `result.json`을 받아 `review_text.txt`, `key_patterns.json`, `normalization_report.json`을 생성한다.
- 이어서 OCR quality gate를 추가한다. 이 도구는 OCR `result.json`을 받아 `verified_text.txt`, `review_text.txt`, `key_patterns.json`, `quality_report.json`을 생성하고, 기준 미달 시 자동 통과시키지 않는다.

## 14. 결론

이번 비교에서 PDF 변환은 정량 CER/F1은 없지만, 급식표의 날짜·메뉴·영양성분·원산지·안내문을 대부분 텍스트로 보존했다.

사진 OCR은 3개 샘플 모두 파이프라인 실행에는 성공했고, sample02에서는 자동 회전 보정이 작동했으며, sample03에서는 표 후보 5개와 cell crop 28개가 생성되었다.

하지만 사진 OCR은 영양성분 숫자 오탐, 메뉴 셀 복원 부족, 흐린 사진 품질 저하가 확인되었기 때문에 MVP 기본 입력으로 바로 쓰기에는 아직 부족하다. 최종 목표는 F1 0.9 이상, CER 0.1 이하 수준의 자동 처리지만, 현재는 quality gate를 통과한 샘플만 `verified_text.txt`로 자동 생성하고 나머지는 `review_text.txt`로 fallback하는 방식이 적절하다.

두 방식 모두 결과를 그대로 정답으로 쓰면 안 된다. 윤정님 모델에 넣기 전에는 줄바꿈, 중복, 숫자 오탐, 표 구조 깨짐을 정리해야 한다. 현재 기준으로는 PDF/HWP/text 변환 결과를 우선 `clean_text` 경로로 유지하고, 사진 OCR은 quality gate 기반의 자동 통과/검토 fallback 실험으로 분리 유지하는 것이 좋다.
