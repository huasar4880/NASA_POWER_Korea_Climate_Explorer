# Final Results Summary

공식 inventory 105 <!-- fact:inventory_n -->개, Tier A 45 <!-- fact:tier_a -->개, Tier B 6 <!-- fact:tier_b -->개, 공통기간 51 <!-- fact:common_n -->개 지점 및 NASA 고유 격자 34 <!-- fact:grid_n -->개. 장기 1981-01-01~2025-12-31 <!-- fact:long_period -->, 공통기간 1991-01-01–2025-12-31 <!-- fact:common_period -->, normal 1991–2020 <!-- fact:normal -->.

- 고정 Tier A의 모든 시작기간에서 TAVG가 증가한 지점은 45 <!-- fact:stability_TAVG_positive_all_count -->개입니다. 공통기간에서는 51 <!-- fact:common_KMA_TAVG_positive -->/51 <!-- fact:common_n -->개 지점이 증가하고 모두 원 MK의 BH-FDR 기준을 충족했습니다.

- 공통기간 TMIN–TMAX 기울기 차이의 중앙값은 0.1470 <!-- fact:contrast_median --> °C/decade이며, TMIN 상승이 더 큰 지점은 40 <!-- fact:contrast_positive -->개입니다. KMA DTR 기울기 중앙값은 -0.1776 <!-- fact:common_KMA_dtr --> °C/decade입니다.

- 공통기간 TAVG의 NASA–KMA 추세 방향 일치는 51 <!-- fact:agreement_TAVG -->/51 <!-- fact:common_n -->개 지점입니다. 그러나 Bias 중앙값 -1.0155 <!-- fact:validation_TAVG_bias --> °C와 RMSE 중앙값 1.9028 <!-- fact:validation_TAVG_rmse --> °C는 절대 수준의 차이를 보여줍니다.

- NASA TAVG의 공간구조는 station-linked에서 고유 격자로 바꿔도 양의 유의성이 유지됩니다. 대표 가중치 Moran I는 0.8860 <!-- fact:spatial_nasa_tavg_sen_slope_STATION_LINKED_Moran_I -->에서 0.6957 <!-- fact:spatial_nasa_tavg_sen_slope_UNIQUE_GRID_Moran_I -->로 달라지므로 중복의 크기 효과는 무시할 수 없습니다.

- Bias·RMSE의 공간구조는 저장된 기간·가중치 검토에서 반복됩니다. 해안거리와의 연관도 반복되지만, 지형·고도·격자 대표성과 분리된 인과효과를 입증한 것은 아닙니다.

- KMA TAVG 공간군집은 DIRECTION_SENSITIVE <!-- fact:trajectory_kma_tavg_sen_slope_STATION_LINKED_period_robustness -->로 분류됩니다. 고정 Tier A의 가장 긴 기간과 가장 짧은 기간 기울기 중앙값은 각각 0.3888 <!-- fact:window_1981_KMA_TAVG_median -->, 0.5658 <!-- fact:window_2001_KMA_TAVG_median --> °C/decade로 다릅니다. 이를 가속화로 단정하지 않습니다.

증거 등급은 프로젝트 운영규칙이며 학계의 표준 등급이 아닙니다. ROBUST는 해당 명제가 적용 가능한 검증 축에서 유지됨을 뜻하고 모든 통계량이 동일하다는 뜻은 아닙니다. MODERATELY_ROBUST는 반복 방향이 있으나 일부 지점·모형·유의성이 달라지는 경우, SENSITIVE는 기간·가중치·추론법에 따라 해석이 바뀌는 경우, DESCRIPTIVE_ONLY는 강건성 검증 밖의 기술적 요약입니다. 적용 불가능하거나 미검증인 축은 통과로 세지 않습니다.

## 자료와 분석범위

| 지표 | 값 (표시 반올림) | 단위 | 분석기간 | fact_id |
| --- | --- | --- | --- | --- |
| 공식 ASOS inventory · 행 수 | 105 | stations | metadata snapshot | inventory_n |
| Tier A 수 | 45 | stations | metadata | tier_a |
| Tier B 수 | 6 | stations | metadata | tier_b |
| 공통기간 지점수 | 51 | stations | metadata | common_n |
| 공통기간 NASA 고유 격자 수 | 34 | grids | metadata | grid_n |
| 고정 Tier A NASA 고유 격자 수 | 33 | grids | metadata | long_grid_n |
| 분석기간 | 1981-01-01~2025-12-31 | date range | metadata | long_period |
| 분석기간 | 1991-01-01–2025-12-31 | date/year range | metadata | common_period |
| Climate Normal | 1991–2020 | date/year range | metadata | normal |

## 공통기간 기온추세: 지점 중앙값

| 지표 | 값 (표시 반올림) | 단위 | 분석기간 | fact_id |
| --- | --- | --- | --- | --- |
| KMA · TAVG · Sen 기울기 · 지점 중앙값 | 0.4508 | °C/decade | 1991–2025 | common_KMA_TAVG_median |
| KMA · TAVG · Sen 기울기 · 양수 지점수 | 51 | stations | 1991–2025 | common_KMA_TAVG_positive |
| KMA · TAVG · FDR 유의 지점수 | 51 | stations | 1991–2025 | common_KMA_TAVG_fdr |
| KMA · TMAX · Sen 기울기 · 지점 중앙값 | 0.3741 | °C/decade | 1991–2025 | common_KMA_TMAX_median |
| KMA · TMAX · Sen 기울기 · 양수 지점수 | 50 | stations | 1991–2025 | common_KMA_TMAX_positive |
| KMA · TMAX · FDR 유의 지점수 | 46 | stations | 1991–2025 | common_KMA_TMAX_fdr |
| KMA · TMIN · Sen 기울기 · 지점 중앙값 | 0.5097 | °C/decade | 1991–2025 | common_KMA_TMIN_median |
| KMA · TMIN · Sen 기울기 · 양수 지점수 | 51 | stations | 1991–2025 | common_KMA_TMIN_positive |
| KMA · TMIN · FDR 유의 지점수 | 49 | stations | 1991–2025 | common_KMA_TMIN_fdr |
| NASA · TAVG · Sen 기울기 · 지점 중앙값 | 0.4645 | °C/decade | 1991–2025 | common_NASA_TAVG_median |
| NASA · TAVG · Sen 기울기 · 양수 지점수 | 51 | stations | 1991–2025 | common_NASA_TAVG_positive |
| NASA · TAVG · FDR 유의 지점수 | 51 | stations | 1991–2025 | common_NASA_TAVG_fdr |
| NASA · TMAX · Sen 기울기 · 지점 중앙값 | 0.5012 | °C/decade | 1991–2025 | common_NASA_TMAX_median |
| NASA · TMAX · Sen 기울기 · 양수 지점수 | 51 | stations | 1991–2025 | common_NASA_TMAX_positive |
| NASA · TMAX · FDR 유의 지점수 | 51 | stations | 1991–2025 | common_NASA_TMAX_fdr |
| NASA · TMIN · Sen 기울기 · 지점 중앙값 | 0.4352 | °C/decade | 1991–2025 | common_NASA_TMIN_median |
| NASA · TMIN · Sen 기울기 · 양수 지점수 | 51 | stations | 1991–2025 | common_NASA_TMIN_positive |
| NASA · TMIN · FDR 유의 지점수 | 51 | stations | 1991–2025 | common_NASA_TMIN_fdr |

## TMIN–TMAX·DTR·계절

| 지표 | 값 (표시 반올림) | 단위 | 분석기간 | fact_id |
| --- | --- | --- | --- | --- |
| TMIN−TMAX 기울기 차이 · 지점 중앙값 | 0.1470 | °C/decade | 1991–2025 | contrast_median |
| TMIN−TMAX 기울기 차이 · 양수 지점수 | 40 | stations | 1991–2025 | contrast_positive |
| KMA · Sen 기울기 · 지점 중앙값 | -0.1776 | °C/decade | 1991–2025 | common_KMA_dtr |
| KMA · Sen 기울기 · 음수 지점수 | 42 | stations | 1991–2025 | common_KMA_dtr_negative |
| KMA · TAVG · DJF · Sen 기울기 · 지점 중앙값 | 0.0312 | °C/decade | 1991–2025 | common_KMA_DJF |
| KMA · TAVG · MAM · Sen 기울기 · 지점 중앙값 | 0.5425 | °C/decade | 1991–2025 | common_KMA_MAM |
| KMA · TAVG · JJA · Sen 기울기 · 지점 중앙값 | 0.5886 | °C/decade | 1991–2025 | common_KMA_JJA |
| KMA · TAVG · SON · Sen 기울기 · 지점 중앙값 | 0.5067 | °C/decade | 1991–2025 | common_KMA_SON |

## NASA–KMA 일별 validation: 지점 지표 중앙값

| 지표 | 값 (표시 반올림) | 단위 | 분석기간 | fact_id |
| --- | --- | --- | --- | --- |
| TAVG · Bias · 지점 중앙값 | -1.0155 | °C | 1991–2025 | validation_TAVG_bias |
| TAVG · MAE · 지점 중앙값 | 1.5357 | °C | 1991–2025 | validation_TAVG_mae |
| TAVG · RMSE · 지점 중앙값 | 1.9028 | °C | 1991–2025 | validation_TAVG_rmse |
| TAVG · Pearson r · 지점 중앙값 | 0.9907 | 1 | 1991–2025 | validation_TAVG_pearson_r |
| TAVG · Spearman rho · 지점 중앙값 | 0.9909 | 1 | 1991–2025 | validation_TAVG_spearman_rho |
| TAVG · 유효 일별 pair 수 · 지점 중앙값 | 12780 | days | 1991–2025 | validation_TAVG_n_pairs |
| TMAX · Bias · 지점 중앙값 | -1.9873 | °C | 1991–2025 | validation_TMAX_bias |
| TMAX · MAE · 지점 중앙값 | 2.3481 | °C | 1991–2025 | validation_TMAX_mae |
| TMAX · RMSE · 지점 중앙값 | 2.7291 | °C | 1991–2025 | validation_TMAX_rmse |
| TMAX · Pearson r · 지점 중앙값 | 0.9828 | 1 | 1991–2025 | validation_TMAX_pearson_r |
| TMAX · Spearman rho · 지점 중앙값 | 0.9802 | 1 | 1991–2025 | validation_TMAX_spearman_rho |
| TMAX · 유효 일별 pair 수 · 지점 중앙값 | 12783 | days | 1991–2025 | validation_TMAX_n_pairs |
| TMIN · Bias · 지점 중앙값 | -0.0805 | °C | 1991–2025 | validation_TMIN_bias |
| TMIN · MAE · 지점 중앙값 | 1.9294 | °C | 1991–2025 | validation_TMIN_mae |
| TMIN · RMSE · 지점 중앙값 | 2.3809 | °C | 1991–2025 | validation_TMIN_rmse |
| TMIN · Pearson r · 지점 중앙값 | 0.9817 | 1 | 1991–2025 | validation_TMIN_pearson_r |
| TMIN · Spearman rho · 지점 중앙값 | 0.9818 | 1 | 1991–2025 | validation_TMIN_spearman_rho |
| TMIN · 유효 일별 pair 수 · 지점 중앙값 | 12784 | days | 1991–2025 | validation_TMIN_n_pairs |

## 공간구조: 대표 directed KNN

| 지표 | 값 (표시 반올림) | 단위 | 분석기간 | fact_id |
| --- | --- | --- | --- | --- |
| kma_tavg_sen_slope · STATION_LINKED · Moran I | 0.1098 | 1 | 1991–2025 | spatial_kma_tavg_sen_slope_STATION_LINKED_Moran_I |
| kma_tavg_sen_slope · STATION_LINKED · 순열 p | 0.1330 | 1 | 1991–2025 | spatial_kma_tavg_sen_slope_STATION_LINKED_permutation_p |
| kma_tavg_sen_slope · STATION_LINKED · 공간 단위 수 | 51 | spatial units | 1991–2025 | spatial_kma_tavg_sen_slope_STATION_LINKED_n_spatial_units |
| tavg_bias · STATION_LINKED · Moran I | 0.3048 | 1 | 1991–2025 | spatial_tavg_bias_STATION_LINKED_Moran_I |
| tavg_bias · STATION_LINKED · 순열 p | 0.0010 | 1 | 1991–2025 | spatial_tavg_bias_STATION_LINKED_permutation_p |
| tavg_bias · STATION_LINKED · 공간 단위 수 | 51 | spatial units | 1991–2025 | spatial_tavg_bias_STATION_LINKED_n_spatial_units |
| tavg_rmse · STATION_LINKED · Moran I | 0.2461 | 1 | 1991–2025 | spatial_tavg_rmse_STATION_LINKED_Moran_I |
| tavg_rmse · STATION_LINKED · 순열 p | 0.0030 | 1 | 1991–2025 | spatial_tavg_rmse_STATION_LINKED_permutation_p |
| tavg_rmse · STATION_LINKED · 공간 단위 수 | 51 | spatial units | 1991–2025 | spatial_tavg_rmse_STATION_LINKED_n_spatial_units |
| nasa_tavg_sen_slope · STATION_LINKED · Moran I | 0.8860 | 1 | 1991–2025 | spatial_nasa_tavg_sen_slope_STATION_LINKED_Moran_I |
| nasa_tavg_sen_slope · STATION_LINKED · 순열 p | 0.0010 | 1 | 1991–2025 | spatial_nasa_tavg_sen_slope_STATION_LINKED_permutation_p |
| nasa_tavg_sen_slope · STATION_LINKED · 공간 단위 수 | 51 | spatial units | 1991–2025 | spatial_nasa_tavg_sen_slope_STATION_LINKED_n_spatial_units |
| nasa_tavg_sen_slope · UNIQUE_GRID · Moran I | 0.6957 | 1 | 1991–2025 | spatial_nasa_tavg_sen_slope_UNIQUE_GRID_Moran_I |
| nasa_tavg_sen_slope · UNIQUE_GRID · 순열 p | 0.0010 | 1 | 1991–2025 | spatial_nasa_tavg_sen_slope_UNIQUE_GRID_permutation_p |
| nasa_tavg_sen_slope · UNIQUE_GRID · 공간 단위 수 | 34 | spatial units | 1991–2025 | spatial_nasa_tavg_sen_slope_UNIQUE_GRID_n_spatial_units |

## 고정 Tier A 시작기간별 TAVG·고온 proxy

| 지표 | 값 (표시 반올림) | 단위 | 분석기간 | fact_id |
| --- | --- | --- | --- | --- |
| KMA · TAVG · 기울기 중앙값 | 0.3888 | °C/decade | 1981–2025 | window_1981_KMA_TAVG_median |
| KMA · TAVG · 기울기 중앙값 | 0.3906 | °C/decade | 1986–2025 | window_1986_KMA_TAVG_median |
| KMA · TAVG · 기울기 중앙값 | 0.4508 | °C/decade | 1991–2025 | window_1991_KMA_TAVG_median |
| KMA · TAVG · 기울기 중앙값 | 0.4857 | °C/decade | 1996–2025 | window_1996_KMA_TAVG_median |
| KMA · TAVG · 기울기 중앙값 | 0.5658 | °C/decade | 2001–2025 | window_2001_KMA_TAVG_median |
| KMA · TMAX_GE_33 · 기울기 중앙값 | 1.6173 | days/decade | 1981–2025 | threshold_1981_KMA_TMAX_GE_33_median |
| KMA · TMIN_GE_25 · 기울기 중앙값 | 0.8760 | days/decade | 1981–2025 | threshold_1981_KMA_TMIN_GE_25_median |
| KMA · TMAX_GE_33 · 기울기 중앙값 | 2.6795 | days/decade | 1986–2025 | threshold_1986_KMA_TMAX_GE_33_median |
| KMA · TMIN_GE_25 · 기울기 중앙값 | 1.2500 | days/decade | 1986–2025 | threshold_1986_KMA_TMIN_GE_25_median |
| KMA · TMAX_GE_33 · 기울기 중앙값 | 3.1818 | days/decade | 1991–2025 | threshold_1991_KMA_TMAX_GE_33_median |
| KMA · TMIN_GE_25 · 기울기 중앙값 | 1.4286 | days/decade | 1991–2025 | threshold_1991_KMA_TMIN_GE_25_median |
| KMA · TMAX_GE_33 · 기울기 중앙값 | 3.3333 | days/decade | 1996–2025 | threshold_1996_KMA_TMAX_GE_33_median |
| KMA · TMIN_GE_25 · 기울기 중앙값 | 2.1429 | days/decade | 1996–2025 | threshold_1996_KMA_TMIN_GE_25_median |
| KMA · TMAX_GE_33 · 기울기 중앙값 | 4.5299 | days/decade | 2001–2025 | threshold_2001_KMA_TMAX_GE_33_median |
| KMA · TMIN_GE_25 · 기울기 중앙값 | 3.3333 | days/decade | 2001–2025 | threshold_2001_KMA_TMIN_GE_25_median |

## 해안 연관과 통제모형: 서로 다른 추론 범위

| 지표 | 값 (표시 반올림) | 단위 | 분석기간 | fact_id |
| --- | --- | --- | --- | --- |
| kma_tavg_sen_slope · Spearman rho | 0.3938 | 1 | 1991–2025 | coast_kma_tavg_sen_slope_spearman_rho |
| tavg_bias · Spearman rho | -0.5930 | 1 | 1991–2025 | coast_tavg_bias_spearman_rho |
| tavg_rmse · Spearman rho | 0.3746 | 1 | 1991–2025 | coast_tavg_rmse_spearman_rho |
| kma_tavg_sen_slope · HC3 p | 0.1117 | 1 | 1981–2025 | model_kma_tavg_sen_slope_hc3_p |
| tavg_bias · HC3 p | 0.0004 | 1 | 1981–2025 | model_tavg_bias_hc3_p |
| tavg_rmse · HC3 p | 0.2026 | 1 | 1981–2025 | model_tavg_rmse_hc3_p |
| CONVERGED_NEAR_BOUNDARY · numerical class · 행 수 | 6 | model combinations | 1981–2025 | model_count_CONVERGED_NEAR_BOUNDARY |
| FAILED · numerical class · 행 수 | 1 | model combinations | 1981–2025 | model_count_FAILED |
| NUMERICALLY_UNSTABLE · numerical class · 행 수 | 13 | model combinations | 1981–2025 | model_count_NUMERICALLY_UNSTABLE |
| STABLE · numerical class · 행 수 | 34 | model combinations | 1981–2025 | model_count_STABLE |

## 해안/내륙과 오차의 기간 안정성

| 지표 | 값 (표시 반올림) | 단위 | 분석기간 | fact_id |
| --- | --- | --- | --- | --- |
| tavg_bias · 해안−내륙 중앙값 차이 | 1.4660 | °C | 1991–2025 | coast_group_tavg_bias_median_difference |
| tavg_bias · fdr q | 1.38e-05 | 1 | 1991–2025 | coast_group_tavg_bias_fdr_q |
| tavg_bias · 해안 지점수 | 23 | stations | 1991–2025 | coast_group_tavg_bias_coastal_n |
| tavg_bias · 내륙 지점수 | 28 | stations | 1991–2025 | coast_group_tavg_bias_inland_n |
| tavg_rmse · 해안−내륙 중앙값 차이 | -0.4910 | °C | 1991–2025 | coast_group_tavg_rmse_median_difference |
| tavg_rmse · fdr q | 0.0182 | 1 | 1991–2025 | coast_group_tavg_rmse_fdr_q |
| tavg_rmse · 해안 지점수 | 23 | stations | 1991–2025 | coast_group_tavg_rmse_coastal_n |
| tavg_rmse · 내륙 지점수 | 28 | stations | 1991–2025 | coast_group_tavg_rmse_inland_n |
| tavg_bias · period interpretation | DIRECTION_CONSISTENT_SIGNIFICANT | classification | multiple–2025 | period_coast_tavg_bias_period_interpretation |
| tavg_rmse · period interpretation | DIRECTION_CONSISTENT_SIGNIFICANT | classification | multiple–2025 | period_coast_tavg_rmse_period_interpretation |
| TAVG · bias median | -0.9959 | °C | 1981–2025 | period_validation_1981_TAVG_bias_median |
| TAVG · rmse median | 1.9495 | °C | 1981–2025 | period_validation_1981_TAVG_rmse_median |
| TAVG · bias median | -0.9967 | °C | 1986–2025 | period_validation_1986_TAVG_bias_median |
| TAVG · rmse median | 1.9188 | °C | 1986–2025 | period_validation_1986_TAVG_rmse_median |
| TAVG · bias median | -1.0155 | °C | 1991–2025 | period_validation_1991_TAVG_bias_median |
| TAVG · rmse median | 1.9028 | °C | 1991–2025 | period_validation_1991_TAVG_rmse_median |
| TAVG · bias median | -0.9791 | °C | 1996–2025 | period_validation_1996_TAVG_bias_median |
| TAVG · rmse median | 1.9045 | °C | 1996–2025 | period_validation_1996_TAVG_rmse_median |
| TAVG · bias median | -0.9715 | °C | 2001–2025 | period_validation_2001_TAVG_bias_median |
| TAVG · rmse median | 1.9107 | °C | 2001–2025 | period_validation_2001_TAVG_rmse_median |

## 증거 등급: 강건성과 민감성

| conclusion_id | statement | final_evidence_class |
| --- | --- | --- |
| A | 고정 Tier A의 모든 시작기간에서 TAVG가 증가한 지점은 45개입니다. 공통기간에서는 51/51개 지점이 증가하고 모두 원 MK의 BH-FDR 기준을 충족했습니다. | ROBUST |
| B | 공통기간 TMIN–TMAX 기울기 차이의 중앙값은 0.1470 °C/decade이며, TMIN 상승이 더 큰 지점은 40개입니다. KMA DTR 기울기 중앙값은 -0.1776 °C/decade입니다. | MODERATELY_ROBUST |
| C | 공통기간 TAVG의 NASA–KMA 추세 방향 일치는 51/51개 지점입니다. 그러나 Bias 중앙값 -1.0155 °C와 RMSE 중앙값 1.9028 °C는 절대 수준의 차이를 보여줍니다. | ROBUST |
| D | KMA TAVG 공간군집은 기간·가중치에 민감하며 고정된 전국 군집을 주장할 수 없습니다. | SENSITIVE |
| E | NASA TAVG의 공간구조는 station-linked에서 고유 격자로 바꿔도 양의 유의성이 유지됩니다. 대표 가중치 Moran I는 0.8860에서 0.6957로 달라지므로 중복의 크기 효과는 무시할 수 없습니다. | ROBUST |
| F | NASA–KMA Bias·RMSE의 양의 공간구조는 저장된 기간·가중치에서 반복됩니다. | ROBUST |
| G | 해안거리와 Bias·RMSE 연관은 반복되지만 RMSE의 통제모형 유의성까지 강건한 것은 아닙니다. | MODERATELY_ROBUST |
| H | KMA TAVG 공간군집은 DIRECTION_SENSITIVE로 분류됩니다. 고정 Tier A의 가장 긴 기간과 가장 짧은 기간 기울기 중앙값은 각각 0.3888, 0.5658 °C/decade로 다릅니다. 이를 가속화로 단정하지 않습니다. | SENSITIVE |
