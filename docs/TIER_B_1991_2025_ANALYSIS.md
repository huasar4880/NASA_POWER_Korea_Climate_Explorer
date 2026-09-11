# Tier B 1991–2025 독립 Cohort 분석 (Stage 15)

## 1. 목적과 범위

Stable VERSION 1.0.0, 1–14.5단계 코드·테스트·기존 산출물을 보존하고 Final Tier B만
1991-01-01–2025-12-31에 분석한다. 이 단계는 기온 세 변수만 포함하며 Tier A+B 통합,
전국 공간모형, 강수·일사 확장은 수행하지 않는다.

> Tier B는 1991–2025 공통기간 cohort이며, Tier A 1981–2025 결과와 추세 크기를 직접 비교하면 기간 차이의 영향을 받을 수 있습니다.

## 2. 실제 cohort와 선택

Source of truth는 `output/tables/nationwide_asos_longterm_shortlist.csv`의 eligibility_tier=B.
`nationwide_asos_station_master.csv`에서 eligible_1991_2025=True,
manual_review_required=False, 실제 가용기간이 공통기간을 포함하는지 결합 검사한다.
Continuity risk low/medium만 허용하며 high/manual_review/unresolved/unknown은 거부한다.
후보의 조건 위반이 발견되면 조용히 제외하지 않고 전체 선택을 중단한다. ID/개수는 코드에 고정하지 않는다.

이번 저장 shortlist의 관측소는 95 철원, 136 안동, 185 고산, 216 태백, 248 장수, 271 봉화이다.
실제 좌표·지역·고도·가용기간은 `tier_b_analysis_stations.csv`를 참조한다.
Medium 이력 위험을 제거했다는 의미가 아니며 과거 station screening 판단을 이어 사용한다.

## 3. 실행과 재개

```bash
python main.py --analyze-tier-b --dry-run
python main.py --analyze-tier-b
python main.py --report-tier-b
```

Dry-run은 다운로드·통계적합·프로젝트 파일 저장 없이 관측소, KMA/NASA cache hit와
예상 NASA 요청 수를 출력한다. 완전한 NASA 기간은 관측소당 기본 1회 요청이며 재시도는 별도다.
`--request-interval`을 사용할 수 있으나 실제 요청 사이 최소 1초 간격은 유지한다.
기존 도시/KMA 모드 또는 `--force-download`와 결합하지 않는다.
실패 후 같은 analyze 명령으로 재개한다. 완료 raw는 다시 받지 않으며 실패 이력은 별도
`download_state.json`의 pending/completed/failed 및 누적 api_attempts에 기록한다.
기존 raw가 손상됐으면 덮어쓰지 않고 수동 검토를 요구한다.

## 4. 출처·cache·정제

NASA POWER Daily Point, community RE, LST, 동일 station 위경도,
T2M/T2M_MAX/T2M_MIN (°C). NASA 격자 기온은 ASOS 점 관측과 동일한 자료가 아니다.
공식 출처: [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/).
KMA ASOS avgTa/maxTa/minTa (°C), 출처: [ASOS 일자료](https://www.data.go.kr/data/15059093/openapi.do).
KMA 기존 Stage10 전국 cache는 읽기 전용으로 먼저 찾는다. 안동의 1981–2025 cache도
1991–2025로 메모리에서 잘라 재사용한다. 새 요청이 필요하면 기존 KMA 10년 chunk,
999행 pagination, 인증키 정규화·오류 코드·backoff client를 재사용한다.
완료 chunk는 재사용하고 실패 중인 chunk는 다시 요청할 수 있다. 일일 한도 우회는 하지 않는다.

신규 경로:

- `data/tier_b_nasa_raw/` (NASA 원본, 상태)
- `data/tier_b_kma_raw/` (KMA 상태 및 필요한 경우 신규 원본/chunks)
- `data/tier_b_nasa_processed/`, `data/tier_b_kma_processed/`
- `data/tier_b_matched/`

Raw 불변. 정제 값은 기온 fill code 및 -90–70°C 밖의 값을 NaN으로 처리한다.
누락 날짜도 NaN인 행으로 reindex해 두 source에 모두 12,784일 달력을 유지한다.
Station ID 불일치·중복 날짜는 임의 선택/평균하지 않고 중단한다. 0°C 관측값은 그대로 보존한다.
Processed는 nasa_t2m/nasa_tmax/nasa_tmin, kma_tavg/kma_tmax/kma_tmin 명칭이다.
Matched는 기존 metric별 pair 계산함수의 nasa_T2M/kma_T2M 등 내부 명칭을 유지한다.

## 5. 품질과 제외 정책

Station×source 품질표는 raw 실제 행 수, 누락 날짜, 중복, 세 변수 결측 수/비율,
core(세 변수 중 하나라도 결측) 연속 공백, 연간 completeness를 기록한다.
연간표는 station×source×year별 expected_days와 valid_tavg/tmax/tmin 및 각각 비율을 제공한다.
Core completeness는 세 값이 모두 유효한 날 / 해당 연도 달력일수이다.

기존 `config/nationwide_screening.json`과 evaluate_period_quality를 그대로 적용한다:
변수별 전체 결측률 ≤5%, core 연속 공백 <90일, 전체 연도 중 ≥90%가 core completeness ≥90%.
위반시 analysis_review_required=True로 기록하고 **cohort 전체 통계를 보류**한다.
관측소 수를 몰래 줄이거나 낮은 품질을 정상으로 바꾸지 않는다. Dashboard/보고서는
incomplete manifest 또는 테이블 checksum 불일치 시 이전 표를 최신 결과로 보여주지 않는다.

## 6. 연간 통계·추세·FDR

기존 Tier A period-independent 계산함수를 재사용한다. 각 source/metric/연도별 유효 일값
산술평균(°C), 5·10년 후행 이동평균(min_periods=5/10). 첫 4/9년 이동평균은 NaN이다.
연간 평균은 screening을 통과한 관측소의 가용 관측일로 계산하며 누락일 보간/가중 보정은 없다.
OLS slope×10=°C/10년, R² 및 양측 p; original Mann–Kendall tau/p;
Theil–Sen 실제 연도 간격 기울기 및 95% CI(연간·10년당)를 산출한다.
Lag-1 Ljung–Box p<.05이면 기존 Hamed–Rao lag1 modified MK를 sensitivity로 함께 기록한다.
BH-FDR는 **Tier B 내부 source×metric**별 original MK p값에만 적용한다.
NASA/KMA, TAVG/TMAX/TMIN, Tier A는 다른 family이다. 작은 cohort에서 유의성/비유의성을
과장하지 않으며 유의성은 인과성이나 공간 대표성을 뜻하지 않는다.

## 7. Normal·anomaly·과거/최근

Normal=1991–2020의 30개 연평균 산술평균(연도별 동일 가중), 세 변수/두 source별 계산.
30개 유효 연도가 없으면 중단한다. Anomaly=해당 연평균−normal, °C.
Station summary의 first_10yr=1991–2000 연평균 평균, last_10yr=2016–2025 평균,
last_minus_first=최근−과거(°C)이다. 이는 회귀 기울기나 전체기간 추정 변화량과 다르다.

## 8. 계절

DJF의 12월은 다음 연도에 속한다. 불완전 경계 계절은 제외하여 DJF1992–2025(34개),
MAM/JJA/SON1991–2025(35개)를 사용한다. 계절 달력은 완전해야 하며 변수별 유효일 ≥95%.
Sen/MK 및 BH-FDR family=source×metric×season, Tier B 내부이다.

## 9. Threshold proxy

TMAX≥30°C, TMAX≥33°C, TMIN≥25°C의 연간 일수와 Sen/MK/선형 추세를 제공한다.
NASA/KMA의 각 threshold metric이 모두 유효한 **같은 날짜**만 센다. valid_pair_days를 함께 기록한다.
관측값이 있으나 threshold 미충족인 0일과 관측 pair가 아예 없는 NaN을 구분한다.
누락일을 무사건으로 채우거나 연간 환산하지 않는다. 작은 공백도 count 비교에 영향을 줄 수 있다.
Count=일/년, 기울기=일/10년, FDR family=source×threshold.
공식 KMA 폭염일/열대야 통계와 관측 기준이 같다고 주장하지 않는다.

## 10. NASA–KMA validation와 consistency

각 metric마다 유효 pair를 별도로 선택한다. d=NASA−KMA:
Bias=mean(d), MAE=mean(|d|), RMSE=sqrt(mean(d²)), 단위 °C.
Pearson r와 Spearman rho는 무차원이다. n_pairs>0, 유한 통계, RMSE≥MAE,
두 correlation의 -1…1 범위를 검증한다.
Sen 부호의 일치와 FDR 유의성 패턴을 따로 보고한다. 높은 correlation은 작은 Bias를 보장하지 않는다.

## 11. Summary·ranking·해안거리

Summary는 station 위치·지역·품질, KMA TAVG 평균·Sen·FDR q, TMAX/TMIN Sen,
NASA TAVG Sen, 일별 TAVG 검증, 33/25°C proxy 평균·추세 및 과거/최근 비교를 결합한다.
`*_sen_slope_decade` 단위는 °C/10년(기온), proxy 필드는 일/10년이다.
`days_tmax_ge_33_*_mean`, `days_tmin_ge_25_*_mean`은 연평균 proxy 일수이다.
Ranking은 각 추세 family별 Tier B 내부 내림차순, 동률 최소순위; 기후위험 순위가 아니다.

Stage13의 공식 국립해양조사원 coastline 원본·component·processed checksum/CRS를 확인하고
EPSG:5179에서 station point→전체 검증 coastline(도서 포함) 최단거리 /1000 (km)를 계산한다.
이는 Stage16 준비용 속성이며 Coastal/Inland 통계검정은 하지 않는다.
Stage14.5의 [가중치 수치 안정성 문서](SPATIAL_MODEL_NUMERICAL_ROBUSTNESS.md)는 그대로 유지하며
Tier B에서는 directed KNN4 등을 포함해 어떠한 Moran/SAR/SEM도 적합하지 않는다.

## 12. 산출물·재현성·UI

`output/tables/tier_b/` 15 CSV, `output/charts/tier_b/` 8 PNG,
`output/reports/tier_b/tier_b_temperature_analysis_report.html/.md`,
`output/manifests/tier_b_analysis_manifest.json`을 생성한다.
Manifest는 selection·기간·raw 입력 hash·processed/코드 hash·coastline manifest·통계설정,
실제 이번 실행 API 시도 횟수(재시도 포함)·출력 목록/hash·보호파일 결과를 기록한다.
인증키나 개인 절대경로는 기록하지 않는다. 다운로드 상태의 api_attempts는 실패한 연결 시도도 포함한다.
`--report-tier-b`는 저장 CSV만 사용하며 수치계산/API를 하지 않는다.
15번째 Dashboard `Tier B 1991–2025`도 저장 표/PNG만 읽는다.
검증 스크립트 `python scripts/verify_tier_b.py --baseline /private/tmp/stage15_protected_baseline.json`은
HTTP를 차단한 채 Stage15 재실행/보고서 재생성/모든 Dashboard 페이지/기존 hash·mtime를 확인한다.
Baseline 인수는 사용 환경에 존재하는 별도 snapshot 경로로 지정한다.

## 13. 한계와 Stage16 준비

이 여섯 관측소는 전국 면적 평균을 대표하지 않는다. 점과 격자, 지형·해안·고도,
관측소 이력, 자기상관, 표본 선택, 누락 및 서로 다른 기간의 영향이 남는다.
Tier A보다 빠르다/느리다는 추세 크기 직접 비교를 하지 않는다.
다음 단계에서만 별도 승인 후 Final A+B를 1991–2025 공통기간에 다시 계산하여 비교한다.
기존 Tier A1981–2025 결과는 그때에도 별도 보존해야 한다.

실제 이번 자료에서는 태백(216)과 봉화(271)의 NASA 세 변수 전체 일시계열이 동일하다.
각 station의 서로 다른 실제 좌표로 요청해 받은 결과이며 관측소를 복제한 것이 아니다.
NASA 공식 [API 안내](https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/)는
기상자료 해상도 0.5°×0.625°보다 가까운 위치에서 같은 정보를 요청할 수 있다고 설명한다.
이번 일치는 격자 공유와 부합하지만 raw CSV에는 원본 격자 ID가 없어 동일 격자임을 별도 확정한 것은 아니다.
따라서 NASA 6개 station 조회를 6개 독립 공간 관측으로 해석하지 않는다.

## 실제 검증 결과 (2026-09-09)

- 기존 375개 회귀 테스트 유지, 신규 56개 포함 전체 431개 통과.
- KMA 6개 cache 재사용, 신규 호출 0회. NASA 신규 다운로드 성공 6회;
  첫 표본의 sandbox DNS 실패 4회까지 포함한 GET 시도 누계는 10회. 성공 후 재실행은 모두 0회.
- 관측소별 공통달력 12,784일. 봉화 raw 12,783행의 누락일 1개를 NaN으로 유지했다.
- KMA TAVG/TMAX/TMIN 결측 수 범위 0–8 / 0–4 / 0–2, NASA는 모두 0.
  최장 core 결측 2일, 최소 연간 core completeness 99.4521%, 모든 station 품질 재검사 통과.
- KMA TAVG Sen 기울기 0.363831–0.513546 °C/10년, 중앙값 0.450999.
  FDR 유의 증가 6곳, 감소 0곳. TMAX 유의 증가 5곳, TMIN 6곳.
- 일별 세 변수 18개 validation 모두 sanity check 통과.
- 인터넷 요청을 차단한 재실행에서 25개 CSV/PNG/보고서 hash 동일,
  보고서 재생성 동일, 15개 Dashboard 페이지 및 기본 router 통과.
- 기존 data/output/VERSION 1,467개 파일의 hash·mtime 변화 없음.
