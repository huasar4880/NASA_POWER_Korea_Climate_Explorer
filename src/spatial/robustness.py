"""Stage-13 weight families and reproducible sensitivity analysis (no network)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.sparse.csgraph import connected_components, minimum_spanning_tree

from src.spatial.autocorrelation import GLOBAL_VARIABLES, global_moran_permutation, local_moran_permutation
from src.spatial.distances import validate_distance_matrix
from src.spatial.weights import SpatialWeights, align_values, build_knn_weights


def row_standardize(matrix: np.ndarray) -> np.ndarray:
    """Normalize nonnegative zero-diagonal weights; reject isolates and nonfinite data."""
    raw = np.asarray(matrix, dtype=float)
    if raw.ndim != 2 or raw.shape[0] != raw.shape[1] or not np.isfinite(raw).all():
        raise ValueError('Invalid weight matrix')
    if (raw < 0).any() or np.any(np.diag(raw) != 0) or np.any(raw.sum(axis=1) == 0):
        raise ValueError('Negative/self weights or isolated station')
    return raw / raw.sum(axis=1, keepdims=True)


def distance_band_limits(distances: pd.DataFrame) -> tuple[float, float]:
    """Return minimal no-isolate and connected radii (MST bottleneck), in km."""
    validate_distance_matrix(distances)
    values = distances.to_numpy(float).copy()
    np.fill_diagonal(values, np.inf)
    no_isolate = float(values.min(axis=1).max())
    np.fill_diagonal(values, 0)
    connected = float(minimum_spanning_tree(values).data.max())
    return no_isolate, max(no_isolate, connected)


def weight_configurations(distances: pd.DataFrame, config: dict) -> list[dict]:
    """Generate fixed KNN/IDW settings and data-based connected distance bands."""
    no_isolate, connected = distance_band_limits(distances)
    settings = []
    for family in ('directed_knn', 'symmetric_knn'):
        for k in config['knn_values']:
            settings.append(dict(weight_family=family, weight_variant=f'{family}_k{k}', k=k))
    for factor in config['distance_band_multipliers']:
        if factor < 1:
            raise ValueError('Distance bands must be at least the connected radius')
        settings.append(dict(weight_family='distance_band', weight_variant=f'distance_band_x{factor:g}',
                             distance_threshold_km=float(np.nextafter(connected * factor, np.inf)),
                             no_isolate_threshold_km=no_isolate, connected_threshold_km=connected))
    for power in config['inverse_distance_powers']:
        settings.append(dict(weight_family='inverse_distance', weight_variant=f'inverse_distance_p{power}',
                             inverse_distance_power=power))
    return settings


def build_weight(distances: pd.DataFrame, setting: dict) -> SpatialWeights:
    """Build a row-standardized family; symmetric KNN uses union adjacency."""
    validate_distance_matrix(distances)
    values = distances.to_numpy(float)
    family = setting['weight_family']
    k = int(setting.get('k', 0))
    if family in ('directed_knn', 'symmetric_knn'):
        raw = build_knn_weights(distances, k).matrix
        if family == 'symmetric_knn':
            raw = ((raw > 0) | (raw.T > 0)).astype(float)
    elif family == 'distance_band':
        raw = ((values > 0) & (values <= setting['distance_threshold_km'])).astype(float)
    elif family == 'inverse_distance':
        power = float(setting['inverse_distance_power'])
        if power <= 0:
            raise ValueError('Inverse distance power must be positive')
        raw = np.zeros_like(values)
        np.power(values, -power, out=raw, where=values > 0)
    else:
        raise ValueError(f'Unknown weight family: {family}')
    matrix = row_standardize(raw)
    ids = tuple(distances.index.astype(str))
    i, j = np.nonzero(matrix)
    neighbors = pd.DataFrame({'station_id': np.array(ids)[i], 'neighbor_station_id': np.array(ids)[j],
                              'distance_km': values[i, j], 'weight': matrix[i, j]})
    return SpatialWeights(ids, matrix, neighbors, family, k, values)


def network_summary(weight: SpatialWeights, setting: dict) -> dict:
    """Describe adjacency, components and numeric symmetry after normalization."""
    adjacency = weight.matrix > 0
    counts = adjacency.sum(axis=1)
    return {**setting, 'n_stations': len(counts), 'isolates': int((counts == 0).sum()),
            'mean_neighbor_count': float(counts.mean()), 'median_neighbor_count': float(np.median(counts)),
            'min_neighbor_count': int(counts.min()), 'max_neighbor_count': int(counts.max()),
            'weak_components': int(connected_components(adjacency, directed=False)[0]),
            'adjacency_symmetric': bool(np.array_equal(adjacency, adjacency.T)),
            'numeric_weights_symmetric': bool(np.allclose(weight.matrix, weight.matrix.T)),
            'row_standardized': True, 'finite_weights': bool(np.isfinite(weight.matrix).all())}


def classify_robustness(group: pd.DataFrame, fraction: float = .75, alpha: float = .05) -> str:
    """Operational (not academic standard) rule; sign reversal takes precedence."""
    if group.empty or not np.isfinite(group[['moran_i', 'permutation_p']].to_numpy()).all():
        raise ValueError('Robustness classification requires finite, valid results')
    positive = group.moran_i > 0
    significant = group.permutation_p < alpha
    if positive.any() and (group.moran_i < 0).any():
        return 'INCONSISTENT_DIRECTION'
    if (positive & significant).mean() >= fraction:
        return 'ROBUST_POSITIVE'
    if (~significant).mean() >= fraction:
        return 'ROBUST_NON_SIGNIFICANT'
    return 'WEIGHT_SENSITIVE'


def summarize_robustness(results: pd.DataFrame, fraction: float, alpha: float) -> pd.DataFrame:
    """Retain settings counts and range so labels cannot hide minority settings."""
    rows = []
    for variable, group in results.groupby('variable', sort=False):
        rows.append({'variable': variable, 'robustness_class': classify_robustness(group, fraction, alpha),
                     'n_configurations': len(group), 'n_significant': int((group.permutation_p < alpha).sum()),
                     'n_positive_significant': int(((group.permutation_p < alpha) & (group.moran_i > 0)).sum()),
                     'moran_min': group.moran_i.min(), 'moran_max': group.moran_i.max(),
                     'p_min': group.permutation_p.min(), 'p_max': group.permutation_p.max()})
    return pd.DataFrame(rows)


def stable_local_patterns(local: pd.DataFrame) -> pd.Series:
    """True only if every compared configuration has the same significant quadrant."""
    expected = local.weight_variant.nunique()
    return local.groupby('station_id').apply(
        lambda g: len(g) == expected and g.local_significant_fdr.all() and g.cluster_type_fdr.nunique() == 1,
        include_groups=False,
    ).rename('stable_local_pattern')


def calculate_robustness(master: pd.DataFrame, distances: pd.DataFrame, config: dict) -> dict[str, pd.DataFrame]:
    """Compute eight global metrics and TAVG local comparisons with shared seeds."""
    settings = weight_configurations(distances, config)
    rows, networks, locals_ = [], [], []
    for setting in settings:
        weight = build_weight(distances, setting)
        network = network_summary(weight, setting)
        networks.append(network)
        for offset, variable in enumerate(GLOBAL_VARIABLES):
            values = align_values(master, variable, weight)
            result = global_moran_permutation(values, weight.matrix, config['moran_permutations'], config['random_seed'] + offset)
            rows.append({**setting, 'variable': variable, 'n_stations': len(values),
                         'mean_neighbor_count': network['mean_neighbor_count'],
                         'moran_i': result.moran_i, 'expected_i': result.expected_i,
                         'permutation_p': result.permutation_p, 'significant_0_05': result.permutation_p < config['alpha'],
                         'random_seed': config['random_seed'] + offset, 'permutations': result.permutations})
        if setting['weight_variant'] in ('directed_knn_k4', 'symmetric_knn_k4', 'directed_knn_k3', 'directed_knn_k5', 'distance_band_x1', 'inverse_distance_p2'):
            local = local_moran_permutation(align_values(master, 'kma_tavg_sen_slope', weight), weight,
                                             config['local_moran_permutations'], config['random_seed'], config['alpha'])
            local['weight_variant'] = setting['weight_variant']
            locals_.append(local)
    results = pd.DataFrame(rows)
    local = pd.concat(locals_, ignore_index=True)
    local = local.merge(stable_local_patterns(local), on='station_id', validate='many_to_one')
    local = local.merge(master[['station_id', 'station_name']], on='station_id', validate='many_to_one')
    summary = summarize_robustness(results, config['robust_fraction'], config['alpha'])
    return {'weights': results, 'summary': summary, 'local': local, 'network': pd.DataFrame(networks),
            'validation': summary[summary.variable.isin(['tavg_bias', 'tavg_rmse'])].copy()}
