# Project Owner Glossary

정의를 외우기보다 “프로젝트에서 어디에 쓰는가”를 함께 읽으세요. 상세 계산·제약은 [Handbook Part IV](PROJECT_OWNER_HANDBOOK.md#part-iv--통계량을-자신의-말로-설명하기), [최종 방법](FINAL_METHODS_SUMMARY.md)에 있습니다. 이 표는 신규 분석이나 서비스 규칙 변경이 아닙니다.

## 데이터·품질

| 용어 | 한 줄 정의 | 프로젝트 사용 |
|---|---|---|
| ASOS | 종관 규모의 지상기상 관측체계 | KMA 기온 비교 reference |
| KMA | 대한민국 기상청 | ASOS 일자료·관측소 이력 제공기관 |
| NASA POWER | 기상·태양에너지 관련 지구과학 자료 서비스 | 좌표별 일자료 수집 |
| KHOA | 국립해양조사원 | 공식 해안선 출처 |
| Station | 특정 ID와 이력을 가진 관측지점 | 날짜·관측소별 KMA 비교 단위 |
| Grid | 공간을 나눈 격자 단위 | NASA 대표성·공유 검토 |
| Station-linked | 관측소마다 자료를 연결한 표현 | 공통기간 51개 NASA 연결값 |
| Unique-grid | 동일 격자를 한 번만 나타낸 표현 | 공통기간 34개 공간단위 비교 |
| Inventory | 후보 전체를 담은 목록 | 공식 ASOS snapshot 105개 |
| Screening | 사용 기준으로 자료를 선별하는 절차 | 기간·결측·이력 확인 |
| Tier A | 프로젝트의 장기 적격 집합 | 45개, 1981–2025 |
| Tier B | 프로젝트의 공통기간 적격 집합 | 6개, 1991–2025 |
| Cohort | 같은 선택 조건으로 묶은 집합 | A/B 출신 정보를 보존 |
| Common period | 비교 대상의 기간을 맞춘 구간 | 51개, 1991–2025 |
| Climate Normal | 정한 기준기간의 전형적 평균 수준 | 1991–2020 기준값 |
| Anomaly | 관측 요약값과 기준값의 차이 | 연평균−normal, °C |
| Climatology | 계절·달별 전형적인 기후 요약 | 월별 평균 패턴 |
| TAVG | 평균기온 | KMA avgTa, NASA T2M 대응 |
| TMAX | 최고기온 | 일최고를 연평균 등으로 집계 |
| TMIN | 최저기온 | 일최저·25°C proxy |
| T2M | NASA 지상 2m 기온 변수 | 평균기온 비교 |
| DTR | 최고와 최저의 차이인 일교차 | 연간 차이 시계열의 별도 Sen |
| Precipitation | 비·눈 등을 물 깊이로 나타낸 강수량 | PRECTOTCORR/sumRn, mm/day |
| Relative humidity | 해당 온도에서의 포화 수준 대비 수증기 비율 | RH2M/avgRhm, % |
| Wind speed | 공기의 이동 속력 | WS2M/avgWs, m/s·높이 차이 주의 |
| Solar radiation | 면적당 일사 에너지 | kWh/m²/day; 일조시간 아님 |
| LST | Local Solar Time, 지방 태양시 | NASA 요청의 시간 기준 |
| Raw | 수집한 원자료 | 가공으로 덮어쓰지 않는 cache |
| Processed | 정해진 규칙으로 정제한 자료 | raw와 별도 폴더 |
| Tidy data | 한 행의 관측 단위와 열의 변수가 일관된 표 | 공통 함수의 입력 |
| NaN | 유효 수치가 없음을 나타내는 값 | 결측 보존, 0과 구분 |
| Null/blank | 값 부재 또는 공란인 응답 표현 | sumRn은 무강수로 단정 금지 |
| Fill value | 제공자가 결측을 표시한 특수 수치 | NASA −999를 분석에서 제외 |
| Completeness | 기대 관측에 대한 유효 관측 비율 | core 3기온과 연간 달력 비교 |
| Gap | 연속으로 자료가 비는 구간 | 90일 이상 core gap 검토 |
| Continuity | 관측 이력의 연속성 | 105/104 자동 접합 금지 |
| Homogenization | 비기후적 불연속을 분석·보정하는 절차 | 현재 screening과 구분하는 미실행 확장 |
| QC | 품질관리·품질검사 | 날짜·단위·중복·의심 범위 |
| Matched pair | 동일 날짜에 양쪽 값이 유효한 관측쌍 | 변수별 validation 분모 |

## 통계·공간·해석

| 용어 | 한 줄 정의 | 프로젝트 사용 |
|---|---|---|
| Linear slope | 직선 회귀의 시간당 변화량 | OLS 기울기×10 |
| Sen slope | 시점쌍 기울기의 중앙값 | 기온·DTR·proxy 추세 크기 |
| Theil–Sen | 쌍별 기울기를 사용하는 강건 회귀 방법 | Sen와 CI 구현 참고 |
| Decade | 10년 | °C/decade·days/decade |
| Moving average | 정한 개수의 연속 관측 평균 | 5/10년 후행 평활 표시 |
| Mann–Kendall | 단조 추세를 평가하는 비모수 검정 | 주요 original MK p |
| Modified MK | 자기상관 영향 등을 보완하는 MK 변형 | Hamed–Rao 보조 민감도 |
| Autocorrelation | 시간 순서에서 값들 사이의 상관 | lag-1 진단 |
| Confidence interval | 반복 추정 절차의 포괄 성질을 갖는 구간 | Sen 95% CI |
| p-value | 귀무가설 아래의 통계량 극단성 확률 | 효과크기와 별도 표시 |
| BH-FDR | 여러 검정의 거짓 발견 비율을 관리하는 보정 | 원 MK family별 q |
| Family | 함께 다중검정 보정하는 집합 | source×metric×window 등 |
| Pearson r | 선형 동조성 지표 | 일별 NASA/KMA 변화 동조 |
| Spearman rho | 순위 동조성 지표 | 비선형 단조 연관·validation |
| Bias | 부호 있는 차이의 평균 | NASA−KMA, °C 등 |
| MAE | 절대 오차의 평균 | 오차의 전형적 크기 |
| RMSE | 제곱오차 평균의 제곱근 | 큰 오차에 민감, 같은 pair에서 MAE 이상 |
| R² | 회귀·예측이 변동을 설명하는 정도 | OLS 적합 설명, 인과 아님 |
| Pooled metric | 여러 지점 관측을 합쳐 구한 지표 | 현재 지점 지표 중앙값과 구분 |
| Median | 정렬했을 때 가운데 값 | 지점 기울기·오차 요약 |
| Threshold proxy | 문턱 조건으로 만든 분석용 대리지표 | TMAX≥30/33, TMIN≥25 |
| Wet day | 정한 강수 기준을 충족한 날 | 여기서는 ≥1 mm/day |
| POD | 실제 사건 중 탐지한 비율 | hit/(hit+miss) |
| FAR | 탐지 사건 중 오경보 비율 | false alarm/(hit+false alarm) |
| CSI | 탐지·누락·오경보를 합친 사건 적중 지표 | hit/(hit+miss+false alarm) |
| Global Moran I | 전체 공간적 유사성 통계 | 추세·오차의 W별 구조 |
| Local Moran | 개별 위치 주변의 공간 패턴 통계 | HH/LL/HL/LH와 FDR |
| HH/LL | 자신과 이웃이 모두 높거나 낮은 유형 | 상대 기울기 군집, 위험등급 아님 |
| HL/LH | 자신과 이웃의 상대 수준이 다른 유형 | 국지적 대비 |
| Spatial weight W | 위치 사이 이웃 관계·비중을 담은 행렬 | 공간통계와 SAR/SEM 입력 |
| Directed KNN | 각 지점이 가까운 k곳을 고르는 연결 | 대표 k4, 대칭 보장 없음 |
| Symmetric KNN | 어느 방향에서든 선택된 관계를 양방향 연결 | 이웃 정의 민감도 |
| IDW | 거리가 멀수록 작은 비중을 주는 가중치 | p1/p2·cutoff 수치 검토 |
| Distance-band | 정한 반경 내 위치를 연결하는 방식 | 거리 기준 공간 민감도 |
| Row-standardization | 행의 가중치 합을 1로 맞추는 변환 | 이웃 평균 표현, 대칭성 주의 |
| Permutation | 값 위치를 재배치하는 모의 검정 | Moran raw p와 seed |
| OLS | 제곱잔차 합을 최소화하는 선형 추정 | 추세·해안 통제모형 |
| HC3 | 이분산에 강건한 표준오차 보정 | 주요 비공간 추론 |
| SAR | 결과의 공간지연을 포함한 모형 | 공간의존 보조 분석 |
| SEM | 오차의 공간구조를 포함한 모형 | SAR와 다른 specification |
| Residual | 관측과 모형 적합값의 차이 | 모형 진단·잔차 Moran |
| Solver | 수치 해를 찾는 계산 절차 | 경계·후속 실패 검사 |
| Numerical stability | 작은 계산 조건에서 결과가 신뢰성 있게 유지되는 성질 | STABLE/경계/불안정/실패 분리 |
| Robustness | 검토한 조건 변화에 결론이 유지되는 정도 | evidence 운영 등급 |
| Sensitivity | 선택 조건에 따라 결과가 변하는 정도 | W·grid·start-year |
| Causality | 원인 변화가 결과에 미치는 효과 관계 | 현재 관측적 연관과 구분 |

## 구현·운영·보안

| 용어 | 한 줄 정의 | 프로젝트 사용 |
|---|---|---|
| API | 프로그램이 자료를 요청하는 인터페이스 | NASA·KMA 수집 경로 |
| Endpoint | 요청을 보내는 서비스 주소 | client 한 곳에서 관리 |
| Parameter | 요청 조건을 지정하는 이름·값 | 좌표·기간·변수·station |
| URL encoding | URL에 맞게 문자를 표현하는 변환 | ServiceKey 이중 처리 방지 |
| Pagination | 응답을 여러 페이지로 나눠 받기 | KMA 999행 요청 |
| Chunk | 큰 기간을 작은 구간으로 나누기 | KMA 최대 10년 단위 |
| Retry/backoff | 실패 후 제한된 재시도·대기 증가 | 429/23 등 일시 장애 |
| Cache | 이미 받은 결과를 저장해 재사용 | API 중복 호출 감소 |
| Checkpoint | 중단 뒤 재개할 진행 기록 | 완료 station·chunk 보존 |
| ETL | 추출·변환·적재의 흐름 | 수집→정제→저장 |
| CLI | 터미널 명령으로 실행하는 인터페이스 | main.py 옵션 |
| Virtual environment | 프로젝트별 Python 패키지 공간 | .venv |
| Dependency | 실행에 필요한 외부 패키지 | public/full requirements 분리 |
| pytest | 자동 시험 실행 도구 | 단위·회귀·UI·보안 |
| Regression test | 변경 뒤 기존 동작 유지 확인 | 과거 기능을 깨뜨리지 않기 |
| Mock | 시험용 대체 객체·응답 | 실제 API 반복 호출 방지 |
| Manifest | 입력·출력·설정·검증을 묶은 기록 | provenance·재현·보존 |
| SHA256 | 파일 내용 지문을 만드는 hash | 변경 탐지·payload 계약 |
| mtime | 파일 수정 시각 | 내용이 같아도 재저장 탐지 |
| Fact layer | 수치와 source 행·열을 연결한 근거층 | 655개 저장 fact |
| Evidence matrix | 주장과 검증 범위·등급을 연결한 표 | A–H 결론 분류 |
| Streamlit | Python 기반 데이터 UI 도구 | public 7·full 18 |
| Entrypoint | 프로그램이 시작되는 파일 | public_app/streamlit_app.py |
| Public mode | 선별 공개 결과 열람 모드 | 키·raw 불필요 |
| Full mode | 전체 연구 archive 열람 모드 | APP_MODE=full |
| Git | 로컬 변경 이력 관리 | 검토·stage·commit |
| GitHub | 원격 Git 저장소·공개 협업 서비스 | 공개 source·Release |
| Commit | 선택한 변경의 이력 단위 | 메시지·해시로 추적 |
| Branch | 이어지는 commit의 이름 | main |
| Remote | 연결된 원격 저장소 | origin 별칭 |
| Tag | 특정 이력에 붙인 기준 이름 | v1.1.0 고정 |
| Release | tag에 연결된 공개 배포 설명 | 정식 v1.1.0 |
| SSH | 키 기반 원격 인증 프로토콜 | GitHub push 인증 |
| OAuth | 서비스 간 제한적 접근 승인 방식 | Cloud와 GitHub 연결 |
| PAT | 계정 API 접근용 개인 token | 비밀이며 공개·채팅 공유 금지 |
| Allowlist | 공개를 허용한 범위를 명시한 목록 | exact path 예외만 추가 |
| CORS | 브라우저 출처 간 요청 제어 장치 | 보호 비활성화 금지 |
| XSRF | 인증 상태를 악용한 위조 요청 위험 | 관련 보호 비활성화 금지 |

[Quickstart](PROJECT_OWNER_QUICKSTART.md) · [Handbook](PROJECT_OWNER_HANDBOOK.md) · [문서 색인](INDEX.md)
