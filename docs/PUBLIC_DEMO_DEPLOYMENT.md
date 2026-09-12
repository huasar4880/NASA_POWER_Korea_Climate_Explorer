# Public Streamlit Demo — v1.1.0

검증된 precomputed 결과를 읽는 경량 공개 UI입니다. 신규 분석·API 호출·raw 배포를 하지 않습니다.
main의 후속 데모 개선과 기존 v1.1.0 Release/tag는 구분합니다.

## 배포 완료

[Live Demo](https://korea-climate-explorer.streamlit.app/)가 Streamlit Community Cloud에 공개 배포됐습니다.
사용자가 시크릿 브라우저의 익명 접근을 확인했고, 링크 통합 작업에서도 로그인 없이 Home과 7개 공개 메뉴의 렌더링을 확인했습니다.
[공개 링크 패키지](PUBLIC_PORTFOLIO_LINKS.md)에서 저장소·Release·보고서까지 연결합니다.

## 범위와 설치

Home / Nationwide Trends / NASA × KMA Validation / Spatial Patterns / Period Sensitivity /
Methods / Limitations / Research Report의 7개 view를 제공합니다.
기존 18-page 전체 연구 모드는 별도 cache와 전체 의존성을 사용하는 `APP_MODE=full`로 보존합니다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r public_app/requirements.txt
python -m pip install pytest
python -m pytest tests/test_public_demo.py -q
python -m pip check
streamlit run public_app/streamlit_app.py
```

로컬 clean-room 검증 환경은 Python 3.13입니다. 직접 runtime 의존성은 Streamlit 1.62.0과 pandas 3.0.5입니다.
루트 requirements의 과학·지리공간 패키지는 전체 연구용으로 유지합니다. Cloud에서 공개 화면 실행을 확인했으나 서버의 정확한 Python 버전과 설치 로그를 재조회한 것은 아닙니다.
환경변수 없는 루트 entrypoint도 public이 기본이며, Cloud 전용 entrypoint는 항상 public입니다.
`.env`, Streamlit secrets, NASA/KMA key, `data/` 및 QA 로그가 필요하지 않습니다.

## Streamlit Community Cloud 설정

| 항목 | 설정 |
|---|---|
| Repository | huasar4880/NASA_POWER_Korea_Climate_Explorer |
| Branch | main |
| Main file path | public_app/streamlit_app.py |
| Python | 3.13 (로컬 clean-room 검증 버전) |
| Secrets | 설정하지 않음 |
| Dependency file | public_app/requirements.txt |

공식 문서에 따라 [entrypoint 폴더의 dependency 파일을 먼저 찾습니다](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).
따라서 루트 연구용 requirements를 대체하거나 삭제하지 않고 공개 runtime을 분리합니다.
[배포 화면](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)에서 위 repository/branch/main file을 지정합니다.
로그인 또는 GitHub OAuth 승인이 필요하면 사용자가 직접 브라우저에서 완료해야 합니다. 키나 token을 코드·채팅으로 전달하지 않습니다.

## 공개 assets와 한계

`output/public_demo/deployment/manifest.json`은 runtime이 사용하는 11개 파일의 SHA256을 고정합니다.
payload는 약 1.85 MB이며 PNG 5개, facts/evidence CSV 2개, Executive Summary, 방법/한계 문서 2개,
자체 포함형 HTML 보고서 1개입니다. 대표 그림은 기존 검증 산출물의 사본입니다. 지도나 통계를 새로 계산하지 않습니다.
보고서는 앱에서 다운로드 후 브라우저에서 열 수 있으며 GitHub blob 페이지의 렌더링에 의존하지 않습니다.
전체 공간 지도·대용량 상세 결과는 full environment 전용입니다. 공개 자료가 없거나 checksum이 다르면
"This analysis is available in the full reproducible research environment." 안내를 표시합니다.

CSV의 source_file은 원래 연구 archive의 provenance이며 공개 저장소에 그 원자료가 있다는 뜻이 아닙니다.
관측소 결과는 면적가중 전국 평균이 아니며, threshold는 analytical proxy이고 공간 연관성은 인과 추정이 아닙니다.
결과는 기간·관측소 집합·공간가중치에 민감할 수 있습니다. 전체 원자료와 cache는 공개하지 않습니다.

## 검증 범위와 기록

배포 전 clean-room에서 7개 view, 그림, 보고서 다운로드 및 desktop/mobile 기본 배치를 확인했습니다.
현재 공개 URL의 접근 확인과 과거 로컬 검증은 구분해 기록하며, 서버의 내부 호출 로그를 실측했다고 주장하지 않습니다.
공개 소스는 precomputed assets만 읽고 NASA/KMA API나 인증정보를 필요로 하지 않습니다.
배포 전 release/qa/public_demo22와 readiness 기록은 그대로 보존합니다. 실제 URL·검증 시각·commit·회귀 결과를 기록한
공개 metadata만 담은 [배포 완료 manifest](../output/final/release/v1.1.0_public_demo_deployment_manifest.json)는 사용자 승인 exact-path 예외로 공개합니다. 내부 QA와 이전 snapshot은 계속 로컬에 보관합니다.

공개 개발컨테이너에서는 사용자 승인에 따라 CORS/XSRF 비활성화 옵션과 자동 시스템 업그레이드 명령만 제거했습니다.
나머지 개발환경 구조와 설치 명령은 유지하며 이번 작업에서 해당 명령이나 컨테이너를 실행하지 않았습니다.
이는 Streamlit Community Cloud 앱 설정을 변경하거나 그 앱이 이 개발컨테이너를 사용한다고 가정한 작업이 아닙니다.

문서·링크 통합 commit은 main에 추가하되 v1.1.0 tag는 변경하지 않습니다. 이번 단순 문서 변경에는 v1.1.1이 필요하지 않으며 새 release를 만들지 않습니다.
