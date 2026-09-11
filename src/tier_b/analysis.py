"""Independent cohort statistics using the existing Tier A numerical functions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.nationwide import tier_a_analysis as shared
from src.nationwide.tier_a_pipeline import PreparedStation
from src.statistical_analysis import analyze_trend_series, apply_fdr_correction


def cohort_family(frame: pd.DataFrame) -> pd.DataFrame:
    """Label already cohort-local FDR families accurately, without changing statistics."""
    result = frame.copy()
    result['fdr_family'] = result.fdr_family.str.replace('Tier A', 'Tier B', regex=False)
    return result


def threshold_trends(annual: pd.DataFrame) -> pd.DataFrame:
    """Sen/MK/linear and source×proxy BH families on pair-matched annual counts."""
    rows = []
    for (sid, threshold), group in annual.groupby(['station_id', 'threshold'], sort=True):
        for source in ('KMA', 'NASA'):
            values = group[f'{source.lower()}_count']
            rows.append({'station_id': sid, 'source': source, 'threshold': threshold,
                         'mean_annual_count': float(values.mean()), 'unit': 'days/decade',
                         **analyze_trend_series(group.year, values)})
    frames = []
    for (source, threshold), group in pd.DataFrame(rows).groupby(['source', 'threshold'], sort=True):
        corrected = apply_fdr_correction(group)
        corrected['fdr_family'] = f'Tier B {source} {threshold}'
        frames.append(corrected)
    return pd.concat(frames, ignore_index=True)


def validate_results(tables: dict[str, pd.DataFrame], stations: pd.DataFrame) -> None:
    """Fail closed for nonfinite metrics, wrong cohort/calendar, or invalid confidence bounds."""
    validation = tables['tier_b_nasa_kma_temperature_validation']
    if len(validation) != len(stations)*3 or (validation.n_pairs <= 0).any():
        raise ValueError('Incomplete validation pairs')
    if not np.isfinite(validation[['bias', 'mae', 'rmse', 'pearson_r', 'spearman_rho']]).all().all():
        raise ValueError('Nonfinite validation metric')
    if (validation.rmse + 1e-12 < validation.mae).any():
        raise ValueError('RMSE below MAE')
    if not validation[['pearson_r', 'spearman_rho']].map(lambda x: -1 <= x <= 1).all().all():
        raise ValueError('Correlation out of bounds')
    annual = tables['tier_b_annual_temperature_1991_2025']
    for _, group in annual.groupby(['station_id', 'source', 'metric']):
        if sorted(group.year) != list(range(1991, 2026)):
            raise ValueError('Wrong annual period')
    for key in ('tier_b_temperature_trends', 'tier_b_seasonal_temperature_trends', 'tier_b_threshold_trends'):
        frame = tables[key]
        if not frame.fdr_q_value.between(0, 1).all():
            raise ValueError('Invalid FDR')
        if not ((frame.sen_ci_lower <= frame.sen_slope_per_decade + 1e-12)
                & (frame.sen_slope_per_decade <= frame.sen_ci_upper + 1e-12)).all():
            raise ValueError('Invalid Sen CI')
    summary = tables['tier_b_station_temperature_summary']
    if set(summary.station_id) != set(stations.station_id):
        raise ValueError('Cohort mismatch')


def build_products(prepared: list[PreparedStation], stations: pd.DataFrame,
                   quality: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Reuse period-independent Tier A functions; no pooling or spatial inference."""
    if quality.analysis_review_required.any():
        raise ValueError('Analysis withheld: data quality review required; inspect tier_b_data_quality.csv')
    annual = shared.calculate_station_annual_temperature(prepared, stations)
    trends = cohort_family(shared.calculate_station_trends(annual, stations))
    normals, anomalies = shared.calculate_normals_and_anomalies(annual)
    seasonal = cohort_family(shared.calculate_seasonal_temperature(prepared, stations))
    thresholds = shared.calculate_threshold_annual(prepared)
    # Zero events on valid days differs from no observations; never turn missing years into zero.
    absent = thresholds.valid_pair_days.eq(0)
    for column in ('nasa_count', 'kma_count', 'difference'):
        thresholds[column] = thresholds[column].astype(float).mask(absent)
    comparison = shared.calculate_threshold_comparison(thresholds, stations)
    validation = shared.calculate_temperature_validation(prepared, stations)
    trend_table = shared.build_station_trend_table(trends, validation)
    summary = shared.build_station_summary(trend_table, comparison)
    summary = summary.merge(trend_table.loc[trend_table.metric.eq('TAVG'), ['station_id', 'kma_fdr_q']]
                            .rename(columns={'kma_fdr_q': 'kma_tavg_fdr_q'}), on='station_id', validate='one_to_one')
    summary['data_quality_flag'] = 'passed_screening_recheck'
    summary = summary.merge(stations[['station_id', 'region_level1', 'region_level2']], on='station_id', validate='one_to_one')
    for source in ('KMA', 'NASA'):
        sub = annual.loc[annual.source.eq(source) & annual.metric.eq('TAVG')]
        first = sub.loc[sub.year.between(1991, 2000)].groupby('station_id').annual_mean.mean()
        last = sub.loc[sub.year.between(2016, 2025)].groupby('station_id').annual_mean.mean()
        summary[f'{source.lower()}_first_10yr_mean'] = summary.station_id.map(first)
        summary[f'{source.lower()}_last_10yr_mean'] = summary.station_id.map(last)
        summary[f'{source.lower()}_last_minus_first'] = summary.station_id.map(last-first)
    consistency = shared.build_trend_consistency(trend_table)
    for source in ('kma', 'nasa'):
        consistency[f'{source}_trend_direction'] = np.sign(consistency[f'{source}_sen_slope_per_decade']).map(
            {-1.0: 'decreasing', 0.0: 'flat', 1.0: 'increasing'})
    consistency['same_direction'] = np.sign(consistency.kma_sen_slope_per_decade).eq(np.sign(consistency.nasa_sen_slope_per_decade))
    rankings = shared.build_rankings(summary)
    rankings['ranking_scope'] = 'Tier B 1991–2025 only; not nationwide or Tier A+B'
    products = {'tier_b_annual_temperature_1991_2025': annual, 'tier_b_temperature_trends': trends,
                'tier_b_temperature_normals_1991_2020': normals, 'tier_b_temperature_anomalies_1991_2025': anomalies,
                'tier_b_seasonal_temperature_trends': seasonal, 'tier_b_threshold_annual': thresholds,
                'tier_b_threshold_trends': threshold_trends(thresholds),
                'tier_b_nasa_kma_temperature_validation': validation,
                'tier_b_nasa_kma_trend_consistency': consistency, 'tier_b_station_temperature_summary': summary,
                'tier_b_temperature_rankings': rankings}
    validate_results(products, stations)
    return products
