# Roadmap

## 현재 기준 — v1.0

**8-city validated version**

- 1981–2025 NASA POWER 7개 변수 분석
- 8개 KMA ASOS 관측소 교차검증
- 통계적 추세, normal/anomaly, 계절 및 proxy 분석
- 읽기 전용 대시보드, 자동 보고서, 테스트와 공개 준비 문서

v1.0에는 전국 ASOS 확대, 미래기후 시나리오, 기온 예측, 머신러닝을 포함하지 않는다.
아래 v1.1 기능은 stable 결과와 분리된 experimental namespace다.

## Phase B — 전국 ASOS 확장

### v1.1 — Nationwide station inventory & screening (experimental, 완료)

- 공식 ASOS metadata와 이력의 cache 가능한 inventory
- 전 station 소구간 availability probe와 metadata A/B 후보의 상세 일자료 검사
- 기온 completeness·장기 gap·continuity 기준의 보수적 A/B shortlist
- 지역·고도 요약, 제외 reason code, 재시작 state와 읽기 전용 station 지도

### v1.2 — Nationwide Tier-A climate trend (experimental, 완료)

- Final Tier A만 1981–2025 공통기간으로 NASA POWER × ASOS 수집·매칭
- TAVG/TMAX/TMIN station 추세, 1991–2020 anomaly, 계절, threshold proxy
- source×metric station family FDR, NASA–KMA validation, 지역·고도 탐색 요약
- interactive station map, read-only 전국 기후추세 dashboard, 전국 종합보고서
- Tier B 6개는 섞지 않고 후속 단계로 보류

### v1.3 — Nationwide spatial climate pattern (experimental, 완료)

- Stage-11 Final Tier A 결과만 읽는 API-free spatial master
- Haversine distance와 directed row-standardized KNN(k=4)
- 8개 metric Global Moran, 5개 metric Local Moran와 BH-FDR
- k=3/4/5 weight sensitivity, 위도·경도·고도 탐색 연관
- Tmax/Tmin contrast, DTR, 계절, threshold proxy, Bias/RMSE 공간패턴
- station point maps, 12번째 read-only dashboard page, deterministic report/manifest
- 신뢰 가능한 local coastline geometry가 없어 해안/내륙 비교는 보류

### v1.4 — Continuity 심화 및 해안거리

- manual review station의 공식 이력·overlap 근거 보강
- 관측소 밀도·해발·해안/도서 편향과 지역 weighting 검토
- 국립해양조사원 coastline SHP의 reproducible acquisition·checksum·CRS·geometry 검증
- 검증 완료 시 station-to-coast distance와 20/30/50 km sensitivity

### v1.5 — geospatial climate map 고도화

- 관측소 point와 격자값을 혼동하지 않는 지도 표현
- trend, uncertainty, coverage와 결측을 함께 표시
- 지도 투영과 경계자료 출처 문서화

### v1.6 — regional comparison 고도화

- 기후·행정 권역별 비교와 분포 요약
- 도시 평균의 단순 합산을 피하는 weighting·대표성 검토
- 대규모 결과의 dashboard/report 성능 최적화

## 예상 과제

| 과제 | 대응 방향 |
|---|---|
| station 수 증가 | metadata 기반 선별, incremental processing |
| 서로 다른 시작일 | 공통기간·가용기간 결과를 분리 |
| 관측소 이전 | 이력과 overlap 검증, 무근거 splice 금지 |
| 결측과 관측방식 변화 | 변수별 품질규칙과 provenance 기록 |
| station continuity | 단절·대체관측소를 명시적으로 모델링 |
| API 호출 한도 | cache, checkpoint, rate limit, 다음 실행 이어받기 |
| geospatial visualization | point/grid 의미와 uncertainty 동시 표기 |
| memory/performance | column pruning, chunk aggregation, columnar format 검토 |

각 버전은 별도 요구사항·검증을 통과한 뒤 진행하며, 이 문서는 일정 약속이 아니다.

## Experimental Stage 13 — 공간 강건성·해안성

Stable VERSION 1.0.0 및 Stage 10–12 산출물을 유지한다. Directed/symmetric KNN,
data-based distance band, inverse distance의 13개 설정으로 Global/Local Moran을 재검증한다.
공식 국립해양조사원 SHP의 checksum/CRS/속성·도형을 검증하고 최단 해안거리,
20/30/50 km 분류 민감도, continuous association, MWU/BH-FDR/effect size,
사전지정 탐색적 OLS를 별도 namespace에 생성한다. 13번째 읽기 전용 Dashboard와
deterministic report/manifest를 제공한다. NASA/KMA API 호출 없음.

## Experimental Stage 14 — Spatial Dependence–Adjusted Modeling

저장된 Final Tier A 및 12·13단계 결과만 사용해 OLS/HC3 → 잔차 Moran/LM →
SAR/SEM, 4개 가중치 민감도, predictor 표준화, 경도 sensitivity, LOO를 추가했다.
모든 결과는 신규 spatial_models namespace에 저장한다. Gaussian likelihood IC의
모수 개수와 SEM innovation 정의를 통일하고 불안정/실패 모형은 별도 표시한다.
Stable 1.0.0과 기존 결과는 변경하지 않는다. 상세 방법과 한계는
[공간보정 모델 문서](SPATIAL_DEPENDENCE_ADJUSTED_MODELING.md)를 참조한다.

Stage 15 권장 검토: 작은 표본의 강건 추론, 역거리 가중치의 추정 경계/수치 안정성,
모형별 admissible parameter domain, slope 추정불확실성. 실패를 숨기거나
가중치를 유의성에 맞춰 고르지 않는다. 별도 사용자 요청과 검증 후 진행한다.

## Experimental Stage 14.5 — Numerical Robustness Review

기존 1–14단계 결과를 보존한 별도 수치 진단이다. 9개 사전 지정 W, spectrum 및
비특이 구간/Neumann 구간/고정 solver bounds의 구분, native solver 관찰,
p1/p2·단일 cutoff·raw/row 비교와 canonical 재현성 검증을 수행한다.
실패를 강제 구제하지 않고 비권장 specification을 구분한다.
Non-spatial inference 우선순위는 HC3, classical OLS는 참고값으로 명시한다.
기존 14번째 대시보드에 expander와 별도 technical report를 제공한다.

Stage15의 소규모 Tier B에는 공간모형을 적용하지 않는다.
Tier A에서 수치적으로 안정적인 weight가 Tier B에서도 안정적이라고 가정하지 않는다.

## Experimental Stage 15 — Tier B 1991–2025 Independent Cohort

Final B shortlist와 실제 cache 품질을 다시 확인하고 1991–2025 기온 3변수만 독립 분석한다.
기존 KMA raw 재사용, 격리된 NASA/processed/matched namespace, source별 BH-FDR,
normal/anomaly·계절·threshold proxy·daily validation·내부 ranking·기술적 해안거리,
15번째 Dashboard·보고서·manifest를 제공한다. Stable 1.0.0 및 과거 결과는 불변이다.
상세: [Tier B 분석 문서](TIER_B_1991_2025_ANALYSIS.md).

## Experimental Stage 16 — A+B Common-Period Analysis

Final A+B의 실제 적격 ID/기간/품질을 재검증하고 51개 station을 1991–2025에 다시 계산한다.
기존 A1981–2025와 B1991–2025 slope/q를 합치지 않는다. 공통 BH-FDR, normal/anomaly,
계절/threshold/validation, origin·지역·고도·해안 기술통계, 공식 grid 규격에 따른34개 격자 추정과
공유14그룹의 전체 시계열 일치를 검증한다. 16번째 Dashboard·별도 보고서/manifest를 제공한다.
상세: [공통기간 분석](COMMON_PERIOD_51_STATION_ANALYSIS.md).

## Experimental Stage 17 — Common-period spatial reanalysis

51개 관측소/34개 추정 NASA 격자를 분리하여 Global/Local Moran과 9개 권고 가중치
민감성을 재분석한다. 45/1981→45/1991→51/1991 bridge, grid duplication sensitivity,
contrast/DTR/계절/proxy/Bias/RMSE, 해안거리·20/30/50 km와 지역/고도 기술통계를 제공한다.
17번째 읽기 전용 Dashboard와 별도 보고서/manifest를 추가하며 기존 데이터·결과와
stable 1.0.0은 보존한다. 공간모형·예측·보간 또는 인과분해는 수행하지 않는다.
상세: [51개 공통기간 공간 재분석](COMMON_PERIOD_51_STATION_SPATIAL_REANALYSIS.md).

## Stage 18 — Period sensitivity

Final Tier A 45개를 고정하여 1981/1986/1991/1996/2001–2025를 저장 일자료에서 새로 계산한다.
window별 BH, 부호·유의성·절대 slope range, contrast/DTR/계절/proxy/validation,
고정 공간가중행렬의 Moran trajectory, NASA45/33 표현 비교, 해안 연관 민감성을 제공한다.
18번째 읽기 전용 Dashboard와 새 namespace의 CSV·차트·보고서·manifest만 추가한다.
시작연도와 window 길이의 결합 민감성이며 가속화나 인과효과를 입증하지 않는다.
상세: [기간 민감성 분석](TREND_PERIOD_SENSITIVITY_ANALYSIS.md).

## Stage 19 — Final integration / research outputs (not started)

18단계의 실제 검증 완료 결과를 검토한 후 사용자 확인을 받아 진행한다.
현재 단계에서 19단계 기능이나 연구 결론을 선행 생성하지 않는다.
