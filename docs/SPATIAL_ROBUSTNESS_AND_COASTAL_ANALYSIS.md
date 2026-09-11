# Spatial Robustness & Coastal–Inland Analysis (Stage 13)

Stable VERSION **1.0.0**은 유지한다. 이 기능은 experimental nationwide extension이며 NASA/KMA API를 호출하지 않는다. 기존 1–12단계 결과를 갱신하지 않는다.

## 실행 및 재현

```bash
python main.py --analyze-spatial-robustness --dry-run
python main.py --analyze-spatial-robustness
python main.py --report-spatial-robustness
python -m pytest -q
python -m pip check
streamlit run streamlit_app.py
```

입력은 Final Tier A CSV, Stage-10 shortlist 및 `output/tables/spatial/`의 17개 Stage-12 표다. station 수는 입력에서 계산하며 B/미해결 continuity station을 허용하지 않는다. Stage-12 master와 Final A의 ID, 좌표, 고도, 기간을 검증한다. DTR은 기존 연평균 TMAX−연평균 TMIN의 Sen 추세를 읽고 재계산하지 않는다. 누락 metric을 0으로 채우지 않는다.

설정은 `config/spatial_robustness.json`. Global/Local permutation 수는 Stage 12보다 줄일 수 없다. 기본 각각 999, seed 20250905. 변수별 seed offset은 Stage 12와 같다. 같은 변수는 모든 weight에서 같은 permutation 난수열을 사용한다.

## 공간가중치 정의

- 거리: 기존 Haversine 지점 간 거리(km), 대각선 0.
- Directed KNN: k=3,4,5,6. 거리 동률은 기존 station-ID 정렬로 해결, 지점당 이웃 k개.
- Symmetric KNN: directed KNN의 **union adjacency** (`i→j OR j→i`). 이웃 관계는 대칭이지만 이후 row normalization을 하면 수치 가중치 행렬은 일반적으로 비대칭이다.
- Distance band: 최소 무고립 반경은 각 지점 최근접 거리의 최댓값. 전체 연결 최소반경은 minimum spanning tree의 최대 edge 거리. 둘은 개념상 다르다. 전체 연결 반경 ×1.0/1.1/1.25를 사용한다(실제 45개 지점에서는 142.348656/156.583522/177.935820 km). floating-point 경계는 `nextafter`로 포함한다. 울릉도 등 섬은 제거하지 않아 큰 반경이 필요하다.
- Inverse distance: 모든 다른 지점에 `d^-p`, p=1,2, cutoff 없음. self/zero 거리 제외.
- 모두 음수/inf 없음, self 0, row sum=1, isolates=0 검증. neighbor count, 약연결 component 수, adjacency/numeric symmetry를 별도 표에 기록한다.

## Global Moran 및 강건성 분류

`I = (n/S0) × Σ_iΣ_j w_ij z_i z_j / Σ_i z_i²`, `E[I]=−1/(n−1)`.
기존 12단계 two-sided permutation: `(|I_perm−E[I]| >= |I_obs−E[I]| 건수 +1)/(P+1)`.
8개 변수는 KMA TAVG/TMAX/TMIN Sen slope, NASA TAVG Sen slope, KMA33/25°C proxy slope, TAVG Bias/RMSE.
Global p는 104개 variable×weight 검정에 대해 다중검정 보정되지 않았다. 유의 설정을 골라 확증 결론을 내리지 않는다.

아래 분류는 **프로젝트 operational rule이며 학계 표준이 아니다**. 13개 설정에 동일한 비중을 준다. 설정 간 독립성은 가정하지 않으며 이 비율에 별도 확률적 의미를 부여하지 않는다.

1. 양·음 Moran I가 모두 있으면 `INCONSISTENT_DIRECTION` (우선 적용; 아주 작은 음수라도 원자료 범위를 함께 보고).
2. 유효 설정의 75% 이상에서 `I>0 AND p<0.05`: `ROBUST_POSITIVE`.
3. 75% 이상 비유의: `ROBUST_NON_SIGNIFICANT`.
4. 나머지: `WEIGHT_SENSITIVE`.

각 분류와 함께 유의 설정 수, I/p 최솟값·최댓값을 제공한다. `ROBUST_POSITIVE`가 모든 설정 유의를 뜻하지 않으며, 비유의가 효과 부재의 증명도 아니다.

## Local Moran robustness

KMA TAVG에 directed k3/k4/k5, symmetric k4, minimum connected distance band, inverse distance p2를 비교한다. focal z_i를 고정하고 다른 지점의 z를 섞는 기존 조건부 permutation을 재사용한다. 두 꼬리는 `|local I_perm| >= |local I_obs|`로 정의된다(conditional expected I 중심 방식과 다름). 각 설정의 45개 local p에 Benjamini–Hochberg FDR 적용. 모든 6개 설정에서 같은 FDR-significant quadrant를 유지해야 `stable_local_pattern=True`. 인제는 결과 조회에만 사용하며 결과를 하드코딩하지 않는다. 설정별 FDR은 전체 설정을 합친 FDR 보장이 아니다.

## 공식 해안선, 출처 및 검증

[국립해양조사원 해안선 공식 자료](https://www.data.go.kr/data/15083948/fileData.do), 포털 기준일 2025-12-31, 수정일 2026-06-25. 이용허락범위 제한 없음, 무료(2026-09-08 확인). 실제 첨부 이름은 **2026 해안선.zip**으로 포털 기준일과 다르다. 이를 숨기지 않고 manifest에 양쪽을 기록한다. 개별 조사년도 SOR_DAT는 2019–2025이므로 전체 선이 같은 시점에 측량된 것이 아니다.

공식 페이지 → 공식 attachment metadata → check-limit → fileDownload 순서로 확보했다. CAPTCHA/권한 제한을 우회하지 않는다. 다음 acquisition 함수는 사용자가 다운로드를 원할 때만 명시적으로 실행하며 분석 CLI는 네트워크를 쓰지 않는다.

```bash
python -c "from src.spatial.coastline import download_official_archive, prepare_coastline; prepare_coastline(download_official_archive())"
```

저장 위치: `data/geospatial/coastline/raw/`, `processed/`, `acquisition.json`, `coastline_manifest.json`.
ZIP SHA256: `a0011a20eccf300b68c2e8827863a93ff32d3caf650cd1ba7e89b5e2f343b24f`.
SHP/SHX/DBF/PRJ 필수. 실제 .cpg는 EUC-KR이며 DBF 해독에 사용한다. zip path traversal, 불명확한 여러 SHP, CRS 누락, 도형 null/empty/invalid/non-line을 거부한다. 원본을 수정하지 않는다. 원본 99,166개 선 도형은 invalid/empty/duplicate=0.

동봉 `해안선 속성테이블 명세서.pdf` 1·3쪽에 따라 **GRP_CON=1 또는 2(자연·인공 해안선), GRP_STA=Y(통계 반영)**만 거리계산에 사용한다. 교량기준선(3), 강하구 종점기준선(4), 통계 미반영선은 제외한다. 자연해안선의 공식 하구 경계는 포함하며 임의 하천 경계를 추가하지 않는다. GRP_ISL 필터는 적용하지 않으므로 육지부(제주 본도 포함)와 도서부 모두 유지한다. 제외 수와 두 그룹 수는 manifest에 기록한다.

원본 CRS **EPSG:5186**, 분석 CRS **EPSG:5179 (KGD2002 / Unified CS, metre)**. station은 WGS84 EPSG:4326, 모든 변환은 `always_xy=True`. 도 단위 Euclidean 거리를 사용하지 않는다. 좌표변환 후 source ID 73660의 multipart에 약 5.8e−11 m 선 조각이 같은 점으로 붕괴해 invalid가 된 것을 확인했다. 남은 유효 선 위에 정확히 겹치는 zero-length 부분만 제거한다. 이 수리는 도형이 덮는 점 집합이나 station 거리 자체를 바꾸지 않으며, 그 외 invalid는 거부한다. 원본은 그대로이며 처리 후 invalid 수를 따로 기록한다.

전체 해상도의 분석 선은 hex-WKB JSON으로 processed에 저장하고 checksum을 검증해 재사용한다. 공식 archive/구성요소/processed hash가 바뀌면 `coastline source changed`로 coastal만 중단한다. 다운로드나 공식 도형 검증 실패 시 robustness는 계속하고 Coastal unavailable을 보고한다. 임의 geometry/행정경계 대체는 없다. raw 갱신을 자동 덮어쓰기하지 않는다.

## 해안거리 및 operational threshold

거리: EPSG:5179에서 station point와 모든 **선분**의 최단거리(m)/1000. 최근접 꼭짓점 거리와 다르다. STRtree로 최근접 feature를 찾고 full-resolution 도형으로 거리를 계산한다. 최단 source feature ID도 기록한다. 지점 수 일치, finite 및 0 이상을 검사한다.

20/30/50 km 각각 Coastal=`distance<=threshold`, Inland=`distance>threshold`. 행정구역/도시 이름과 무관하다. 주기준은 결과 유의성을 보기 전에 **30 km 우선, 양 집단 n>=5**로 정한다. 불충분하면 가능한 threshold 중 작은 집단 크기를 최대화하며 tie는 설정 순서로 해소한다. p값에 의한 threshold 선택은 하지 않는다. 연속거리 관계와 전 threshold 결과를 항상 함께 제공한다.

## 통계비교 및 공간적 교란

9개 metric: TAVG/TMAX/TMIN, TMIN−TMAX contrast, DTR, 33°C/25°C proxy, TAVG Bias/RMSE. 추세 단위 °C/10년, proxy 일/10년, Bias/RMSE °C. 연속거리에 대한 단순 회귀 기울기는 해당 단위/km.

- 연속 분석: Pearson r, Spearman rho, 유효 n, p, OLS slope/intercept/R², slope95% CI.
- 집단 분석: 유효 n, mean, median, IQR(75%−25%), Coastal−Inland 중앙값 차이.
- Mann–Whitney U: 양측, asymptotic tie correction + continuity correction. 분포 검정이며 일반적인 중앙값 차이만의 검정으로 말하지 않는다.
- rank-biserial=`2U_C/(n_C n_I)−1`, [-1,1], 양수는 Coastal 값이 더 큰 방향.
- 각 threshold의 9개 metric p에 BH-FDR, alpha .05. 전 27개를 합친 FDR은 아니다.
- 일부 threshold만 FDR 유의: threshold-sensitive. 모두 유의하고 중앙값 차이 방향 동일: threshold-robust tendency. 전부 비유의이며 방향 같으면 direction-consistent; not FDR significant. 부호가 바뀌면 inconsistent direction.
- 다변량은 사전 지정 TAVG/TMIN/Bias ~ distance + latitude + elevation, intercept 포함. coefficient95% CI/p/R²/n, singular design은 중단 상태 반환. feature selection 없음.
- 지역 빈도, 위도·고도·해안거리 분포를 그룹별로 제공. 단변량/다변량 차이를 공간적 교란 가능성과 함께 검토한다. 통상적 correlation/OLS/MWU 추론은 지점 독립을 가정하고 공간 의존성을 교정하지 않으므로 탐색적이다.

## 산출물과 Dashboard

- `output/tables/robustness/`: weights, summary, local, network, 별도 Bias/RMSE summary.
- `output/tables/coastal/`: distances, classification, continuous associations, main comparison, threshold sensitivity, group characteristics, exploratory models.
- `output/tables/spatial_robustness_and_coastal_summary.csv`.
- `output/charts/robustness/`: heatmap와 TAVG/Bias/RMSE/proxy 민감도.
- `output/charts/coastal/`: 공식 선+station HTML 3종, 분포/scatter/boxplot. 기존 페이지와 같이 Plotly JS를 버전 지정 CDN에서 읽으므로 HTML 지도 첫 로딩에 네트워크가 필요하다. 지도 토큰/외부 topojson 의존은 없다. 전체 Plotly bundle을 inline으로 넣으면 라이브러리의 예시 문자열이 기존 secret scanner에 걸리므로 scanner를 약화시키지 않고 CDN 방식으로 통일했다. 지도만 250 m 단순화하며 분석 geometry와 분리한다.
- `output/reports/robustness/`: deterministic HTML/Markdown 17개 주제 보고서.
- `output/manifests/spatial_robustness_manifest.json`: input/output hashes, source/CRS/geometry 검증, station 수, weight 설정, seed/P, threshold, 결과 목록, 보존 검사.
- 13번째 Streamlit 페이지 **공간 강건성·해안성**. 저장 파일 읽기 전용, coastline unavailable이어도 robustness 표시. CSV mtime가 캐시 키에 포함된다.

## 한계 및 다음 단계

45개 장기 Final A는 전국의 모든 공간을 대표하는 표본이 아니다. 섬 포함 시 distance band가 넓어지는 점, 서로 관련된 weight 설정을 동일비중 집계한 점을 고려한다. 해안선 버전과 정의, 고정 해안선을 45년 추세와 비교하는 시간 불일치, 육지/바다 경계의 복잡성, 지형/풍향·해류, 관측소 이력, slope 추정 불확실성은 해결하지 않았다. 연관성은 바다의 영향이라는 인과 설명이 아니다.

14단계에서는 새 기능 도입 전에 공간 의존성을 반영한 추론과 weight family별 균형을 별도 사전 계획으로 검토할 수 있다. 예측, 보간, 위험점수, 미래시나리오는 이 단계에 포함되지 않는다.

공식 기술 근거: [SciPy MWU](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html), [Shapely STRtree](https://shapely.readthedocs.io/en/stable/strtree.html), [PyProj Transformer](https://pyproj4.github.io/pyproj/stable/api/transformer.html).
