# Stage17 — 51-Station Common-Period Spatial Reanalysis

## 1. 목적과 범위

Stage16의 저장된 공통기간 자료를 공간적으로 재분석한다. API를 호출하거나 원본·기존
processed·기존 분석 결과를 수정하지 않는다. stable `VERSION=1.0.0`을 유지한다.
새 결과는 `output/{tables,charts,reports}/common_period_spatial/`에만 저장한다.

## 2. 관측소 네트워크

Final Tier A-origin 45개와 Tier B-origin 6개, 총 51개 ASOS 관측소를 사용한다.
ID·이름·좌표·고도·지역·continuity risk·coast distance는 Stage16 master에서 읽는다.
관측소 수·격자 수는 코드에서 고정하지 않고 입력으로부터 계산한다.
Stage16 manifest의 CSV checksum과 51개 NASA 일별 시계열 fingerprint를 재검사한다.

## 3. 공통기간

1991-01-01–2025-12-31, 35년이다. 연평균·Sen slope·고온일수 proxy·validation은
Stage16에서 이 기간으로 다시 계산한 값을 사용한다. 기존 1981–2025 기울기를
연수 비율로 변환하거나 서로 다른 기간의 추세를 합치지 않는다.

## 4. 과거 공간분석 기준

Stage12의 `nationwide_global_morans_i.csv`와 Stage13의 weight/robustness/local,
coastal 및 좌표 연관표를 읽는다. 같은 Final A-origin ID인지 확인한다.
과거 결과 파일은 재생성하지 않는다. 새 비교표에 old/new 값을 나란히 기록한다.

## 5. 공간가중치

거리: 기존 Haversine 함수, 지구 반경 6371.0088 km. station은 ASOS 좌표,
unique-grid는 NASA native grid 추정 중심 좌표로 각각 거리행렬을 만든다.
대칭·대각선 0·유한값·비음수를 검사한다.

- 주 분석: directed KNN k=4, row-standardized.
- 민감도: directed k=3/5/6, symmetric union KNN k=4, 전체거리 IDW p=2 row,
  cutoff IDW p=1/p=2 row, connected distance-band.
- cutoff는 각 네트워크의 MST 최장 edge 거리보다 부동소수점 한 단위 큰 값이다.
  동일 숫자 cutoff를 서로 다른 네트워크에 강제로 적용하지 않는다.
- 제외: full-distance IDW p=1 row, IDW p=1/p=2 raw.
- Stage14.5 권고 설정을 재사용하며 고립점·비유한값·단절 네트워크를 거부한다.
  distance-band의 SAR/SEM near-boundary 문제를 숨기지 않는다. 여기서는 Moran만
  계산하며 SAR/SEM의 수치적 안정성이나 과학적 타당성을 새로 주장하지 않는다.

각 representation에서 9개 설정을 사용한다. directed graph의 edge는 방향별로 센다.
network summary는 edge count, density, 평균/중앙/최소/최대 이웃 수, 고립점,
weak component 수와 행 표준화 여부를 기록한다.

## 6. 강건성 분류

Stage13 `classify_robustness`를 그대로 재사용한다. 아래 순서가 우선순위다.

1. 양·음 Moran I가 함께 존재: `INCONSISTENT_DIRECTION`.
2. 전체 설정 중 양의 I이면서 p<0.05인 비율 ≥75%: `ROBUST_POSITIVE`.
3. p≥0.05인 비율 ≥75%: `ROBUST_NON_SIGNIFICANT`.
4. 나머지: `WEIGHT_SENSITIVE`.

프로젝트 운영 규칙이며 학계의 표준 분류가 아니다. 과거 13개, 현재 권고 9개라는
설정 구성 차이가 있어 분류 변화가 기간/관측소 변화만을 나타내지는 않는다.

## 7. KMA Global Moran

TAVG/TMAX/TMIN Sen, 33°C/25°C proxy Sen, Tmin−Tmax contrast, DTR Sen,
NASA−KMA TAVG Bias/RMSE를 검정한다. Bias/RMSE source는 `NASA-KMA`로 구분한다.

`I=(n/S0)×(z'Wz)/(z'z)`, `E[I]=−1/(n−1)`이다. 기존 함수를 재사용하여
999회 permutation, `(|Iperm−E[I]|≥|Iobs−E[I]| 횟수+1)/1000`의 양측 p를 계산한다.
기본 seed는 기존 config의 20250905이며 기존 8개 변수의 seed offset을 유지한다.
추가 NASA Tmax/Tmin은 100/101, NASA proxy 33/25는 200/201,
contrast/DTR은 300/301을 더한다. 같은 metric은 weight/representation 간 같은 seed다.

전체 Global 171행, Local 153행, 계절 Moran 12행, bridge 8행을 예상하고 검증한다.
Global p는 보정하지 않은 탐색적 p이며 다중검정으로 인한 우연 발견 가능성을 경고한다.

## 8. NASA Station-linked

51개 ASOS 좌표마다 대응 NASA 값 하나를 둔다. 공유 격자에 대응하는 같은 값이
반복 표현된다. 이것을 51개 독립적인 NASA 격자라고 부르지 않는다.

## 9. NASA Unique-grid

Stage16에서 추정한 native MERRA-2 grid ID로 그룹화하여 34개 중심점을 사용한다.
14개 공유 그룹, 공유 관측소 31개, 최대 그룹 크기 3이다.
공식 grid 원점·해상도에서 추정된 좌표이지 API가 반환한 cell metadata가 아니다.
공유 그룹의 날짜와 기온 3변수 전체 시계열을 다시 비교한다. 하나라도 다르면 중단한다.
TAVG/TMAX/TMIN 및 33/25 proxy 기울기의 그룹 내 일치도 확인하고 하나의 값을 취한다.
NASA 값이 다를 때 첫 관측소 선택이나 평균으로 차이를 숨기지 않는다.

공식 grid provenance와 단독 격자 확인의 한계는
[Stage16 방법론](COMMON_PERIOD_51_STATION_ANALYSIS.md)을 따른다.

## 10. Grid duplication sensitivity

`difference_I=I_unique_grid−I_station_linked`이다. 주 분석 TAVG 결과는
0.885956→0.695686, ΔI=−0.190270이다. 둘 다 p=0.001이다.

- 부호가 다르면 `DUPLICATION_HIGH_IMPACT`.
- 부호가 같지만 p<0.05 여부가 달라지거나 |ΔI|>0.10이면 `DUPLICATION_MODERATE_IMPACT`.
- 나머지는 `DUPLICATION_LOW_IMPACT`.

사전 고정한 프로젝트 규칙이다. 학계 표준으로 표현하지 않는다. 주 K4에서 NASA
TAVG/TMAX/TMIN/33/25는 모두 MODERATE이며 양의 방향과 유의성은 유지된다.
이 비교에는 중복 제거뿐 아니라 좌표·이웃·표본 수 변경도 동반되므로 순수 중복의
인과효과를 분리한 값이 아니다. 34개 grid도 독립 표본임을 보장하지 않는다.

## 11. 45/1981→45/1991→51/1991 bridge

A=과거45/1981–2025, B=동일45/1991–2025, C=51/1991–2025이다.
B의 directed K4 이웃도 45개에서 새로 만든다. KMA3변수, NASA TAVG,
Bias/RMSE, KMA33/25 proxy를 비교한다.

`delta_period=I_B−I_A`, `delta_station_addition=I_C−I_B`이고 합이 전체 ΔI인지 검증한다.
절대변화 크기 비교는 어떤 변경과 더 큰 변화가 **연관됐는지**만 나타낸다.
동일 크기라면 `equal associated changes`로 표시한다. 인과분해가 아니다.

## 12. Local Moran + FDR

기존 conditional permutation 함수를 그대로 사용한다. focal z는 고정하고 나머지
값을 permutation하여 양측 local p를 계산한다. `variable×weight`별 모든 station에
BH-FDR을 적용한다. Directed K4/symmetric K4/IDW p2 row 세 설정 **모두** 같은
FDR-significant quadrant일 때만 stable이다. 과거 여섯 설정과 안정성 정의의 비교
범위를 함께 표시한다. 새 기간의 인제는 주 K4 raw HH지만 FDR 비유의이며 stable이 아니다.
유의한 Local Moran을 자동 hotspot 또는 위험지역으로 해석하지 않는다.

## 13. Tmax/Tmin warming contrast

`TMIN Sen−TMAX Sen`, °C/decade. 양수는 Tmin 상승이 더 빠름을 의미한다.
±1e−12 내 값은 동률이다. 분포·방향·Global Moran을 별도로 계산한다.

## 14. DTR

각 station×source×year의 `annual Tmax mean−annual Tmin mean`을 만든 후
그 연도별 DTR에 Theil–Sen 추세를 다시 적합한다. 두 Sen 기울기의 차이를 DTR
Sen으로 대체하지 않는다. °C/decade이며 KMA/NASA 결과를 각각 저장한다.
DTR MK에 대한 BH family는 source별 공통기간 관측소다. KMA DTR 공간통계를 제공한다.

## 15. 계절

Stage16 KMA TAVG DJF/MAM/JJA/SON 기울기를 사용한다. DJF의 전년도 12월 귀속 및
95% completeness/full-boundary 정책을 유지한다. DJF는 1992–2025, 나머지는 1991–2025다.
세 주요 W별 Moran, 계절 중앙 기울기, 계절 지도 네 장을 생성한다.
dominant season은 범주 지도일 뿐 수치 Moran에 넣지 않는다.

## 16. Threshold proxies

TMAX≥33°C, TMIN≥25°C의 연간 유효-pair일 기반 count에 대한 Sen, days/decade다.
NASA/KMA 비교에 쓰인 Stage16 정의를 유지한다. 결측일수 보정이나 0 채움을 하지 않는다.
같은 NASA grid라도 KMA 결측 패턴 때문에 파생 proxy가 달라질 가능성이 있으므로
그룹 내 Sen이 다르면 grid 재분석을 중단한다. 이번 실제 입력에서는 모두 일치했다.
희소 count에서 Sen=0인 경우와 공식 폭염/열대야 통계가 아니라는 점에 주의한다.

## 17. Bias/RMSE

TAVG Bias=NASA−KMA, RMSE는 paired daily error의 제곱평균제곱근, 모두 °C다.
관측소별 대조값이므로 unique-grid로 평균내어 accuracy를 계산하지 않는다.
공유/단독 grid에 연결된 station 집단의 n·중앙값·IQR은 기술적 비교일 뿐이다.

## 18. 해안거리와 좌표 연관

공식 해안선 기반 Stage16 distance_to_coast_km를 재사용한다. 해안거리 대 KMA3변수,
contrast/DTR/Bias/RMSE/33/25의 Pearson·Spearman·p·유효 n을 계산한다.
위도·경도·고도 대 KMA3변수/Bias/RMSE도 계산하고 과거 존재하는 결과와 나란히 기록한다.
이전 단계에 없는 조합은 old_result_available=False와 NaN으로 남긴다.
연관검정 p는 탐색적 raw p다. 공간적으로 독립한 station이라는 가정은 성립하지 않을 수 있다.
NASA 고도 연관을 새로 수행하지 않으며 ASOS 고도를 grid 고도로 대체하지 않는다.

## 19. 해안/내륙 20/30/50 km

distance≤threshold는 Coastal, 초과는 Inland. 주 기준 30 km를 결과 유의성으로 바꾸지 않는다.
각 기준별 9변수의 n·median·IQR·양측 asymptotic tie-corrected MWU·효과크기를 저장한다.
`rank_biserial=2U/(n_coastal×n_inland)−1`; 양수는 Coastal 값이 더 큰 방향이다.
각 threshold의 9개 p에 별도 BH-FDR을 적용한다.
Stage13 threshold consistency 함수를 재사용하여 old/new 분류를 비교한다.
현재 20/30/50 모두 TAVG/33/25/Bias가 FDR 유의, Tmin/RMSE는 20/30에서만 유의하다.

## 20. 지역/고도 기술통계

region_level1별 관측소 n, KMA3변수/Bias/RMSE 중앙값·IQR, n<3 flag를 유지한다.
`<50m`, `50–200m`, `200–500m`, `>=500m`의 기존 고도 band를 재사용한다.
원래 지역 라벨은 변경하지 않는다. 면적가중 지역 기후값이나 고도의 인과효과가 아니다.

## 21. 한계와 다음 단계

모든 공간통계는 점/격자 표본에 대한 탐색 결과다. 상관은 정확도·인과성이 아니다.
원자료의 결측·일 경계·고도·관측소 이력, NASA 격자 추정, 공간대표성 불균등을 고려한다.
SAR/SEM·보간·예측·기후위험 종합점수·자동 hotspot 기능을 추가하지 않았다.
18단계의 상세 기간 민감성 분석은 별도 요청 후 진행한다.

## 22. 실행과 재현성

```bash
python main.py --analyze-common-period-spatial --dry-run
python main.py --analyze-common-period-spatial
python main.py --report-common-period-spatial
python -m pytest -q
python -m pip check
python scripts/verify_common_period_spatial.py
```

dry-run은 입력 검증과 예상 계산 수만 표시하며 파일을 쓰지 않는다. 전체 실행은
26개 CSV·18개 interactive HTML 지도·9개 PNG·HTML/Markdown 보고서를 생성한다.
보고서: `output/reports/common_period_spatial/common_period_51station_spatial_reanalysis_report.html`.
manifest: `output/manifests/common_period_spatial_reanalysis_manifest.json`.
검증 기록: `output/reports/common_period_spatial/common_period_spatial_verification.json`.

manifest는 입력/처리코드/출력 SHA256, seed, permutations, 각 W의 설정, representation,
bridge, coastal 기준, grid 일치 검사, 과거 파일 SHA256/mtime 보존 결과를 기록한다.
개인 경로나 인증키를 넣지 않는다. 고정 정렬·seed·HTML div ID로 산출물을 재현한다.
검증 스크립트는 requests HTTP를 차단한 채 재실행하고 17개 대시보드 페이지 및 NASA
representation 선택기를 검사한다. plotly HTML의 브라우저 표시에는 CDN JS/지도 자원이
필요할 수 있지만 분석·CSV·PNG·통계 검증은 외부 API 없이 수행한다.
