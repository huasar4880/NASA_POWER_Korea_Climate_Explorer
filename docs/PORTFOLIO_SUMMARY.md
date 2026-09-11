# Portfolio Summary

## A. 1-line

NASA POWER와 KMA ASOS의 45년 기후자료를 수집·분석·교차검증하고 대시보드와 자동 보고서로 연결한 8개 도시 Python 기후데이터 시스템.

## B. Short

NASA POWER 격자자료와 KMA ASOS 지점관측을 같은 날짜·도시 기준으로 비교할 수 있도록 수집, 정제, 품질검사 파이프라인을 구축했다. 1981–2025년 8개 도시와 7개 변수를 대상으로 선형회귀, Mann–Kendall, Sen's slope, FDR, normal/anomaly 및 계절분석을 구현했다. 결과는 9페이지 Streamlit 대시보드와 출처 추적 가능한 HTML/Markdown 보고서로 재사용한다. 120개 테스트와 캐시 기반 회귀 실행으로 API 장애와 분석 결과 변경 위험을 관리한다.

## C. Detailed

서로 생산 방식이 다른 장기 기후자료를 일관된 기준으로 비교하고, 결과의 근거까지 추적할 수 있게 만드는 문제를 해결했다. NASA POWER Daily API와 KMA ASOS 일자료 API에서 1981–2025년 8개 도시·7개 변수 데이터를 수집하고 raw/processed cache, schema·결측·범위·중복 검사를 분리했다. 선형회귀, Mann–Kendall, Modified MK, Sen's slope, BH-FDR, 1991–2020 normal/anomaly와 계절·기후지표 proxy를 계산했으며, 같은 날짜의 NASA–KMA pair로 Bias·MAE·RMSE·상관과 강수 contingency를 검증했다. 결과 CSV를 단일 근거로 사용하는 9페이지 Streamlit 대시보드와 deterministic 보고서를 구현하고 120개 회귀 테스트로 보호했다. 격자와 관측소의 공간 차이, 강수 공란의 불확실성, 8개 도시 표본이라는 한계도 함께 공개한다.

