"""Identical common-period calculations, fresh union BH families and descriptive summaries."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from src.tier_b.analysis import build_products as shared_products
from src.nationwide.tier_a_analysis import assign_elevation_band
from src.nationwide.tier_a_pipeline import PreparedStation
from src.statistical_analysis import apply_fdr_correction


def verify_common_fdr(trends: pd.DataFrame, group_keys: list[str]) -> None:
    """Independently recalculate BH from union raw p; never accept merged old q-values."""
    for _, frame in trends.groupby(group_keys, sort=False):
        expected = apply_fdr_correction(frame)
        if not np.allclose(frame.fdr_q_value, expected.fdr_q_value, atol=1e-14, rtol=1e-12):
            raise ValueError('Common FDR differs from union raw-p BH')


def distribution(values: pd.Series) -> dict:
    """Unweighted descriptive distribution; not an area-weighted national estimate."""
    v = values.dropna()
    return {'n': len(v), 'mean': float(v.mean()), 'median': float(v.median()),
            'iqr': float(v.quantile(.75)-v.quantile(.25)), 'min': float(v.min()), 'max': float(v.max())}


def describe_groups(summary: pd.DataFrame, group_column: str, fields: list[str]) -> pd.DataFrame:
    """Describe station samples, retaining cohort membership counts in aggregated rows."""
    rows = []
    for group, frame in summary.groupby(group_column, observed=True, sort=True):
        for field in fields:
            rows.append({group_column: group, 'metric': field, **distribution(frame[field]),
                         'station_count': len(frame), 'tier_a_count': int(frame.cohort_origin.eq('TIER_A').sum()),
                         'tier_b_count': int(frame.cohort_origin.eq('TIER_B').sum()),
                         'cohort_origins': '|'.join(sorted(frame.cohort_origin.unique())),
                         'small_group_flag': len(frame) < 3,
                         'kma_tavg_fdr_significant_count': int(frame.kma_tavg_fdr_significant.sum()),
                         'scope': 'descriptive station sample, no causal inference'})
    return pd.DataFrame(rows)


def unique_grid_summary(trends: pd.DataFrame, mapping: pd.DataFrame, stations: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Represent each verified NASA series once; compare station- versus grid-linked summaries."""
    nasa = trends.loc[trends.source.eq('NASA')].merge(stations[['station_id', 'nasa_grid_id']], on='station_id', validate='many_to_one')
    rows = []
    for grid in mapping.itertuples():
        frame = nasa.loc[nasa.nasa_grid_id.eq(grid.nasa_grid_id)]
        row = {'nasa_grid_id': grid.nasa_grid_id, 'grid_lat': grid.nasa_grid_latitude, 'grid_lon': grid.nasa_grid_longitude,
               'station_count': grid.station_count, 'station_ids': grid.station_ids, 'cohort_origins': grid.cohort_origins}
        for metric, family in frame.groupby('metric'):
            if not np.allclose(family.sen_slope_per_decade, family.sen_slope_per_decade.iloc[0], rtol=0, atol=1e-12):
                raise ValueError('Shared-grid NASA slopes differ')
            row[f'nasa_{metric.lower()}_sen_slope'] = float(family.sen_slope_per_decade.iloc[0])
        rows.append(row)
    unique = pd.DataFrame(rows)
    weighted = pd.DataFrame([{'weighting': label, 'source': 'NASA', 'metric': 'TAVG', **distribution(values),
                              'station_count': len(stations), 'unique_grid_count': len(unique),
                              'cohort_origins': 'TIER_A|TIER_B', 'unit': 'deg C/decade'}
                             for label, values in [('station-linked', nasa.loc[nasa.metric.eq('TAVG'), 'sen_slope_per_decade']),
                                                   ('unique-grid', unique.nasa_tavg_sen_slope)]])
    return unique, weighted


def reproduce_tier_b(products: dict, root: Path) -> pd.DataFrame:
    """Compare Stage15 raw statistics, excluding intentionally recalculated FDR q/decisions."""
    specs = {
        'annual_temperature_1991_2025': (['station_id', 'source', 'metric', 'year'], ['annual_mean', 'moving_average_5yr', 'moving_average_10yr']),
        'temperature_trends': (['station_id', 'source', 'metric'], ['linear_slope_per_decade', 'mk_p_value', 'sen_slope_per_decade', 'sen_ci_lower', 'sen_ci_upper']),
        'temperature_normals_1991_2020': (['station_id', 'source', 'metric'], ['normal_mean', 'normal_std']),
        'temperature_anomalies_1991_2025': (['station_id', 'source', 'metric', 'year'], ['anomaly']),
        'seasonal_temperature_trends': (['station_id', 'source', 'metric', 'season'], ['seasonal_mean', 'sen_slope_per_decade', 'mk_p_value']),
        'threshold_annual': (['station_id', 'threshold', 'year'], ['nasa_count', 'kma_count', 'valid_pair_days']),
        'threshold_trends': (['station_id', 'source', 'threshold'], ['mean_annual_count', 'sen_slope_per_decade', 'mk_p_value']),
        'nasa_kma_temperature_validation': (['station_id', 'metric'], ['bias', 'mae', 'rmse', 'pearson_r', 'spearman_rho', 'n_pairs'])}
    rows = []
    for name, (keys, columns) in specs.items():
        old = pd.read_csv(root/f'output/tables/tier_b/tier_b_{name}.csv', dtype={'station_id': str})
        current = products[f'tier_b_{name}']
        current = current.loc[current.station_id.isin(old.station_id)]
        paired = old[keys+columns].merge(current[keys+columns], on=keys, suffixes=('_old', '_new'), validate='one_to_one', how='outer', indicator=True)
        passed, differences = paired['_merge'].eq('both').all(), []
        for col in columns:
            x, y = paired[f'{col}_old'].to_numpy(float), paired[f'{col}_new'].to_numpy(float)
            passed = bool(passed and np.allclose(x, y, rtol=1e-9, atol=1e-9, equal_nan=True))
            finite = np.isfinite(x) & np.isfinite(y)
            differences.extend(abs(x[finite]-y[finite]).tolist())
        rows.append({'product': name, 'cohort_origin': 'TIER_B', 'compared_rows': len(paired),
                     'max_absolute_difference': max(differences, default=0.), 'passed': passed,
                     'note': 'raw statistics reproduced; common-family FDR is intentionally recalculated'})
    result = pd.DataFrame(rows)
    if not result.passed.all():
        raise ValueError('Tier B reproduction mismatch')
    return result


def period_comparison(trends: pd.DataFrame, stations: pd.DataFrame, root: Path) -> pd.DataFrame:
    """Link saved Tier A long-period slopes only for the explicitly separate preparation table."""
    old = pd.read_csv(root/'output/tables/nationwide/nationwide_station_temperature_trends.csv', dtype={'station_id': str})
    frames = []
    for source in ('KMA', 'NASA'):
        before = old[['station_id', 'metric', f'{source.lower()}_sen_slope_per_decade']].rename(
            columns={f'{source.lower()}_sen_slope_per_decade': 'sen_1981_2025'})
        now = trends.loc[trends.source.eq(source) & trends.station_id.isin(stations.loc[stations.cohort_origin.eq('TIER_A'), 'station_id'])]
        frame = now[['station_id', 'station_name', 'metric', 'sen_slope_per_decade']].rename(columns={'sen_slope_per_decade': 'sen_1991_2025'}).merge(
            before, on=['station_id', 'metric'], validate='one_to_one')
        frame['source'], frame['cohort_origin'] = source, 'TIER_A'
        frame['difference'] = frame.sen_1991_2025-frame.sen_1981_2025
        frame['unit'] = 'deg C/decade'
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def build_products(prepared: list[PreparedStation], stations: pd.DataFrame, quality: pd.DataFrame,
                   grid_mapping: pd.DataFrame, root: Path, *, verify_history: bool = True) -> dict:
    """Compute all station trends from 1991–2025 daily values before union-wide BH correction."""
    old_schema = shared_products(prepared, stations, quality)
    reproduction = reproduce_tier_b(old_schema, root) if verify_history else pd.DataFrame()
    products = {key.replace('tier_b_', 'common_period_', 1): value.copy() for key, value in old_schema.items()}
    for key, groups in [('common_period_temperature_trends', ['source', 'metric']),
                        ('common_period_seasonal_temperature_trends', ['source', 'metric', 'season']),
                        ('common_period_threshold_trends', ['source', 'threshold'])]:
        frame = products[key]
        verify_common_fdr(frame, groups)
        frame['fdr_family'] = frame.fdr_family.str.replace('Tier B', 'common-period union', regex=False)
        frame['fdr_family_size'] = frame.groupby(groups).station_id.transform('size')
    annual = products.pop('common_period_annual_temperature_1991_2025')
    for source in ('KMA', 'NASA'):
        products[f'common_period_{source.lower()}_annual_temperature'] = annual.loc[annual.source.eq(source)].copy()
    trends = products['common_period_temperature_trends']
    summary = products['common_period_station_temperature_summary']
    for metric in ('tavg', 'tmax', 'tmin'):
        summary[f'kma_{metric}_sen_slope'] = summary[f'kma_{metric}_sen_slope_decade']
    summary['nasa_tavg_sen_slope'] = summary.nasa_tavg_sen_slope_decade
    summary['kma_tavg_fdr_significant'] = summary.kma_tavg_fdr_significant.astype(bool)
    nasa = trends.loc[trends.source.eq('NASA') & trends.metric.eq('TAVG')]
    summary = summary.merge(nasa[['station_id', 'series_mean', 'fdr_q_value']].rename(
        columns={'series_mean': 'nasa_tavg_mean', 'fdr_q_value': 'nasa_tavg_fdr_q'}), on='station_id', validate='one_to_one')
    validation = products['common_period_nasa_kma_temperature_validation']
    summary = summary.merge(validation.loc[validation.metric.eq('TAVG'), ['station_id', 'spearman_rho']]
                            .rename(columns={'spearman_rho': 'tavg_spearman'}), on='station_id', validate='one_to_one')
    summary = summary.merge(stations[['station_id', 'cohort_origin', 'distance_to_coast_km', 'nasa_grid_id', 'nasa_grid_group_size', 'nasa_grid_shared']],
                            on='station_id', validate='one_to_one')
    summary['elevation_band'] = assign_elevation_band(summary.elevation_m).astype(str)
    summary['coastal_class'] = np.where(summary.distance_to_coast_km.le(30), 'coastal_le30km', 'inland_gt30km')
    products['common_period_station_temperature_summary'] = summary
    consistency = products['common_period_nasa_kma_trend_consistency']
    consistency['both_significant'] = consistency.kma_significant_fdr & consistency.nasa_significant_fdr
    seasonal = products['common_period_seasonal_temperature_trends']
    dominant = seasonal.loc[seasonal.metric.eq('TAVG')].copy()
    dominant = dominant.loc[dominant.groupby(['station_id', 'source']).sen_slope_per_decade.idxmax(),
                             ['station_id', 'station_name', 'source', 'season', 'sen_slope_per_decade']]
    products['common_period_dominant_warming_season'] = dominant.rename(columns={'season': 'dominant_season'})
    fields = ['kma_tavg_sen_slope', 'kma_tmax_sen_slope', 'kma_tmin_sen_slope', 'tavg_bias', 'tavg_rmse']
    products['common_period_cohort_origin_comparison'] = describe_groups(summary, 'cohort_origin', fields)
    for group, name in [('region_level1', 'regional_temperature'), ('elevation_band', 'elevation'), ('coastal_class', 'coastal')]:
        products[f'common_period_{name}_summary'] = describe_groups(summary, group, fields)
    rankings = products['common_period_temperature_rankings']
    rankings['ranking_scope'] = 'all common-period stations, 1991–2025; not climate risk'
    rankings = rankings.rename(columns={'sen_slope_per_decade': 'value'})
    rankings['unit'] = np.where(rankings.ranking.str.contains('proxy'), 'days/decade', 'deg C/decade')
    for metric, values in [('absolute TAVG Bias', summary.tavg_bias.abs()), ('TAVG RMSE', summary.tavg_rmse)]:
        frame = summary[['station_id', 'station_name', 'region']].copy()
        frame['value'], frame['ranking'] = values, metric
        frame['rank'], frame['unit'] = values.rank(method='min', ascending=False).astype(int), 'deg C'
        frame['is_climate_risk_ranking'], frame['ranking_scope'] = False, 'descriptive error ranking, 1991–2025'
        rankings = pd.concat([rankings, frame], ignore_index=True)
    products['common_period_temperature_rankings'] = rankings
    unique, weighting = unique_grid_summary(trends, grid_mapping, stations)
    products['common_period_nasa_unique_grid_summary'] = unique
    products['common_period_nasa_station_vs_grid_summary'] = weighting
    products['common_period_nasa_grid_mapping'] = grid_mapping
    if verify_history:
        products['common_period_tier_b_reproduction'] = reproduction
        products['tier_a_period_comparison_preparation'] = period_comparison(trends, stations, root)
    for key, frame in products.items():
        if 'station_id' in frame and 'cohort_origin' not in frame:
            products[key] = frame.merge(stations[['station_id', 'cohort_origin']], on='station_id', validate='many_to_one')
    return products
