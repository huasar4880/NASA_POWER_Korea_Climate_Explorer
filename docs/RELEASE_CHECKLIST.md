# Release Checklist — v1.1.0

## 현재 공개 상태

- [x] GitHub repository 공개
- [x] main push
- [x] MIT License
- [x] v1.1.0 tag — 기존 공식 release commit에 고정
- [x] GitHub Release 발행
- [x] Streamlit Community Cloud deployment
- [x] anonymous/public access verified — 사용자 시크릿 브라우저 확인 및 에이전트의 로그인 없는 Home·7개 메뉴 확인
- [x] README Live Demo 및 공개 포트폴리오 링크 연결

[Live Demo](https://korea-climate-explorer.streamlit.app/) · [Repository](https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer) · [Release](https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer/releases/tag/v1.1.0).

직전 공개 데모 준비 검증은 기존 743개 + 공개 모드 21개 = 전체 764개 통과입니다.
최종 링크 통합·보안 수정 후 기존 764개 + exact-path 및 개발컨테이너 보안 회귀 12개 = 전체 776개가 통과했습니다. pip check 정상, 기존 경고 2개 외 실패·skip은 없습니다.
배포·링크 통합 회귀 결과는 [공개 배포 manifest](../output/final/release/v1.1.0_public_demo_deployment_manifest.json)에 기록합니다. 내부 QA·snapshot은 공개하지 않습니다.
기존 연구 artifact와 tag를 보존하고 문서 변경만 main에 추가합니다. v1.1.1은 발행하지 않습니다.

## 과거 준비 검증 기록

다음 수량은 당시의 검증 기록입니다. 2026-09-11 로컬 실행에서 기존 711개 + 신규 29개 = 전체 740개 pytest가 통과했습니다. 신규 테스트는 공개용 26개와 로컬 보호 검증 3개입니다. 기존 synthetic MK fixture의 RuntimeWarning 2건 외 실패·skip은 없습니다.

21단계 MIT 적용 후 재검증: 기존 740개와 공개 identity 보안 테스트 3개, 총 743개 통과.
의존성 검사 정상, 외부 HTTP 시도 0건. 현재 공개 파일 235개이며, 이전 단계의 수량은 역사적 검증 기록입니다.

- [x] 기존 711개 테스트 기준선 통과
- [x] 변경 전 pip check 정상
- [x] 19단계 완료 manifest와 231개 artifact hash 확인
- [x] 기존 data/output 2,098개 SHA256·mtime 기준선 저장
- [x] 승인된 VERSION 1.0.0 → 1.1.0, 역사적 연구 버전 보존
- [x] README·CHANGELOG·경량 공개 정책·재현 절차
- [x] 최종 전체 pytest 740/740 및 신규 release 테스트 통과
- [x] 최종 pip check: No broken requirements found
- [x] 공개 후보 secret / 개인경로 / 링크 / 크기 검사: 발견 0건
- [x] 연구 artifact 2,098개 content / mtime 변경 0건
- [x] Dashboard 18페이지·상호작용·router 및 기존 보고서 검사
- [x] archive 없는 임시 공개 사본의 26개 테스트·Home 정상, 외부 HTTP 차단
- [x] 선택 staging 234개 파일·.env / data / QA / 대용량 제외 확인
- [x] 로컬 Git main 초기화, Git identity 존재 여부만 안전하게 확인
- [x] Git identity: 사용자 승인 공개 이름·GitHub noreply, repository-local 설정만 적용
- [x] 첫 로컬 commit 사전 검증: MIT·identity·전체 테스트·staging 안전성 확인
- [x] Choose code license before public GitHub push — MIT, 사용자 지정 저작권자
- [x] GitHub repository 사용자 결정 — 후속 단계 완료
- [x] Remote 연결 사용자 승인 — 후속 단계 완료
- [x] Push 사용자 승인 — 후속 단계 완료
- [x] Tag / GitHub Release 사용자 승인 — 후속 단계 완료
- [ ] 공개 자료 인용·Git 작성자 metadata 최종 사용자 확인

Code License: [MIT](../LICENSE). 데이터 제공기관의 권리·출처표시는 별도입니다.
기존 preparation/public-release 중단 기록은 보존합니다. 현재 로컬 commit 검증은
`output/final/release/v1.1.0_local_commit_verification.json`에 별도로 기록합니다.
실제 commit 생성 여부와 hash는 commit 이후 작성되는 위 로컬 검증 파일을 따릅니다. commit에 포함되는 문서는 자기 commit hash를 포함하지 않습니다.
Git identity는 사용자 지정 정보만 local 설정에 사용했습니다. 과거 로컬 검증 파일은 생성 당시의 상태를 유지합니다.
[파일 목록](GITHUB_STAGED_FILE_PREVIEW.txt)은 현재 공개 후보를 나타냅니다. 실제 공개 상태는 위 현재 공개 상태와 링크를 따릅니다.
