# Reproducibility — v1.1.0

## 공통 설치

전체 연구 환경은 Python 3.11 이상입니다. 공개 데모 전용 설치는 아래 B를 따릅니다.
공개 저장소 또는 제공받은 소스 폴더에서 전체 연구용으로 설치할 경우:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

의존성 설치는 인터넷이 필요할 수 있습니다. 범위형 requirements이므로 모든 환경에서 비트 단위 동일성을 보장하지 않습니다.

## B. 경량 GitHub demo — 원본 cache와 키 불필요

포함 자료: 검증된 facts/evidence CSV, Executive Summary, 무결성 manifest, 대표 PNG 5개,
자체 포함형 HTML 보고서 및 방법/한계 문서. Python 3.13의 새 가상환경에서 검증합니다.
공개 runtime은 Streamlit와 pandas만 직접 의존하며 연구용 공간분석 패키지를 import하지 않습니다.

```bash
python -m pip install -r public_app/requirements.txt
python -m pip install pytest
python -m pytest tests/test_public_demo.py -q
streamlit run streamlit_app.py
```

기본 public mode는 7개 핵심 view만 노출합니다. 보고서와 대표 그림도 공개 사본에서 읽습니다.
전체 지점 지도·상세 연구 표 등은 full environment 전용이라고 안내하며 자동 API 수집하지 않습니다.
공개 bundle이 없거나 손상돼도 private cache로 우회하지 않고 자료 부족 안내를 표시합니다.
Cloud 전용 entrypoint `public_app/streamlit_app.py`는 APP_MODE 값과 무관하게 public으로 실행됩니다.
CSV의 source_file은 연구 archive 내 provenance 경로이며, 경량 저장소에 원자료가 포함됐다는 의미가 아닙니다.
공개 demo는 전체 분석을 재현하거나 source CSV까지 다시 검증하는 기능이 아닙니다.

## A. 연구 archive를 가진 로컬 환경 — 전체 회귀 / 전체 분석

기존 `data/`, `output/` 및 원본 metadata/checkpoint/manifest를 별도 보관·복원해야 합니다.

```bash
python -m pytest -q
python -m pip check
APP_MODE=full streamlit run streamlit_app.py
```

전체 suite에는 저장된 연구 결과를 읽는 회귀 테스트가 포함되므로 경량 clone만으로 전체 통과를 보장하지 않습니다.
`tests/test_release_preparation.py`도 작업 전 로컬 보호 snapshot이 필요합니다.
CLI의 수집·분석 실행법은 [기존 단계 기록](STAGE_HISTORY.md)에 보존합니다.
원자료가 없다면 별도 사용자 승인 아래 공식 API 수집부터 실행해야 하며, 시간·권한·호출량 제약이 있습니다.
KMA 수집에만 `.env.example`의 `KMA_API_KEY`를 로컬 `.env`에 설정합니다.
키를 명령줄이나 로그에 출력하지 않습니다. NASA POWER 요청에는 사용자 API 키가 필요하지 않습니다.

## 역사적 final package와 현재 릴리스의 구분

VERSION 1.1.0은 공개 소프트웨어 버전입니다. 기존 1~19단계 manifest의 1.0.0은 생성 당시 값으로 보존합니다.
현재 릴리스에서 기존 연구 데이터와 output을 다시 생성하지 않습니다. 이전 final builder를 수동 실행하면
final 연구 파일이 갱신되므로, 보존된 archive에서 검증만 할 때는 실행하지 않습니다.
향후 명시적으로 연구 package를 재생성할 경우에만 `scripts/build_final_integration.py`를 사용합니다.
1.1.0에서는 역사적 문서 생성기로 현재 공개 정책을 덮어쓰지 않습니다.

## 공개 준비 검증

```bash
python scripts/prepare_public_release.py audit
python scripts/prepare_public_release.py protected
```

audit는 공개 후보를 검사하며 결과는 로컬 release/qa에 기록합니다.
protected는 이미 저장된 작업 전 snapshot과 SHA256·mtime을 비교합니다. baseline을 새로 만들어 결과를 맞추지 않습니다.
mtime은 변경 탐지용이며 관측일이나 취득일이 아닙니다.
릴리스 manifest는 Git commit 자체 해시를 기록하므로 순환참조를 피하기 위해 commit 밖 로컬에 보관합니다.
GitHub의 v1.1.0 Release와 tag는 발행되었으며, 후속 데모 변경으로 이동하지 않습니다.
공개 전용 테스트 외 기존 `tests/test_public_release.py`는 전체 연구 의존성으로 실행합니다.
Code License: [MIT](../LICENSE). 데이터 제공기관의 이용조건은 별도로 적용됩니다.

[문서 색인](INDEX.md) · [공개 계획](GITHUB_PUBLICATION_PLAN.md) · [점검표](RELEASE_CHECKLIST.md)
