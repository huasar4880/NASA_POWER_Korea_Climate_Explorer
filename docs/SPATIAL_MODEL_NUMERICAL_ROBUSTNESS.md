# Spatial Model Numerical Robustness Review — Experimental Stage 14.5

## 1. 문제와 범위

Stage14의 역거리 p=1 기반 Bias SEM / RMSE SAR / RMSE SEM 실패를 진단한다.
동일 Final Tier A, 동일 세 outcome 및 기본 predictor를 사용한다. 새로운 station,
기후지표, 기후계수 해석 또는 API 호출은 추가하지 않는다. 기존 1–14단계 데이터,
수치 결과, 실패값, 보고서는 수정하지 않으며 VERSION 1.0.0을 유지한다.

실행 전 기존 328개 테스트와 pip check를 확인하고 VERSION/data/output 전체의
SHA-256 및 mtime snapshot을 기록한다. 이번 namespace만 보호대상에서 제외한다.
14단계 보고서 및 manifest도 보호 대상이다.

## 2. Inverse-distance 정의와 비교 범위

관측소 간 거리는 기존 Haversine(km), Wᵢⱼ=dᵢⱼ^(−p), i≠j, Wᵢᵢ=0이다.
서로 다른 station의 거리가 0이면 중단한다. 원시 가중치와 행표준화 행렬을 분리한다.

사전 지정한 9개 configuration만 비교한다:

- Directed KNN k=4, symmetric union KNN k=4, 기존 main distance-band.
- IDW p=1/p=2 각각 full row-standardized, full raw, cutoff row-standardized.

3 outcomes×SAR/SEM×9 weights=54개 numerical combination이다. 동일 seed 재실행,
입력 shuffle 후 canonical 재구성 검증을 포함하면 총 162회 같은 라이브러리를 호출한다.
후속 시도에서 parameter bounds나 tolerance를 바꾸지 않는다.

Density=nnz/[n(n−1)]로 대각선을 분모에서 제외한다. effective neighbor count는
행을 합 1로 정규화한 비중을 qᵢⱼ라 할 때 1/Σqᵢⱼ²이며 지점별 값을 평균한다.
행합은 standardization 전/후 지점별 표와 min/median/max를 저장한다.
Raw matrix symmetry, adjacency symmetry, 표준화 후 numeric symmetry를 구분한다.

## 3. Spectral properties

numpy eigvals로 고유값 전체(실수부·허수부·절댓값)를 저장한다.
Spectral radius는 max|eigenvalue|이다. Directed KNN은 복소 고유값을 가질 수 있으므로
실수부의 min/max를 실고유값 범위와 혼동하지 않는다.

실고유값 판정 tolerance는 |imag|≤1e−9·max(1,radius)이다.
수치 rank와 condition number는 W에 대해 계산하되, **W의 특이성은 I−theta W의
특이성과 다르다**. 실제 directed KNN W의 condition number가 매우 커도
작은 rho/lambda의 autoregressive system은 안정적일 수 있다.

## 4. 세 종류의 parameter 범위

다음을 엄격히 구분한다.

1. **0을 포함하는 비특이 연결 구간**: det(I−theta W)≠0인 실수 구간 중 0을 포함하는
   성분. 실고유값 μ의 역수 1/μ가 singular point다. 음의 실고유값 중 가장 작은 값의
   역수가 lower, 양의 실고유값 중 가장 큰 값의 역수가 upper이다. 해당 부호가 없으면
   경계는 무한대일 수 있다. 이 구간 밖에도 별도의 비특이 성분이 존재할 수 있다.
2. **Neumann series 수렴 구간**: |theta|·radius(W)<1. 충분·필요한 행렬 급수 수렴 조건이며
   비특이성보다 강한 조건이다. 어떤 벡터의 Euclidean norm이 매회 감소한다는 뜻은 아니다.
3. **현재 PySAL solver window**: 설치된 spreg 1.9.1의 ML_Lag/ML_Error(method FULL)는
   scipy bounded optimizer에 (-1,1)을 넘긴다. 실제 W spectrum에서 경계를 자동 계산해
   전체 비특이 구간을 탐색하는 구현이 아니다.

행표준화 IDW p1의 실제 고유값 실수부 범위는 약 [-0.194605,1], radius=1,
비특이 연결 구간은 약 **(-5.138610,1)**이다. 따라서 기존 lambda≈−1은
**solver 경계**이지 이 W의 singular boundary가 아니다.
SAR rho와 SEM lambda는 동일 W에 대해 같은 비특이 구간을 갖는다.
이 설명은 특정 통계모형의 모든 stationarity/식별 조건이 충족됐다는 뜻이 아니다.

## 5. Row-standardization

Wᵣ=D⁻¹W이며 D는 raw row sum이다. 대칭 raw IDW도 행합이 다르면 Wᵣ는 수치적으로
비대칭이 된다. 행표준화는 단순한 공통상수 배율이 아니므로 추정 대상 specification도 변한다.
비음수 row-standardized W의 radius는 약 1이다. p나 cutoff 변경 후에도 radius가
1인 사실만으로 안정성 개선/악화를 설명할 수 없다.

PySAL full2W가 raw weights를 그대로 전달하는지 검사했다. 하지만 raw W에서
theta의 단위·크기가 달라져 고정 (-1,1) solver window의 의미도 바뀐다.
Raw p1/p2가 경계에 도달한 결과를 row-standardized보다 나쁜 기후모형이라고 해석하지 않는다.
이번에는 raw용 bounds를 재조정하거나 raw 결과를 정상값으로 구제하지 않았다.

## 6. p=1 / p=2 sensitivity

행표준화 p2의 spectrum은 약 [-0.651656,1], 비특이 구간 (-1.534551,1)이다.
원거리 연결은 그대로 모두 유지되지만 근거리 비중이 증가한다.
이번 자료에서 p2 row는 여섯 조합 모두 STABLE이었다. 이는 수치적 sensitivity 근거이며
과학적 우월성이나 main specification 승격의 근거가 아니다. p=2를 유의한 결과를 얻기 위해
선택하지 않았고 기후계수/p-value를 새로 산출물에 추가하지 않았다.

## 7. Single distance cutoff

기존 Stage13의 MST 연결 거리대역 반경 하나를 사용한다. 실제 반경은
142.3486559347028 km이며 좌표에서 재현한다. 다른 cutoff 탐색은 하지 않는다.
밀도는 full IDW 1에서 cutoff IDW 약 0.330303으로 감소하고 isolate는 없다.
Row-standardized radius는 여전히 1이다. p1/p2 cutoff는 각각 여섯 조합 모두 STABLE이었다.
주요 모형으로 자동 채택하지 않고 사전 지정된 민감도 분석용으로만 분류한다.

## 8. Boundary diagnostics와 정상 추정값 구분

distance_to_lower=theta−lower, distance_to_upper=upper−theta,
relative_boundary_distance=min(distance_to_lower,distance_to_upper)/(upper−lower)이다.
Signed distance를 보존해 구간 외부 여부도 기록한다.

운영기준은 서로 다른 공간에 대해 별도로 적용한다:

- 비특이 연결 구간 폭의 **1% 이내**: near_admissible flag.
- 고정 solver 구간 폭의 **5% 이내**: near_solver flag.
- solver 경계와 절대거리 **1e−6 이내**: solver_boundary_hit.

분류 우선순위:

| 분류 | 정의 |
|---|---|
| NOT_SUPPORTED | 고정 library window가 계산된 비특이 구간 안에 있지 않아 실행하지 않음 |
| FAILED | library fit 반환 전 예외 발생; optimizer만 성공했어도 해당 |
| NUMERICALLY_UNSTABLE | 비유한값, audit 실패, optimizer 실패, solver boundary hit 또는 재현성 실패 |
| CONVERGED_NEAR_BOUNDARY | 유효한 반환값이지만 위 1%/5% 근접 기준에 해당 |
| STABLE | 유한·optimizer success·내부 후보·유효 잔차 및 재현성 확인 |

`diagnostic_estimate`는 native solver가 낸 감사용 후보이며 fit이 뒤에서 실패해도 기록할 수 있다.
`estimate`는 STABLE일 때만 채운다. 실패/근접/경계 모형은 **estimate=NaN**을 유지한다.
기존 14단계의 값이나 failure reason은 덮어쓰지 않는다.

## 9. Solver / likelihood behavior

라이브러리의 minimize_scalar를 투명하게 감싸 native success, nit, nfev, message,
후보 parameter를 관찰한다. 모든 호출 인자와 반환 객체는 원형 그대로 통과시키며
라이브러리 파일을 수정하지 않는다. 계측 중 전역 모듈 변경은 lock/context로 제한·복원한다.
warning, exception, power expansion failure, likelihood audit, I−theta W의 condition
number/최소 singular value도 기록한다.

이번 p1 불안정 세 조합의 I−theta W condition number는 약 2.497,
최소 singular value는 약 0.805로 singularity 징후가 아니다.
Bias SEM과 RMSE SEM은 optimizer success이지만 fixed lower bound에 도달했다.
RMSE SAR도 optimizer success 뒤 power expansion 단계에서 실패했다.

설치된 spreg.utils.power_expansion은 increment norm이 이전보다 한 번 커지면 예외를 낸다.
실제 RMSE SAR에서는 두 번째 단계 norm ratio≈1.000579가 재현됐다.
|rho|·radius(W)는 약 0.999999951로 1 미만이지만 매우 가깝다. 비정규 행렬은
수렴 가능한 급수여도 초기에 Euclidean norm이 증가할 수 있다. 따라서 이 예외를
수학적 급수 발산이나 I−rho W singularity와 동일시하면 안 된다. 다만 near-unit
급수는 매우 느릴 수 있으며, 이번 검토는 다른 역행렬 solver로 교체해 구제하지 않았다.

세 불안정 조합의 profile NLL은 solver lower bound에서 양의 우측 기울기를 보였다.
81점의 fixed-window profile 및 계산된 비특이 구간의 81점 진단 profile을 저장한다.
후자는 경계 바깥 모양 확인용이며 **넓힌 bounds로 최적화하지 않고, grid 최적값을
새 추정값으로 채택하지 않는다**. Profile에 쓰는 conditional least squares도 NLL 계산의
내부 수단일 뿐 새로운 기후계수/추론 산출물이 아니다.

## 10. Recommended weight families

권장 기준은 p-value가 아닌 수치 상태와 기존 baseline 유지 여부다.

- RECOMMENDED_MAIN: directed KNN k4, 6/6 STABLE.
- RECOMMENDED_SENSITIVITY: symmetric KNN k4, row-standardized IDW p2,
  row-standardized IDW p1/p2 + 단일 cutoff. 각각 6/6 STABLE.
- Distance-band는 조건부 RECOMMENDED_SENSITIVITY: Bias 2개는 STABLE,
  TAVG/RMSE 4개는 solver-window 5% 근접. 근접 행을 정상 추정으로 사용하지 않는다.
- NOT_RECOMMENDED_NUMERICAL: full row-standardized IDW p1, full raw IDW p1/p2.
  **현재 자료와 고정 library specification에 대한 권고**이지 모든 역거리 모형의 금지는 아니다.

## 11. HC3 baseline

세 outcome에 이분산 징후가 있었으므로 primary non-spatial inference는
**HC3 robust standard errors**로 정리한다. Classical OLS p-value는 descriptive/reference다.
이번 정리는 해석 우선순위 변경이며 기존 coefficient/p-value/CI/보고서를 수정하지 않는다.
HC3는 공간의존성을 보정하는 방법 자체는 아니다.

## 12. 기존 기후결과 해석 상태

상태표의 계수 방향과 p-value는 오직 기존 Stage14 CSV에서 읽는다.

- TAVG: DIRECTIONALLY_STABLE_HETEROSKEDASTICITY_SENSITIVE.
  Classical p≈0.02866, HC3 p≈0.11174. 방향 유지와 추론 강건성을 구분한다.
- Bias: ROBUST_ASSOCIATION_WITH_UNSUPPORTED_INVERSE_DISTANCE_SPECIFICATION.
  HC3 p≈0.000438 및 기존 주요 비교군의 방향·유의성 유지. 불안정 full IDW p1은 제외한다.
- RMSE: MODEL_SENSITIVE_NOT_UPGRADED. HC3 p≈0.20256이며 모형 간 유의성이 다르다.
  IDW p2/cutoff 수치 성공만으로 robust로 승격하지 않는다.

이 상태들은 프로젝트 내부의 탐색적 요약이지 새로운 인과적·공간적 기후 결론이 아니다.

## 13. 실행·산출물·한계

```bash
python scripts/review_spatial_numerics.py --dry-run
python scripts/review_spatial_numerics.py
python scripts/review_spatial_numerics.py --report-only
python -m pytest -q
python -m pip check
```

새 CLI script만 추가하고 기존 main.py의 모드와 동작은 유지한다.
`output/tables/spatial_models_numerical/`에 CSV 15개,
`output/charts/spatial_models_numerical/`에 PNG 7개,
`output/reports/spatial_models_numerical/`에 MD/HTML technical report를 생성한다.
`output/manifests/spatial_model_numerical_review_manifest.json`에는 source hash,
canonical station ordering, weight/spectral/model 설정, library version/source hash,
output hash 및 이전 단계 보호파일 검증을 기록한다.
Dashboard는 기존 14번째 페이지에 수치 안정성 expander만 추가하며 15번째 페이지는 만들지 않는다.

동일 seed 재실행과 input shuffle→numeric station ID canonical 정렬 후 재구성에서
W/result/order hash가 동일한지 확인한다. 결과가 다르면 NUMERICALLY_UNSTABLE로 표시한다.
Float32로 관측값을 바꾸는 실험은 하지 않는다. 복소 고유값 판정 tolerance,
근접경계 threshold, 단일 profile grid는 운영규칙이다. 수렴은 scientific validity,
small-n 추론, 이분산, slope 추정불확실성 또는 인과성 문제를 해결하지 않는다.

공식 구현과 설치 소스를 함께 확인했다:

- [PySAL ML_Lag source](https://pysal.org/spreg/_modules/spreg/ml_lag.html)
- [PySAL ML_Error source](https://pysal.org/spreg/_modules/spreg/ml_error.html)
- [PySAL spatial weights](https://pysal.org/spreg/notebooks/4_spatial_weights.html)
- `spreg.utils.power_expansion`은 설치된 소스를 직접 검사했다.

웹 개발 문서와 설치 버전 차이가 있을 수 있어 manifest에 설치 소스 hash를 남긴다.
