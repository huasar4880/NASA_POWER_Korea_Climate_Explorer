# Project

## NASA POWER Korea Climate Explorer

### 프로젝트 목적

여러 API에서 생산 방식이 다른 장기 기후자료를 가져와 동일한 품질기준으로 비교하고,
통계결과를 연구자뿐 아니라 일반 사용자도 검토할 수 있는 dashboard/report로 연결하는
재현 가능한 end-to-end 시스템을 구축했다.

### 사용 기술

- Python 3.11+, Requests
- NumPy, Pandas, SciPy, Statsmodels, PyMannKendall
- Matplotlib, Plotly, Streamlit
- Jinja2, Pytest
- JSON configuration, CSV/PNG/HTML/Markdown

목록은 `requirements.txt`와 실제 import를 기준으로 작성했다.

### 내가 구현한 핵심 기능

- NASA POWER와 KMA ASOS API integration 및 오류·제한 처리
- 8개 도시 설정 기반 ETL과 raw/processed cache 분리
- 결측·fill value·중복·기간·물리범위 데이터 품질검사
- 회귀, MK/Modified MK, Sen slope, FDR, normal/anomaly, 계절 및 proxy 분석
- 7개 변수의 grid–station 교차검증과 강수 contingency
- 저장 결과만 읽는 9-page Streamlit dashboard
- source-addressable Fact Layer 기반 deterministic 보고서
- mock/network 차단을 포함한 120-test regression suite

### 핵심 기술적 문제와 해결

1. **NASA 장기 수집:** 도시·기간별 cache와 schema validation으로 불필요한 재요청을 줄였다.
2. **ServiceKey double encoding:** KMA의 이미 인코딩된 key를 `params=`에 다시 넣지 않고
   최종 query에 한 번만 전달하며 key 없는 redacted 진단을 만들었다.
3. **KMA chunk/pagination:** 최대 기간에 맞춘 5개 chunk와 `totalCount` 기반 pagination,
   도시별 cache, 요청 간격과 code 22/23 처리로 이어받기를 가능하게 했다.
4. **NASA solar −999:** processed에서 NaN으로 유지하고 유효 추세기간을 1984–2025로 표시했다.
5. **KMA precipitation blank:** 공식 규칙이 불충분하고 강수현상과 공란이 함께 있는 실제
   사례가 있어 0으로 바꾸지 않았다. validation 범위를 유효 numerical pair로 명시했다.
6. **Gangneung continuity:** 105를 primary, 104를 overlap-only로 분리하고 별도 지표를 만들었다.
7. **다중 통계검정:** 지표군별 BH-FDR과 자기상관 sensitivity를 추가해 raw p-value 과해석을 줄였다.
8. **Dashboard cache:** read-only loader와 `st.cache_data`로 widget rerun의 반복 I/O를 줄였다.
9. **Report Fact Layer:** 문장·표·차트의 값에 source cell/hash/mtime을 연결하고 생성 전후 대조했다.

### 주요 성과

- 8개 도시, 45년, 도시당 16,436일, 7개 기후변수
- 8×17=136개 연간 통계 series와 8×4×5=160개 계절 trend
- NASA–KMA 8도시×7변수 validation 및 강릉 6,365 overlap pair
- 대시보드 9페이지, 도시보고서 8개와 비교보고서 1개
- 1,392 report scalar source checks, 81 report charts, 9 manifests
- 120 tests 및 실제 CLI/dashboard/report regression

### 프로젝트에서 배운 점

- API 성공은 HTTP 200만이 아니라 body code, pagination, cache completeness로 검증해야 한다.
- 결측의 의미가 불확실할 때 편리한 0 대치는 재현성보다 큰 분석오류를 만든다.
- 유의성, 효과크기, 절대오차, 상관과 공간대표성을 분리해야 한다.
- 결과 CSV를 stable contract로 두면 dashboard와 report를 독립적으로 검증할 수 있다.
- release 품질에는 코드뿐 아니라 credentials, data terms, provenance와 failure recovery가 포함된다.

### 활용 가능 분야

공공기관·R&D 데이터 분석, 환경·기후 연구지원, 정책지원 지표 탐색, 연구행정,
데이터 품질관리, dashboard/monitoring, 다기관 관측자료 교차검증에 적용할 수 있다.

### 정직한 한계

8개 point/station 비교이며 전국 대표성·인과귀속·미래예측·종합위험평가는 아니다.
강수 공란 의미, station history, 데이터 공개정책은 후속 검토가 필요하다.
