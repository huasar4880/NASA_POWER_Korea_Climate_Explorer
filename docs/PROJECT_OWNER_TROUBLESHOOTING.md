# Project Owner Troubleshooting

증상부터 찾는 운영 가이드입니다. 아래 대응은 기존 결과를 보존하는 진단 순서입니다. 새 자료 수집·결과 재생성·인증설정 변경·이력 수정은 각각 영향과 권한을 확인한 뒤 별도로 결정합니다. [전체 설명서](PROJECT_OWNER_HANDBOOK.md) · [Quickstart](PROJECT_OWNER_QUICKSTART.md).

## 먼저: 이 다섯 명령으로 위치를 확인

프로젝트 폴더의 로컬 터미널에서 실행합니다. 파일을 수정하지 않지만 출력 경로에 개인정보가 있을 수 있어 공유 전 가립니다.

```bash
pwd
git status --short --branch
git rev-parse --show-toplevel
git remote -v
git log -1 --oneline
```

루트 이름과 origin이 NASA_POWER_Korea_Climate_Explorer인지 확인하세요. 이어서 `python --version`, `python -m pip check`로 환경을 확인합니다. `git status`에 모르는 수정이 있으면 삭제하지 않습니다. 오류 보고에는 목적·모드·commit·첫 오류를 기록하고 키·개인 경로는 제외합니다.

## 증상 색인

| 증상 | 아래 항목 |
|---|---|
| 앱이 안 켜져요 / ModuleNotFoundError / 가상환경·pip | 01–04 |
| 파일이 없어요 / 결과 무결성 오류 / 보고서 링크 | 05–07 |
| API key / KMA 403·429·22·23 / NASA 장애 | 08–11 |
| push·GH007·SSH / 다른 repository | 12–15 |
| Cloud 로그인·OAuth·공개 범위·sleep·build | 16–19 |
| 새 공개 파일 때문에 시험 실패 / devcontainer | 20–21 |
| 숫자가 다름 / 테스트 실패 / 과거 결과 변경 의심 | 22–24 |

## 01. “Streamlit 앱이 안 켜져요”

**확인:** 브라우저보다 실행 터미널의 첫 오류를 봅니다. 프로세스가 계속 실행 중이고 Local URL만 있다면 정상 서버 상태일 수 있습니다.

**대응:** 루트·가상환경을 확인한 뒤 `python -m streamlit run public_app/streamlit_app.py`로 공개 모드를 실행합니다. 실제 출력 URL을 브라우저에서 엽니다. 종료는 해당 터미널 Ctrl+C입니다. 포트가 사용 중이면 본인이 실행한 이전 서버인지 확인하고 종료한 뒤 재시작합니다.

**중단 기준:** 원인을 모르는 프로세스를 강제 종료하거나 방화벽을 끄지 않습니다. 데이터 분석 재실행은 앱 시작 문제의 첫 해결책이 아닙니다.

## 02. “ModuleNotFoundError가 나요”

**확인:** `python -m pip --version`의 환경과 public/full을 확인합니다. 공개 설치에서 full 모듈이 없는 것은 설치 범위 차이일 수 있습니다.

**대응:** public이면 `public_app/requirements.txt`, full이면 루트 `requirements.txt`를 준비한 별도 환경에서 설치합니다. 설치 후 pip check와 해당 시험을 실행합니다. 이 명령은 환경을 변경하므로 동작 중인 환경의 무작위 업그레이드는 피합니다.

**중단 기준:** 시스템 Python에 `sudo pip`로 덧붙이지 않습니다. 여러 Python을 섞어 쓰는 문제가 먼저 해결돼야 합니다.

## 03. “가상환경 활성화가 안 돼요”

**확인:** 올바른 폴더에 `.venv/bin/activate`가 있는지 Finder에서 봅니다. 새 터미널마다 활성화가 필요합니다.

**대응:** 기존 환경이면 `source .venv/bin/activate`. 환경이 없으면 [Handbook의 새 설치](PROJECT_OWNER_HANDBOOK.md)를 따라 호환 Python으로 새 환경을 준비합니다. 프롬프트 표시만 보지 말고 Python/pip도 확인합니다.

**중단 기준:** 원래 `.venv`나 연구 archive를 삭제하지 않습니다. 운영체제가 달라진 환경은 그대로 복사한 venv가 작동하지 않을 수 있습니다.

## 04. “pip dependency conflict가 나요”

**확인:** `python -m pip check`의 요구·설치 버전 차이를 기록합니다. 공개 runtime의 고정 버전과 연구용 범위형 requirements는 목적이 다릅니다.

**대응:** 새 가상환경에서 해당 requirements를 설치하고 테스트합니다. 공개 데모 clean-room 기준은 Python 3.13입니다. 설치한 Cloud 서버의 정확한 버전은 로그에서 따로 확인해야 합니다.

**중단 기준:** 충돌을 무시하거나 과거 연구환경 전체를 최신화하지 않습니다. 의존성 변경은 별도 유지보수입니다.

## 05. “data file not found가 나요”

**확인:** public payload 누락인지 private 연구 archive 누락인지 구분합니다. 공개 clone에는 대부분의 data/output이 없습니다.

**대응:** 공개 모드라면 필요한 tracked 파일을 같은 commit 기준으로 확인합니다. full이면 로컬 백업과 재현 가이드의 archive 조건을 확인합니다. 공개 provenance의 source_file이 GitHub에 없는 것은 정상일 수 있습니다.

**중단 기준:** 빈 CSV나 0값으로 화면만 채우지 않습니다. 자료가 없다고 자동 NASA/KMA 수집을 시작하지 않습니다.

## 06. “Public result package integrity check가 실패해요”

**확인:** 공개 manifest와 11개 payload가 같은 검증 묶음인지 확인합니다. 방법/한계 Markdown도 payload입니다.

**대응:** Git diff와 checksum을 비교해 파일 변경·손상·다른 버전 혼합을 찾습니다. 승인된 사본 복구 또는 정식 payload 갱신 절차가 필요합니다.

**중단 기준:** 오류를 없애려고 manifest hash만 현재 값으로 바꾸지 않습니다. 보호장치 우회가 됩니다.

## 07. “보고서 링크가 안 열려요”

**확인:** GitHub blob 페이지의 소스 보기와 실제 HTML 문서를 구분합니다.

**대응:** [Live Demo](https://korea-climate-explorer.streamlit.app/)의 Research Report에서 HTML을 다운로드하고 브라우저로 엽니다. [공개 사본](../output/public_demo/deployment/Final_Research_Report.html)은 그림을 포함합니다. 로컬 원래 보고서 파일명과 공개 사본 이름은 다릅니다.

**중단 기준:** private 절대경로를 공개 링크로 바꾸어 붙이지 않습니다. 보고서 재생성으로 링크 문제를 해결하지 않습니다.

## 08. “API key 오류가 나요”

**확인:** 공개 앱은 키가 필요 없습니다. 수집을 의도했는지부터 확인하세요. 현재 KMA client는 환경변수 `KMA_API_KEY`를 읽으며 `.env` 존재만으로 자동 전달을 보장하지 않습니다.

**대응:** 별도 수집이 승인된 상황에서 로컬 환경 전달, 활용신청 서비스, 키 활성화 상태를 확인합니다. encoded 키에 추가 encoding을 적용하지 않습니다. 존재 여부 확인과 실제 권한 확인은 다릅니다.

**중단 기준:** 키를 화면·명령·로그·Issue에 출력하지 않습니다. 인증을 시험한다며 8도시 전체 요청을 실행하지 않습니다.

## 09. “KMA 403이 나요”

**확인:** HTTP status와 공공데이터포털 resultCode/resultMsg를 민감정보 제거 후 읽습니다. XML/JSON 오류 body가 HTTP 200 안에 있을 수도 있습니다.

**대응:** 서비스 권한·키 등록/활성화·endpoint·파라미터 대소문자·encoded/decoded 처리·제공기관 장애를 분리합니다. 현재 client의 `ServiceKey` 정규화 규칙을 확인합니다.

**중단 기준:** 403 하나로 원인을 확정하지 않습니다. key 존재 True도 권한의 증거가 아닙니다. 원인 확인 없는 반복 호출은 중단합니다.

## 10. “KMA 429 또는 code 22/23이 나요”

**확인:** code 22는 일일 호출량 초과, code 23은 초당 제한 오류로 구분합니다. HTTP 429는 속도/제한 관련 응답일 수 있어 공식 코드도 봅니다.

**대응:** 23/429에는 현재 client의 간격·제한된 backoff를 따릅니다. 22는 멈추고 제공기관이 허용하는 다음 시점에 완료 cache를 유지한 채 재개합니다. 10년 이하 chunk·999행 pagination 때문에 도시 하나에도 여러 요청이 생깁니다.

**중단 기준:** 다른 키·계정으로 한도를 우회하지 않습니다. 성공한 서울이나 완료 chunk를 지우지 않습니다. 일부 미완료 chunk는 다시 요청할 수 있습니다.

## 11. “NASA network error가 나요”

**확인:** DNS·연결·timeout·HTTP 오류와 응답 schema 실패를 구분합니다. 자료 내용 문제와 네트워크 문제는 다른 층입니다.

**대응:** 환경이 복구됐는지 확인한 뒤 승인된 수집 범위에서 제한적으로 재시도합니다. 기존 유효 cache를 보존합니다.

**중단 기준:** 값이나 날짜를 임의로 생성하지 않습니다. 공개 데모 열람 문제를 NASA 서버 재접속으로 해결하려 하지 않습니다.

## 12. “Git push가 403으로 실패해요”

**확인:** origin의 repository, 현재 인증 계정, write 권한을 확인합니다. 브라우저에서 로그인됐다고 터미널 인증까지 같은 것은 아닙니다.

**대응:** 현재 연결 방식(SSH/HTTPS)의 공식 인증 흐름을 확인하고 사용자 직접 승인을 받습니다. 원격이 앞서 있으면 별도 fetch·diff로 이력을 비교합니다.

**중단 기준:** force push, 비밀번호·PAT를 URL에 삽입, 권한 없는 repository의 remote 임의 변경을 하지 않습니다.

## 13. “GH007 이메일 privacy 오류가 나요”

**확인:** 비공개 작성자 이메일의 공개를 차단하는 설정인지 확인합니다.

**대응:** GitHub가 제공하는 noreply와 저장소 로컬 작성자 설정을 검토합니다. 설정 변경은 미래 commit에 적용되며 과거 commit은 자동으로 바뀌지 않습니다. 미공개 commit 수정이 필요하면 공개 이력과 범위를 먼저 확인합니다. [공식 안내](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address).

**중단 기준:** privacy 보호를 무조건 끄거나 공개 commit을 amend/rebase하지 않습니다. 실제 이메일을 도움 요청에 붙이지 않습니다.

## 14. “SSH authentication이 실패해요”

**확인:** 로컬에서 `ssh -T "git"@"github.com"`으로 인증 메시지를 확인합니다. 따옴표는 셸에서 제거되므로 동일한 GitHub SSH 주소로 연결됩니다. 새 host fingerprint는 공식 값과 대조합니다.

**대응:** 공개키 등록·계정·agent를 확인합니다. 성공 인증 후 shell 미제공 안내와 exit 1은 GitHub에서 정상일 수 있습니다. [공식 SSH 시험](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection).

**중단 기준:** `id_ed25519` private key를 읽어 공유하지 않습니다. 인증 성공과 해당 repo 쓰기 권한은 별도입니다.

## 15. “다른 repository에서 실행했어요”

**확인:** git root와 origin 이름을 봅니다. NASA 폴더와 별도 R&D/다른 프로젝트 폴더가 함께 있을 때 특히 확인하세요.

**대응:** 추가 명령을 멈추고 실제 변경·stage 여부를 읽기 전용으로 기록한 뒤 올바른 폴더로 이동합니다. 이미 생긴 변경은 소유권·내용을 검토해 처리합니다.

**중단 기준:** 잘못된 위치의 origin을 NASA로 바꾸거나 broad reset·삭제로 흔적을 없애지 않습니다.

## 16. “Cloud 관리 로그인이 안 돼요”

**확인:** 익명 방문자 열람과 소유자 관리 화면을 구분합니다.

**대응:** 소유자가 직접 정상 계정으로 로그인하고 repository owner에 맞는 workspace를 선택합니다. 일반 방문자는 공개 URL만 필요합니다.

**중단 기준:** 관리 세션·쿠키·비밀번호를 대화나 repository에 넣지 않습니다. 로그인 문제를 앱의 KMA 키로 해결할 수 없습니다.

## 17. “GitHub OAuth 승인이 떠요”

**확인:** 요청 서비스·계정·대상 repository·권한을 봅니다.

**대응:** 사용자가 브라우저에서 직접 허용 여부를 결정합니다. 기존 연결 계정이 다른지 먼저 확인합니다.

**중단 기준:** 편의를 위해 필요 없는 저장소 전체 권한이나 credential 전달을 제안하지 않습니다.

## 18. “공개 앱인데 로그인하라고 해요”

**확인:** 시크릿 창의 Live URL과 Cloud Sharing 상태를 비교합니다. 소유자만 보이는 상태인지 확인합니다.

**대응:** 의도된 공개 범위에 맞게 사용자가 Sharing을 확인합니다. [공식 public/private 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app).

**중단 기준:** 원자료를 공개하면 로그인 문제가 해결된다고 생각하지 않습니다. 삭제·중복 앱 생성부터 시작하지 않습니다.

## 19. “앱이 자거나 배포가 멈춘 것 같아요”

**확인:** sleep 안내인지 build/runtime 오류인지 구분하고 관리 로그를 봅니다.

**대응:** 잠든 앱은 화면의 깨우기 안내를 따릅니다. build는 main·entrypoint `public_app/streamlit_app.py`·동일 폴더 requirements를 확인합니다. 의존성 변경은 재설치가 필요할 수 있습니다. [공식 앱 관리](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app).

**중단 기준:** 몇 초마다 reboot하지 않습니다. HTTP 200만 보고 모든 view가 정상이라고 보고하지 않습니다.

## 20. “새 공개 파일 때문에 security test가 실패해요”

**확인:** 실제 경로·크기·비밀·개인 경로·공개 필요성과 `classify` 결과를 봅니다. docs 확장자와 output manifest의 허용 규칙은 다릅니다.

**대응:** 허용범위 밖이면 로컬에 두거나 사용자의 exact-path 공개 승인을 받습니다. 기존 승인 예외는 devcontainer 파일과 공개 배포 manifest 두 경로뿐입니다. owner handbook manifest는 로컬입니다.

**중단 기준:** `.devcontainer/**`, `output/**` 같은 wildcard를 추가하거나 시험을 삭제하지 않습니다. `git add -f`는 공개 승인 자체가 아닙니다.

## 21. “devcontainer issue가 있어요”

**확인:** 개발 이미지·의존성·lifecycle 명령의 실제 오류를 봅니다. 현재 이미지 3.11과 공개 검증 3.13은 다릅니다.

**대응:** devcontainer는 Cloud 앱 설정과 별개입니다. 필요한 수정만 별도 승인·검증합니다. 이미 제거된 CORS/XSRF disable과 자동 시스템 upgrade를 되살리지 않습니다.

**중단 기준:** privileged·Docker socket/host mount나 위험한 lifecycle 명령을 추가하지 않습니다. 모든 보안을 끄는 우회는 하지 않습니다.

## 22. “두 문서의 숫자가 달라요”

**확인:** 지점 수, 기간, source, metric, OLS/Sen, raw p/FDR, station/grid, median/pooled, 표시 반올림을 비교합니다.

**대응:** [fact layer](../output/public_demo/final_research_fact_layer.csv)의 fact_id와 source_row/key·column을 따라갑니다. 45개 1991 결과와 51개 1991 결과, TMIN/TMAX contrast와 DTR는 같은 계산이 아닙니다.

**중단 기준:** 숫자를 맞추려고 CSV를 고치지 않습니다. 역사적 문서 차이는 documentation discrepancy로 기록합니다.

## 23. “pytest가 실패해요”

**확인:** 전체 연구 환경인지 경량 clone인지, 첫 failure와 missing dependency/archive인지 봅니다. warnings와 failures를 구분합니다.

**대응:** 실패한 시험명·환경·commit을 기록하고 해당 원인을 좁힙니다. 코드 수정이 필요하면 최소 범위로 변경하고 전체 suite를 다시 실행합니다.

**중단 기준:** 통과 수를 맞추려고 skip·테스트 삭제·실제값 수정하지 않습니다. 저장 QA baseline이 없는데 새로 만들어 과거 검증을 흉내 내지 않습니다.

## 24. “기존 연구 결과가 바뀐 것 같아요”

**확인:** 작업 전 snapshot의 SHA256·mtime과 현재를 비교합니다. Git만으로 gitignored 연구 파일 변경을 모두 확인할 수는 없습니다.

**대응:** 추가 쓰기를 멈추고 어느 실행이 결과를 재생성했는지 기록합니다. 백업은 원본을 덮어쓰지 않는 별도 위치에서 비교합니다.

**중단 기준:** 새 snapshot으로 기준을 바꾸거나 mtime을 조작하지 않습니다. 이전 결과 복구·재생성은 차이와 권한을 확인한 뒤 별도 처리합니다.

> 진단의 원칙: 위치→환경→실행모드→입력→오류코드→최소 대응 순서입니다. 비밀정보와 실패 증거를 보호하고, 관측값을 만들거나 검증 기준을 낮추지 않습니다.
