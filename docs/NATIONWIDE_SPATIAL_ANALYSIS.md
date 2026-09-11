# Nationwide Spatial Climate Pattern Analysis

## 1. 목적

12단계는 11단계 Final Tier A station의 1981–2025 장기 기온추세가 공간적으로 어떤
구조를 보이는지 탐색하고 정량화한다. 인과관계, 미래예측, 기후위험 종합점수는 다루지
않으며 `VERSION`은 stable `1.0.0`을 유지한다.

## 2. Input

NASA POWER·KMA API를 호출하지 않고 `output/tables/nationwide/`의 Stage-11 CSV만 읽는다.
핵심 입력은 station summary/trends/anomalies, NASA–KMA validation, threshold comparison,
seasonal trends, annual temperature다. 기존 입력을 다시 계산하거나 덮어쓰지 않는다.

## 3. Tier A station

`output/tables/nationwide_tier_a_analysis_stations.csv`를 station source of truth로 사용한다.
station 수는 실행 시 계산하며 코드에 고정하지 않는다. Tier B, manual-review,
continuity unresolved station은 제외한다. 현재 입력은 45개이며 station ID와 좌표는 모두
고유하고 완전하다.

## 4. Distance method

거리 단위는 km이고 위경도 degree 차이를 직접 사용하지 않는다. 지구 평균반경
6,371.0088 km의 Haversine 대권거리로 모든 station pair를 계산한다. 거리행렬은 비음수,
대칭, self distance 0을 자동 검사한다.

## 5. Spatial weights

기본값은 directed K-nearest neighbors, `k=4`다. 각 station에서 가장 가까운 4개 station에
동일 가중치 `1/4`를 주어 행 합을 1로 표준화한다. 거리 동률은 station ID 순으로 재현
가능하게 해소한다. 현재 45개 station의 최근접 거리는 16.14–142.35 km, 중앙값 31.82 km로
분산되어 있어 단일 고정거리보다 모든 station에 이웃을 보장하는 KNN을 택했다. k=4는
고립 station을 만들지 않으면서 국지성과 안정성의 균형을 보는 중심 설정이다.

## 6. Moran's I

Global Moran's I는 다음 식으로 계산한다.

`I = (n / S0) × [ΣiΣj wij zi zj / Σi zi²]`

`z`는 station metric의 표준화 값이고 `S0`는 전체 weight 합이다. 기대값은
`−1/(n−1)`이다. 기본 999회 permutation에서 관측 I와 기대값의 거리를 기준으로 한
two-sided pseudo p-value `(extreme+1)/(permutations+1)`를 사용한다. seed는 고정한다.
양의 I만으로 cluster를 단정하지 않고 permutation p를 함께 해석한다.

## 7. Local Moran

KMA TAVG/TMAX/TMIN Sen slope, TAVG Bias, TAVG RMSE에 Local Moran을 계산한다. quadrant는
High-High, Low-Low, High-Low, Low-High로 나누되, 유의하지 않으면 `Not Significant`로
표시한다. High-Low/Low-High는 공간 outlier 표현이며 원인을 추정하지 않는다.

## 8. FDR

Local Moran station 동시검정은 변수별 station family에 Benjamini–Hochberg FDR을 적용한다.
지도와 핵심 cluster 수는 `local_significant_fdr`와 `cluster_type_fdr`를 우선한다.

## 9. Latitude/elevation associations

위도·경도와 KMA TAVG/TMAX/TMIN Sen slope, 고도와 같은 세 추세 및 TAVG Bias/RMSE에
Pearson, Spearman, 탐색적 단순선형회귀를 계산한다. 회귀 slope, R², p-value를 보존한다.
이 연관은 causality가 아니며 confounding 가능성이 있다.

## 10. Tmax/Tmin contrast

station별 `TMIN Sen slope − TMAX Sen slope`를 계산한다. 양수는 TMIN warming이 상대적으로
빠른 방향, 음수는 TMAX warming이 빠른 방향이다. 방향 차이에서 도시화·지형 등 원인을
자동 추론하지 않는다.

## 11. DTR

Stage-11 연평균값으로 `DTR = TMAX − TMIN`을 station·source·year별 계산하고 1981–2025
Sen slope(°C/10년)를 구한다. KMA와 NASA를 분리하며 원 일자료를 수정하지 않는다.

## 12. Seasonal spatial pattern

Stage-11 KMA TAVG DJF/MAM/JJA/SON Sen slope를 그대로 사용한다. 계절별 station 중앙값과
Global Moran을 계산하고 계절별 point map과 station별 최대 slope 계절을 기록한다. 정확한 동률은
DJF→MAM→JJA→SON 고정 순서로 선택하고 `tie_count`를 함께 남긴다.

## 13. Threshold proxy

KMA/NASA `TMAX ≥33°C`, `TMIN ≥25°C` station Sen slope의 중앙값·범위·Moran·위도/고도
연관을 계산한다. 이는 같은 threshold를 적용한 분석 proxy이며 공식 폭염일수 또는
열대야 통계가 아니다.

## 14. NASA–KMA spatial validation

`Bias = NASA − KMA`와 RMSE의 station 분포, Global/Local Moran, 위도·경도·고도 연관을
분석한다. Bias가 양수면 NASA가 상대적으로 높고 음수면 낮다는 뜻이다. 차이를 NASA 오류나
지형 효과로 단정하지 않는다.

## 15. Coastal/inland methodology

신뢰 가능한 후보는 공공데이터포털의
[국립해양조사원 2025 전국 해안선 SHP](https://www.data.go.kr/data/15083948/fileData.do)다.
제공기관은 해양수산부 국립해양조사원이고 포털 표시는 무료·이용허락범위 제한 없음이다.
다만 현재 저장소에는 해당 geometry가 없으며, 자동 재현 가능한 취득 URL·checksum,
원본 CRS, geometry validity와 섬/인공해안 포함 규칙을 아직 검증하지 않았다. 도시명이나
행정구역으로 임의 분류하지 않고 이번 단계의 coastal distance, coastal/inland 비교,
20/30/50 km sensitivity는 보류한다. 향후 geometry가 검증되면 결과는 별도 provenance와
operational threshold로 추가해야 한다.

## 16. Sensitivity

KNN `k=3,4,5`에서 요청된 8개 metric의 Global Moran을 모두 다시 계산해
`nationwide_spatial_weight_sensitivity.csv`에 저장한다. 유의성 또는 방향이 설정에 따라
달라지면 핵심 limitation으로 보고하며 단일 k 결과를 확정적 cluster 증거로 쓰지 않는다.

## 17. Limitations

- Final Tier A station만 사용하며 공간분포가 불균등하다.
- station은 면적표본이 아니고 지역 median은 면적가중 지역기후가 아니다.
- KNN 정의에 따라 공간 자기상관이 달라질 수 있다.
- Local Moran은 multiple testing의 영향을 받는다.
- NASA grid와 KMA station의 공간대표성이 다르다.
- 공간 연관은 인과관계가 아니며 위도·고도 분석에는 confounding이 가능하다.
- threshold는 공식 기후현상 통계가 아닌 proxy다.
- point map만 제공하며 IDW/Kriging 같은 전국 연속면 보간은 하지 않는다.
- 해안/내륙은 검증된 geometry가 준비될 때까지 보류한다.

## 18. Reproducibility

설정은 `config/spatial_analysis.json`, 표는 `output/tables/spatial/`, interactive HTML과
PNG는 `output/charts/spatial/`, 보고서는 `output/reports/spatial/`에 분리한다.
`output/manifests/spatial_analysis_manifest.json`에는 입력 상대경로·SHA-256, station 수,
공간설정, permutation 수, seed와 생성파일을 기록한다. 개인경로와 API key는 쓰지 않는다.

```bash
python main.py --analyze-spatial --dry-run
python main.py --analyze-spatial
python main.py --report-spatial
```

dry-run은 입력 station 수·표·weight·예상 output·coastline 상태만 출력하고 분석파일을
수정하지 않는다. 세 명령 모두 NASA/KMA API를 호출하지 않는다.

### 현재 결과 스냅샷

기본 k=4에서 KMA TAVG Global Moran은 I=0.157643, permutation p=0.043이다. k=3/4/5의
p-value는 각각 0.098/0.043/0.024여서 유의성 결론이 weight 설정에 민감하다. 따라서
확정적 cluster 증거가 아니라 탐색적·약한 공간구조로 해석한다. TAVG Local Moran에서
BH-FDR 유의 High-High/Low-Low cluster는 없고 Low-High outlier 1개가 남았다.
