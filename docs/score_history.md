# Android ML Kit OCR — 실험 노트 (최종)

**목표:** overall_score ≥ 0.90 (auto_pass)  
**ground truth:** `data/reference/ocr_ground_truth.txt`  
**threshold:** 0.90 / CER 목표 ≤ 0.10 / F1 목표 ≥ 0.90

---

## 단계별 기법 적용 이력

| # | 기법 | 적용 위치 | 효과 |
|---|---|---|---|
| 1 | postProcess (짧은 줄 필터) | Android Java | 기울임 0.7593 → 0.8077 (+0.048) |
| 2 | EXIF 자동 회전 보정 | Android Java | 기울임 +0.002 |
| 3 | 그레이스케일 + 대비강화 (ColorMatrix) | Android Java | 정면 +0.004 |
| 4 | 이진화 (128 threshold) | Android Java | 전 조건 손해 — 단독 사용 비추 |
| 5 | Perspective Transform (OpenCV 4.9) | Android Java | 구겨짐 최고 0.8219 |
| 6 | 멀티 variant 자동 선택 (scoreText) | Android Java | BEST txt 자동 저장 |
| 7 | warped + gray_contrast 조합 | Android Java | 기울임 CER 0.3255 최저 |

---

## Round 1 — 낮 촬영 (원본 빌드)

| 파일 | overall | CER | F1 | 비고 |
|---|---|---|---|---|
| android_mlkit_112127 (정면) | 0.8085 | 0.3606 | 0.9364 | |
| android_mlkit_112155 (기울임, postProcess 전) | 0.7593 | - | - | |
| android_mlkit_112155 (기울임, postProcess 후) | 0.8077 | 0.3230 | 0.9192 | +0.048 |
| android_mlkit_112228 (구겨짐) | 0.8108 | 0.3681 | 0.8937 | |
| android_mlkit_113327 (정면 재촬영) | 0.8122 | 0.3673 | 0.9209 | |

---

## Round 2 — 밤 촬영 (3종 variant, EXIF 보정 전)

| 조건 | raw | gray_contrast | binary |
|---|---|---|---|
| 정면 | 0.8147 | **0.8183** | 0.8092 |
| 기울임 | 0.8155 | 0.8096 | 0.8080 |
| 구겨짐 | **0.8242** | 0.8238 | 0.8190 |

---

## Round 3 — EXIF 회전 보정 추가 (3종 variant)

| 조건 | raw | gray_contrast | binary |
|---|---|---|---|
| 정면 | 0.8147 | 0.8147 | 0.8097 |
| 기울임 | **0.8177** | 0.8154 | 0.8139 |
| 구겨짐 | 0.8211 | **0.8222** | 0.8165 |

---

## Round 4 — 4종 variant (warped 추가)

| 조건 | raw | gray_contrast | binary | warped |
|---|---|---|---|---|
| 정면 | 0.8177 | 0.8156 | 0.8196 | 0.8182 |
| 기울임 | 0.8175 | **0.8210** | 0.8149 | 0.8180 |
| 구겨짐 | 0.8211 | 0.8152 | 0.8132 | **0.8217** |

---

## Round 5 — 6종 전 조합 + BEST 자동 선택

| 조건 | raw | gray | binary | warped | warped_gray | warped_binary | BEST |
|---|---|---|---|---|---|---|---|
| 정면 | 0.8193 | 0.8193 | 0.8154 | 0.8178 | 0.8187 | 0.8144 | **0.8195** |
| 기울임 | 0.8152 | 0.8180 | 0.8172 | 0.8157 | 0.8177 | 0.8179 | 0.8169 |
| 구겨짐 | 0.8214 | 0.8143 | 0.8126 | **0.8219** | 0.8139 | 0.8133 | 0.8216 |

### Round 5 CER / F1 상세

| 조건 | variant | overall | CER | F1 |
|---|---|---|---|---|
| 정면 | raw | 0.8193 | 0.2679 | 0.9045 |
| 정면 | gray_contrast | 0.8193 | 0.2763 | 0.9239 |
| 정면 | binary | 0.8154 | **0.2663** | 0.8493 |
| 정면 | warped | 0.8178 | 0.2705 | 0.9228 |
| 정면 | warped_gray | 0.8187 | 0.2688 | 0.9137 |
| 정면 | BEST | 0.8195 | 0.2688 | 0.9045 |
| 기울임 | raw | 0.8152 | 0.3389 | 0.9176 |
| 기울임 | gray_contrast | 0.8180 | 0.3272 | 0.9292 |
| 기울임 | binary | 0.8172 | 0.3773 | 0.7920 |
| 기울임 | warped | 0.8157 | 0.3414 | 0.9176 |
| 기울임 | warped_gray | 0.8177 | **0.3255** | **0.9292** |
| 기울임 | BEST | 0.8169 | 0.3756 | 0.7920 |
| 구겨짐 | raw | 0.8214 | 0.4866 | 0.8582 |
| 구겨짐 | warped | **0.8219** | 0.4866 | 0.8582 |
| 구겨짐 | gray_contrast | 0.8143 | 0.4374 | 0.8696 |
| 구겨짐 | warped_gray | 0.8139 | 0.4357 | 0.8696 |
| 구겨짐 | binary | 0.8126 | **0.4149** | 0.7572 |
| 구겨짐 | BEST | 0.8216 | 0.4866 | 0.8582 |

---

## 전체 실험 최고 기록

| 조건 | 최고 overall | variant | Round |
|---|---|---|---|
| 정면 | **0.8242** | raw | R2 |
| 기울임 | **0.8210** | gray_contrast | R4 |
| 구겨짐 | **0.8219** | warped | R5 |

| 조건 | 최저 CER | variant |
|---|---|---|
| 정면 | **0.2663** | binary |
| 기울임 | **0.3255** | warped_gray |
| 구겨짐 | **0.4149** | binary |

---

## Round 5 전체 지표 (eval_ocr.py — BEST variant 기준)

| 지표 | 정면 BEST | 기울임 warped_gray | 구겨짐 warped |
|---|---|---|---|
| **CER** | 0.282 | 0.343 | 0.506 |
| **WER** | 0.322 | 0.330 | 0.579 |
| **자모 CER** | 0.249 | 0.256 | 0.416 |
| **line_accuracy** | 0.000 | 0.063 | 0.020 |
| **Precision** | 0.970 | 0.964 | 0.946 |
| **Recall** | 0.960 | 0.952 | 0.948 |
| **F1** | **0.965** | **0.958** | **0.947** |

**해석:**
- F1 0.95~0.97 — 어떤 단어가 있는지(집합 기준)는 거의 다 잡음
- CER 0.28~0.51 — 글자 위치/순서까지 정확히는 어려움
- 자모 CER < CER — 완전히 틀린 글자보다 비슷한 글자 오인식이 많음 (한국어 특성)
- line_accuracy ≈ 0 — OCR이 줄 순서/병합을 다르게 처리하기 때문

---

## 최종 결론

```
ML Kit Korean OCR 한계치: overall ~0.82, CER ~0.27~0.49
목표(overall ≥ 0.90 / CER ≤ 0.10) 미달

→ 사진 입력은 항상 review_required
→ 사용자 확인 UX 필요
→ 디지털 입력(HWP/PDF → pdfplumber)이 기본 경로
→ 사진 OCR은 보조 경로로 분리 운용

binary 전처리: overall 손해, CER은 낮지만 F1 동반 하락 → 제외
warped_gray: 기울임에서 CER 0.3255, F1 0.9292 — 기울임 최적 조합
warped: 구겨짐에서 overall 최고 — 구겨짐 최적 조합
gray_contrast: 정면에서 안정적
```

---

## 구현 완료 목록 (OcrActivity.java)

- [x] 조건 선택 버튼 (정면/기울임/구겨짐)
- [x] 카메라 라벨 자동 적용 (실험2/3/4)
- [x] UTF-8 BOM 저장
- [x] EXIF 회전 보정
- [x] 6종 전처리 variant 동시 실행
- [x] scoreText() 자동 점수 계산
- [x] BEST variant 자동 선택 및 저장
- [x] Perspective Transform (OpenCV 4.9)
