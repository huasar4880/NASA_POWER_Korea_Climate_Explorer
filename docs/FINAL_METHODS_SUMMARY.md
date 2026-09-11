# Final Methods Summary

## 자료 품질

일력·중복·결측·이상범위·연 completeness·관측소 이력을 점검한 기존 screening을 사용합니다. Tier B는 짧은 자료를 장기 Tier A에 접합하지 않고 공통기간에서만 결합합니다. 결측을 임의로 보간하거나 영으로 채우지 않습니다.

## 효과크기와 검정

Sen slope는 연간 값의 시점쌍 기울기 중앙값이며 °C/decade로 환산된 저장값을 사용합니다. Mann–Kendall은 단조 추세 검정입니다. 원 MK의 raw p에 설정된 비교군별 BH-FDR가 주 추론이고, 자기상관 진단과 Hamed–Rao modified MK는 보조 결과입니다. 표본·기간 변경 때 비교군도 함께 확인합니다.

## TMIN/TMAX contrast와 DTR

contrast는 저장된 TMIN Sen 기울기에서 TMAX Sen 기울기를 뺀 값입니다. DTR은 각 지점·자료원·연도의 연평균 TMAX에서 연평균 TMIN을 뺀 연간 시계열에 적합했던 Sen 기울기입니다. 두 기온 Sen 기울기의 차이와 DTR Sen은 같은 연산이 아니므로 서로 대체하지 않습니다. 지점별 contrast의 중앙값도 두 전국 지점 중앙값을 뺀 값과 일반적으로 다릅니다. 단위는 모두 °C/decade입니다.

## Normal·계절·proxy

Climate Normal 1991–2020 <!-- fact:normal --> 대비 anomaly를 사용합니다. 계절은 DJF/MAM/JJA/SON이며 겨울 연도 귀속과 completeness는 기존 방법 문서에 따릅니다. TMAX ≥ 33°C와 TMIN ≥ 25°C 일수는 유효한 matched daily pair의 proxy입니다. 공식 폭염·열대야 정의나 관측시간 조건을 대체하지 않습니다.

## 교차검증

차이를 NASA−KMA로 정의합니다. Bias는 차이 평균, MAE는 절대차 평균, RMSE는 제곱차 평균의 제곱근입니다. Pearson과 Spearman은 각각 선형·순위 동조성을 나타냅니다. 모든 pair는 양쪽 유효일을 기준으로 합니다. 최종 표의 중앙값은 지점별 지표의 중앙값으로, 전체 일자료를 합친 pooled 오차가 아닙니다.

## 공간 통계

Global Moran I는 저장된 순열검정 결과, Local Moran은 다중검정 보정과 패턴 안정성을 함께 읽습니다. 대표 directed KNN과 대칭 KNN·거리 가중치 민감도를 구분합니다. Global/해안 상관의 탐색적 raw p를 지점 추세의 FDR q와 혼용하지 않습니다. 추정 NASA native 중심과 동일 일시계열 검증으로 격자 중복을 점검했습니다.

## 해안·모형 진단

공식 KHOA 해안선으로 계산된 거리와 연속 상관·해안/내륙 구분을 읽습니다. OLS classical p보다 HC3 추론을 우선하고, HC3가 공간상관까지 보정하는 것은 아님을 명시합니다. SAR/SEM은 수렴·경계·스펙트럼·정렬·solver 진단을 통과한 범위에서만 보조 해석합니다. 수치적 실패나 비유의를 삭제하거나 다른 specification의 유의성으로 덮지 않습니다.

## 기간 민감성

동일 Tier A 집합, 고정 종료연도에서 저장된 시작기간을 비교합니다. 기간들은 중첩되고 시작연도와 길이가 함께 변합니다. 유의 기간 수는 독립 반복실험의 확률이 아닙니다. 최종 통합에서는 저장 추정치의 중앙값·건수만 집계하고 새 기울기·검정·회귀를 계산하지 않습니다.

## 자료 출처

NASA POWER: NASA Langley Research Center의 POWER 프로젝트(Earth Science Division 지원), Daily Point 서비스. 기온 변수 T2M/T2M_MAX/T2M_MIN, 단위 °C, 요청 시간기준 LST. KMA ASOS: 기상청 지상(종관, ASOS) 일자료 조회서비스, 지점 일평균·최고·최저기온(°C). KHOA coastline: 해양수산부 국립해양조사원 해안선. 해안거리 단위 km. 데이터의 서비스 버전·취득일은 보존된 원본 metadata/manifest를 기준으로 하며 누락 정보는 추정하지 않습니다.
