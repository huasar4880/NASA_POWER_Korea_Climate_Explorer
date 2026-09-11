# Changelog

이 프로젝트의 주요 공개 버전 변경사항을 기록한다.

## [1.1.0] - 2026-09-11

- Public Release 로컬 준비: 사용자 승인 MIT License, repository-local 공개 Git identity, 기존 연구 결과 보존 및 첫 commit 검증. GitHub remote / push / tag / Release는 후속 단계입니다.

### Added

- 전국 ASOS screening, Tier A/B와 51개 관측소 공통기간 분석
- NASA grid sharing, station-linked / unique-grid 공간구조 비교
- 공간가중치·해안거리·공간보정 모형·수치 안정성·기간 민감성 검토
- 저장 결과에서 추적 가능한 final research package, 포트폴리오, 근거표와 대표 그림
- 경량 `output/public_demo/`와 cache 없는 Home 요약, 독립적인 공개용 offline 테스트

### Changed

- VERSION 1.0.0 → 1.1.0: 초기 8개 도시 stable에서 전국 연구 플랫폼으로 공개 버전 확정
- 원본·가공 데이터와 기존 연구 output은 로컬 유지, Git 공개 파일은 명시적 allowlist로 분리
- 과거 manifest의 1.0.0은 생성 당시 버전으로 보존; 현재 릴리스 메타데이터와 구분
- README·설치/재현/공개 정책 정리 및 기존 안전성 테스트의 읽기 전용 검사

### Validated

- 릴리스 변경 전 기존 711개 pytest 통과 및 pip check 정상
- 최종 회귀·공개 안전성·보존 검증 결과는 [Release Checklist](docs/RELEASE_CHECKLIST.md) 참조
- 연구 수치는 기존 fact layer / manifest가 근거이며 이 단계에서 재추정하지 않음

### Known Limitations

- NASA 격자 / ASOS 지점 대표성, 관측소 집합·기간·가중치 민감성, 공간모형 수치 불안정 유지
- 관측소 중앙값은 면적가중 전국 평균이 아니며 연관을 인과 또는 가속화로 단정하지 않음
- 경량 저장소는 전체 cache와 실자료 회귀 테스트 환경을 포함하지 않음
- Code License: MIT. 데이터 이용조건은 별도이며, 공개 remote / push / release tag는 이번 로컬 작업 범위 밖임

아래 Unreleased 항목은 1.1.0 이전 단계별 개발 기록입니다. 당시의 VERSION·Git 상태 표기는 역사적 기록입니다.

## [Unreleased] — final research package / v1.1.0 candidate review

- 전국 screening, Tier A/B와 공통기간 분석, 공간가중치·해안·격자 중복 검토를 최종 근거표로 통합
- SAR/SEM 수치 불안정과 HC3 해석을 보존하고 시작기간 민감성을 최종 방법론 결과로 제시
- 저장된 CSV/manifest에서 추적 가능한 final fact layer, evidence matrix 및 선택 그림 registry 생성
- 최종 HTML/Markdown 연구보고서, Executive Summary, 연구·기술 포트폴리오와 면접·이력서 문서
- 기존 Dashboard 페이지와 URL을 유지하며 Home·메뉴·Reports의 정보구조 정리
- 공개 파일 allowlist, 비밀·개인경로 검사, 데이터 정책, 보호파일 hash/mtime 및 실제 QA gate
- API 재호출·기존 분석 재추정·VERSION 변경·git init/remote/push 없음
- 코드 라이선스와 공개 여부는 사용자 승인 사항이며 실제 release가 완료됐다는 표시는 아님

## [Unreleased] — nationwide experimental expansion

- Final Tier A Stage-11 결과 전용 Haversine/KNN 전국 공간분석 namespace
- 8개 Global Moran, 5개 Local Moran와 BH-FDR, k=3/4/5 sensitivity
- 위도·경도·고도 연관, Tmax/Tmin contrast, DTR, 계절·threshold·Bias/RMSE 공간요약
- 보간 없는 14개 interactive station map(계절 4종 포함), 9개 PNG, 12번째 Streamlit 공간패턴 페이지
- deterministic HTML/Markdown 보고서와 input hash·seed 기반 spatial manifest
- 공식 coastline 후보/라이선스는 확인했으나 local geometry 검증 전 해안/내륙 분석 보류
- NASA/KMA API 호출 없이 44개 공간분석 테스트 추가, stable VERSION 1.0.0 유지

- 공식 KMA ASOS station metadata CSV 수집·cache 및 ASOS-only inventory
- station history·인접 후보·continuity risk를 자동 연결 없이 review flag로 분리
- 전 station 일자료 availability probe와 metadata Tier A/B 후보 상세 기온 screening
- 윤년 달력, 변수별 결측률, 연 completeness, 7/30/90일 gap과 표준 reason code
- station/chunk cache, 재시작 state, 실제 cache를 반영한 dry-run 호출량 산정
- 전국 station master, A/B shortlist, 제외·지역·고도·품질표와 interactive inventory map
- 읽기 전용 Streamlit 전국 ASOS 페이지와 28개 네트워크 없는 단위 테스트
- stable VERSION과 v1.0 분석 데이터·결과는 변경하지 않음

## [1.0.0] - 2026-09-04

- NASA POWER Daily API 수집·cache·정제 pipeline
- 1981–2025년 대한민국 주요 8개 도시 다변수 기후분석
- 선형회귀, Mann–Kendall, Modified MK, Sen's slope와 BH-FDR 통계분석
- 1991–2020 normal, anomaly, 계절분석과 기후지표 proxy
- KMA ASOS 8개 관측소 및 7개 변수 교차검증
- 데이터 품질검사와 강릉 105/104 continuity 검증
- 9페이지 Streamlit 대시보드
- source-addressable Fact Layer 기반 HTML/Markdown 자동 보고서
- 120개 pytest 회귀 테스트와 v1.0 공개 안전성 검사
- Architecture, Pipeline, Methodology, Results, Portfolio와 데이터 공개정책 문서

[1.0.0]: ./docs/V1_STATUS.md
