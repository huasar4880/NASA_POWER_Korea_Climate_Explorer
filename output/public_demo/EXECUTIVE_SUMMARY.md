# Executive Summary

NASA POWER와 KMA ASOS를 활용한 대한민국 장기 기온변화 및 공간적 특성 분석

## 목적과 범위

본 연구는 장기 기온변화의 방향과 공간적 특성을 공공 지점관측 및 NASA 격자자료로 교차검증합니다. 공식 ASOS inventory 105 <!-- fact:inventory_n -->개에서 선정된 Tier A 45 <!-- fact:tier_a -->개와 Tier B 6 <!-- fact:tier_b -->개를 장기 및 공통기간으로 구분했습니다. Sen slope, MK/FDR와 공간·기간 민감성 검토 결과, 기온 상승 방향과 NASA–KMA 오차의 공간구조는 반복되지만 KMA 추세 군집과 기울기 크기는 조건에 민감했습니다. 자료 대표성·표본·기간·검정방법을 함께 명시하는 재현 가능한 해석이 본 연구의 핵심입니다.

## 핵심 결과

- 고정 Tier A의 모든 시작기간에서 TAVG가 증가한 지점은 45 <!-- fact:stability_TAVG_positive_all_count -->개입니다. 공통기간에서는 51 <!-- fact:common_KMA_TAVG_positive -->/51 <!-- fact:common_n -->개 지점이 증가하고 모두 원 MK의 BH-FDR 기준을 충족했습니다.

- 공통기간 TMIN–TMAX 기울기 차이의 중앙값은 0.1470 <!-- fact:contrast_median --> °C/decade이며, TMIN 상승이 더 큰 지점은 40 <!-- fact:contrast_positive -->개입니다. KMA DTR 기울기 중앙값은 -0.1776 <!-- fact:common_KMA_dtr --> °C/decade입니다.

- 공통기간 TAVG의 NASA–KMA 추세 방향 일치는 51 <!-- fact:agreement_TAVG -->/51 <!-- fact:common_n -->개 지점입니다. 그러나 Bias 중앙값 -1.0155 <!-- fact:validation_TAVG_bias --> °C와 RMSE 중앙값 1.9028 <!-- fact:validation_TAVG_rmse --> °C는 절대 수준의 차이를 보여줍니다.

- NASA TAVG의 공간구조는 station-linked에서 고유 격자로 바꿔도 양의 유의성이 유지됩니다. 대표 가중치 Moran I는 0.8860 <!-- fact:spatial_nasa_tavg_sen_slope_STATION_LINKED_Moran_I -->에서 0.6957 <!-- fact:spatial_nasa_tavg_sen_slope_UNIQUE_GRID_Moran_I -->로 달라지므로 중복의 크기 효과는 무시할 수 없습니다.

- Bias·RMSE의 공간구조는 저장된 기간·가중치 검토에서 반복됩니다. 해안거리와의 연관도 반복되지만, 지형·고도·격자 대표성과 분리된 인과효과를 입증한 것은 아닙니다.

- KMA TAVG 공간군집은 DIRECTION_SENSITIVE <!-- fact:trajectory_kma_tavg_sen_slope_STATION_LINKED_period_robustness -->로 분류됩니다. 고정 Tier A의 가장 긴 기간과 가장 짧은 기간 기울기 중앙값은 각각 0.3888 <!-- fact:window_1981_KMA_TAVG_median -->, 0.5658 <!-- fact:window_2001_KMA_TAVG_median --> °C/decade로 다릅니다. 이를 가속화로 단정하지 않습니다.

## 방법과 근거

저장된 Sen/MK/BH-FDR, validation, 공간가중치·격자 공유·기간 민감성 결과를 fact layer와 연결했습니다. 증거 등급은 프로젝트 운영규칙이며 학계의 표준 등급이 아닙니다. ROBUST는 해당 명제가 적용 가능한 검증 축에서 유지됨을 뜻하고 모든 통계량이 동일하다는 뜻은 아닙니다. MODERATELY_ROBUST는 반복 방향이 있으나 일부 지점·모형·유의성이 달라지는 경우, SENSITIVE는 기간·가중치·추론법에 따라 해석이 바뀌는 경우, DESCRIPTIVE_ONLY는 강건성 검증 밖의 기술적 요약입니다. 적용 불가능하거나 미검증인 축은 통과로 세지 않습니다.

## 한계와 활용

관측소 중앙값은 면적가중 전국 평균이 아닙니다. NASA 격자와 ASOS 지점의 공간대표성이 다릅니다. 상관은 정확도 또는 인과성을 뜻하지 않습니다. 고온일수는 공식 폭염·열대야 통계가 아닌 threshold proxy입니다. 분석기간·관측소 집합·공간가중치를 함께 확인해야 합니다. 연구 탐색·자료 비교·재현성 교육에 활용하되 인과귀속·미래예측에는 사용하지 않습니다.
