# v1.0 Status Snapshot

스냅샷 날짜: **2026-09-04**

| Category | Status |
|---|---|
| Version | 1.0.0 |
| Python | target ≥3.11; regression environment 3.14.6 |
| Analysis | 8 cities, 1981–2025, 7 climate variables |
| Daily coverage | 16,436 dates per city for primary NASA/KMA daily datasets |
| Tests | 120 passed |
| Dashboard | 9 pages |
| Reports | 8 city + 1 comparison report; HTML and Markdown |
| Report validation | 1,392 scalar source checks; 81 charts; 9 manifests |
| NASA–KMA validation | 8 cities × 7 variables |
| Gangneung continuity | station 105 primary; 104 overlap-only, 6,365 T2M pairs |
| API keys | not included in public-candidate files; local `.env` ignored |
| Git state | not initialized; no remote or push performed |

## Regression status

- 전체 pytest: 120 passed
- dependency consistency: no broken requirements
- CLI help, Seoul analysis, all-city cache workflow: passed
- cached Seoul KMA validation: passed without network request
- Seoul report generation: passed
- Streamlit headless startup and health response: passed
- release safety scan: no secret, personal path, personal username or personal email found
- protected analysis inputs/results: hash and mtime unchanged during stage 9

## Known limitations

- 8개 도시 point/station 비교로 전국 공간대표성을 보장하지 않는다.
- grid 기반 NASA 자료와 station 기반 KMA 자료의 차이는 오류만이 아니라 대표공간 차이를 포함한다.
- KMA `sumRn` 공란을 무강수로 단정할 근거가 충분하지 않아 NaN으로 유지한다.
- NASA solar는 1981–1983 fill value를 제외해 유효 추세기간이 1984–2025다.
- 기후지표는 NASA 기반 proxy이며 공식 KMA 극한기후 통계가 아니다.
- 관측소 이전·장비·관측방식 변화가 장기 비교에 영향을 줄 수 있다.
- 코드 LICENSE, raw 데이터 Git 포함, public repository 여부는 사용자 결정 전이다.

