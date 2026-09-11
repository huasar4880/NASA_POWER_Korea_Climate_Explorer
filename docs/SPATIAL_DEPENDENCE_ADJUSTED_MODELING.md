# Spatial Dependence–Adjusted Modeling — Experimental Stage 14

## 1. 목적 및 범위

해안거리·위도·고도와 KMA 기온추세 및 NASA−KMA 차이의 통계적 연관을
공간의존성 진단과 함께 평가한다. 인과효과, 예측, 머신러닝, 자동 변수선택,
기후위험 점수는 구현하지 않는다. Stable VERSION은 1.0.0으로 유지한다.

## 2. 13단계 배경

원변수의 Moran과 회귀잔차 Moran은 다르다. 해안거리·위도·고도가 원변수의
공간패턴 일부를 설명하면 잔차 Moran은 비유의일 수 있다. 저장된 13단계 robustness
summary를 그대로 연결하며 TAVG를 임의로 robust positive라고 재분류하지 않는다.

## 3. 데이터 및 outcomes

Final Tier A station 목록, screening shortlist, 12단계 spatial master 및
13단계 공식 해안선 기반 station distance CSV를 읽는다. ID 집합, 중복, 좌표·고도,
Tier A, manual-review 및 unresolved continuity 제외 조건을 검증한다.
관측소 수는 파일에서 계산하며 특정 수를 분석 선택 조건으로 하드코딩하지 않는다.

| Outcome | 정의 | 단위 |
|---|---|---|
| kma_tavg_sen_slope | KMA 연평균 기온의 기존 Sen slope | °C/10년 |
| tavg_bias | 동일 pair의 NASA−KMA 기온 Bias | °C |
| tavg_rmse | 동일 pair의 NASA−KMA 기온 RMSE | °C |

Raw/processed/기존 결과 모두 읽기 전용이다. NASA/KMA API와 해안선 다운로드는 없다.
관측소 slope의 추정오차는 이번 단면 회귀에 별도로 반영하지 않는다.

## 4. Predictors 및 scaling

Main은 distance_to_coast_km(km), latitude(degree), elevation_m(m)이다.
Longitude(degree)는 directed KNN k=4 sensitivity에서만 추가한다.
필수값이 NaN/inf이거나 설계행렬이 rank-deficient이면 자동 대체/삭제 없이 중단한다.

Original model과 standardized_predictors를 분리한다. z=(x−mean)/SD, SD는 ddof=0.
Outcome은 표준화하지 않는다. 따라서 표준화 계수 단위는 outcome/1 predictor SD이며
predictor의 상대 크기 참고용이지 영향력 순위가 아니다.

별도 중복 적합 대신 정확한 affine reparameterization을 사용한다:
βz,j=SDj·βj, βz,0=β0+Σmeanj·βj, Covz=T·Cov·Tᵀ.
SAR의 rho와 SEM의 lambda는 그대로 유지한다. 독립적으로 z-score 자료를 재적합한
단위 테스트에서 coefficient와 SE의 동등성을 검증한다.

## 5. OLS

y=β0+β1·coast+β2·latitude+β3·elevation+ε.
statsmodels OLS, classical SE, df=n−p의 t검정과 95% CI, R², adjusted R²를 저장한다.
동일 OLS 적합을 네 가중치의 잔차 진단에 재사용한다. 13단계 TAVG/Bias의 모든
OLS 계수를 기존 표와 대조해 재현 여부를 별도 표에 저장한다.

## 6. HC3

HC3 sandwich covariance=(XᵀX)⁻¹Xᵀdiag[eᵢ²/(1−hᵢᵢ)²]X(XᵀX)⁻¹.
작은 표본을 고려해 t(df=n−p) CI/p를 사용한다. 계수는 OLS와 같으며 SE만 다르다.
HC3는 이분산 강건 추론이지 공간상관 보정이 아니다. SAR/SEM의 ML z검정이
유의해도 OLS-HC3의 비유의를 지워서 해석하지 않는다.

## 7. OLS diagnostics 및 영향점

- Jarque–Bera: 정규성 진단.
- Breusch–Pagan: statsmodels 기본 robust=True의 studentized Koenker 버전.
- VIF: intercept를 포함한 설계행렬에서 predictor만 보고; VIF>5 flag, 자동 제거 없음.
- Cook's distance: D>4/n flag; 모든 station은 main 결과에 유지한다.

Main/longitude 모델의 진단은 별도로 저장한다. LM 입력용 spreg OLS는 사용하지 않는
nonspatial summary diagnostics를 끄고, 실제 OLS diagnostics는 statsmodels 결과를 쓴다.

## 8. Residual Moran

기존 `global_moran_permutation`과 `align_values`를 재사용한다.
Seed는 13단계 설정값 + 기존 GLOBAL_VARIABLES outcome index
(TAVG 0, Bias 4, RMSE 5). 999회이며 양측 극단성은 |I−E[I]|,
E[I]=−1/(n−1), p=(extreme+1)/(999+1)이다.

모든 잔차는 station ID로 명시적 정렬 후 같은 W를 사용한다. 무작위 순열마다
회귀를 재적합하지 않으므로 잔차의 교환가능성 가정이 제한적이다. 이 p는
탐색적 공간잔차 진단이며 작은 표본에서 엄밀한 모형별 검정으로 과대해석하지 않는다.

p<.05면 선택한 W에 잔차 공간구조가 남을 가능성, p≥.05면 해당 W에서 유의한
증거가 확인되지 않았다고 기술한다. 원래 비유의인 잔차를 spatial model로
비유의로 만들었다고 해서 개선이 입증된 것은 아니다.

## 9. SAR

y=ρWy+Xβ+ε. spreg.ML_Lag(method='full'), Gaussian ML, 점근적 z검정.
보고하는 β는 구조식 coefficient이며 total/direct/indirect impact가 아니다.
잔차 ε=y−ρWy−Xβ를 비교한다. 구조식에서 Wy를 빼기 전 y−Xβ도 별도 저장한다.
rho를 인과적 주변지역 영향으로 해석하지 않는다.

## 10. SEM

y=Xβ+u; u=λWu+ε. spreg.ML_Error(method='full').
spreg.u는 structural residual u, spreg.e_filtered는 ε=(I−λW)u이다.
OLS/SAR와 post-adjustment Moran을 비교할 때 filtered innovation ε를 사용한다.
u의 Moran도 summary의 structural_residual_moran_I/p에 저장해 정의 차이를 숨기지 않는다.
lambda는 미관측 공간잔차 구조와 관련된 통계적 모수이지 물리적 확산이 아니다.

## 11. LM diagnostics

spreg.LMtests의 lml, rlml, lme, rlme를 가중치별로 저장한다. Robust LM은
대안 spatial lag/error specification에 대한 보정이며 HC3 이분산 강건 검정과 다르다.
계산이 실패하면 unavailable을 기록하고 다른 분석을 계속한다. LM 하나로 모델을 고르지 않는다.

## 12. Spatial weights 및 alignment

13단계 함수를 그대로 재사용한다. 자기 자신 가중치 0, 비음수, 행합 1.

1. Directed KNN k=4 baseline.
2. Union adjacency symmetric KNN k=4. 행표준화 후 수치 W는 비대칭일 수 있다.
3. Haversine 거리 MST 연결 최소 반경 distance_band_x1. 실제 반경은 manifest 기록.
4. 모든 지점쌍 inverse distance p=1, cutoff 없음.

PySAL W 변환 후 행렬과 ID 순서가 입력과 정확히 같은지 검증한다.
Manifest에 station ordering SHA-256과 float64 little-endian W matrix hash를 저장한다.

## 13. Model comparison 및 수렴

비교 순서는 OLS→HC3→residual Moran→LM→SAR/SEM 계수 안정성→AIC/BIC→
공간모형 innovation Moran→weight sensitivity이다. 기본 OLS 잔차가 비유의이면
OLS를 설명용 baseline으로 유지한다. 유의이면 residual p≥.05인 후보의 AIC를
보조 비교하고 ΔAIC<2를 유사 fit으로 표시한다. 어떤 preferred label도 정답 모델이 아니다.

Full Gaussian likelihood는 동일 y/n에 대해서만 비교한다. 프로젝트 IC는
AIC=−2logL+2k, BIC=−2logL+k·log(n), **k에 분산 모수 포함**.
Main OLS k=5(β4+σ²), SAR/SEM k=6(β4+spatial parameter+σ²).
Longitude sensitivity는 각각 6/7이다. spreg 1.9.1은 SAR와 SEM native IC의
공간 모수 계산 관례가 다르므로 native_AIC/native_BIC를 비교 순위에 사용하지 않는다.
OLS R²와 spreg pseudo-R²(관측/모형값 상관의 제곱)는 서로 같은 지표가 아니다.
residual_variance는 innovation SSE/n이다.

spreg는 scipy optimizer success를 결과 객체에 보존하지 않는다. 별도 stable
least-squares 기반 concentrated Gaussian likelihood를 (-1,1)에서 최적화하고
success, spatial parameter 차이≤2e−4, logL 일치, finite coefficient/covariance,
양의 covariance diagonal, 잔차 정의 일치를 검증한다. |rho/lambda|>.999는
boundary-unstable로 처리한다. 이 범위는 이번 구현/라이브러리의 제한이며
가능한 모든 W의 이론적 admissible interval을 탐색한 것은 아니다.
단일 최적화 성공은 전역 최적성이나 과학적 모형 적합성의 증명이 아니다.

실패/경계 추정은 NaN과 failure log로 남기고 다른 조합을 계속한다.
예외가 없었다는 이유만으로 수렴했다고 쓰지 않는다. spreg의 bounded tolerance
warning은 기록하며, 독립 audit는 xatol을 명시한다. SAR의 power expansion 오류는
원식/가중치를 임의로 바꿔 회피하지 않는다.

## 14. Coefficient stability와 다중검정

3 outcomes×3 predictors에 대해 3 model families×4 weights의 12셀을 평가한다.
OLS 4셀은 재사용된 같은 적합임을 명시한다. 이 비율은 독립 검정 성공률이 아니다.
HC3는 별도 coefficient/p 컬럼이며 클래스만 보지 말고 함께 확인한다.

운영 분류 우선순위:

1. INCOMPLETE_MODELS: 실패/누락 셀이 하나라도 있음.
2. NON_ROBUST: coefficient 부호가 일치하지 않음.
3. WEIGHT_SENSITIVE: 같은 family 내 weight별 부호/유의성 변화.
4. MODEL_SENSITIVE: 같은 weight 내 family별 부호/유의성 변화.
5. ROBUST_SIGNIFICANT: 방향 동일이고 75% 이상 p<.05.
6. ROBUST_DIRECTION: 방향 동일, 위 조건 없음.

robust_direction, robust_significant, model_sensitive, weight_sensitive 중첩 flag도
함께 저장한다. 학계 표준 분류가 아니라 사전 정의한 프로젝트 요약규칙이다.
실패를 제외한 일부 셀만으로 robust라고 선언하지 않는다.

BH-FDR primary family는 **baseline 원단위 main coast의 3 outcomes**이며
OLS classical / OLS-HC3 / SAR / SEM 네 family를 따로 계산한다. 모델별 family를
섞지 않는다. 나머지 predictor, weight, 경도 sensitivity는 미보정 탐색적 p;
fdr_q 공란은 비유의라는 뜻이 아니다. 실패로 family가 불완전하면 q를 만들지 않는다.

## 15. LOO sensitivity

각 outcome에서 n번 OLS 재적합, 한 번에 station 하나만 일시 제외한다.
coast coefficient의 min/median/max, full-sample 대비 sign consistency와 개별 p를 저장한다.
원본과 main master는 유지하며 influential station을 자동 제외하지 않는다.

## 16. Bias/RMSE와 지도 해석

Bias/RMSE는 격자 및 관측 지점의 공간적 대표성·고도·해안·관측 특성 차이를 포함한다.
"NASA가 내륙에서 틀리다" 같은 지역별 정확성 단정은 금지한다.
지도는 baseline 각 모형의 세 outcome innovation point map만 제공한다.
동일 outcome은 모형 간 색 범위를 통일한다. 공간보간/전국 면 추정은 하지 않는다.
Plotly CDN은 지도 표시용으로만 인터넷을 사용하며 데이터 API는 호출하지 않는다.

## 17. Small-sample limitation

약 45지점의 coefficient uncertainty, model instability, influential station,
점근적 spatial z/LM의 소표본 한계, residual permutation exchangeability,
정적 해안선과 관측소 이력, omitted predictors 및 slope 추정오차가 남는다.
유의한 SAR/SEM 결과가 비유의 HC3를 무효화하지 않는다. AIC가 낮다는 이유로
인과 설명 또는 예측력을 주장하지 않는다.

## 18. 실행·재현성·산출물

```bash
python main.py --analyze-spatial-models --dry-run
python main.py --analyze-spatial-models
python main.py --report-spatial-models
python -m pytest -q
python -m pip check
streamlit run streamlit_app.py
```

Dry-run은 입력·가중치만 검증하고 모델 적합/프로젝트 파일 생성을 하지 않는다.
Main unique fits=3 OLS+24 SAR/SEM=27; 경도 sensitivity=9; 표준화 추가 fit=0;
LOO=3n. Main model×weight 비교셀은 36이며 실제 적합 횟수와 구분한다.
실패 모형이 있으면 모든 생성 가능한 산출물을 저장한 뒤 CLI 종료코드 1로 알린다.

결과는 `output/tables/spatial_models/` CSV 20개, `output/charts/spatial_models/`
PNG 8개+HTML 지도 3개, `output/reports/spatial_models/` MD/HTML 보고서,
`output/manifests/spatial_modeling_manifest.json`에만 저장한다.
Manifest는 input/output SHA-256, station ordering, weight hash, 라이브러리 버전,
seed, 검정 설정, 실패 개수, 보호파일 hash/mtime 비교를 포함한다.
보고서 재생성은 저장된 CSV/chart checksum 검증 후 보고서만 쓴다.
같은 입력의 재실행에서 표·그림·보고서 hash 재현성을 확인한다.
기존 VERSION 및 data/output(13단계 해안선 파일 포함)은 hash/mtime로 보호한다.
새 Streamlit 14번째 "공간보정 모델" 페이지는 저장파일만 읽는다.

## 공식 구현 근거

- [PySAL ML_Lag API](https://pysal.org/spreg/generated/spreg.ML_Lag.html)
- [PySAL ML_Error source: structural/filtered residual](https://pysal.org/spreg/_modules/spreg/ml_error.html)
- [PySAL ML_Lag source](https://pysal.org/spreg/_modules/spreg/ml_lag.html)
- [PySAL LMtests API](https://pysal.org/spreg/generated/spreg.LMtests.html)

실제 설치한 spreg/libpysal 버전은 manifest를 참조한다. 문서의 개발 버전과 차이가
있을 수 있으므로 잔차/최적화/likelihood 구현은 설치된 소스도 함께 점검했다.
