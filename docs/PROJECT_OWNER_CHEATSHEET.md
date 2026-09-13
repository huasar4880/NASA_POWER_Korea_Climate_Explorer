# Project Owner Cheatsheet

면접 전·운영 중 빠르게 보는 표입니다. [Handbook](PROJECT_OWNER_HANDBOOK.md) · [Quickstart](PROJECT_OWNER_QUICKSTART.md) · [Glossary](PROJECT_OWNER_GLOSSARY.md) · [Troubleshooting](PROJECT_OWNER_TROUBLESHOOTING.md).

## 핵심 숫자와 해석

| 항목 | 확인된 값 | 의미·제약 |
|---|---|---|
| 공식 inventory | 105 | 전부 최종 분석 대상 아님 |
| Tier A | 45, 1981–2025 | 고정 장기 관측소 |
| Tier B | 6, 1991–2025 | 독립 공통기간 cohort |
| Common | 51, 1991–2025 | A도 같은 기간으로 맞춤 |
| NASA grids | common34 / fixed A33 | station 수와 다름 |
| Normal | 1991–2020 | anomaly 기준 |
| KMA TAVG Sen 중앙값 | 0.4508°C/decade | common51, 면적가중 국가 평균 아님 |
| KMA TAVG 양수·FDR | 51/51, 51/51 | original MK BH-FDR |
| TMIN 더 빠른 지점 | 40/51 | 지점별 TMIN−TMAX Sen 비교 |
| contrast 중앙값 | 0.1470°C/decade | DTR의 부호 반대값과 동일하지 않음 |
| DTR Sen 중앙값 | −0.1776°C/decade | 연간 차이 시계열 직접 적합 |
| TAVG 방향 일치 | 51/51 | NASA/KMA 절대 기온 동일 아님 |
| TAVG Bias·MAE·RMSE | −1.0155·1.5357·1.9028°C | 지점 지표 중앙값, NASA−KMA |
| TAVG Pearson·Spearman | 0.9907·0.9909 | 정확도 백분율 아님 |
| NASA TAVG Moran | .8860→.6957 | directed k4, station→unique-grid; 두 p=.001 |
| 고정45 시작기간 Sen | .3888→.5658°C/decade | 1981 시작→2001 시작, 둘 다 2025 종료; 가속도 아님 |
| 수치 진단 | 안정34·경계6·불안정13·실패1 | 54개 모형 조합, 실패값 보존 |
| Public / full | 7 / 18 | 공개 열람과 전체 archive 구분 |
| 소프트웨어 | v1.1.0, MIT 코드 | 데이터 조건은 각 제공기관 |

수치 출처는 [공개 fact layer](../output/public_demo/final_research_fact_layer.csv), [evidence matrix](../output/public_demo/final_evidence_matrix.csv), [Handbook 부록](PROJECT_OWNER_HANDBOOK.md#d-key-fact-provenance)입니다. 기존 시험 기준 776개는 배포 manifest의 역사적 결과이며 최신 실행은 해당 작업 QA를 확인합니다.

## 결론의 강도

| 자신 있게 말하기 | 반드시 조건 붙이기 | 말하면 안 되는 주장 |
|---|---|---|
| 검토한 지점·기간에서 TAVG 상승 반복 | TMIN 우세·DTR 경향은 전 지점 법칙 아님 | 모든 위치·매년 같은 속도로 상승 |
| 방향 일치와 절대 수준 차이가 함께 존재 | 오차는 변수·위치·유효 pair에 의존 | 상관 .99는 99% 정확도 |
| 고유 격자에서도 NASA 양의 구조 유지 | I 크기·n·W는 달라짐 | grid 중복 영향 0 |
| Bias/RMSE 공간구조 반복 | 해안 연관·통제모형은 구분 | 해안 인과효과 입증 |
| 실패·조건·출처를 보존 | KMA 군집·기간별 크기는 민감 | 고정 hotspot·온난화 가속도 검증 완료 |

## 공개 링크

| 목적 | 링크 |
|---|---|
| 바로 체험 | [Live Demo](https://korea-climate-explorer.streamlit.app/) |
| 코드·최신 문서 | [GitHub main](https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer) |
| 고정 공식 배포 | [v1.1.0 Release](https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer/releases/tag/v1.1.0) |
| 읽을 보고서 | [공개 HTML](../output/public_demo/deployment/Final_Research_Report.html) — 데모에서 다운로드 권장 |
| 링크 사용 맥락 | [Portfolio links](PUBLIC_PORTFOLIO_LINKS.md) |

## 자주 쓰는 명령 — 프로젝트 루트에서

| 목적 | 명령 | 예상 결과·주의 |
|---|---|---|
| 위치 | `pwd` | 개인 경로 공유 전 가리기 |
| 저장소 상태 | `git status --short --branch` | main·변경 파일 확인 |
| 원격 | `git remote -v` | NASA repo 확인, 인증정보 공유 금지 |
| 최근 이력 | `git log -1 --oneline` | commit 확인 |
| 기존 환경 | `source .venv/bin/activate` | Python/pip도 확인 |
| 환경 건전성 | `python -m pip check` | 충돌 없음; 실패 시 별도 환경 검토 |
| 공개 데모 | `python -m streamlit run public_app/streamlit_app.py` | 7 view, 키 불필요 |
| 전체 연구 UI | `APP_MODE=full python -m streamlit run streamlit_app.py` | archive·전체 의존성 필요 |
| public 시험 | `python -m pytest tests/test_public_demo.py -q` | 경량 환경용 |
| 전체 회귀 | `python -m pytest -q` | 전체 archive 환경용 |
| CLI 도움말 | `python main.py --help` | 목록만 표시; 전체 연구 의존성 |
| 서버·환경 종료 | Ctrl+C 다음 `deactivate` | 브라우저 닫기와 다름 |
| 최신 이력 가져오기 | `git pull --ff-only origin main` | 변경 적용; 깨끗한 상태에서, 분기 시 중단 |
| 공개 문서 선택 | `git add README.md` | README만 바꾼 경우의 예시 |
| 변경 기록 | `git commit -m "Clarify project documentation"` | 검증한 stage만 기록 |
| 공개 반영 | `git push origin main` | 성공·원격 동기화 확인, force 금지 |

`python main.py`, `--all`, `--validate-kma`, `--analyze-*`, `--report-*`는 평상시 읽기 전용 명령이 아닙니다. 수집이나 결과 파일 재작성이 될 수 있습니다.

## 파일 지도와 금지사항

| 위치 | 역할 | 운영 원칙 |
|---|---|---|
| docs/PROJECT_OWNER_*.md | 소유자 설명서 | 사실·링크 검사 후 수정 |
| config/ | 도시·station·분석 조건 | 무단 추가·기간 변경 금지 |
| data/ | raw·processed·metadata·cache | 공개·수기 변경 금지 |
| output/tables·charts·reports | 실제 연구 결과 | 분석 없이 읽기만 |
| output/public_demo/ | 선택 공개 자료 | checksum 계약 확인 |
| output/final/release/project_owner_handbook_manifest.json | 이번 문서 검증 기록 | 로컬 보관, 자동 공개 아님 |
| .env / private key / PAT | 인증정보 | 공유·stage 금지 |
| v1.1.0 tag | 공식 기준점 | 이동·삭제·재생성 금지 |

## 1분 면접 메모

“한국의 장기 기온변화를 분석하면서 어떤 결론이 분석 조건을 바꿔도 유지되는지 검증했습니다. NASA POWER와 ASOS를 비교하고, 공식 목록 105개를 품질·기간으로 선별해 장기 45개와 공통기간 51개를 구분했습니다. 평균기온 상승 방향은 일관됐지만 절대 기온과 공간군집은 조건에 따라 달랐습니다. 격자 중복·다중검정·모형 실패·기간 민감성을 숨기지 않고 근거를 기록했습니다. 결과는 원본 행·열을 추적하는 보고서와 API 키 없는 7개 공개 화면으로 전달했습니다. 미래예측이나 인과성은 주장하지 않습니다.”

본인 역할에 맞게 조정하고 30초·3분·5분 버전과 32개 질문은 [Handbook Part XIII](PROJECT_OWNER_HANDBOOK.md#part-xiii--취업면접발표에서-활용하기)에서 연습하세요.
