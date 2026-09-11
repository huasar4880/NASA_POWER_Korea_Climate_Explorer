# GitHub Publication Plan — v1.1.0

## COMMIT

`src/`, `dashboard/`, `reporting/`(템플릿 포함), `scripts/`, `tests/`, 작은 `config/`,
`requirements.txt`, `main.py`, `streamlit_app.py`, `VERSION`, `AGENTS.md`, `README.md`,
`CHANGELOG.md`, `LICENSE`, `.gitignore`, 빈 키의 `.env.example`, Markdown 문서.
대표 그림은 `docs/assets/final/`의 기존 그림 3개만 사용합니다.
`output/public_demo/`에는 Executive Summary, facts/evidence CSV 및 사본 해시 manifest만 포함합니다.
정확한 경로·파일 수·논리 크기는 [선택 staging 미리보기](GITHUB_STAGED_FILE_PREVIEW.txt)에 있습니다.
목록은 `scripts/prepare_public_release.py`의 명시적 allowlist와 비교합니다.

## OPTIONAL

전체 최종 HTML/Markdown 연구보고서, 추가 요약 CSV, 기존 portfolio 그림과 report/assets.
로컬에 보존하며 첫 공개 commit에는 넣지 않습니다. 별도 승인 후 크기·인용·secret 검사를 다시 거쳐 배포합니다.

## DO_NOT_COMMIT

`.env`와 변형, `.streamlit/secrets*`, raw / processed / KMA / NASA / nationwide /
common-period / period-subset cache를 포함한 `data/` 전체, 해안선 원자료·변환 geometry,
기존 대용량 output, 내부 QA, 로그, 임시파일, `.venv/`, Python/도구 cache.
`output/final/release/`의 로컬 검증 manifest·snapshot도 첫 commit에서 제외합니다.
**제외는 Git 추적 제외이며 파일 삭제가 아닙니다.**

## 로컬 Git과 승인 범위

사용자가 VERSION 1.1.0 확정, `main` branch의 로컬 `git init`, 명시적 파일 staging을 승인했습니다.
설정된 Git identity가 있을 때만 검증 후 첫 commit을 만듭니다. identity는 존재 여부만 검사하고
이름·이메일을 출력하거나 임의로 설정하지 않습니다. Git commit 자체에는 Git 작성자 metadata가
들어가므로 공개 전 본인 계정의 공개 적합성은 별도 확인해야 합니다.

GitHub 저장소 생성·remote 연결·push·tag는 이번 승인 범위가 아닙니다.
**Code License: [MIT](../LICENSE).** 공개용 이름과 GitHub noreply 주소는 사용자 승인 정보이며, 이 저장소의 local Git 설정에만 사용합니다. 다른 개인 이메일·API 키·개인 절대경로는 허용하지 않습니다.
기술 준비 완료와 실제 공개 승인은 별개입니다. [Release Checklist](RELEASE_CHECKLIST.md).

## 보존 및 용량 증거

기존 data/output 전체의 SHA256와 mtime은 새 작업 전 snapshot에 고정합니다.
파일 수·통합 digest·변경 여부·제외 용량은 로컬
`output/final/release/v1.1.0_release_preparation_manifest.json`에서 확인합니다.
원래 19단계 manifest는 1.0.0 시점의 역사적 증거로 수정하지 않습니다.
현재 코드·문서와 당시 hash 차이는 릴리스 변경이며 연구 artifact 보존 검사와 구분합니다.
