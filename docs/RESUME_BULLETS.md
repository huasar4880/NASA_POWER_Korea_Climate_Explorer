# Resume Bullets

실제 담당 역할과 검증 가능한 기여 범위에 맞춰 사용하세요.

## 한국어

- NASA POWER·KMA ASOS 공공 API 수집부터 cache·정제·screening·시각화까지 재사용 가능한 Python 기후분석 파이프라인 구현.

- 공식 ASOS inventory 105 <!-- fact:inventory_n -->개를 출발점으로 Tier A 45 <!-- fact:tier_a -->개와 Tier B 6 <!-- fact:tier_b -->개를 구분하고, 51 <!-- fact:common_n -->개 공통기간 관측소 비교의 기간·품질 조건을 관리.

- Sen slope, Mann–Kendall, BH-FDR 및 NASA–KMA Bias·MAE·RMSE·상관으로 장기 기온변화와 자료 차이를 분리하여 검증.

- 51 <!-- fact:common_n -->개 지점에 연결된 34 <!-- fact:grid_n -->개 NASA 격자를 비교하고 공간가중치·기간·수치모형 민감성을 별도로 검토.

- 통계적으로 불안정한 결과를 제외 기준과 함께 보존하고, source-addressable fact layer·SHA256·회귀 테스트로 보고서 재현성 구축.

- 읽기 전용 Streamlit 대시보드, 최종 연구보고서, 공개 범위·비밀정보 검사를 연결한 전달 패키지 구성.

## English

- Built a reusable Python pipeline for NASA POWER and KMA ASOS ingestion, caching, quality screening and visualization.

- Organized an official inventory of 105 <!-- fact:inventory_n --> ASOS stations into a 45 <!-- fact:tier_a -->-station long-period cohort and a 6 <!-- fact:tier_b -->-station shorter-period cohort for a 51 <!-- fact:common_n -->-station common-period comparison.

- Combined saved Sen slopes, Mann–Kendall tests and BH-FDR with Bias, MAE, RMSE and correlation to separate trend agreement from absolute differences.

- Audited 34 <!-- fact:grid_n --> unique NASA grids linked to 51 <!-- fact:common_n --> stations and documented spatial-weight, period and numerical-model sensitivity.

- Preserved failed model diagnostics and implemented source-addressable facts, checksums and regression tests for reproducible reporting.

- Integrated a read-only Streamlit interface, research report and publication-safety documentation without rerunning data downloads.
