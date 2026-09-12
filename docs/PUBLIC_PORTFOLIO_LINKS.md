# Public Portfolio Links — v1.1.0

## 1. Live Dashboard

[Streamlit 공개 대시보드](https://korea-climate-explorer.streamlit.app/)

채용담당자와 연구 결과를 빠르게 살펴볼 독자에게 권합니다. 로그인·API 키·원자료 설치 없이 검증된 기온 추세, NASA–KMA 비교, 공간·기간 민감성의 핵심 결과를 7개 화면에서 확인할 수 있습니다.

## 2. GitHub Repository

[NASA POWER Korea Climate Explorer](https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer)

개발자·기술 면접관이 구현 구조, 테스트, 재현 절차를 확인할 때 사용합니다. 전체 연구 파이프라인과 공개 데모 코드는 포함하지만 대용량 원자료·cache는 배포하지 않습니다. 전체 연구 실행에는 별도 archive가 필요합니다.

## 3. v1.1.0 Release

[공식 v1.1.0 Release](https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer/releases/tag/v1.1.0)

공개 버전의 범위와 고정된 소프트웨어 기준점을 확인할 때 사용합니다. 데모·문서 개선은 후속 main에 추가됐으며, 기존 v1.1.0 tag는 원래 공식 release commit에 고정되어 있습니다.

## 4. Final Research Report

[공개 HTML 연구보고서](../output/public_demo/deployment/Final_Research_Report.html)

방법·수치·그림과 해석상의 한계를 자세히 읽을 연구자·면접관에게 권합니다. GitHub에서는 파일을 내려받아 브라우저로 열거나 Live Dashboard의 Research Report 화면에서 다운로드하세요. 보고서는 그림을 자체 포함하며 원자료 다운로드나 재분석 없이 읽을 수 있습니다.

## 활용 순서와 주의사항

Live Dashboard → [Executive Summary](../output/public_demo/EXECUTIVE_SUMMARY.md) → 보고서 → 소스·테스트 순서로 볼 수 있습니다. 공개 데모는 validated precomputed results의 전달 도구이며 전체 연구 재현을 대체하지 않습니다.
관측소 표본은 면적가중 전국 평균이 아니며, threshold는 분석 proxy이고 공간 연관은 인과관계가 아닙니다. [방법](FINAL_METHODS_SUMMARY.md) · [한계](FINAL_LIMITATIONS.md).
