# Project Owner Quickstart

완성본을 다시 사용하는 한 장 안내입니다. 개념은 [Handbook](PROJECT_OWNER_HANDBOOK.md), 오류는 [Troubleshooting](PROJECT_OWNER_TROUBLESHOOTING.md), 숫자·명령표는 [Cheatsheet](PROJECT_OWNER_CHEATSHEET.md)를 보세요.

## 1. 설치 없이 먼저 보기

[Live Demo](https://korea-climate-explorer.streamlit.app/) → Home → NASA × KMA Validation → Period Sensitivity → Methods / Limitations → Research Report 순서로 엽니다. 보고서는 다운로드 후 브라우저로 열 수 있습니다. 키·raw cache는 필요 없습니다.

기억할 숫자는 inventory 105, 장기 Tier A 45(1981–2025), Tier B 6, 공통기간 51(1991–2025), NASA 고유 격자 34입니다. 지점 중앙값은 면적가중 국가 평균이 아닙니다. 상관이 높아도 오차가 있고, 기간별 기울기 차이는 가속도 증명이 아닙니다.

## 2. 기존 Mac 환경에서 공개 앱 켜기

Finder에서 README·main.py·docs가 있는 프로젝트 폴더를 찾습니다. `<PROJECT_ROOT>`를 실제 경로로 바꾸어 터미널에서 실행하세요. 개인 경로는 외부에 공유하지 않습니다.

```bash
cd "<PROJECT_ROOT>"
source .venv/bin/activate
python --version
python -m pip check
python -m streamlit run public_app/streamlit_app.py
```

정상: pip check에 충돌 없음, 터미널에 Local URL, 브라우저에 7개 메뉴. 종료: 실행 터미널에서 Ctrl+C, 그다음 `deactivate`. 환경이 없거나 패키지가 없으면 [Handbook Part VII](PROJECT_OWNER_HANDBOOK.md#part-vii--몇-달-뒤-mac에서-다시-실행하기)의 새 설치 절차를 따릅니다. 공개 데모 검증 Python은 3.13입니다.

## 3. 테스트와 full mode는 환경을 구분

| 준비된 환경 | 명령 | 기대 결과·실패 시 |
|---|---|---|
| 경량 공개 설치+pytest | `python -m pytest tests/test_public_demo.py -q` | public 시험 통과; 패키지·payload 확인 |
| 원래 전체 연구 archive+의존성 | `python -m pytest -q` | 전체 회귀 통과; 실패 근거 보존 |
| 같은 전체 연구 환경 | `APP_MODE=full python -m streamlit run streamlit_app.py` | 18페이지; 누락 archive는 별도 복원 |

공개 clone만으로 전체 연구 테스트 통과를 보장하지 않습니다. 기존 정상 기준은 776개이며 현재 문서 검증 결과는 로컬 handbook manifest를 확인합니다. `python main.py`나 `--all`은 단순 열람이 아닙니다. 수집·재계산·결과 재작성이 될 수 있어 이번 운영에는 실행하지 않습니다.

## 4. 문제가 생겼을 때 첫 다섯 확인

프로젝트 루트에서 한 줄씩 실행합니다. 읽기 전용이지만 개인 경로는 공유 전에 가립니다.

```bash
pwd
git status --short --branch
git rev-parse --show-toplevel
git remote -v
git log -1 --oneline
```

위치가 맞고 origin이 [공식 GitHub](https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer)인지 확인합니다. 그다음 Python 환경·public/full·첫 오류를 확인하세요. 지우기·force push·API 재호출부터 시작하지 않습니다.

## 5. 공개 전의 다섯 금지

- `.env`, API key, SSH private key, PAT, 개인 이메일·경로를 올리지 않기.
- raw·processed·기존 결과와 manifest를 손으로 고치지 않기.
- 결측을 임의로 0으로 바꾸지 않기.
- `git add .` 대신 검토한 파일만 stage하기.
- [v1.1.0 Release](https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer/releases/tag/v1.1.0)의 tag를 움직이거나 force push하지 않기.

[문서 색인](INDEX.md) · [용어사전](PROJECT_OWNER_GLOSSARY.md)
