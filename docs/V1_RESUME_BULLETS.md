<!-- Historical documentation snapshot before final integration; not current result claims. -->
# Resume Bullets

- NASA POWER·KMA ASOS API 기반 1981–2025년 8개 도시·7개 변수 기후자료 수집, raw/processed cache, 오류 복구 및 데이터 품질검사 파이프라인 구축
- 선형회귀, Mann–Kendall·Modified MK, Sen's slope, BH-FDR, 1991–2020 normal/anomaly를 적용한 장기 기후추세 분석 및 136개 연간 통계 series 산출
- 도시·날짜별 유효 pair를 이용해 NASA 격자자료와 KMA 지점관측의 Bias·MAE·RMSE·상관 및 강수 POD/FAR/CSI를 8개 도시 × 7개 변수에서 교차검증
- 동일한 결과 CSV를 사용하는 9페이지 Streamlit 대시보드와 8개 도시·1개 비교 HTML/Markdown 자동 보고서, source-addressable Fact Layer 구현
- API mock, 네트워크 차단, 통계·시각화·보고서·release contract를 포함한 120개 pytest 회귀 테스트와 credential 안전성 검사 구축

> 수치는 v1.0 검증 스냅샷 기준이다. 이력서 사용 시 본인의 실제 역할과 검증 가능한 범위에 맞게 표현을 조정한다.
