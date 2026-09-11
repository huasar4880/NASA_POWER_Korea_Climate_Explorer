"""Reuse established spatial statistics with prespecified Stage17 comparisons."""
from __future__ import annotations

import numpy as np
import pandas as pd
from src.spatial.autocorrelation import GLOBAL_VARIABLES, global_moran_permutation, local_moran_permutation
from src.spatial.weights import SpatialWeights, align_values
from src.spatial.distances import calculate_distance_matrix, validate_distance_matrix
from src.spatial.robustness import network_summary, summarize_robustness, stable_local_patterns
from src.spatial_numerical.weights import weight_settings, build_matrix
from src.spatial.associations import calculate_dtr_trends, build_tmax_tmin_contrast, calculate_association
from src.spatial.coastal_analysis import METRICS, continuous_associations, coastal_comparisons, threshold_consistency

KMA_VARIABLES = ['kma_tavg_sen_slope', 'kma_tmax_sen_slope', 'kma_tmin_sen_slope',
                 'days_tmax_ge_33_kma_slope', 'days_tmin_ge_25_kma_slope', 'tmin_minus_tmax', 'dtr_slope', 'tavg_bias', 'tavg_rmse']
NASA_VARIABLES = ['nasa_tavg_sen_slope', 'nasa_tmax_sen_slope', 'nasa_tmin_sen_slope', 'nasa_33c_sen_slope', 'nasa_25c_sen_slope']
LOCAL_WEIGHTS = ('directed_knn_k4', 'symmetric_knn_k4', 'inverse_distance_p2_row')
# Preserve historical offsets for all eight old comparison variables.
SEED_OFFSETS = {**{v: i for i, v in enumerate(GLOBAL_VARIABLES)}, 'nasa_tmax_sen_slope': 100,
                'nasa_tmin_sen_slope': 101, 'nasa_33c_sen_slope': 200, 'nasa_25c_sen_slope': 201,
                'tmin_minus_tmax': 300, 'dtr_slope': 301}


def configurations(distances: pd.DataFrame) -> list[dict]:
    """Stage14.5 recommended row weights plus directed K3/K5/K6; never raw or full IDW p1."""
    chosen = [s for s in weight_settings(distances) if s['row_standardized'] and
              not (s['family'] == 'inverse_distance' and s['power'] == 1 and s['cutoff_km'] is None)]
    for k in (3, 5, 6):
        if k < len(distances):
            chosen.append(dict(weight_type=f'directed_knn_k{k}', family='directed_knn', k=k, row_standardized=True))
    return [s for s in chosen if s.get('k', 0) < len(distances)]


def build_networks(data: pd.DataFrame, representation: str) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Rebuild distance-dependent cutoffs separately for each spatial representation."""
    distances = calculate_distance_matrix(data)
    validate_distance_matrix(distances)
    networks, summaries = {}, []
    for spec in configurations(distances):
        _, matrix = build_matrix(distances, spec)
        weight = SpatialWeights(tuple(distances.index), matrix, pd.DataFrame(), spec['family'], spec.get('k', 0), distances.to_numpy())
        setting = dict(weight_family=spec['family'], weight_variant=spec['weight_type'], k=spec.get('k'),
                       distance_threshold=spec.get('cutoff_km'), idw_power=spec.get('power'))
        summary = network_summary(weight, setting)
        summary.update(representation=representation, n_spatial_units=len(data), edge_count=int((matrix > 0).sum()),
                       density=float((matrix > 0).sum()/(len(data)*(len(data)-1))))
        if summary['isolates'] or summary['weak_components'] != 1:
            raise ValueError(f'Invalid network: {representation}/{spec["weight_type"]}')
        networks[spec['weight_type']] = (weight, setting)
        summaries.append(summary)
    return distances, networks, pd.DataFrame(summaries)


def global_results(data: pd.DataFrame, networks: dict, variables: list[str], source: str,
                   representation: str, config: dict) -> pd.DataFrame:
    """Compute deterministic two-sided permutation tests with historical metric seeds."""
    rows = []
    for weight, setting in networks.values():
        for variable in variables:
            seed = config['random_seed'] + SEED_OFFSETS[variable]
            values = align_values(data, variable, weight)
            result = global_moran_permutation(values, weight.matrix, config['moran_permutations'], seed)
            rows.append({**setting, 'variable': variable, 'source': source, 'representation': representation,
                         'n_spatial_units': len(values), 'Moran_I': result.moran_i, 'moran_i': result.moran_i,
                         'expected_I': result.expected_i, 'permutation_p': result.permutation_p,
                         'significant_0_05': result.permutation_p < config['alpha'], 'seed': seed,
                         'permutations': result.permutations})
    return pd.DataFrame(rows)


def robustness(results: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Apply exactly Stage13's sign-first/75% operational rule separately by representation."""
    frames = []
    for (source, representation), group in results.groupby(['source', 'representation'], sort=True):
        result = summarize_robustness(group, config['robust_fraction'], config['alpha'])
        frames.append(result.assign(source=source, representation=representation))
    return pd.concat(frames, ignore_index=True)


def duplication_class(station_i: float, grid_i: float, station_p: float, grid_p: float,
                      small_difference: float = .1, alpha: float = .05) -> str:
    """Project rule: sign change HIGH; same sign but p-class change or |ΔI|>.1 MODERATE."""
    if not np.isfinite([station_i, grid_i, station_p, grid_p]).all():
        raise ValueError('Duplication classification requires finite paired results')
    if np.sign(station_i) != np.sign(grid_i):
        return 'DUPLICATION_HIGH_IMPACT'
    if (station_p < alpha) != (grid_p < alpha) or abs(grid_i-station_i) > small_difference:
        return 'DUPLICATION_MODERATE_IMPACT'
    return 'DUPLICATION_LOW_IMPACT'


def duplication_sensitivity(results: pd.DataFrame) -> pd.DataFrame:
    """Pair exactly the same NASA metric and weight family across the two geometries."""
    nasa = results.loc[results.source.eq('NASA')]
    keys = ['variable', 'weight_variant']
    left = nasa.loc[nasa.representation.eq('STATION_LINKED')].set_index(keys)
    right = nasa.loc[nasa.representation.eq('UNIQUE_GRID')].set_index(keys)
    # A small grid network may not support the station network's largest k.
    # Compare only configurations valid in both; never classify an absent result.
    common = left.index.intersection(right.index, sort=False)
    left, right = left.loc[common], right.loc[common]
    rows = []
    for key, station in left.iterrows():
        grid = right.loc[key]
        delta = grid.Moran_I - station.Moran_I
        rows.append(dict(zip(keys, key)) | {'station_linked_Moran_I': station.Moran_I,
                    'station_linked_p': station.permutation_p, 'unique_grid_Moran_I': grid.Moran_I,
                    'unique_grid_p': grid.permutation_p, 'difference_I': delta, 'absolute_difference_I': abs(delta),
                    'significance_same': station.significant_0_05 == grid.significant_0_05,
                    'direction_same': np.sign(station.Moran_I) == np.sign(grid.Moran_I),
                    'duplication_class': duplication_class(station.Moran_I, grid.Moran_I, station.permutation_p, grid.permutation_p)})
    return pd.DataFrame(rows)


def bridge_comparisons(master: pd.DataFrame, results: pd.DataFrame, summary: pd.DataFrame,
                       inputs: dict, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute fixed A-origin bridge; associated I differences do not constitute causation."""
    bridge = master.loc[master.cohort_origin.eq('TIER_A')].copy()
    _, networks, _ = build_networks(bridge, 'BRIDGE_TIER_A')
    main_network = {'directed_knn_k4': networks['directed_knn_k4']}
    new = results.loc[results.weight_variant.eq('directed_knn_k4') & results.representation.eq('STATION_LINKED')].set_index('variable')
    middle = global_results(bridge, main_network, list(GLOBAL_VARIABLES), 'BRIDGE', 'STATION_LINKED', config).set_index('variable')
    old = inputs['old_global'].set_index('variable')
    old_class = inputs['old_robustness'].set_index('variable')
    new_class = summary.loc[summary.representation.eq('STATION_LINKED')].set_index('variable')
    comparison, bridges = [], []
    for variable in GLOBAL_VARIABLES:
        a, b, c = old.loc[variable], middle.loc[variable], new.loc[variable]
        if int(a.n_stations) != len(bridge):
            raise ValueError('Historical and bridge Tier A counts differ')
        period, composition = b.Moran_I-a.moran_i, c.Moran_I-b.Moran_I
        bridges.append({'variable': variable, 'n_old': int(a.n_stations), 'n_bridge': len(bridge), 'n_new': len(master),
                        'I_45_1981': a.moran_i, 'p_45_1981': a.permutation_p,
                        'I_45_1991': b.Moran_I, 'p_45_1991': b.permutation_p,
                        'I_51_1991': c.Moran_I, 'p_51_1991': c.permutation_p,
                        'delta_period': period, 'delta_station_addition': composition,
                        'interpretation_flag': ('equal associated changes' if np.isclose(abs(period), abs(composition), rtol=0, atol=1e-12)
                                                else 'period-associated larger' if abs(period) > abs(composition) else 'composition-associated larger'),
                        'interpretation_scope': 'sensitivity association, not causal decomposition'})
        comparison.append({'variable': variable, 'old_Moran_I': a.moran_i, 'old_p': a.permutation_p,
                           'new_Moran_I': c.Moran_I, 'new_p': c.permutation_p, 'delta_I': c.Moran_I-a.moran_i,
                           'old_classification': old_class.loc[variable, 'robustness_class'],
                           'new_classification': new_class.loc[variable, 'robustness_class'],
                           'significance_changed': (a.permutation_p < .05) != (c.permutation_p < .05),
                           'classification_changed': old_class.loc[variable, 'robustness_class'] != new_class.loc[variable, 'robustness_class'],
                           'classification_caveat': 'same rule, historical 13 weights vs current recommended 9 weights'})
    return pd.DataFrame(comparison), pd.DataFrame(bridges)


def local_results(master: pd.DataFrame, networks: dict, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """BH per weight×TAVG across all stations; stable requires all three weights to agree."""
    frames = []
    for name in LOCAL_WEIGHTS:
        weight, _ = networks[name]
        local = local_moran_permutation(align_values(master, 'kma_tavg_sen_slope', weight), weight,
                                       config['local_moran_permutations'], config['random_seed'], config['alpha'])
        frames.append(local.assign(weight_variant=name, variable='kma_tavg_sen_slope', fdr_family=f'KMA TAVG/{name}', fdr_family_size=len(master)))
    local = pd.concat(frames, ignore_index=True)
    stable = stable_local_patterns(local).reset_index()
    stable = stable.merge(master[['station_id', 'station_name']], on='station_id', validate='one_to_one')
    base = local.loc[local.weight_variant.eq('directed_knn_k4'), ['station_id', 'cluster_type_fdr']]
    stable = stable.merge(base, on='station_id', validate='one_to_one')
    local = local.merge(stable[['station_id', 'station_name', 'stable_local_pattern']], on='station_id', validate='many_to_one')
    return local, stable


def add_contrast_dtr(master: pd.DataFrame, inputs: dict, config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """DTR is annual Tmax mean minus annual Tmin mean, then refitted Sen, not slope subtraction."""
    contrast = build_tmax_tmin_contrast(master)
    annual = pd.concat([inputs['kma_annual_temperature'], inputs['nasa_annual_temperature']], ignore_index=True)
    dtr = calculate_dtr_trends(annual, master, config['alpha'])
    dtr['fdr_family'] = dtr.source + ' DTR: all common-period stations 1991–2025'
    result = master.copy()
    result['tmin_minus_tmax'] = result.station_id.map(contrast.set_index('station_id').tmin_minus_tmax)
    kma = dtr.loc[dtr.source.eq('KMA')].set_index('station_id')
    result['dtr_slope'] = result.station_id.map(kma.sen_slope_per_decade)
    return result, contrast, dtr


def seasonal_results(master: pd.DataFrame, inputs: dict, networks: dict, config: dict) -> pd.DataFrame:
    """Four seasonal KMA TAVG Moran tests using main/symmetric/IDW p2 weights."""
    rows = []
    data = inputs['seasonal_temperature_trends']
    for offset, season in enumerate(('DJF', 'MAM', 'JJA', 'SON')):
        selected = data.loc[data.source.eq('KMA') & data.metric.eq('TAVG') & data.season.eq(season)]
        for name in LOCAL_WEIGHTS:
            weight, setting = networks[name]
            values = align_values(selected, 'sen_slope_per_decade', weight)
            result = global_moran_permutation(values, weight.matrix, config['moran_permutations'], config['random_seed']+offset)
            rows.append({**setting, 'season': season, 'source': 'KMA', 'representation': 'STATION_LINKED',
                         'n_spatial_units': len(values), 'median_slope': float(np.median(values)),
                         'Moran_I': result.moran_i, 'expected_I': result.expected_i, 'permutation_p': result.permutation_p,
                         'seed': config['random_seed']+offset, 'permutations': result.permutations})
    return pd.DataFrame(rows)


def descriptive_groups(master: pd.DataFrame, group_column: str) -> pd.DataFrame:
    """Unweighted station medians/IQR, explicitly retaining small sample flags."""
    rows = []
    for group, data in master.groupby(group_column, sort=True):
        row = {group_column: group, 'station_count': len(data), 'small_sample_region': len(data) < 3,
               'scope': 'unweighted station sample, not area mean or causality'}
        for variable in ('kma_tavg_sen_slope', 'kma_tmax_sen_slope', 'kma_tmin_sen_slope', 'tavg_bias', 'tavg_rmse'):
            row.update({f'{variable}_median': data[variable].median(), f'{variable}_iqr': data[variable].quantile(.75)-data[variable].quantile(.25)})
        rows.append(row)
    return pd.DataFrame(rows)


def associations(master: pd.DataFrame, inputs: dict, config: dict) -> dict[str, pd.DataFrame]:
    """Recompute coast and coordinate associations; preserve Stage13 group/FDR rules."""
    coast = threshold_consistency(coastal_comparisons(master, config['coastal_thresholds_km'], config['alpha']))
    old = inputs['old_coastal'][['variable', 'threshold_km', 'threshold_interpretation', 'fdr_significant']]
    comparison = coast.merge(old, on=['variable', 'threshold_km'], suffixes=('_new', '_old'), validate='one_to_one')
    comparison['classification_same'] = comparison.threshold_interpretation_new.eq(comparison.threshold_interpretation_old)
    coordinates = []
    for x in ('latitude', 'longitude', 'elevation_m'):
        for y in ('kma_tavg_sen_slope', 'kma_tmax_sen_slope', 'kma_tmin_sen_slope', 'tavg_bias', 'tavg_rmse'):
            row = calculate_association(master, x, y)
            old = inputs[f'old_{x}'].loc[lambda d: d.climate_metric.eq(y)]
            row.update(old_pearson_r=old.pearson_r.iloc[0] if len(old) else np.nan,
                       old_spearman_rho=old.spearman_rho.iloc[0] if len(old) else np.nan,
                       old_result_available=bool(len(old)))
            coordinates.append(row)
    shared = descriptive_groups(master, 'nasa_grid_shared')
    return {'coastal_distance_associations': continuous_associations(master),
            'coastal_threshold_sensitivity': coast, 'coastal_old_new_comparison': comparison,
            'coordinate_associations': pd.DataFrame(coordinates),
            'spatial_regional_summary': descriptive_groups(master, 'region_level1'),
            'spatial_elevation_summary': descriptive_groups(master, 'elevation_band'),
            'bias_rmse_shared_grid_sensitivity': shared}
