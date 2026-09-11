<!-- Historical documentation snapshot before final integration; not current result claims. -->
# Interview Notes

## 1. 왜 이 프로젝트를 시작했는가

- 장기간 기후자료의 다운로드부터 통계, 검증, 전달까지 단절된 작업을 하나의 재현 가능한 흐름으로 만들고 싶었다.
- 도시 간 비교에서 기간·변수·결측 처리·계산식이 달라지는 문제를 설정과 공통 함수로 통제했다.

## 2. NASA POWER를 선택한 이유

- 동일한 Daily Point 인터페이스로 여러 도시와 변수를 장기간 조회할 수 있다.
- 다만 격자형 위성·모델 기반 자료이므로 지상 관측과 같다고 가정하지 않고 KMA 검증을 설계했다.

## 3. 왜 KMA ASOS와 검증했는가

- 실제 관측소와의 systematic difference와 일별 동조성을 Bias, 오차, 상관으로 분리해 확인하기 위해서다.
- KMA를 절대적 참값으로 선언하기보다 grid–station의 생산 방식과 위치 차이를 해석 조건으로 남겼다.

## 4. 가장 어려웠던 기술 문제

- 장기간 API의 chunk·pagination·호출 제한·부분 실패를 데이터 중복이나 재다운로드 없이 처리하는 일이었다.
- 결측처럼 보이는 값의 의미가 변수·기관별로 달라 임의 보정보다 provenance와 보수적 처리가 중요했다.

## 5. serviceKey 이중 인코딩 문제를 어떻게 해결했는가

- `.env`의 key가 이미 URL-encoded일 수 있는데 `requests params=`가 `%`를 다시 인코딩하면 인증이 실패한다.
- 일반 parameter와 인증값을 분리해 serviceKey가 최종 query에 한 번만 들어가게 했고, 진단 출력에는 항상 `REDACTED`를 사용했다.
- HTTP status뿐 아니라 HTTP 200 body의 공공데이터포털 `resultCode/resultMsg`도 검사했다.

## 6. 강수 공란을 왜 0으로 바꾸지 않았는가

- 공식 명세만으로 모든 공란을 무강수로 단정할 수 없었고, 실제 자료에서 강수현상과 공란이 함께 있는 사례도 확인됐다.
- 0 대치는 wet-day와 누적강수, Bias를 체계적으로 바꿀 수 있으므로 numerical pair만 검증하고 공란은 NaN으로 유지했다.

## 7. 왜 Mann–Kendall / Sen's slope를 사용했는가

- Mann–Kendall은 분포 가정을 덜 요구하며 단조 추세를 검정한다.
- Sen's slope는 모든 시점쌍 기울기의 중앙값이라 outlier에 비교적 견고한 효과크기를 제공한다.
- 선형회귀도 함께 표시해 서로 다른 가정에서 방향과 규모가 일관적인지 본다.

## 8. FDR을 왜 사용했는가

- 도시와 지표가 늘어나면 유의수준 0.05만으로 우연한 양성이 증가한다.
- 관련 지표군 안에서 Benjamini–Hochberg 보정을 적용해 false-discovery 비율을 통제하고 raw p-value도 보존했다.

## 9. Dashboard 구조

- Streamlit은 API를 직접 부르지 않고 저장된 output table만 읽는 read-only consumer다.
- 공통 loader와 cache를 공유하고, 개요·도시·변수·추세·극한/anomaly·계절·validation·방법론·보고서의 9페이지로 구성했다.

## 10. 자동 보고서 Fact Layer

- 문장이나 표의 숫자를 직접 작성하지 않고 source CSV의 파일·행·열에 연결했다.
- source hash와 mtime, scalar consistency checks, manifest로 보고서가 사용한 근거를 추적한다.

## 11. 프로젝트 한계

- 8개 city point와 ASOS station은 전국 기후를 대표하지 않으며 인과귀속이나 미래예측을 제공하지 않는다.
- NASA LST와 KMA 관측일, grid–station 거리, station history, 강수 공란 및 solar 유효기간이 비교에 영향을 준다.
- threshold는 NASA 기반 분석 proxy이지 기상청 공식 통계가 아니다.

## 12. 전국 확장 시 어떻게 설계할 것인가

- station metadata와 이력부터 수집하고 시작일·이전·결측·중첩기간 기준으로 station을 선별한다.
- station 단위 checkpoint, rate limiter, retry budget와 incremental table을 사용한다.
- 분석 contract는 유지하되 지역 집계와 지도표현 전 별도 공간대표성·성능 검증을 거친다.
