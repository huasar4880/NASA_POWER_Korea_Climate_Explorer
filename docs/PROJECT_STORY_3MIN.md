# Project Story — 약 3분 설명 개요

## 문제

기온이 올랐다는 그래프만으로는 기관·지점·기간이 달라질 때 어떤 결론을 유지할 수 있는지 알기 어려웠습니다.

## 데이터

공식 inventory 105 <!-- fact:inventory_n -->개, Tier A 45 <!-- fact:tier_a -->개, Tier B 6 <!-- fact:tier_b -->개, 공통기간 51 <!-- fact:common_n -->개 지점 및 NASA 고유 격자 34 <!-- fact:grid_n -->개. 장기 1981-01-01~2025-12-31 <!-- fact:long_period -->, 공통기간 1991-01-01–2025-12-31 <!-- fact:common_period -->, normal 1991–2020 <!-- fact:normal -->. 원본 cache와 정제 결과를 분리하고 실제 품질조건으로 관측망을 선별했습니다.

## 파이프라인

도시별 복사 코드를 늘리는 대신 공통 수집·정제·검정 함수를 사용하고 단계별 결과를 별도 보존했습니다.

## 분석

효과크기와 유의성, 일별 오차와 장기 방향, 공간구조와 해안 연관을 구분했습니다.

## 예상 밖의 문제

### 격자 중복

**Situation:** 여러 관측소가 같은 NASA 격자와 연결되어 공간구조를 독립 관측소 결과처럼 해석할 위험이 있었습니다.

**Task:** 관측소 연결과 고유 격자 표현의 차이를 분리해야 했습니다.

**Action:** native 중심 추정과 같은 일시계열 검증을 거쳐 두 공간표현의 저장 결과를 비교하고 표본수와 해시를 기록했습니다.

**Result:** 공통기간 51 <!-- fact:common_n -->개 지점은 34 <!-- fact:grid_n -->개 NASA 격자에 연결됐습니다. 양의 공간구조는 유지되지만 Moran 크기는 달라졌습니다.

### 기간 민감성

**Situation:** 장기 분석의 공간군집을 공통기간으로 옮기자 같은 결론이 유지되지 않았습니다.

**Task:** 관측소 집합 변화와 기간 변화가 뒤섞이지 않도록 검증해야 했습니다.

**Action:** Tier A 집합과 종료연도를 고정한 시작기간 비교를 별도 namespace에서 수행하고 이전 결과를 보호했습니다.

**Result:** TAVG 상승 방향은 45 <!-- fact:stability_TAVG_positive_all_count -->개 Tier A 지점에서 모든 기간에 유지됐지만 군집 방향과 기울기 크기는 민감했습니다.

### 수치 불안정

**Situation:** 공간모형에서 라이브러리의 수렴 표시만으로 신뢰하기 어려운 경계·solver 차이가 발견됐습니다.

**Task:** 좋은 결과만 선택하지 않고 기존 결론의 사용 가능 범위를 분류해야 했습니다.

**Action:** 관측소 정렬, 스펙트럼 허용구간, likelihood, solver와 잔차를 검토하고 HC3를 별도 추론으로 유지했습니다.

**Result:** 수치 불안정 13 <!-- fact:model_count_NUMERICALLY_UNSTABLE -->개 및 실패 1 <!-- fact:model_count_FAILED -->개 조합을 명시적으로 남겨 핵심결론에서 제외했습니다.

## 강건성

올랐다는 방향은 일관됐지만 어느 지역이 더 빠른지, 그 속도가 얼마나 되는지는 조건에 민감했습니다. 검증 결과는 성공·비유의·실패를 함께 기록했습니다.

## 성과

원자료에서 보고서 문장까지 출처를 추적하는 fact layer, 회귀 테스트와 읽기 전용 UI로 전달했습니다. 이 설명은 실제 담당 역할에 맞게 조정하며 자료의 한계와 미실행 기능을 숨기지 않습니다.

GitHub v1.1.0 Release와 [Streamlit 공개 배포](https://korea-climate-explorer.streamlit.app/)를 완료했습니다. 검증된 공개 파일만으로 실행되는 reproducible demo는 API 키·raw cache 없이 열람할 수 있고, 전체 연구 파이프라인은 별도 archive를 사용하는 모드로 보존했습니다. [공개 결과물 링크](PUBLIC_PORTFOLIO_LINKS.md).
