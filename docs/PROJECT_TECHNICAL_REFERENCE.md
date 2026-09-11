# NASA_POWER_Korea_Climate_Explorer

## 프로젝트 목적

NASA POWER Daily Point API를 이용해 대한민국 주요 도시의 장기 기후자료를 수집하고, 동일한 pipeline으로 정제·통계·시각화하는 프로젝트다.

- 1단계: 서울 1981-2025 일별 기온 수집과 연평균 그래프
- 2단계: 서울 이동평균, 선형추세, 월 climatology와 연도×월 heatmap
- 3단계: 8개 도시 자동 수집·검증·장기추세 분석과 도시 비교
- 4단계: 8개 도시의 기온·강수·상대습도·풍속·일사량과 threshold proxy를 함께 분석
- 5단계: Mann-Kendall, 자기상관 sensitivity, Sen slope, FDR, normal/anomaly, 계절·연속일수 분석
- 6단계: 기존 분석 결과를 재사용하는 read-only Streamlit interactive dashboard
- 7단계: NASA POWER 격자자료와 KMA ASOS 지점 일자료의 독립적 교차검증 workflow

현재 범위는 NASA POWER 기반 다도시·다변수 과거 기후통계, 로컬 Streamlit dashboard, 선택적으로 실행하는 KMA ASOS agreement 분석까지다. 머신러닝, 예측, 미래 시나리오와 종합 기후위험 점수는 포함하지 않는다.

## NASA POWER 데이터

[NASA POWER](https://power.larc.nasa.gov/)는 위성 관측과 모델 기반 자료를 활용해 에너지·농업·기후 분석용 기상 자료를 제공한다. 이 프로젝트는 [Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)와 point endpoint를 사용하며, 변수 정의와 단위는 [NASA POWER Parameter Dictionary](https://power.larc.nasa.gov/parameters/) 및 실제 API metadata를 기준으로 기록했다.

- endpoint: `https://power.larc.nasa.gov/api/temporal/daily/point`
- community: `RE` (Renewable Energy)
- time-standard: `LST` (Local Solar Time)
- 분석기간: 1981-01-01 ~ 2025-12-31, 총 16,436일

### 4단계 사용 변수와 공식 metadata

| NASA POWER short name | API metadata의 변수명 | 단위 | temporal resolution | 기본 연간 집계 |
|---|---|---|---|---|
| `T2M` | Temperature at 2 Meters | °C | daily | 일자료 평균 |
| `T2M_MAX` | Temperature at 2 Meters Maximum | °C | daily | 일자료 평균 및 연간 최댓값 |
| `T2M_MIN` | Temperature at 2 Meters Minimum | °C | daily | 일자료 평균 및 연간 최솟값 |
| `PRECTOTCORR` | Precipitation Corrected | mm/day | daily | 일 강수깊이 합계 |
| `RH2M` | Relative Humidity at 2 Meters | % | daily | 일자료 평균 |
| `WS10M` | Wind Speed at 10 Meters | m/s | daily | 일자료 평균 |
| `ALLSKY_SFC_SW_DWN` | All Sky Surface Shortwave Downward Irradiance | kW-hr/m²/day | daily | 일별 조사량 평균 |

코드가 사용한 metadata는 `output/tables/nasa_power_climate_parameter_metadata.csv`에도 저장한다. 한 도시의 7개 변수는 API 한 번의 요청으로 받는다.

NASA POWER의 결측 코드 `-999`는 raw CSV에는 그대로 보존하고 processed CSV에서 `NaN`으로 변환한다. 결측치를 보간하거나 임의 값으로 채우지 않는다.

## 분석 대상 도시

모든 이름과 좌표는 `config/locations.json`에서 읽는다.

| 도시 | 위도 | 경도 |
|---|---:|---:|
| Seoul | 37.5665 | 126.9780 |
| Busan | 35.1796 | 129.0756 |
| Daejeon | 36.3504 | 127.3845 |
| Daegu | 35.8714 | 128.6014 |
| Gwangju | 35.1595 | 126.8526 |
| Gangneung | 37.7519 | 128.8761 |
| Jeju | 33.4996 | 126.5312 |
| Jeonju | 35.8242 | 127.1480 |

## 계산 방법과 단위

| 분석값 | 계산 방법 | 단위 |
|---|---|---|
| 연평균 `T2M`, `T2M_MAX`, `T2M_MIN` | 각 연도의 유효한 일별 값을 산술평균 | °C |
| `T2M_MAX` 연간 최대 | 각 연도의 유효한 일최고기온 중 최댓값 | °C |
| `T2M_MIN` 연간 최소 | 각 연도의 유효한 일최저기온 중 최솟값 | °C |
| 연간 강수량 | `PRECTOTCORR` 일 강수깊이의 연도별 합계 | mm/year |
| 연도별 최대 일강수량 | 각 연도의 유효한 `PRECTOTCORR` 중 최댓값 | mm/day |
| 연평균 상대습도 | `RH2M` 일자료의 연도별 산술평균 | % |
| 연평균 풍속 | `WS10M` 일자료의 연도별 산술평균 | m/s |
| 연평균 일사 특성 | `ALLSKY_SFC_SW_DWN` 일별 조사량의 연도별 산술평균 | kW-hr/m²/day |
| 5년 이동평균 | 현재 연도를 포함한 최근 5개 연평균의 후행 산술평균 | °C |
| 10년 이동평균 | 현재 연도를 포함한 최근 10개 연평균의 후행 산술평균 | °C |
| 선형 추세 | `연간 값 = 절편 + 기울기 × 연도` 최소제곱 회귀 | 변수 단위/year |
| `trend_per_decade` | 회귀 기울기 × 10 | 변수 단위/10년 |
| 전체기간 적합 변화 | 회귀 기울기 × `(2025 - 1981)` | °C |
| 월별 climatology | 유효한 일별 값을 1~12월별로 묶은 평균 | 각 변수 단위 |
| 월 누적 강수 climatology | 먼저 각 연도·월의 `PRECTOTCORR`를 합한 뒤 같은 달의 연도별 합계를 평균 | mm/month |
| 연도×월 평균 | 각 연도와 달력 월 조합의 일별 평균 | °C |

이동평균은 완전한 창이 있을 때만 계산한다. 따라서 5년 이동평균의 첫 4개 연도와 10년 이동평균의 첫 9개 연도는 빈 값이다. 2월 climatology에는 윤년의 2월 29일도 포함된다.

각 연간 series의 회귀 결과에는 `slope_per_year`, `trend_per_decade`, 결정계수 R², 기울기가 0이라는 귀무가설에 대한 양측 t-test p-value를 저장한다. 회귀는 결측 연도를 제외한 유효 연도만 사용한다. p-value가 작더라도 원인이나 인과관계를 뜻하지 않는다.

### Threshold 기반 climate indices

아래 값은 NASA POWER 격자형 일자료에 동일한 경계조건을 적용한 연도별 일수다. 경계값은 포함하며, 결측일은 기준 충족 또는 미충족으로 세지 않는다.

| 컬럼 | 계산 기준 | 단위 |
|---|---|---|
| `days_tmax_ge_30` | `T2M_MAX >= 30 °C` | days/year |
| `days_tmax_ge_33` | `T2M_MAX >= 33 °C` | days/year |
| `days_tmin_ge_25` | `T2M_MIN >= 25 °C` | days/year |
| `days_precip_ge_30` | `PRECTOTCORR >= 30 mm/day` | days/year |
| `days_precip_ge_50` | `PRECTOTCORR >= 50 mm/day` | days/year |
| `days_precip_lt_1` | `PRECTOTCORR < 1 mm/day` | days/year |

`days_tmax_ge_33`와 `days_tmin_ge_25`는 각각 본 프로젝트의 33 °C threshold heat-day proxy와 daily-minimum-temperature warm-night proxy다. 대한민국 기상청의 공식 폭염일수·열대야 통계와 동일한 지표가 아니다. 강수 threshold와 dry-day 값도 NASA POWER 기반 분석용 proxy다.

### 과거와 최근 비교

`city_climate_past_vs_recent.csv`는 1981~1990 연간 값의 평균과 2016~2025 연간 값의 평균을 비교한다. `absolute_difference = recent_mean - past_mean`이다. 온도와 상대습도는 percent difference를 제시하지 않으며, 강수·풍속·일사·일수 지표는 과거 평균이 0이 아닐 때만 `absolute_difference / past_mean × 100`을 계산한다.

`city_climate_trend_heatmap.png`은 단위가 다른 다섯 추세 원값을 직접 비교하지 않는다. 변수별로 8개 도시 추세의 z-score를 계산해 색과 셀 값으로 표시하므로, 각 변수 안에서 도시의 상대적 위치만 해석해야 한다. 실제 단위의 추세는 `city_climate_summary_1981_2025.csv`를 사용한다.

## 5단계 기후통계 고도화

기존 최소제곱 선형회귀를 유지하면서 비모수·강건 통계 결과를 나란히 제공한다. 통계적 유의성은 기후변화의 원인을 증명하는 것이 아니라 NASA POWER 격자자료에서 해당 기간에 관찰되는 단조추세를 기술한다.

### Mann-Kendall과 자기상관

- original Mann-Kendall test는 분포를 정규분포로 가정하지 않고 연간 값의 단조 증가·감소를 검정한다. `mk_tau`는 방향과 순위 일관성, `mk_p_value`는 추세가 없다는 귀무가설 아래의 raw p-value다.
- 기본 유의수준은 `alpha=0.05`이며 결과는 `increasing`, `decreasing`, `no trend`로 기록한다.
- lag-1 autocorrelation은 연간 유효값의 1시차 상관계수로 기록하고, lag 1 Ljung-Box p-value가 0.05보다 작을 때만 `autocorrelation_flag=True`로 표시한다.
- flag가 있는 series에는 [pyMannKendall](https://pypi.org/project/pymannkendall/)의 Hamed-Rao modified Mann-Kendall을 lag 1 variance-correction sensitivity로 추가한다. original MK 결과를 삭제하거나 대체하지 않는다. 적용하지 않은 행은 `modified_mk_method=not applied`와 사유를 기록한다.

### Sen slope와 선형회귀

[SciPy Theil-Sen 구현](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html)으로 모든 유효한 연도 쌍 기울기의 중앙값을 구한다. `sen_slope_per_year`, `sen_slope_per_decade`와 95% slope confidence interval을 저장하며 `sen_ci_lower`, `sen_ci_upper`는 10년당 단위다.

선형회귀 기울기는 제곱오차와 극단값의 영향을 더 받을 수 있지만 R²와 선형 적합 p-value를 제공한다. Sen slope는 이상값에 더 강건하고 단조 변화량 해석에 적합하다. 두 값이 다를 수 있으므로 하나를 다른 하나로 대체하지 않는다. 특히 0이 많은 이산 threshold-count series에서는 MK가 유의해도 pairwise slope의 중앙값과 Sen CI가 0일 수 있다.

### Benjamini-Hochberg FDR

[statsmodels `multipletests`](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)의 `fdr_bh`를 사용한다. `raw_p_value`/`significant_raw`는 개별 original MK 결과이고, `fdr_q_value`/`significant_fdr`는 같은 검정 family 전체에서 false discovery rate를 보정한 결과다.

- 연간 family: 8개 도시 × 17개 연간 변수·proxy = 136개 original MK 검정 전체
- 계절 family: 한 기후변수에 대한 8개 도시 × 4계절 = 32개 검정을 변수별로 보정

q-value는 raw p-value와 같지 않으며, 주요 유의성 해석에는 `significant_fdr`를 우선 사용한다. Modified MK p-value는 sensitivity 결과이며 이 original-MK FDR family에 섞지 않는다.

### 1991-2020 climate normal과 anomaly

1991~2020의 30개 연간 값을 climatological normal baseline으로 사용한다. 강수는 연간 또는 월간 누적량의 30년 평균이고, 기온·습도·풍속·일사는 해당 기간 평균이다. 월 normal은 각 연도·월을 먼저 물리적으로 집계한 뒤 30개 연도를 평균해 특정 월의 일수 차이가 연도 가중치를 바꾸지 않게 한다.

- absolute anomaly: `연간 값 - 1991~2020 normal`
- standardized anomaly: `(연간 값 - normal) / 1991~2020 표본표준편차`

기온 anomaly는 °C, 강수는 mm, 상대습도는 percentage-point, 풍속은 m/s, 일사는 kW-hr/m²/day 차이다. baseline 표준편차가 0 또는 `1e-12` 이하이면 standardized anomaly를 `NaN`으로 두며 percentage anomaly는 계산하지 않는다.

### 계절 정의

| 계절 | 달 | season year 규칙 |
|---|---|---|
| DJF | 12, 1, 2월 | December를 다음 연도 winter에 포함. Dec 2020 + Jan-Feb 2021 = DJF 2021 |
| MAM | 3, 4, 5월 | 달력연도 |
| JJA | 6, 7, 8월 | 달력연도 |
| SON | 9, 10, 11월 | 달력연도 |

완전한 날짜가 없는 첫·마지막 DJF는 제외한다. 따라서 1981~2025 자료의 DJF는 1982~2025의 44개 season year다. 변수의 한 날짜라도 결측이면 그 변수의 해당 계절 집계는 `NaN`이며 부분계절 평균을 만들지 않는다. 강수는 계절 합계, 나머지는 계절 일평균이다. 일사의 유효 계절수는 DJF 41개, 다른 계절 42개다.

### Consecutive climate indices

| 컬럼 | 기준 |
|---|---|
| `max_consecutive_tmax_ge_30` | 한 해 안에서 `T2M_MAX >= 30 °C`가 이어진 최대 일수 |
| `max_consecutive_tmax_ge_33` | 한 해 안에서 `T2M_MAX >= 33 °C`가 이어진 최대 일수 |
| `max_consecutive_tmin_ge_25` | 한 해 안에서 `T2M_MIN >= 25 °C`가 이어진 최대 일수 |
| `max_consecutive_precip_lt_1` | 한 해 안에서 `PRECTOTCORR < 1 mm/day`가 이어진 최대 일수 |

연도 경계, 결측일, 누락된 날짜에서 sequence를 끊는다. 모두 NASA POWER 기반 분석용 지속기간 proxy이며 공식 기상청 지표가 아니다.

### 도시별 변화 순위

10개 변수의 `sen_slope_per_decade`를 큰 값부터 독립적으로 순위화한다. FDR 유의성, original MK와 선형회귀 기울기도 함께 제공한다. 서로 다른 변수를 합산한 종합점수는 만들지 않는다. 순위는 해당 지표의 관찰된 변화량 비교일 뿐 도시 전체의 기후위험도 또는 피해 심각도 순위가 아니다.

### 도시 비교표 컬럼

`output/tables/city_temperature_trends_1981_2025.csv`의 모든 기온값은 T2M 기준이다.

| 컬럼 | 의미와 계산 방법 | 단위 |
|---|---|---|
| `city` | `locations.json`의 도시 이름 | - |
| `latitude` | 분석 지점 위도 | decimal degrees |
| `longitude` | 분석 지점 경도 | decimal degrees |
| `mean_temperature` | 1981-2025의 45개 연평균 T2M 산술평균 | °C |
| `first_10yr_mean` | 1981-1990 연평균 T2M의 산술평균 | °C |
| `last_10yr_mean` | 2016-2025 연평균 T2M의 산술평균 | °C |
| `temperature_difference` | `last_10yr_mean - first_10yr_mean` | °C |
| `trend_per_decade` | 연평균 T2M 선형회귀 기울기 × 10 | °C/10년 |
| `min_annual_temperature` | 45개 연평균 T2M 중 최솟값 | °C |
| `max_annual_temperature` | 45개 연평균 T2M 중 최댓값 | °C |

## 데이터 검증

각 도시마다 다음을 분석 전에 검사한다.

- 시작일 1981-01-01, 종료일 2025-12-31, 16,436행
- 7개 기후변수 컬럼 존재 여부와 숫자형 변환 가능 여부
- 변수별 `-999` fill value, 처리 후 결측치 수
- 중복 날짜 수
- 보수적 점검 범위 밖 값의 수: 기온 `-90~70 °C`, 강수 `0~2,000 mm/day`, 상대습도 `0~100%`, 풍속 `0~150 m/s`, 일사 `0~50 kW-hr/m²/day`

날짜·행 수·필수 컬럼이 잘못된 climate raw 캐시는 사용하지 않고 해당 도시만 다시 다운로드한다. raw 원본은 수정하지 않는다. processed 단계에서 `-999`와 보수적 범위 밖 값만 `NaN`으로 바꾸고, 결측치는 pandas 집계에서 제외한다. 검증 결과는 기존 기온용 `output/tables/city_data_validation_1981_2025.csv`와 4단계용 `output/tables/data_quality_summary.csv`에 각각 저장한다.

실제 2026-09-01 실행에서는 8개 도시 모두 날짜 16,436개, 중복 0개였고 기온·강수·습도·풍속에는 결측이나 범위 밖 값이 없었다. `ALLSKY_SFC_SW_DWN`은 NASA 응답에서 1981-01-01~1983-12-31의 1,095일이 `-999`였으므로 이를 보간하지 않았다. 이에 따라 일사 연평균과 추세는 실제 유효한 1984~2025 자료를 사용하고, `city_climate_annual_1981_2025.csv`의 1981~1983 일사 셀은 비어 있다. 과거 1981~1990 일사 비교값도 그 기간 안의 유효 연도인 1984~1990 평균이다.

## 프로젝트 구조

```text
NASA_POWER_Korea_Climate_Explorer/
├── AGENTS.md
├── README.md
├── requirements.txt
├── config/
│   ├── locations.json
│   └── kma_stations.json   # 공식 ASOS 관측소와 기간별 연결 규칙
├── data/
│   ├── raw/                 # 도시별 NASA 원본 CSV
│   ├── processed/           # 도시별 NASA 정제 CSV
│   ├── kma_raw/             # 도시별 ASOS 원본 CSV
│   └── kma_processed/       # 도시별 ASOS 공통-schema CSV
├── output/
│   ├── charts/validation/   # NASA-KMA 비교 PNG
│   ├── tables/
│   ├── validation/matched/  # 도시별 날짜 inner-join CSV
│   └── reports/
├── dashboard/
│   ├── data_loader.py      # st.cache_data 기반 read-only CSV loader
│   ├── filters.py          # 도시·변수·연도·계절·FDR filter
│   ├── charts.py           # 재사용 가능한 Plotly chart builders
│   ├── components.py       # 표·다운로드·오류·주의문 UI
│   ├── formatting.py       # 도시·변수 표시명과 단위
│   └── pages/              # 8개 dashboard page renderer
├── src/
│   ├── config.py
│   ├── nasa_power.py
│   ├── preprocess.py
│   ├── analysis.py
│   ├── city_analysis.py     # 재사용 가능한 다도시 workflow
│   ├── climate_analysis.py  # 다도시·다변수 수집, 검증, 결과 결합
│   ├── climate_indices.py   # 기후통계, threshold proxy, 기간 비교
│   ├── climatology.py       # 1991-2020 normal, anomaly, 계절 집계
│   ├── statistical_analysis.py # MK, Sen slope, 자기상관, FDR
│   ├── stage5_analysis.py   # 5단계 표·검증 workflow
│   ├── kma_asos.py          # 인증·10년 chunk·pagination·retry·cache
│   ├── kma_preprocess.py    # ASOS 공통 schema와 품질 점검
│   ├── station_metadata.py  # 관측소 설정과 Haversine 거리
│   ├── validation.py        # 매칭·오차·상관·threshold·강수 검증
│   ├── kma_workflow.py      # KMA 전용 CLI workflow
│   ├── validation_visualization.py
│   └── visualization.py
├── tests/
│   ├── test_nasa_power.py
│   ├── test_analysis.py
│   ├── test_city_analysis.py
│   ├── test_climate_analysis.py
│   ├── test_climatology.py
│   ├── test_stage5_indices.py
│   ├── test_statistical_analysis.py
│   ├── test_dashboard.py
│   ├── test_kma_asos.py
│   ├── test_kma_preprocess.py
│   ├── test_station_metadata.py
│   └── test_validation.py
├── main.py                 # 분석 데이터 생성·갱신 CLI
└── streamlit_app.py        # st.Page/st.navigation router
```

## 설치 방법

Python 3.11 이상이 필요하다.

```bash
cd NASA_POWER_Korea_Climate_Explorer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

5단계는 `pymannkendall`을 original/Hamed-Rao MK의 검증된 구현으로, `statsmodels`를 Ljung-Box와 Benjamini-Hochberg FDR에 사용한다. SciPy는 기존 회귀 p-value와 Theil-Sen 95% slope confidence interval 계산에 사용한다. 6단계 UI는 `streamlit`, interactive chart는 `plotly`를 사용한다.

## 실행 방법

### 기본 실행: 기존 서울 workflow

인수 없이 실행하면 기존 1·2단계와 4단계 서울 종합 기후분석을 수행한다.

```bash
python main.py
```

### 특정 도시 분석

도시 이름은 대소문자를 구분하지 않는다.

```bash
python main.py --city Seoul
python main.py --city Busan
python main.py --city Jeju
```

### 전체 도시 분석

```bash
python main.py --all
```

`--all`은 기존 1~4단계 산출물을 유지하면서 5단계 종합 통계표와 그래프도 생성한다. 유효한 climate raw 캐시가 있으면 5단계 때문에 NASA POWER API를 다시 호출하지 않는다.

기본적으로 신규 NASA API 요청 사이에 1초 대기한다. 필요할 때 다음과 같이 늘릴 수 있다.

```bash
python main.py --all --request-interval 2
```

기존 1~3단계 기온 raw와 4단계 climate raw는 파일을 분리한다. 기간과 7개 변수가 완전한 도시별 climate raw CSV가 있으면 API를 다시 호출하지 않는다. 한 도시가 실패해도 앞서 성공한 raw·processed·통계 파일을 삭제하지 않으며, 다음 실행에서 성공한 도시의 raw 캐시를 재사용한다. 원본을 명시적으로 다시 받을 때만 `--force-download`를 사용한다.

```bash
python main.py --all --force-download
```

기존 서울 processed CSV로 2단계 결과만 다시 만들려면 다음을 사용한다.

```bash
python main.py --stage2-only
```

KMA workflow는 기존 NASA workflow와 분리되어 있다. 따라서 `python main.py`,
`--city`, `--all`은 KMA API를 호출하지 않는다. KMA 인증키 설정과 실행 방법은 아래
「NASA POWER × KMA ASOS Validation」 절을 따른다.

테스트 실행:

```bash
python -m pytest -q
```

## Streamlit Dashboard

분석 결과를 먼저 준비한 다음 로컬 dashboard를 실행한다.

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py --all
streamlit run streamlit_app.py
```

브라우저를 열지 않는 startup 검증은 다음처럼 실행할 수 있다.

```bash
streamlit run streamlit_app.py --server.headless true
```

대시보드는 다음 8개 페이지를 제공한다.

1. **종합현황**: 분석기간·도시·지표별 최대 Sen slope, 도시 위치, T2M, 최근 anomaly, FDR heatmap
2. **도시별 탐색**: 한 도시의 기온·강수·습도·풍속·일사·극한지표와 월 climatology
3. **기후변수 비교**: 변수·복수 도시·화면 표시기간별 시계열, 평균, Sen slope와 anomaly
4. **통계적 추세**: Linear regression, MK/Modified MK, Sen slope CI와 FDR filter
5. **극한·Anomaly**: 1991~2020 normal 대비 T2M anomaly, threshold와 consecutive-event proxy
6. **계절 분석**: DJF·MAM·JJA·SON의 도시·변수별 seasonal Sen slope
7. **데이터·방법론**: NASA POWER 변수 metadata, 데이터 품질, 계산 방법과 해석 주의점
8. **NASA–KMA 검증**: 도시·변수·기간·계절별 agreement 지표, 산점도, 연간 비교, 월·계절 오차

Dashboard가 직접 읽는 핵심 파일은 다음 `output/tables/` 결과다. 이 표들은 `main.py --all`이 도시별 `data/processed/{city}_climate_daily_1981_2025.csv`를 입력으로 생성한다.

- `city_climate_annual_1981_2025.csv`
- `city_climate_summary_1981_2025.csv`
- `city_monthly_climatology_1981_2025.csv`
- `city_climate_statistical_trends.csv`
- `city_climate_normals_1991_2020.csv`
- `city_climate_anomalies_1981_2025.csv`
- `city_seasonal_climate_trends_1981_2025.csv`
- `city_consecutive_climate_indices_1981_2025.csv`
- `city_climate_change_rankings.csv`
- `data_quality_summary.csv`

`streamlit_app.py`와 `dashboard/`는 `src.nasa_power` 또는 다운로드 workflow를 호출하지 않는 read-only 탐색 계층이다. CSV 읽기와 dashboard용 연간표 결합은 `st.cache_data`로 캐시하므로 widget rerun 때 파일을 불필요하게 다시 읽지 않는다. 현재 filter가 적용된 표는 `st.download_button`으로 별도 CSV 다운로드가 가능하며 프로젝트 원본·processed·output 파일을 수정하지 않는다.

데이터를 갱신하려면 dashboard를 종료하고 `python main.py --all`을 실행한 뒤 Streamlit의 캐시를 지우거나 앱을 재시작한다. `main.py`는 NASA POWER 자료 수집·정제·분석 결과 생성 역할을 계속 담당하고, dashboard는 그 결과를 표시한다. 필터의 연도 범위는 화면상의 exploratory visualization에만 적용되며 기존 공식 1981~2025 추세, 1991~2020 normal, FDR 결과를 다시 정의하지 않는다. 입력 CSV가 없거나 비어 있거나 필수 컬럼이 없으면 앱은 `python main.py --all` 실행 안내를 표시한다.

`ALLSKY_SFC_SW_DWN`의 1981~1983 NASA fill value `-999`는 processed 단계에서 `NaN`으로 유지한다. Dashboard에서도 이를 0으로 바꾸지 않으며 일사 추세의 유효기간이 1984~2025임을 안내한다.

## 도시 추가 방법

`config/locations.json`에 고유한 소문자 키와 이름·위도·경도를 추가하면 된다. 다운로드, 정제, 연간 분석과 전체 비교 코드는 복사할 필요가 없다.

```json
"new_city": {
  "name": "New City",
  "latitude": 36.0000,
  "longitude": 128.0000
}
```

추가 후 `python main.py --city "New City"` 또는 `python main.py --all`을 실행한다.

## 생성되는 결과물

### 도시별 데이터와 통계

각 도시 키를 `{city}`라고 할 때 다음 파일을 생성한다.

- `data/raw/{city}_power_daily_1981_2025.csv`
- `data/processed/{city}_temperature_daily_1981_2025.csv`
- `output/tables/{city}_temperature_annual_1981_2025.csv`
- `output/tables/{city}_temperature_annual_trends_1981_2025.csv`
- `output/tables/{city}_temperature_linear_trend_summary_1981_2025.csv`

서울의 기존 1·2단계 월별 표, 장기추세 보고서와 그래프도 계속 생성된다.

### 도시 비교 결과

- `output/tables/city_temperature_trends_1981_2025.csv`: 도시별 대표 통계와 추세
- `output/tables/city_data_validation_1981_2025.csv`: 도시별 데이터 품질 검증
- `output/charts/city_annual_temperature_comparison.png`: 8개 도시 연평균 T2M 시계열
- `output/charts/city_temperature_trend_per_decade.png`: 도시별 °C/10년 추세
- `output/charts/city_recent_vs_past_temperature.png`: 1981-1990과 2016-2025 비교
- `output/charts/city_temperature_heatmap.png`: 도시×연도 연평균 T2M heatmap

### 4단계 도시별 기후 데이터

기존 1~3단계 파일은 그대로 유지하고, 도시 키를 `{city}`라고 할 때 별도 파일을 생성한다.

- `data/raw/{city}_power_daily_climate_1981_2025.csv`: `DATE`와 NASA POWER 7개 변수 원본
- `data/processed/{city}_climate_daily_1981_2025.csv`: 날짜 파생 컬럼 및 결측 처리를 적용한 분석용 자료
- `output/tables/{city}_climate_annual_1981_2025.csv`: 45개 연도의 기본 통계·이동평균·threshold proxy
- `output/tables/{city}_climate_monthly_1981_2025.csv`: 12개월 climatology
- `output/tables/{city}_climate_summary_1981_2025.csv`: 13개 연간 metric의 회귀 slope·10년당 추세·R²·p-value

### 4단계 종합 tables

- `output/tables/city_climate_annual_1981_2025.csv`: 8개 도시 × 45개 연도, 360행 long-format 연간표
- `output/tables/city_climate_summary_1981_2025.csv`: 도시별 평균·추세·R²·p-value
- `output/tables/city_monthly_climatology_1981_2025.csv`: 8개 도시 × 12개월, 96행 climatology
- `output/tables/city_climate_past_vs_recent.csv`: 도시별 13개 변수·proxy의 과거/최근 비교
- `output/tables/data_quality_summary.csv`: 날짜, 행 수, 중복, 변수별 결측·fill·범위 밖 값
- `output/tables/nasa_power_climate_parameter_metadata.csv`: 분석에 사용한 7개 변수 metadata

### 4단계 charts

- `output/charts/city_temperature_trends.png`: 8개 도시 연평균기온
- `output/charts/city_precipitation_trends.png`: 8개 도시 연간 누적 강수량
- `output/charts/city_humidity_trends.png`: 8개 도시 연평균 상대습도
- `output/charts/city_wind_trends.png`: 8개 도시 연평균 풍속
- `output/charts/city_solar_trends.png`: 8개 도시 연평균 일별 일사량
- `output/charts/city_hot_days_ge_33.png`: 연도별 33 °C threshold heat-day proxy
- `output/charts/city_warm_nights_ge_25.png`: 연도별 25 °C minimum-temperature warm-night proxy
- `output/charts/city_climate_trend_heatmap.png`: 변수 안에서 표준화한 도시별 장기추세 heatmap

### 5단계 statistical tables

- `output/tables/city_climate_statistical_trends.csv`: 8개 도시 × 17개 metric의 선형·MK·자기상관·modified MK·Sen·FDR 결과 136행
- `output/tables/city_climate_normals_1991_2020.csv`: 도시별 annual 8행과 monthly 96행의 normal 및 표준편차
- `output/tables/city_climate_anomalies_1981_2025.csv`: 8개 도시 × 45년의 absolute·standardized anomaly 360행
- `output/tables/city_seasonal_climate_trends_1981_2025.csv`: 8개 도시 × 4계절 × 5변수의 계절 추세 160행
- `output/tables/city_consecutive_climate_indices_1981_2025.csv`: 네 연속일수 proxy의 도시·연도별 결과 360행
- `output/tables/city_climate_change_rankings.csv`: 서로 합산하지 않은 10개 변수별 도시 순위 80행
- `output/tables/busan_jeju_warm_night_validation.csv`: 원자료·연도별 재계산·추세를 포함한 부산·제주 검증 90행

### 5단계 charts

- `output/charts/city_temperature_anomaly_1991_2020.png`: 도시별 연평균 T2M anomaly
- `output/charts/city_temperature_anomaly_heatmap.png`: 도시×연도 T2M anomaly
- `output/charts/city_sen_slope_temperature.png`: T2M Sen slope와 95% CI
- `output/charts/city_extreme_heat_sen_slope.png`: 33 °C threshold-day proxy Sen slope와 95% CI
- `output/charts/city_warm_night_sen_slope.png`: 25 °C minimum-temperature proxy Sen slope와 95% CI
- `output/charts/city_seasonal_temperature_trends.png`: 도시·계절별 T2M Sen slope
- `output/charts/city_seasonal_trend_heatmap.png`: 실제 °C/10년 단위의 도시×계절 T2M Sen slope
- `output/charts/city_climate_significance_heatmap.png`: FDR 유의 증가·감소·비유의 범주

## NASA POWER × KMA ASOS Validation

### 목적과 공식 데이터 소스

7단계는 NASA POWER 격자자료와 한 지점의 KMA ASOS 관측값 사이의 agreement,
systematic difference와 계절별 오차를 정량화한다. 두 자료의 공간대표성과 생산 방식이
다르므로 결과를 NASA POWER의 단순한 “정확도” 판정으로 사용하지 않는다.

KMA 자료는 공공데이터포털의 공식
[기상청 지상(종관, ASOS) 일자료 조회서비스](https://www.data.go.kr/data/15059093/openapi.do?recommendDataYn=Y)를
사용한다.

- endpoint: `https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList`
- 고정 요청값: `dataCd=ASOS`, `dateCd=DAY`, `dataType=JSON`
- 기간·지점값: `startDt`, `endDt`, `stnIds`
- pagination: `pageNo`, `numOfRows=999`, 응답 `totalCount`까지 반복
- 공식 1회 최대 10년 범위에 맞춰 1981~1990, 1991~2000, 2001~2010,
  2011~2020, 2021~2025로 나눈다.
- HTTP 429·5xx, timeout, 연결 실패와 API 결과코드 05·22·23은 제한된 횟수로
  지수형 재시도한다. 이미 검증된 도시 raw 캐시는 재사용한다.

ASOS 관측소 좌표·개시일은 KMA
[관측지점정보](https://data.kma.go.kr/tmeta/stn/selectStnList.do)를 기준으로
`config/kma_stations.json`에 기록한다. NASA point와 관측소 사이 거리는 WGS84 좌표의
Haversine 대권거리이며 거리가 크다는 이유로 도시를 임의 제외하지 않는다.

| 도시 | ASOS | 관측 개시일 | NASA point 거리 | primary 사용기간 |
|---|---|---|---:|---|
| Seoul | Seoul (108) | 1907-10-01 | 1.21 km | 1981-2025 |
| Busan | Busan (159) | 1904-04-09 | 9.22 km | 1981-2025 |
| Daejeon | Daejeon (133) | 1968-12-19 | 2.65 km | 1981-2025 |
| Daegu | Daegu (143) | 1907-01-31 | 4.70 km | 1981-2025 |
| Gwangju | Gwangju (156) | 1939-05-01 | 3.84 km | 1981-2025 |
| Gangneung | Gangneung (105) | 1911-10-03 | 1.31 km | 1981-2025 |
| Gangneung 보조 | Bukgangneung (104) | 2008-07-28 | 6.13 km | overlap 비교만 수행 |
| Jeju | Jeju (184) | 1923-05-01 | 1.62 km | 1981-2025 |
| Jeonju | Jeonju (146) | 1918-06-23 | 3.34 km | 1981-2025 |

KMA 전국 기온 통계의 강원영동 지점은 강릉(105)이므로 105를 1981~2025 primary
시계열로 사용한다. 북강릉(104)은 2008-07-28 이후 겹치는 기간의 continuity 분석용으로만
추가 다운로드하며 105와 임의로 이어 붙이지 않는다. KMA 지침의 “지리적 균질성을 위한
강릉(105) 연계 허용” 안내와 두 관측소 metadata는 설정의 `mapping_note`와 결과표에
기록한다. 겹치는 평균기온 pair는 `gangneung_station_continuity_validation.csv`에서
104-105 bias, MAE, RMSE와 상관을 별도로 제시한다.

### 변수·단위·정제

| 비교 metric | NASA POWER | KMA ASOS 공식 응답 필드 | 공통 단위 |
|---|---|---|---|
| 평균기온 | `T2M` | `avgTa` | °C |
| 최고기온 | `T2M_MAX` | `maxTa` | °C |
| 최저기온 | `T2M_MIN` | `minTa` | °C |
| 강수량 | `PRECTOTCORR` | `sumRn` | mm/day |
| 상대습도 | `RH2M` | `avgRhm` | % (bias는 percentage points) |
| 풍속 | `WS10M` | `avgWs` | m/s |
| 일사량 | `ALLSKY_SFC_SW_DWN` | `sumGsr` | kWh/m²/day |

KMA `sumGsr`의 공식 일사합 단위 MJ/m²/day는 `kWh/m²/day = MJ/m²/day / 3.6`으로
변환한다. API의 빈 문자열과 JSON null은 processed에서 `NaN`으로 유지하고 보간하지
않는다. 관측 강수 `0`은 유효한 0 mm이며 결측값과 구분한다. 확인되지 않은 음수 코드를
임의로 결측 처리하지 않고, 보수적 물리 범위 밖 값은 품질표에서 `suspicious_*` 개수로만
기록해 실제 관측행을 자동 삭제하지 않는다. API 원본 필드값은 `data/kma_raw/`에서 바꾸지
않고 요청·관측소 provenance 컬럼만 덧붙인다.

### ASOS 강수 공란 조사 (2026-09-03)

**판정: 강수 공란 의미 미확정.** `sumRn` 공란을 무강수로 일괄 변환하지 않았다.
현재 품질표의 `missing_precipitation`은 **사용 가능한 수치가 없는 행 수**이며,
실제 강수 관측장애 일수로 확정한 값이 아니다. 이 구분이 해결되기 전에는 강수
agreement 지표를 전체 날씨에 대한 검증 성능으로 해석하지 않는다.

공식 근거를 확인한 범위는 다음과 같다.

- [공공데이터포털 ASOS 일자료 명세](https://www.data.go.kr/data/15059093/openapi.do)는
  `sumRn`을 일강수량으로 정의하지만, 공개 응답항목 표에는 빈 문자열/JSON null을
  무강수와 실제 관측누락으로 구분하는 규칙이 없다.
- [기상자료개방포털 FAQ 2페이지의 「강수량 관측」](https://data.kma.go.kr/community/board/selectBoardList.do?bbrdTypeNo=3&pgmNo=95&pageIndex=2)은
  종관기상관측의 무강수를 0, 결측을 NULL로 설명한다. 이 일반 설명만으로 일자료 API의
  모든 빈 문자열이 무강수라고 판단할 수는 없다.
- [지상기상관측지침(2026.3), 본문 35쪽·161~162쪽](https://data.kma.go.kr/resources/images/publication/지상기상관측지침%282026.3.%29.pdf)은
  고체 강수도 녹인 물의 깊이로 강수량에 포함하고, 강수계속시간은 강수유무센서를
  참고하여 산출한다고 설명한다. `n99Rn`은 09~09시 누적량으로 `sumRn`과 같은
  일계라고 가정하거나 대체값으로 사용하지 않는다.
- [기상관측데이터 품질·통계 관리 지침(2025.9), 본문 24~25쪽](https://data.kma.go.kr/resources/images/publication/기상관측데이터%20품질%20통계%20관리%20지침%282025.9%29.pdf)은
  일정한 관측자료 누락 시 합계값을 미산출하도록 한다(극값 수준 현상에는 예외가 있다).
  기온·습도의 일평균이 존재해도 강수 일합계가 유효하다는 보장은 아니다.

서울 원본 1981-01-01~2025-12-31의 16,436행 중 `sumRn` 공란은 10,005행(60.8725%),
명시적 숫자 0은 1,538행이다. 공란인 날에도 평균기온과 평균습도는 모두 존재하고,
평균풍속은 10,002행에 존재한다. 날짜 누락은 0일이다.

서울(108)에 대해 소규모 실제 API 요청 3건을 수행했다(2020-01-01~07,
2023-11-28~29, 2025-05-14). 모두 HTTP 200 / `resultCode=00` / `NORMAL_SERVICE`이며
아래 값이 원본 캐시와 일치했다. 인증키는 출력하거나 기록하지 않았다.

| 날짜 | API `sumRn` | 관련 관측 | 해석 |
|---|---|---|---|
| 2020-01-03 | 빈 문자열 | 평균운량 0.0, 일조 8.8시간, 박무·연무 기록 | 맑은/무강수 후보이나 강수 공란의 의미를 단독 확정할 수 없음 |
| 2020-01-07 | 46.3 mm | 강수계속시간 24.0시간, 비 기록 | 강수량이 명시된 강수일 |
| 2023-11-28 | 빈 문자열 | 눈 15:50~16:10, 강수계속시간 0.0 | 공란이 강수현상 부재를 뜻하지 않는 사례 |
| 2023-11-29 | 빈 문자열 | 눈 기록 2회, 강수계속시간 0.0 | 공란이 강수현상 부재를 뜻하지 않는 사례 |
| 2025-05-14 | 빈 문자열 | 비 23:10~23:40, 강수계속시간 0.5 | 강수량 누락인지 미량강수 표기인지 추가 확인 필요 |

공란과 비·눈 기록이 함께 있는 날은 총 3일이다. 나머지 날에도 강수센서 정상 여부를
보증하는 일별 플래그가 없으므로, 일기현상이 비어 있거나 다른 관측값이 있다는 이유로
무강수를 확정하지 않는다. 강수계속시간 0.0도 위 눈 사례 때문에 단독 판정에 쓰지 않는다.

서울 공란률은 1981~1990 59.995%, 1991~2000 62.278%, 2001~2010 61.528%,
2011~2020 61.347%, 2021~2025 57.558%다. 특정 시기만의 장기 관측중단 패턴은 아니지만,
이 비율만으로 관측장비·표기 방식의 변경 여부나 원인을 확정할 수는 없다.

따라서 명시적 강수값과 0을 유지하고 공란/null은 `NaN`으로 남긴다. raw, processed와
기존 validation 결과는 다시 쓰지 않았다. 서울 기존 강수 지표는 `n_pairs=6431`,
Bias=-1.329883, MAE=5.426618, RMSE=13.730209 mm/day, Pearson=0.809256,
Spearman=0.777762, POD=0.897585, FAR=0.230916, CSI=0.707040이며 **수치가 있는 날짜만의
결과**다. 무강수일이 제외되어 있을 가능성이 있으므로 표본 선택에 따른 편향에 주의한다.

일괄 재생성 전에 제공기관에 `AsosDalyInfoService/getWthrDataList`의 `sumRn=""`와
JSON null에 대한 무강수·미량강수·합계 미산출 구분, 적용기간, 확인 가능한 QC 필드를
문의해야 한다. 특히 위 3개 날짜를 함께 제시하면 구분 규칙을 확인하는 데 도움이 된다.
현재는 근거 없는 `blank → 0` 테스트 대신 공란 보존, 명시적 0·강수값 보존,
`>= 1 mm/day` 경계와 결측 제외 후 POD/FAR/CSI 계산을 회귀 테스트로 확인한다.

### 계산 방법

NASA와 KMA 자료는 도시별 `date` one-to-one inner join을 수행한다. 한 변수가 결측인
날짜는 그 변수의 pair에서만 제외하므로 metric마다 `n_pairs`가 다를 수 있다.

- `difference = NASA - KMA`
- `bias = mean(difference)`
- `MAE = mean(abs(difference))`
- `RMSE = sqrt(mean(difference²))`
- Pearson `r`과 Spearman `rho`는 유효 pair로 계산하고 각 양측 p-value를 함께 저장한다.
- `normalized_rmse = RMSE / abs(KMA mean)`이며 KMA 평균 절댓값이 `1e-12` 이하이면
  정의하지 않고 `NaN`으로 둔다. 단위가 다른 변수의 raw RMSE를 종합점수로 합치지 않는다.

월별 결과는 1~12월, 계절 결과는 `DJF`, `MAM`, `JJA`, `SON`으로 집계한다. 날짜에는
기존 5단계와 같이 12월을 다음 `season_year`로 배정하며, 전체 계절 agreement 표는 계절별
모든 유효 daily pair를 사용한다. 연도별 bias는 T2M·T2M_MAX·T2M_MIN·PRECTOTCORR에
대해 계산한다. correlation p-value는 긴 daily 표본에서 매우 작아질 수 있으므로
Bias·MAE·RMSE와 correlation 크기를 함께 본다.

극값 비교는 양쪽 일자료에 정확히 같은 `Tmax >= 30 °C`, `Tmax >= 33 °C`,
`Tmin >= 25 °C` 기준을 적용해 연도별 `NASA count`, `KMA count`, `difference`를 만든다.
KMA 기반 count도 본 프로젝트의 재계산값이며 KMA 공식 발표 통계와 같다고 단정하지 않는다.

강수 wet day는 양쪽 모두 `>= 1 mm/day`인 경우 hit, KMA만 wet이면 miss, NASA만 wet이면
false alarm, 둘 다 dry이면 correct negative다.

- `POD = hit / (hit + miss)`
- `FAR = false alarm / (hit + false alarm)`
- `CSI = hit / (hit + miss + false alarm)`

분모가 0이면 해당 값은 `NaN`이다. 강수는 국지성, 지형과 격자 해상도의 영향을 크게
받으므로 낮은 상관이나 큰 RMSE를 곧바로 NASA 자료의 오류로 해석하지 않는다.

### API key와 실행

공공데이터포털에서 받은 일반 인증키의 디코딩 값을 저장소 밖 환경변수로 설정한다.
`.env`와 `.env.local`은 Git에서 제외되며 `.env.example`에는 예시 이름만 있다.

```bash
export KMA_API_KEY="YOUR_KEY"

# 특정 도시 전체 validation
python main.py --validate-kma --city Seoul

# 8개 도시 전체 validation
python main.py --validate-kma --all

# ASOS raw만 다운로드/캐시 확인
python main.py --download-kma --all
```

`.env` 파일을 쓰려면 `.env.example`을 복사해 실제 값을 넣은 뒤 실행 shell에서
`set -a; source .env; set +a`로 환경변수를 불러온다. 키 값은 source, README, test와
log에 출력하지 않는다. 키가 없으면 KMA workflow만 친절한 안내와 함께 건너뛰고 기존
NASA CLI와 dashboard는 정상 동작한다.

### 생성 결과

인증키를 설정해 실제 workflow를 실행하면 기존 NASA 결과를 수정하지 않고 다음을 만든다.

- `data/kma_raw/{city}_asos_daily_1981_2025.csv`
- `data/kma_processed/{city}_asos_daily_1981_2025.csv`
- `output/validation/matched/{city}_nasa_kma_daily_1981_2025.csv`
- `output/tables/kma_station_metadata.csv`
- `output/tables/nasa_kma_station_mapping.csv`
- `output/tables/kma_data_quality_summary.csv`
- `output/tables/nasa_kma_validation_metrics.csv`
- `output/tables/nasa_kma_monthly_validation.csv`
- `output/tables/nasa_kma_seasonal_validation.csv`
- `output/tables/nasa_kma_annual_bias_1981_2025.csv`
- `output/tables/nasa_kma_threshold_validation.csv`
- `output/tables/nasa_kma_precipitation_contingency.csv`
- `output/tables/gangneung_station_continuity_validation.csv`
- `output/charts/validation/`: T2M scatter·bias·RMSE, 강수 비교, correlation 및 normalized-RMSE
  heatmap, T2M Bland–Altman, 도시별 연평균 T2M 비교

Streamlit의 8번째 **NASA–KMA 검증** 페이지는 이 저장 결과만 읽으며 API를 호출하지
않는다. 도시·변수·기간·계절 filter, 지표 카드, 1:1 scatter, 연간 비교, 월별 bias,
계절별 RMSE, 도시×변수 상관 heatmap과 필터 결과 CSV 다운로드를 제공한다. 결과가 없으면
`python main.py --validate-kma --all` 안내를 표시한다.

## Automated Climate Reports

8단계는 **이미 저장된 1~7단계 분석 CSV를 연구보고서로 정리**하는 기능이다.
새로운 통계모형·지표·예측·위험도 점수를 만들지 않으며 LLM이나 외부 API를 사용하지 않는다.
도시별 14개 본문 section과 8개 도시 비교보고서의 19개 section에 방법, 표, PNG 차트,
규칙 기반 해석, 데이터 품질, 한계와 출처를 포함한다. 생성 시각과 분석기간은 구분해서 표시한다.

### 설치 및 실행

기존 Python 3.11+ 가상환경에서 의존성을 설치한다. 보고서용으로 Jinja2가 추가되었다.

```bash
python -m pip install -r requirements.txt

# 서울 보고서
python main.py --report --city Seoul

# 8개 도시 보고서 + 종합 비교보고서
python main.py --report --all

# 종합 비교보고서만
python main.py --report-comparison

# 전체 테스트 / 기존 대시보드 실행
python -m pytest -q
streamlit run streamlit_app.py
```

지원 도시는 Seoul, Busan, Daejeon, Daegu, Gwangju, Gangneung, Jeju, Jeonju다.
보고서 모드는 데이터 다운로드 옵션과 혼용하지 않는다. `--report`에는 `--city` 또는
`--all`이 필요하다. 기존 `python main.py --city Seoul`, `python main.py --all`,
`--validate-kma`, `--download-kma`의 동작은 유지하며 **일반 `--all`은 보고서를 생성하지 않는다.**

### 입력과 생성 구조

```text
reporting/
├── data_provider.py       # CSV 스키마 검사, source-addressable Fact Layer
├── formatters.py          # 표·문장 숫자 표시 규칙
├── narrative.py           # 규칙 기반 한국어 문장, 필수 caveat
├── charts.py              # 기존 결과의 정적 PNG 표현
├── report_builder.py      # 공유 본문 구성 및 HTML/Markdown 렌더링
├── validation.py          # 출처 일치, 파일, 문장, 이미지 검증
├── templates/            # 도시/비교 HTML·Markdown Jinja2 템플릿
└── static/report.css      # 화면·인쇄 CSS

output/reports/
├── cities/{city}_climate_report.html
├── cities/{city}_climate_report.md
├── korea_8city_climate_comparison_report.html
├── korea_8city_climate_comparison_report.md
├── manifests/{city}_report_manifest.json
├── manifests/korea_8city_report_manifest.json
├── assets/{city}/*.png
└── assets/comparison/*.png
```

입력은 다음 **기존 output CSV만** 읽는다. `data/raw`, `data/processed`, KMA raw/processed는
보고서의 입력도 출력도 아니다. 기존 분석 CSV와 기존 차트는 덮어쓰지 않는다.

- `city_climate_annual_1981_2025.csv`, `city_climate_summary_1981_2025.csv`,
  `city_monthly_climatology_1981_2025.csv`, `city_climate_past_vs_recent.csv`
- `city_climate_statistical_trends.csv`, `city_climate_normals_1991_2020.csv`,
  `city_climate_anomalies_1981_2025.csv`, `city_seasonal_climate_trends_1981_2025.csv`,
  `city_climate_change_rankings.csv`, `city_consecutive_climate_indices_1981_2025.csv`
- `nasa_kma_validation_metrics.csv`, `nasa_kma_monthly_validation.csv`,
  `nasa_kma_seasonal_validation.csv`, `nasa_kma_annual_bias_1981_2025.csv`,
  `nasa_kma_threshold_validation.csv`, `nasa_kma_precipitation_contingency.csv`
- `kma_data_quality_summary.csv`, `data_quality_summary.csv`,
  `nasa_kma_station_mapping.csv`, `nasa_power_climate_parameter_metadata.csv`,
  `gangneung_station_continuity_validation.csv`(강릉 및 비교보고서)
- `output/validation/matched/{city}_nasa_kma_daily_1981_2025.csv`
  (기존 T2M scatter·NASA/KMA 연간 비교 그래프 재사용용)

목록에서 경로가 생략된 파일은 `output/tables/` 아래다. 필수 파일, 도시 행, 필수 컬럼이
없거나 row key가 중복이면 생성을 중단하고 `python main.py --all` 또는
`python main.py --validate-kma --all` 등의 선행 명령을 안내한다. **보고서가 그 명령이나
API를 자동 실행하지는 않는다.** 최신 자료가 필요하면 사용자가 선행 workflow를 먼저
완료한 후 보고서를 다시 생성한다.

### Fact Layer 및 숫자 출처

CSV는 data provider에서 한 번 로딩해 `ReportFacts`로 전달한다. 각 scalar에는 원래 값,
`source_file`, `row_key`, `column`을 저장하고 표에는 원본 CSV 행번호와 컬럼을 보존한다.
문장·표·차트는 이 공통 입력을 사용한다. 보고서 manifest에는 다음이 기록된다.

- 생성시점(UTC), HTML·Markdown 경로, engine, API 호출 없음
- 입력 파일별 SHA-256, 파일 수정시점(UTC), 행 수
- 도시별 핵심 지표의 값과 정확한 source cell 주소
- 표의 원본 CSV 행번호(헤더가 1행)·row key 컬럼·표시 가능한 컬럼
- 차트 경로·SHA-256·입력 파일·표현 방법, 생성 코드/템플릿/CSS의 SHA-256
- 숫자 출처 대조 및 렌더링 품질검사 결과

입력 수정시점은 **파일의 mtime**이지 관측일이나 분석 완료일을 보증하지 않는다.
Fact Layer의 모든 값·표를 CSV와 대조하고, 렌더링된 핵심 KPI를 다시 검사한다.
생성 도중 CSV 내용이 바뀌면 배포를 중단한다. 임시 폴더에서 검증이 끝난 파일만 같은
이름의 보고서로 교체하며 입력 파일은 그대로 둔다. 같은 입력과 같은 생성시각을 지정하면
본문은 동일하다(실제 CLI 재실행은 생성시각이 달라진다).

### 계산 및 자동 문장 규칙

Linear Regression, MK, Modified MK, Sen's slope·95% CI, FDR, normal, anomaly,
validation metric은 **기존 계산값을 표시**한다. 표시는 주로 소수 둘째 자리,
기울기·상관·POD/FAR/CSI는 셋째 자리, p/q는 유효숫자 3자리, 날짜·pair 수는 정수다.
원래 CSV 정밀도는 바꾸지 않는다. `None`·비유한 값은 `자료 없음`으로 표시하고 0은
그대로 구분한다. IEEE 음의 0은 표시에서만 `0.000` 등으로 정규화한다.

- 기온 추세: °C/10년. 연간 강수합 추세: (mm/년)/10년.
- 상대습도 평균: %, 변화량: percentage points/10년. 풍속: (m/s)/10년.
- 일사: (kWh/m²/day)/10년. 연간 threshold count: (일/년)/10년.
  최장 연속일수: 일/10년. 추세표의 CI도 동일한 10년당 단위다.
- 최근 anomaly는 **마지막 분석연도 2025**의 1991–2020 normal 대비 값이며,
  최근 10년 평균과 다르다. 이동평균의 초기 부족 창은 채우지 않는다.
- 증가/감소와 FDR 유의/비유의를 분리한다. Sen 기울기가 0이어도
  `기후변화가 없다`고 결론 내리지 않고 MK 기반 FDR 판정을 별도로 설명한다.
- Pearson r ≥0.9일 때 높은 시간적 일치도로 서술하되 Bias·RMSE를 함께 보여준다.
  이는 문장 선택 기준이지 정확도 등급이나 백분율이 아니다.
- threshold는 저장된 연도별 NASA−KMA 차이에서 최대 절대차 행을 선택한다.
  |차이| ≥10일은 검토용 강조 기준으로, 통계적 유의성·위험도 판정이 아니다.
  부산·제주 warm-night 차이를 포함해 원인을 자동 추정하지 않는다.
- 도시 순위는 기존 지표별 ranking을 사용한다. 종합 위험도 점수나 새 순위를 만들지 않는다.

차트는 도시별 9장(기온·이동평균, anomaly, 월별 climatology, threshold proxy,
계절별 T2M Sen/CI, NASA–KMA scatter·연간 비교, 변수별 correlation, 연간 강수량)과
비교 9장(기온/33°C/warm-night 추세, Bias, RMSE, anomaly/계절 heatmap, 품질, 좌표도)이다.
T2M 연간 NASA–KMA 차트만 기존 7단계 시각화 함수를 그대로 재사용해 저장된 matched
일자료의 유효 T2M pair를 연도별 평균으로 표시한다. 새 분석모형이나 지표를 저장하지 않는다.
지도는 저장된 좌표의 위치도이며 행정경계·공간 보간·외부 지도 API를 사용하지 않는다.

### 필수 주의사항

KMA ASOS 일강수량 API의 공란 의미가 무강수와 실제 미산출을 완전히 구분할 수 없어,
NASA–KMA 강수 검증은 양쪽 자료에 유효한 강수 수치가 존재하는 날짜에 한정하였다.
POD/FAR/CSI도 같은 범위이며, 공란을 0으로 바꾸지 않는다. 공란/NaN 개수를
`실제 관측누락률`로 단정하지 않는다.

강릉 본 분석은 Gangneung 105이고 Bukgangneung 104는 중첩기간 continuity 비교다.
높은 상관을 이유로 두 관측소를 이어 붙이거나 동일 연속자료로 간주하지 않는다.
NASA 일사량 1981~1983 fill value는 그대로 결측이며 유효 추세기간 1984~2025를 명시한다.
분석용 threshold proxy는 기상청 공식 폭염일수·열대야 통계가 아니다.
상관은 정확도 백분율이 아니고, 유의성은 인과관계가 아니며, 과거 추세는 미래 예측이 아니다.

### 열람·공유와 검증

HTML은 CSS와 PNG를 내장하므로 **HTML 한 파일만 공유해도** 표·차트를 볼 수 있다.
Markdown은 `assets`를 상대경로로 참조하므로 폴더 구조를 유지해서 함께 공유한다.
출처 CSV 링크는 원래 프로젝트 폴더 구조에서 동작한다. API 인증키 없이 생성할 수 있으며,
보고서에는 인증키를 포함하지 않는다(안전 검사는 환경변수의 인증키와 일치하는 문자열도 차단한다).
한글은 시스템 글꼴과 대체 글꼴을 사용하고, PNG의 축·범례는 영문 표기를 사용해
특정 OS 글꼴에 의존하지 않는다. 화면 목차, 표 스크롤, A4 인쇄 CSS를 제공하며
PDF 생성은 이번 단계 범위에 포함하지 않는다.

Streamlit의 기존 8개 페이지는 유지하고 **기후보고서** 다운로드 페이지를 추가했다.
이 페이지는 이미 생성된 HTML/Markdown만 읽는다. 없으면 CLI 명령을 안내하고 자동 분석,
보고서 생성 또는 API 요청은 하지 않는다. 보고서 생성 후 페이지를 새로고침하면 반영된다.

`tests/test_reporting.py`는 로더, Fact mapping, 보수적 narrative, 두 템플릿, 필수 section,
미치환 placeholder, credential 노출 방지, NaN·0·표 서식, source consistency,
모든 도시 생성, 출력 경로, CLI 분기, 읽기 전용 Streamlit 페이지를 검증한다.
보고서 테스트는 네트워크 요청을 차단하고, 출력은 임시 폴더에 생성한다.

## 해석 시 주의점

- NASA POWER 자료는 NASA의 위성관측 및 모델 기반 격자형 기상·태양에너지 자료이며, 특정 지점의 지상 관측소 실측값과 동일하지 않을 수 있다.
- 도시 좌표 한 점의 값이 도시 전체의 공간 평균을 의미하지 않는다.
- `LST`는 한국 표준시(KST)가 아니라 경도 기반 Local Solar Time이다.
- 서로 다른 도시 좌표가 NASA POWER의 같은 격자에 속하면 값이 같거나 매우 유사할 수 있다.
- `trend_per_decade`와 전체기간 변화는 적합된 선형 추세이며 실제 첫해·마지막 해 값의 단순 차이가 아니다.
- NASA POWER 자료의 장기간 일관성, 격자 해상도, 위성·재분석 입력 및 자료처리 특성이 결과에 영향을 줄 수 있다.
- 일사량의 1981~1983 결측을 비롯해 결측이 있는 평균·추세는 명시된 전체 달력기간보다 유효 표본기간이 짧을 수 있다.
- `T2M_MAX >= 33 °C`, `T2M_MIN >= 25 °C` 등의 threshold 지표는 본 프로젝트의 장기 변화 분석용 proxy이며 대한민국 기상청의 공식 폭염일수 또는 열대야 통계와 동일한 지표로 간주하지 않는다.
- R², p-value와 선형 기울기만으로 원인 또는 인과관계를 판단할 수 없다. 다중검정·자기상관·비선형성까지 교정한 귀속분석이 아니다.
- FDR q-value는 다중검정의 false-discovery 비율을 제어하지만 개별 결과가 참이라는 확률이나 효과의 크기를 뜻하지 않는다.
- Hamed-Rao modified MK는 lag-1 자기상관 flag가 있는 series의 sensitivity 분석이며 모든 형태의 시간의존성·변화점·비선형성을 해결하지 않는다.
- 도시별 순위는 해당 Sen slope의 상대적 순서일 뿐 도시 전체 기후위험, 노출, 취약성 또는 적응역량을 평가하지 않는다.
