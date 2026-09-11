# Public Streamlit Demo — v1.1.0

검증된 precomputed 결과를 읽는 경량 공개 UI입니다. 신규 분석·API 호출·raw 배포를 하지 않습니다.
main의 후속 데모 개선과 기존 v1.1.0 Release/tag는 구분합니다. 실제 live URL 확인 전에는 배포 완료로 표기하지 않습니다.

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
루트 requirements의 과학·지리공간 패키지는 전체 연구용으로 유지합니다. Cloud Linux 실행은 실제 배포 후 별도 확인해야 합니다.
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

## 공개 배포 완료 조건

실제 URL에서 Home, 7개 view, 그림, 보고서 다운로드, desktop/mobile 기본 배치와 secret 미노출을 확인한 뒤
README Live Demo와 포트폴리오 링크를 추가합니다. 로컬 성공을 Cloud 배포 성공으로 간주하지 않습니다.
배포 전 증거는 로컬 release/qa/public_demo22와 readiness 기록에 별도 보관합니다.
배포 완료 manifest는 실제 URL·시각·commit과 smoke test 결과가 있을 때만 생성합니다.

새 commit은 main에 추가하되 v1.1.0 tag는 변경하지 않습니다. 필요하다면 v1.1.1을 후속 후보로 검토하되 자동 발행하지 않습니다.
