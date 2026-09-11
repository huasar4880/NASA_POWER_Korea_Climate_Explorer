# Tier A+B Common-Period Analysis, 1991–2025 (Stage 16)

## 1. 왜 공통기간인가

1981–2025의 Tier A 추세와 1991–2025의 Tier B 추세를 합치면 기간 효과가 섞인다.
이번 단계에서는 모든 station의 **일자료를 1991-01-01–2025-12-31로 맞춰 다시 집계·적합**한다.
기존 slope를 변환하거나 과거 q-value를 병합하지 않는다. Stable VERSION 1.0.0 및 1–15단계 산출물은 불변이다.

## 2. Tier provenance와 동적 선택

Source of truth는 Stage10 `nationwide_asos_longterm_shortlist.csv`와 station master이다.
기존 Final A/B 선택함수를 재사용하고, Stage11/15의 station-set 및 summary ID 집합과 교차 확인한다.
실제 선택은 A-origin45+B-origin6=51, 교집합0이다. 이 숫자나 ID 목록은 분석 코드에 고정하지 않는다.
Manual review, unresolved/high/unknown continuity, 불완전 가용기간은 자동 승인하지 않는다.
Source 간 불일치가 있으면 중단한다. Medium continuity는 기존 적격 판단을 계승하지만
이력 위험이 없다는 뜻은 아니다.

Station-grain 결과와 processed/matched에는 `cohort_origin=TIER_A/TIER_B`가 유지된다.
이는 과거 자료기간 eligibility metadata이며 품질 우열이나 기후학적 집단 분류가 아니다.
여러 cohort가 섞이는 grid/지역 집계에는 `cohort_origins`와 구성 개수를 별도로 기록한다.

## 3. 공통 달력과 품질

Python 날짜 연산으로 윤일을 포함한 12,784일을 계산한다. 원자료에 없는 날짜는 NaN으로
보존한 달력 행을 만들며 값 보간·0 대체를 하지 않는다. 기온 fill code와 -90–70°C 밖의
값은 기존 정제 규칙으로 NaN 처리한다. 중복 날짜와 다른 station ID는 임의 병합하지 않는다.

KMA/NASA 모두 station×source에서 날짜·중복·변수별 결측 수/비율·core 연속 결측을 검사한다.
`common_period_annual_completeness.csv`는 station×source×year×metric별 expected_days,
valid_days, completeness_ratio이다. Origin별 분포는 `common_period_completeness_cohort_summary.csv`.
기존 screening 설정을 재사용한다: 변수 결측률 ≤5%, 최장 core 공백 <90일,
연도 중 ≥90%가 core completeness ≥90%. 위반하면 common_period_review_required=True로 기록하고
cohort 전체 통계를 보류한다. 이전 Tier만으로 통과시키지 않는다.

## 4. Climate Normal

1991–2020의 유효 연평균 30개를 동일 가중 평균한다(°C).
Station×source×TAVG/TMAX/TMIN 모두 계산하며 30개 유효 연도가 없으면 실패한다.
이는 전체 일값을 한꺼번에 평균하는 방식과 윤년 가중치가 다를 수 있다.

## 5. 데이터 재사용·CLI·resume

```bash
python main.py --analyze-common-period --dry-run
python main.py --analyze-common-period
python main.py --report-common-period
```

Dry-run은 파일 저장·HTTP·추세적합 없이 cohort 수, cache hit/miss, 예상 요청량,
공식 grid 규격 기반 예상 고유 격자 수, 출력 경로를 보여준다.
Tier A NASA1981–2025 raw 및 전국 KMA raw는 공통기간 subset으로, Tier B는 기존 raw를
다시 동일 정제 경로로 처리한다. 완전한 캐시가 있으면 NASA/KMA HTTP 요청은 0회이다.

부족한 자료만 `data/common_period/nasa_raw/` 또는 `kma_raw/`에 새로 받는다.
기존 NASA HTTP/429/5xx retry와 KMA 인증키 처리·10년 chunk·999행 pagination·backoff를 재사용한다.
요청은 최소1초 간격이며 일일 제한을 우회하지 않는다. KMA 완료 chunk는 실패 후 재사용한다.
캐시가 손상되면 덮어쓰지 않고 검토를 요구한다.

최종 자료는 다음 경로에만 쓴다:

- `data/common_period/kma_processed/<id>_kma_temperature_1991_2025.csv`
- `data/common_period/nasa_processed/<id>_nasa_temperature_1991_2025.csv`
- `data/common_period/matched/<id>_nasa_kma_temperature_1991_2025.csv`

값 이름은 kma_tavg/kma_tmax/kma_tmin과 nasa_t2m/nasa_tmax/nasa_tmin이다.
`workflow_state.json`에 processed→matched→analyzed→validated를 기록한다.
같은 명령으로 다시 실행하면 캐시를 사용해 결과를 결정적으로 재생성한다.
다운로드 상태 예외에는 오류 유형만 저장하여 키·요청 URL을 노출하지 않는다.

## 6. Tier A 실제 재계산

Stage15에서 사용한 공통기간 정제·품질함수와 기존 Tier A의 period-independent 연간·계절·
통계함수를 그대로 재사용한다. A-origin도 1991–2025 annual series의 35개 값을 입력한다.
1981–1990 자료는 새 추세 입력에 포함되지 않는다. 기존 장기 slope를 읽는 곳은
`tier_a_period_comparison_preparation.csv`를 만드는 별도 연결 단계뿐이다.

## 7. Tier B 재현성

Stage15의 annual/moving average, trend, normal/anomaly, seasonal, threshold count/trend,
daily validation을 새 결과와 비교한다. 허용오차 rtol=atol=1e-9, NaN 위치도 비교한다.
`common_period_tier_b_reproduction.csv`에 항목별 행 수·최대 차이·통과 여부를 저장한다.
실제 최대 차이는 약3.55e-15로 부동소수점 수준이다.
**FDR q-value와 FDR 유의성은 family가 바뀌므로 재현 비교 대상에서 제외**한다.

## 8. Common FDR

Original Mann–Kendall raw p에서 BH-FDR을 새로 계산한다. KMA/NASA를 분리하고,
기온은 source×metric, 계절은 source×metric×season, proxy는 source×threshold별
선택된 **모든 공통기간 station**이 family다. 현재 각 family의 station 수는 51이다.
기존 A/B q를 사용하지 않았는지 별도 재계산 검사와 테스트를 수행한다.
α=.05. NASA station-linked family는 요청된 주요 결과로 유지하되, 공유 grid로 인한
의존성이 사라진 독립 표본 검정이라고 주장하지 않는다.

## 9. NASA grid 식별 근거와 한계

기존 NASA CSV에는 API가 반환한 resolved cell 좌표 metadata가 저장되지 않았다.
따라서 query 좌표를 반환 격자 좌표라고 표현하거나 같은 query 문자열만 비교하지 않는다.
NASA POWER의 [공식 자료원 설명](https://power.larc.nasa.gov/docs/methodology/data/sources/)은
기상자료 native grid가 MERRA-2 위도0.5°×경도0.625°임을 명시한다.
GMAO [격자 문서](https://gmao.gsfc.nasa.gov/media/publications/zbly36ziNFDFbmYmvhQeVqPhUo/Collow1341.pdf)의
원점 위도−90°, 경도−180°와 격자 간격을 사용해 가장 가까운 centre를 **추정**한다.

격자 인덱스는 floor((query−origin)/spacing+0.5)로 계산한다.
정확히 두 centre의 중간이면 반올림 규칙을 임의 선택하지 않고 returned metadata 검토를 요구한다.
ID는 `merra2_<lat:3 decimals>_<lon:3 decimals>`이며 station 이름을 포함하지 않는다.
`nasa_grid_returned_metadata_available=False`, 좌표 방법 및 공식 출처를 결과에 명시한다.
이는 검증된 native-grid 추정이지 API 반환 좌표를 직접 확인했다는 주장이 아니다.

## 10. 중복과 고유 grid 수

동일 inferred grid의 station 사이에서 전체 공통기간 날짜 및 T2M/TMAX/TMIN 값과 NaN 위치를
직접 비교한다. Fingerprint도 저장한다. 같은 grid인데 다른 시계열, 또는 다른 grid인데
동일 시계열이면 flag 후 grid-level 결과 생성을 중단한다. Singleton의 inferred 위치는
이 시계열 일치 검사만으로 별도 확정할 수 없다는 한계를 유지한다.

실제 결과는 51 station→34 native-grid 추정 그룹, 공유 그룹14개, 공유 그룹 내31 station이다.
최대 그룹 크기3. 태백216/봉화271/영주272는 (37.000,128.750) 그룹이며 기온3종 시계열이 완전히 일치한다.
모든 공유 그룹이 일치하고 mapping mismatch=0이다. Station을 삭제·병합하지 않는다.
다른 KMA 점 관측과 대조하기 때문에 station별 validation은 계속 필요하다.

NASA-only slope summary는 station-linked51행과 unique-grid34행을 각각 요약한다.
TAVG Sen 중앙값은 각각0.464521/0.465482°C/10년이다. Unique-grid 표는 각 동일 시계열을
한 번만 표현하지만 grid 간 공간 독립성이나 전국 면적 대표성을 보장하지 않는다.

## 11. Trend

유효 일값의 연평균, 5/10년 후행 이동평균(min_periods=5/10).
OLS slope×10, R²와 p; Original MK; Theil–Sen slope/year와 slope/decade 및95% CI.
Lag1 Ljung–Box p<.05이면 기존 Hamed–Rao lag1 modified MK를 sensitivity로 계산한다.
기온 slope는 °C/10년, 연평균은 °C. Station summary의 `*_sen_slope`도 °C/10년이다.
유의성은 원인 규명이 아니며 초기기간에 따른 slope 차이가 존재한다.

## 12. Anomaly

Anomaly=해당 연평균−1991–2020 normal(°C). 2025 요약은 source별 min/median/max와 양수/음수
station 수로 보고한다. 전체 연도 heatmap은 **위도 내림차순, 동률 station ID 순**이다.

## 13. Seasonal

December는 다음 해 DJF로 배정한다. 완전한 계절 달력과 변수별 ≥95% 유효일이 필요하다.
DJF1992–2025(34시즌), MAM/JJA/SON1991–2025(35시즌).
계절별 평균·Sen·MK·common FDR와 source별 TAVG 최대 Sen 계절을 저장한다.
Dominant season은 signed slope가 가장 큰 계절이며 유의성 또는 인과 우세를 뜻하지 않는다.

## 14. Threshold proxy

TMAX≥30°C, ≥33°C, TMIN≥25°C. 각 threshold 변수의 NASA/KMA가 함께 유효한 날짜만 세고
valid_pair_days를 같이 저장한다. 누락일을 무사건으로 바꾸거나 연간 환산하지 않는다.
유효 관측에서 사건0일과 관측이 전무한 NaN을 구분한다.
Count는 일/년, slope는 일/10년. 공식 KMA 폭염·열대야 통계가 아니다.
희소한 정수 count에서는 Sen=0이면서 MK가 유의할 수도 있으므로 두 통계를 함께 해석한다.

## 15. Validation와 trend consistency

Metric별 유효 pair를 따로 사용한다. d=NASA−KMA:
Bias=mean(d), MAE=mean(|d|), RMSE=sqrt(mean(d²)), 단위°C.
Pearson/Spearman은 무차원이며 correlation p를 핵심 결과로 쓰지 않는다.
오차에 새 significance test를 만들지 않는다. RMSE≥MAE, correlation −1…1,
finite bias, n_pairs>0를 검사한다. Trend의 signed direction, source별 FDR와 both_significant도 기록한다.
NASA LST와 ASOS 일자료 기준, 격자/점 대표성 및 고도 차이를 고려한다.

## 16. Origin·지역·고도·해안·기간 비교

Origin별 TAVG/TMAX/TMIN Sen, Bias/RMSE의 n·mean·median·IQR·min·max를 기술적으로 비교한다.
Tier B n=6의 작은 표본이며 eligibility 이력이 기후학적 집단 구분은 아니다. MWU는 실시하지 않았다.
지역은 Stage10 `region_level1` 문자열 그대로 사용한다. '(산지)강원특별자치도'도 별도 그룹으로
남기므로 행정구역을 정규화한 전국 권역 통계와 다르다. n<3 그룹에 flag를 부여한다.
Summary의 `kma_tavg_fdr_significant_count`는 TAVG 유의 station 개수임을 명시한다.
고도대 <50/50–200/200–500/≥500m, 기존 공식 해안거리 ≤30km/초과를 기술적으로 요약한다.
해안23/내륙28 station이지만 인과효과나 면적가중 전국 평균으로 해석하지 않는다.

기존 A1981–2025와 새 A1991–2025 slope 연결표는 source×metric별 차이(새값−과거값)를 담는다.
이는 Stage18 준비이며 기간 민감성의 심층 검정은 수행하지 않았다.
공통기간 ranking은 각각의 추세 또는 절대 Bias/RMSE 크기 순위일 뿐 기후위험 순위가 아니다.

## 17. 산출물·Dashboard·재현성·제한

26 CSV는 `output/tables/common_period/`, 8 point map+interactive scatter(9 HTML)와
6 PNG는 `output/charts/common_period/`, 보고서 HTML/Markdown은 `output/reports/common_period/`.
파일명은 원 요청의 51station label을 유지하되 표시 station 수는 데이터에서 계산한다.
16번째 Dashboard '51개 공통기간 분석'은 checksum 검증된 저장 표만 읽고 origin/region/station/
elevation/coastal/shared-grid 필터와 요청한12개 섹션을 제공한다. 필터는 기존 common FDR를 변경하지 않는다.
지도는 station point와 추정 grid centre·연결선을 구분하며 보간 surface를 만들지 않는다.
Interactive HTML의 Plotly 및 지리 배경은 외부 CDN 접근이 필요할 수 있고 PNG/CSV는 오프라인이다.

Manifest `output/manifests/common_period_51station_manifest.json`에는 selection·기간·cache 출처·
실제 API 시도 수·grid 방법/그룹·FDR 설정·입력/정제/코드/산출물 hash를 저장한다.
인증키·개인 절대경로를 쓰지 않는다. `--report-common-period`는 CSV checksum을 검사하고
저장 결과만으로 보고서를 재생성한다. Incomplete manifest에서 오래된 결과를 최신처럼 보여주지 않는다.

```bash
python scripts/verify_common_period.py --baseline /private/tmp/stage16_protected_baseline.json
python -m pytest -q
python -m pip check
```

위 baseline은 작업 전 별도로 저장한 hash/mtime snapshot 경로이다. 검증 스크립트는 HTTP를
차단하고 신규 단계만 재실행, 결과 hash·보고서 재생성·모든16페이지와 필터·이전 파일 보존을 검사한다.
API 반환 격자 metadata 부재, grid 의존성, 작은 origin 표본, 관측 이력과 결측,
표본의 불균등 분포 때문에 추론을 과장하지 않는다.

## 18. 다음 단계

Stage17에서만 별도 요청 후 51-station 공통기간의 공간 재분석을 검토한다.
Stage14.5 weight 수치 안정성 기준을 참고하되 기존45-station 공간모형 결과를 재사용하지 않는다.
Grid sharing·점/격자 차이와 공간 가중치 민감도를 고려해야 한다.
이번 단계에서는 Moran/SAR/SEM, 보간, 예측, 미래시나리오 및 종합 위험점수를 만들지 않았다.

## 실제 실행 검증 (2026-09-09)

- 기존431개 유지 + 신규60개 = 전체491개 pytest 통과; pip check 문제 없음.
- 51곳 모두 cache 재사용, KMA/NASA API 각각0회. 공통 processed/matched153개 파일의
  12,784일 달력·고유 station ID·origin을 검사했다.
- KMA 결측 범위 TAVG0–24일, TMAX/TMIN0–7일; 최장 core 공백6일.
  원자료 날짜 누락은 통영2일·봉화1일·거제1일이며 NaN으로 유지했다. 중복0, NASA 결측0.
- 306개 normal(51×2×3), 공통 FDR, 8항목 Tier B 재현성 및153개 validation을 검증했다.
- 인터넷 요청을 차단한 재실행에서43개 결과물 hash 동일, 보고서 재생성 동일,
  Dashboard16페이지·공유 grid/origin/빈 선택 필터·기본 router 통과.
- 기존1–15단계 data/output/VERSION1,520개 파일 hash·mtime 변경 없음.
- KMA TAVG Sen 최소/중앙/최대0.178683/0.450836/0.728906°C/10년,
  common BH-FDR 유의 증가51개, 유의 감소0개.
- 상세 실행 증거: `output/reports/common_period/common_period_verification.json` 및 manifest.
