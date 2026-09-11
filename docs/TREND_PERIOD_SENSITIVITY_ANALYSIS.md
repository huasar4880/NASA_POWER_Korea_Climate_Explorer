# Stage18 — Trend Period Sensitivity & Start-Year Robustness

## 1. 목적

종료연도를 2025년으로 고정하고 시작연도에 따라 추정 추세의 부호·크기·유의성 및
공간·해안 연관이 얼마나 달라지는지 검증한다. 기존 1–17단계와 stable VERSION 1.0.0을 유지한다.
새 예측, 기후 시나리오, 도시 확장, composite risk/stability score는 추가하지 않는다.

## 2. Fixed Tier A station network

`output/tables/nationwide_tier_a_analysis_stations.csv`의 Final Tier A를 사용한다.
Stage10 shortlist/master 및 Stage17의 Tier A-origin 집합과 일치하고 Tier B와 교집합이 없어야 한다.
N은 목록에서 읽으며 현재 45개다. 동일 ID 집합을 모든 window에 사용한다.
품질 실패 시 자동 탈락·대체하지 않고 REVIEW_REQUIRED로 중단한다.

## 3. Daily cache sources

`data/nationwide_matched/`, `data/nationwide_kma_processed/`, `data/nationwide_nasa_processed/`의
1981–2025 저장 자료만 사용한다. matched의 6개 기온열을 독립 NASA/KMA processed 값과
NaN 위치까지 대조한다. NASA POWER T2M/T2M_MAX/T2M_MIN과 ASOS 평균/최고/최저기온이며 단위 °C다.
API fallback은 없다. 파일 부재·불일치 시 중단하며 인증키나 개인 절대경로를 manifest에 기록하지 않는다.

## 4. Windows / calendar

| 시작 | 종료 | 연수 | 일수 |
|---|---|---:|---:|
| 1981-01-01 | 2025-12-31 | 45 | 16,436 |
| 1986-01-01 | 2025-12-31 | 40 | 14,610 |
| 1991-01-01 | 2025-12-31 | 35 | 12,784 |
| 1996-01-01 | 2025-12-31 | 30 | 10,958 |
| 2001-01-01 | 2025-12-31 | 25 | 9,131 |

`config/period_sensitivity.json`이 유일한 Stage18 설정원이다. 25년 미만 window는 허용하지 않는다.
시작과 끝을 포함하며 날짜 중복·누락·재정렬·다른 station ID를 허용하지 않는다.

## 5. Subsets and preservation

새 subset은 `data/period_sensitivity/START_YYYY/{station_id}_nasa_kma_temperature_YYYY_2025.csv`에
station×window 225개로 저장한다. 6변수 관측값과 NaN은 그대로 보존한다.
이전 data/output 및 VERSION의 SHA256와 mtime_ns를 전후 비교한다. 이전 검증 스크립트를
재실행하여 과거 결과를 덮어쓰지 않고 새 Stage18 전용 검증 스크립트를 사용한다.

## 6. Window-specific quality

station×source×window 450개 품질 행과 연도별 completeness를 저장한다.
3변수별 valid/missing/rate/longest-gap, 실제 시작/종료, expected dates, 중복수를 기록한다.
기존 screening 규칙: 변수 결측률 ≤5%, core gap <90일, 연도의 ≥90%가 completeness ≥90%.
완전성은 3기온 모두 유효한 날 / 실제 해당 연도 달력일수다. inf·미처리 결측코드와
[-90,65]°C 바깥 값은 넓은 보수적 sanity gate로 중단한다. 이 범위를 공식 KMA QC 기준이라고
주장하지 않는다. 결측 보간·0 치환·임의 보정·관측 생성은 없다.
선정 metadata의 기존 `annual_completeness`는 전체기간 기준으로 유지하며, window별 실제 품질은
`data_quality` 및 `annual_completeness` 결과표에서 확인한다.

## 7. Trend estimation and units

각 window의 일자료에서 연평균을 새로 산출하고 연도-연평균에 OLS, original Mann–Kendall,
기존 자기상관 진단 및 조건부 Hamed–Rao modified MK, Sen slope와 95% CI를 계산한다.
Sen은 모든 유효 연도 쌍의 `(value_j−value_i)/(year_j−year_i)` 중앙값이다.
OLS/Sen의 연간 기울기에 10을 곱해 °C/decade로 표시한다. CI도 °C/decade이다.
5/10년 후행 이동평균은 새 annual CSV에 유지하되 추세 적합 입력으로 쓰지 않는다.
전체 추세 적합은 4,950개: 기온 1,350, 계절 TAVG 1,800, threshold 1,350, DTR 450.

## 8. Window-specific BH-FDR

original MK raw p에서 새 BH를 계산한다. 기본 family는 window×source×metric 내 N개 관측소다.
계절은 season, threshold는 proxy를 추가한다. DTR은 window×source×DTR이다.
이전 q를 재사용하지 않고 window 간 합쳐 보정하지 않는다. 1991 결과도 이전 51개 family의
q를 가져오지 않고 고정 Tier A 45개의 raw p로 계산한다. 모든 family 크기를 저장·검증한다.

## 9. Sign stability

각 station×source×metric의 5개 slope, min/median/max/range, 1981 대비 최대 절대차,
1991−1981 및 2001−1981 차이를 저장한다. `slope_range=max−min`이며 °C/decade다.
양수 전부 POSITIVE_ALL_WINDOWS, 음수 전부 NEGATIVE_ALL_WINDOWS,
양·음 공존 SIGN_SENSITIVE, 전부0 ZERO_ALL_WINDOWS, 나머지는 NONNEGATIVE_WITH_ZERO /
NONPOSITIVE_WITH_ZERO로 구분한다. 부호변경수는 시작연도 순서에서 0을 제외한 인접 비영 부호 반전 수다.
near-zero 분모를 사용하는 상대 range와 합성 score는 만들지 않는다.

## 10. Significance stability

FDR 유의 window 5/5 SIGNIFICANT_ALL_WINDOWS, 3–4 MOST_WINDOWS_SIGNIFICANT,
1–2 SOME_WINDOWS_SIGNIFICANT, 0 NEVER_SIGNIFICANT. CI가 0을 배제하는 window 수도 별도다.
window는 강하게 중첩되므로 유의 비율은 독립 반복시험 성공확률이 아니다.

## 11. TMAX/TMIN contrast

TMIN Sen slope − TMAX Sen slope. 양수는 Tmin 기울기가 더 크다는 뜻이다.
KMA/NASA 각각 window 분포와 station별 부호 안정성을 제공한다.
두 양의 추세 차이뿐 아니라 음의 추세에서도 단순 기울기 비교이므로 원인·가속을 뜻하지 않는다.

## 12. DTR

각 station/source/year의 연평균 Tmax−연평균 Tmin으로 연간 DTR을 만들고 직접 Sen/MK/BH를
다시 계산한다. `Sen(Tmax)−Sen(Tmin)`으로 대체하지 않는다. °C/decade; 음수는 연간 DTR 감소다.

## 13. Seasonal sensitivity

TAVG만 DJF/MAM/JJA/SON으로 계산한다. December는 다음 연도의 DJF.
실제 달력이 완전한 season만 허용하고 유효일 ≥95%이면 산술평균, 아니면 NaN.
DJF는 각 start+1부터 2025까지여서 적합 유효 연수가 전체 window보다 한 해 적다.
dominant season은 최대 KMA TAVG Sen slope이며 동률 순서는 DJF/MAM/JJA/SON.
dominant_1981/1986/1991/1996/2001 및 최빈 계절·빈도를 저장한다.

## 14. Threshold proxies

Tmax≥30/33°C, Tmin≥25°C를 NASA/KMA 동일 유효 pair 날짜에서 계산한다. `>=`는 경계를 포함한다.
관측 누락일을 무사건일로 처리하지 않으며 연간 일수를 확장·스케일링하지 않는다.
valid pairs=0이면 count=NaN, 유효일은 있지만 사건이 없으면 count=0이다.
연간 count에 직접 추세 적합, 단위 days/decade. 공식 폭염·열대야 통계와 구분한다.
희소 사건의 다수 동률 때문에 Sen slope가 0이어도 MK가 유의할 수 있다. 따라서
“FDR 유의”와 “양의 Sen slope이면서 FDR 유의”의 관측소 수를 혼동하지 않는다.

## 15. Validation / consistency

매 window station×metric 유효 daily pairs에서 Bias=mean(NASA−KMA), MAE=mean(abs(diff)),
RMSE=sqrt(mean(diff²)), Pearson r, Spearman rho 및 n_pairs를 새로 계산한다.
Bias/MAE/RMSE는 °C, 상관은 무차원. window별 중앙값·범위와 station별 변화폭을 제공한다.
NASA/KMA Sen 부호 일치·양측양수·양측FDR유의를 별도 집계한다.
Bias/RMSE 변화는 기간 구성 변화와 연관되며 자동으로 정확도 향상을 의미하지 않는다.

## 16. Moran trajectory

관측소 geometry N=45와 고유격자 geometry G=33 각각에서 거리/가중행렬을 한 번 만들고
전 window에 그대로 재사용한다. 주 directed K4, 민감도 directed K3/K5, symmetric K4,
full inverse-distance p2 row-standardized. 고립점·분리 component는 중단한다.
Global Moran: 고정 seed 20250905 + 기존 변수별 offset, 999회 양측 순열.
관측소 10변수×5weight×5window=250, NASA 고유격자 TAVG 25, 총275검정.
Global p는 다중검정 보정하지 않은 탐색적 raw p이며 .05 미만을 표시한다.

기간분류는 weight 강건성 분류와 별개인 사전 명시한 운영 규칙이다. 부호 반전이면
DIRECTION_SENSITIVE. 그 외 유의성 전환이 하나라도 있거나 I range>0.2이면 PERIOD_SENSITIVE.
그 외 ≥80% 양의유의이면 SPATIALLY_STABLE_POSITIVE, ≥80% 비유의면 ROBUST_NON_SIGNIFICANT,
나머지는 PERIOD_SENSITIVE. 전환 우선 규칙 때문에 이 5-window 설계에서 두 안정분류는
실제로 동일 유의 상태 5/5가 필요하다. 학계의 보편적 임계값으로 제시하지 않는다.
인접 start 간 양방향 유의성 전환을 모두 기록한다.

## 17. NASA grid handling

이전 단계의 native MERRA-2 중심 추정 표현을 유지한다. 같은 격자 그룹의 세 기온 전체
일자료/NaN 위치가 각 window에서 같은지 다시 검증한 후 NASA TAVG를 격자당 하나만 사용한다.
격자좌표는 ASOS 평균좌표가 아니며 API 반환 metadata가 아니다. 동일 자료의 격자추정
일관성을 확인하는 것이지 POWER 제품의 전 지구·전 기간 grid 불변을 입증하는 것은 아니다.
NASA station-linked I와 unique-grid I/p 및 unique−station 차이를 각각 저장한다.
KMA 및 Bias/RMSE는 관측소 단위를 유지한다.

## 18. Coastal associations and station summaries

기존 고정 해안거리(km)와 9개 기후 metric의 Pearson/Spearman/raw p/n을 매 window 재계산한다.
Coastal은 거리≤30km, Inland는 >30km. 20/50km는 대표 start 1981/1991/2001에서만 비교한다.
양측 tie-corrected asymptotic Mann–Whitney U와 rank-biserial 효과, window×threshold의
9개 metric BH-FDR를 사용한다. 양의 rank-biserial/median difference는 coastal 쪽이 높음.
30km의 5기간 차이방향/유의성 안정성과 연속거리 상관 안정성을 구분한다.
station_metric_summary는 source×metric 별 slope_range 내림차순이며 기후 위험도 순위가 아니다.
전국 summary는 관측소 분포 min/Q1/median/Q3/max이며 면적가중 전국 대표값이 아니다.

## 19. Limitations

25년 window는 45년보다 짧아 slope 불확실성과 극한·계절 연변동의 영향이 클 수 있다.
관측 이력·고도·지형·시간체계·잔여 결측·공간 자기상관 및 다중 탐색을 고려해야 한다.
fixed stations는 구성효과를 통제할 뿐 모든 혼란요인을 제거하지 않는다. 종료연도 민감성,
change-point, 예측, 미래 시나리오, 전체국토 면적 평균은 이번 단계 범위 밖이다.

## 20. Why this is not acceleration analysis

후기 시작 window의 slope가 커져도 시작과 길이가 동시에 변하고 관측이 중첩되어 있다.
허용 표현은 “분석 시작연도에 따라 추정된 장기추세 크기가 달라졌다”이다.
“기후변화가 가속되었다”는 별도 검증 없이 주장하지 않는다.

## 21. Reproducibility / CLI / artifacts

```bash
python main.py --analyze-period-sensitivity --dry-run
python main.py --analyze-period-sensitivity
python main.py --report-period-sensitivity
python -m pytest -q
python -m pip check
python scripts/verify_period_sensitivity.py
```

dry-run은 cache 검증과 계획 출력만 수행하며 결과파일을 만들지 않는다.
분석 결과는 `output/{tables,charts,reports}/period_sensitivity/`에만 저장한다.
필수25 CSV와 보조 annual/quality/summary/geometry/reproduction CSV,
PNG15개, station trajectory HTML1개, 대표기간 point map HTML9개,
`trend_period_sensitivity_report.html/.md`를 생성한다.
실제 목록·행수·해시는 `output/manifests/period_sensitivity_manifest.json`과 CSV에 있다.
입력/계산코드/결과 SHA256, 설정, source, 고정 N/G, 방법·FDR·seed·가중행렬 정의를 기록한다.

18번째 Dashboard **기간 민감성**은 완료 manifest와 CSV 해시를 검증한 후 저장 결과만 읽는다.
Window A/B 선택으로 slope 차이, FDR 변화, Moran 차이, Bias/RMSE 차이를 표시한다.
미완료·파일 변조 상태에서는 결과 표시를 거절한다. fitting/API/파일 갱신은 없다.
대화형 HTML은 Plotly CDN과 지도 지형 리소스가 브라우저에서 필요할 수 있다. PNG/표/보고서 본문은 로컬이다.

검증 스크립트는 HTTP 요청을 차단한 상태로 전체 재계산, 모든 생성물 해시 동일성,
보고서 재생성 동일성, dry-run 무변경, 기존 모든18개 화면과 새 선택기 동작,
과거 파일 SHA256+mtime 보존을 확인한다. 결과는 새 reports 폴더의
`period_sensitivity_verification.json`에 기록한다. 전체 pytest 결과는 실행 후 별도 보고한다.

### 실제 실행 검증 — 2026-09-10

- 기존 569 + 신규 84 = 전체 **653 passed**, 323.93초. 합성 선형 test fixture의
  보조 Hamed–Rao 계산에서 RuntimeWarning 2건이 있었으며 기존 non-finite 상태 처리로 보존된다.
  실제 분석 실패나 원자료 변경은 없다. `pip check`: No broken requirements found.
- 실제 CLI dry-run / 분석 / report 전부 성공. 4,950개 추세 적합과 275개 Global Moran 검정.
- 전체 재계산에서 daily225 + table42 + PNG15 + HTML시각화10 + 보고서2 = **294개 해시 동일**.
  manifest 및 독립 verification JSON은 이 294개와 별도다.
- HTTP 요청 자체를 차단한 검증에서 요청 시도 0; NASA/KMA 각각0.
- 모든18개 Dashboard 페이지, 기본 진입화면, Stage18 A/B·metric·source 선택기 정상.
- 과거 data/output/VERSION **1,776개 SHA256+mtime_ns 무변경**, 기존 기간과 수치 재현 검사24개 통과.
- station×source×window 품질450행 전부PASS. 모든NASA 기온 결측0;
  1981 window KMA TAVG/TMAX/TMIN 결측 총204/63/61일을 그대로 유지했다.
- KMA TAVG 모든 window 양수45개, 5/5 FDR유의42개, slope range 중앙값0.174492°C/decade.
  window별 Sen 중앙값0.388787 / 0.390613 / 0.450836 / 0.485722 / 0.565778°C/decade.
- 주 K4 KMA TAVG Moran I는0.157643 / 0.129988 / 0.037171 / −0.091544 / −0.097121,
  p=.043 / .091 / .542 / .436 / .411. 방향·유의성 민감성을 함께 확인했다.
- Bias/RMSE 및 NASA TAVG의 양의 공간 자기상관은 주K4의 모든 window에서 raw p<.05로 반복됐다.
  이는 가속화·인과·예측에 관한 증명이 아니다. 19단계는 아직 시작하지 않았다.
