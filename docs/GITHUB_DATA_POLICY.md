# GitHub Data Policy

## 코드와 데이터의 권리 분리

코드는 사용자가 승인한 [MIT License](../LICENSE)를 적용합니다. 저작권자는 LICENSE에 명시합니다. 코드 라이선스는 NASA·KMA·KHOA 자료의 권리를 자동 변경하지 않습니다. 원자료 재배포는 별도 검토 대상입니다.

## 공식 데이터 출처

NASA POWER: NASA Langley Research Center의 POWER 프로젝트(Earth Science Division 지원), Daily Point 서비스. 기온 변수 T2M/T2M_MAX/T2M_MIN, 단위 °C, 요청 시간기준 LST. KMA ASOS: 기상청 지상(종관, ASOS) 일자료 조회서비스, 지점 일평균·최고·최저기온(°C). KHOA coastline: 해양수산부 국립해양조사원 해안선. 해안거리 단위 km. 데이터의 서비스 버전·취득일은 보존된 원본 metadata/manifest를 기준으로 하며 누락 정보는 추정하지 않습니다.

- [NASA POWER referencing](https://power.larc.nasa.gov/docs/referencing/)

- [KMA ASOS service](https://www.data.go.kr/data/15059093/openapi.do)

- [KHOA coastline](https://www.data.go.kr/data/15083948/fileData.do)

## 공식 조건 확인

NASA는 프로젝트와 데이터 출처, 서비스명·버전·접근일을 함께 표기하고 출판·재배포 알림을 요청합니다. KMA ASOS 포털 표시는 공공저작물 출처표시 제1유형입니다. KHOA 해당 해안선 포털 표시는 이용허락범위 제한 없음입니다. 이 조건을 다른 데이터셋이나 코드에 일반화하지 않습니다. 공식 문서 확인은 자료 API 재호출이 아닙니다.

## 취득 metadata

취득일·제품버전·좌표계·해안선 파일 해시는 기존 metadata와 coastline manifest에 있는 값만 사용합니다. 최종 fact manifest의 mtime은 취득일이 아닙니다. 누락된 서비스 버전은 UNKNOWN으로 남기고 임의 채우지 않습니다. 공개 전 상세 인용문은 사용하는 cache별 metadata와 대조해야 합니다.

## 기본 제외와 보존

data/의 19단계 기록상 논리적 파일 크기는 1,514,480,883 bytes입니다. 현재 보존 크기는 새 release manifest에서 확인합니다. 이 수치는 디스크 할당 크기가 아니라 파일 size 합계입니다. raw·processed·공식 geometry는 .gitignore로 기본 제외하며 삭제하지 않습니다. 전체 output은 public_demo의 최소 명시적 파일만 허용하며 기존 final package도 첫 commit에서는 제외합니다.

## 선택 공개

COMMIT: public_demo의 fact/evidence/Executive Summary 사본과 해시 manifest, 대표 그림 3개. OPTIONAL: 전체 final 보고서와 추가 그림·요약. DO_NOT_COMMIT: 원자료·가공 cache·QA·로그·개인 환경 snapshot. 원자료 샘플은 추가하지 않았습니다. 요약도 데이터 출처와 proxy·표본 한계를 함께 표시합니다. 전체 분류는 [공개 계획](GITHUB_PUBLICATION_PLAN.md)을 따릅니다.

## 코드 라이선스와 공개 단계

[MIT 표준문구](https://opensource.org/license/mit)를 적용했으며 저작권자와 공개용 Git identity는 사용자가 명시적으로 승인했습니다. 현재 범위는 첫 로컬 commit까지입니다. GitHub 저장소 생성·remote·push·tag·Release는 후속 단계입니다.
