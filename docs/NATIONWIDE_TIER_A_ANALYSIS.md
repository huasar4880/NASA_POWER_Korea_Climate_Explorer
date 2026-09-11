# Nationwide Tier-A Climate Trend Analysis

## 1. 목적과 stable 경계

11단계는 10단계에서 엄격히 선별된 Final Tier A ASOS station만 동일한 1981–2025
기간으로 비교하는 experimental nationwide 분석이다. `VERSION`은 1.0.0으로 유지하며,
기존 8개 도시의 raw, processed, tables, reports는 입력으로 덮어쓰지 않는다. Tier B 6개와
manual review 또는 continuity unresolved station은 이 분석에 포함하지 않는다.

## 2. Tier A 선정과 분석 station

`output/tables/nationwide_asos_longterm_shortlist.csv`의 `eligibility_tier=A`를 출발점으로,
station master에서 다음을 모두 확인한다.

- `eligible_1981_2025=True`
- `manual_review_required=False`
- continuity risk가 `high`, `manual_review`, `unresolved`가 아님
- 실제 시작일 ≤ 1981-01-01, 실제 종료일 ≥ 2025-12-31

현재 선별 결과는 45개다. station ID는 코드에 고정하지 않으며 실행 때 CSV에서 읽는다.

`90 속초, 108 서울, 112 인천, 114 원주, 115 울릉도, 127 충주, 129 서산, 130 울진,
133 대전, 135 추풍령, 138 포항, 156 광주, 162 통영, 165 목포, 168 여수, 170 완도,
184 제주, 189 서귀포, 201 강화, 202 양평, 203 이천, 211 인제, 212 홍천, 221 제천,
226 보은, 235 보령, 236 부여, 238 금산, 243 부안, 244 임실, 260 장흥, 261 해남,
262 고흥, 272 영주, 273 문경, 277 영덕, 278 의성, 279 구미, 281 영천, 284 거창,
285 합천, 288 밀양, 289 산청, 294 거제, 295 남해`

좌표·고도·실제 자료기간·품질 metadata 전체는
`output/tables/nationwide_tier_a_analysis_stations.csv`에 기록한다.

## 3. 공통기간과 NASA query coordinates

- 분석기간: 1981-01-01~2025-12-31, 윤년 포함 16,436일
- Climate Normal: 1991-01-01~2020-12-31
- NASA 변수: `T2M`, `T2M_MAX`, `T2M_MIN` (°C)
- KMA 변수: `avgTa`, `maxTa`, `minTa` (°C)

NASA POWER Daily Point API는 각 ASOS station의 공식 위·경도를
`nasa_query_latitude/longitude`로 사용한다. 도시 대표좌표를 쓰는 stable v1.0 NASA 값과
완전히 같을 필요는 없다.

## 4. Cache, KMA processing과 daily matching

- NASA raw: `data/nationwide_nasa_raw/`
- NASA processed: `data/nationwide_nasa_processed/`
- KMA input cache: `data/nationwide_asos_raw/stations/` (10단계, 읽기 전용)
- KMA processed: `data/nationwide_kma_processed/`
- 일별 pair: `data/nationwide_matched/`
- NASA state: `data/nationwide_nasa_raw/download_state.json`
- 분석 manifest: `output/manifests/nationwide_analysis_manifest.json`

NASA raw가 16,436일·필수 schema·기간·중복 조건을 만족하면 재호출하지 않는다. ASOS raw에
관측 행 자체가 없는 날짜는 공통 달력에 행만 만들고 기온을 `NaN`으로 유지한다. 값이나 0을
만들지 않는다. 두 source는 날짜 기준 one-to-one inner join하며 각 metric은 양쪽 모두 유효한
pair만 validation에 사용한다.

## 5. Statistical methods

각 station·source·metric에서 일자료의 연평균을 먼저 만든다. 후행 5년/10년 이동평균은
각각 최소 5/10개 연도가 있을 때만 계산한다.

- 선형추세: OLS 기울기 ×10, °C/10년; R²와 p-value 병기
- Mann–Kendall: 원 단조추세 검정, tau와 p-value
- Modified MK: lag-1 Ljung–Box가 유의할 때 Hamed–Rao를 sensitivity로 적용
- Sen slope: 모든 연도쌍 기울기의 중앙값, °C/년과 °C/10년, 95% CI
- 유의수준: 0.05

## 6. FDR

Benjamini–Hochberg FDR은 `source × metric`별 Tier A station 전체를 하나의 family로
적용한다. 즉 KMA TAVG 45개, KMA TMAX 45개, KMA TMIN 45개가 각각 독립 family이며
NASA도 동일하다. 계절은 `source × metric × season`별 station 전체를 family로 둔다.

## 7. Normal과 anomaly

station·source·metric별 1991~2020 연평균 30개 평균을 normal로 계산한다. 연도별 anomaly는
`해당 연도 annual_mean - 1991~2020 normal_mean`이며 단위는 °C다.

## 8. Seasonal analysis

DJF, MAM, JJA, SON을 분석한다. 12월은 다음 해 `season_year`로 배정한다. 분석기간 경계에서
달력이 완전하지 않은 DJF는 제외하며, 달력 season이 완전하고 기온 유효율이 95% 이상인
seasonal mean만 추세에 사용한다. TAVG/TMAX/TMIN 모두 계산한다.

## 9. Threshold proxy

NASA와 KMA가 모두 유효한 같은 날짜에서 `TMAX ≥30°C`, `TMAX ≥33°C`, `TMIN ≥25°C`
일수를 연도별로 센다. station별 평균 연간일수와 Sen slope를 source별로 비교한다. 이는
공식 KMA 폭염·열대야 통계가 아니라 동일 threshold로 재계산한 analysis proxy다.

## 10. NASA–KMA validation

station×metric에서 `Bias=mean(NASA−KMA)`, MAE, RMSE(°C), Pearson r, Spearman ρ,
`n_pairs`를 계산한다. NASA는 격자자료, KMA는 지점관측이므로 차이를 단순 오류라고 부르지
않는다. Correlation은 accuracy가 아니며 Bias/MAE/RMSE와 함께 해석한다.

## 11. Region과 elevation exploratory summary

지역 요약은 `region_level1`별 station의 KMA TAVG Sen slope median/mean/min/max와
FDR 유의 station 수다. 면적가중 지역 평균이나 지역 기후의 참값이 아니다. 고도는 10단계와
같이 `<50m`, `50–200m`, `200–500m`, `≥500m`로 나눠 station 분포만 탐색한다.
위도·경도·고도와 Bias/RMSE의 Spearman 연관도 인과관계가 아닌 탐색 결과다.

## 12. Maps와 heatmap

`output/charts/nationwide_analysis/`에 KMA TAVG/TMAX/TMIN, NASA TAVG, TAVG Bias/RMSE,
FDR significance interactive HTML과 정적 PNG를 저장한다. Marker는 station 값이며
면적 격자나 전국 연속 surface가 아니다. KMA anomaly heatmap 행은 latitude 내림차순이다.

## 13. CLI와 복구

```bash
python main.py --analyze-nationwide-tier-a --dry-run
python main.py --analyze-nationwide-station 108
python main.py --analyze-nationwide-tier-a
python main.py --report-nationwide
```

dry-run은 station/cache/download/API 예상량만 출력한다. 한 station 완료 시 raw cache와
manifest가 갱신되므로 중간 실패 후 다시 실행하면 완료 station은 skip한다. 집계 CSV는
임시 파일이 완성된 뒤 원자적으로 교체한다. KMA cache가 없으면 임의 자료를 만들지 않고
10단계 screening 완료 방법을 안내하며 실패한다.

## 14. 현재 실행 결과

2026-09-05 실행에서 Tier A 45개 모두 NASA/KMA 1981~2025 자료 준비와 validation을
완료했다. 최초 NASA 실제 요청은 station당 1건, 총 45건이며 이후 재실행은 45 cache hit,
0 API 요청이었다. KMA TAVG Sen slope 중앙값은 약 +0.3888°C/10년이고 45개 모두
BH-FDR 유의한 양의 추세였다. 상세 수치는 결과 CSV와 전국 종합보고서가 source of truth다.

## 15. Limitations

- Tier A 45개만 분석하며 station 분포가 전국을 균등 대표하지 않는다.
- Tier B, manual review, continuity unresolved station을 제외했다.
- NASA grid와 KMA station의 공간대표성이 다르다.
- station-level 결과와 지역 sample 요약을 전국·지역 면적 평균으로 해석하지 않는다.
- threshold는 분석 proxy이고 correlation은 accuracy가 아니다.
- 유의성은 인과관계가 아니며 과거 추세는 미래예측이 아니다.
- NASA/KMA 추세 방향 일치는 absolute agreement를 뜻하지 않는다.
