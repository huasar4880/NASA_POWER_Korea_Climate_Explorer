"""Isolated, fail-closed Stage17 orchestration; never invokes a downloader."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

from src.config import PROJECT_ROOT
from src.nationwide.tier_a_pipeline import _atomic_csv, _atomic_json
from src.spatial.robustness_audit import sha256, check_snapshot
from src.common_period_spatial.data import (TABLE_DIR, MANIFEST, PREFIX, OLD_INPUTS, TABLE_NAMES, snapshot, load_inputs,
                                           build_masters, validate_grid_series, grid_coordinates)
from src.common_period_spatial.statistics import (KMA_VARIABLES, NASA_VARIABLES, build_networks, global_results,
        robustness, duplication_sensitivity, bridge_comparisons, local_results, add_contrast_dtr,
        seasonal_results, associations)


def prepare_plan(root: Path = PROJECT_ROOT) -> tuple[dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """Read/validate inputs and describe computations without any write or HTTP request."""
    inputs, config, hashes = load_inputs(root)
    master, grids = build_masters(inputs)
    hashes.update(validate_grid_series(master, root))
    _, station_networks, sn = build_networks(master, 'STATION_LINKED')
    _, grid_networks, gn = build_networks(grid_coordinates(grids), 'UNIQUE_GRID')
    recommended = inputs['weight_recommendations'].set_index('weight_type').recommended_status
    for name in station_networks:
        if name in recommended and not recommended[name].startswith('RECOMMENDED_'):
            raise ValueError(f'Weight is not recommended by Stage14.5: {name}')
    old_ids = set(inputs['old_local'].station_id)
    if set(master.loc[master.cohort_origin.eq('TIER_A'), 'station_id']) != old_ids:
        raise ValueError('Bridge A-origin membership differs from historical Final A')
    from src.common_period_spatial.artifacts import MAPS, PNGS
    plan = {'status': 'dry_run', 'station_count': len(master), 'unique_NASA_grid_count': len(grids),
            'tier_a_count': int(master.cohort_origin.eq('TIER_A').sum()), 'tier_b_count': int(master.cohort_origin.eq('TIER_B').sum()),
            'shared_grid_groups': int(grids.station_count.gt(1).sum()),
            'stations_in_shared_grids': int(grids.loc[grids.station_count.gt(1), 'station_count'].sum()),
            'largest_grid_group': int(grids.station_count.max()), 'analysis_period': [1991, 2025],
            'NASA_API_calls': 0, 'KMA_API_calls': 0, 'station_weights': list(station_networks),
            'grid_weights': list(grid_networks), 'KMA_variables': KMA_VARIABLES, 'NASA_variables': NASA_VARIABLES,
            'bridge_variables': list(inputs['old_global'].variable),
            'expected_global_rows': (len(KMA_VARIABLES)+len(NASA_VARIABLES))*len(station_networks)+len(NASA_VARIABLES)*len(grid_networks),
            'expected_local_rows': len(master)*3, 'expected_bridge_rows': len(inputs['old_global']),
            'expected_seasonal_rows': 12, 'output_directories': [str(TABLE_DIR), 'output/charts/common_period_spatial', 'output/reports/common_period_spatial'],
            'expected_outputs': {'tables': [f'{PREFIX}{name}.csv' for name in TABLE_NAMES],
                'maps': [f'{name}.html' for name in MAPS]+[f'kma_tavg_{s}_map.html' for s in ('djf','mam','jja','son')],
                'charts': [f'{name}.png' for name in PNGS],
                'reports': ['common_period_51station_spatial_reanalysis_report.html', 'common_period_51station_spatial_reanalysis_report.md'],
                'manifest': str(MANIFEST)},
            'weight_networks': pd.concat([sn, gn], ignore_index=True).astype(object).where(pd.notna(pd.concat([sn, gn], ignore_index=True)), None).to_dict('records')}
    return inputs, config, hashes, master, grids, plan


def build_products(inputs: dict, config: dict, master: pd.DataFrame, grids: pd.DataFrame) -> dict:
    """Compose pure calculations into independent tables with no filesystem writes."""
    master, contrast, dtr = add_contrast_dtr(master, inputs, config)
    sd, sn, ss = build_networks(master, 'STATION_LINKED')
    gd, gn, gs = build_networks(grid_coordinates(grids), 'UNIQUE_GRID')
    results = pd.concat([global_results(master, sn, KMA_VARIABLES, 'KMA', 'STATION_LINKED', config),
                         global_results(master, sn, NASA_VARIABLES, 'NASA', 'STATION_LINKED', config),
                         global_results(grid_coordinates(grids), gn, NASA_VARIABLES, 'NASA', 'UNIQUE_GRID', config)], ignore_index=True)
    results.loc[results.variable.isin(['tavg_bias', 'tavg_rmse']), 'source'] = 'NASA-KMA'
    summary = robustness(results, config)
    old_new, bridge = bridge_comparisons(master, results, summary, inputs, config)
    local, stable = local_results(master, sn, config)
    inje_ids = master.loc[master.station_name.str.contains('인제', regex=False), 'station_id']
    old_local = inputs['old_local'].loc[lambda d: d.station_id.isin(inje_ids)].copy().assign(analysis='45 stations / 1981–2025')
    new_local = local.loc[local.station_id.isin(inje_ids)].copy().assign(analysis=f'{len(master)} stations / 1991–2025')
    products = {'spatial_station_master': master, 'nasa_unique_grid_spatial_master': grids,
                'station_distance_matrix': sd.rename_axis('station_id').reset_index(),
                'nasa_grid_distance_matrix': gd.rename_axis('nasa_grid_id').reset_index(),
                'spatial_weight_network_summary': pd.concat([ss, gs], ignore_index=True),
                'global_morans_i': results, 'spatial_robustness_summary': summary,
                'nasa_grid_duplication_spatial_sensitivity': duplication_sensitivity(results),
                'vs_1981_spatial_comparison': old_new, 'spatial_bridge_comparison': bridge,
                'local_moran_results': local, 'stable_local_patterns': stable,
                'inje_local_continuity': pd.concat([old_local, new_local], ignore_index=True),
                'tmax_tmin_warming_contrast': contrast, 'dtr_trends': dtr,
                'seasonal_spatial_analysis': seasonal_results(master, inputs, sn, config),
                'dominant_season': inputs['dominant_warming_season'].loc[lambda d: d.source.eq('KMA')].copy(),
                'data_quality': inputs['data_quality'].copy()}
    products.update(associations(master, inputs, config))
    # Save source-level seasonal map values for a read-only dashboard, without source reloading.
    products['seasonal_station_trends'] = inputs['seasonal_temperature_trends'].loc[lambda d: d.source.eq('KMA') & d.metric.eq('TAVG')].copy()
    return products


def validate_products(tables: dict, plan: dict) -> None:
    """Sanity gates for identity, finite statistics, family sizes and bridge accounting."""
    if set(tables) != set(TABLE_NAMES):
        raise ValueError('Expected Stage17 table inventory differs from generated products')
    global_ = tables['global_morans_i']
    if len(global_) != plan['expected_global_rows'] or not np.isfinite(global_[['Moran_I', 'expected_I']]).all().all():
        raise ValueError('Global Moran count/finite sanity failed')
    if not global_.permutation_p.between(0, 1).all():
        raise ValueError('Global p outside [0,1]')
    local = tables['local_moran_results']
    if len(local) != plan['expected_local_rows'] or not local.local_fdr_q.between(0, 1).all():
        raise ValueError('Local Moran family/q sanity failed')
    for key in ('coastal_distance_associations', 'coordinate_associations'):
        for column in ('pearson_r', 'spearman_rho'):
            if not tables[key][column].dropna().between(-1, 1).all():
                raise ValueError('Association coefficient out of range')
    if not tables['coastal_threshold_sensitivity'].fdr_q.between(0, 1).all():
        raise ValueError('Coastal FDR q out of range')
    bridge = tables['spatial_bridge_comparison']
    if not np.allclose(bridge.delta_period+bridge.delta_station_addition, bridge.I_51_1991-bridge.I_45_1981):
        raise ValueError('Bridge difference accounting failed')


def run_analysis(root: Path = PROJECT_ROOT, *, dry_run: bool = False) -> dict:
    """Run cache-only computations and export only the new namespace; gate publication on protection."""
    inputs, config, hashes, master, grids, plan = prepare_plan(root)
    if dry_run:
        return plan
    protected = snapshot(root)
    manifest = {**plan, 'status': 'pending', 'input_hashes': hashes,
                'permutations': config['moran_permutations'], 'seed': config['random_seed'],
                'coastal_thresholds_km': config['coastal_thresholds_km'], 'main_coastal_threshold_km': 30,
                'old_sources': OLD_INPUTS,
                'representation_definitions': {'STATION_LINKED': 'ASOS point coordinates; one NASA value per station',
                    'UNIQUE_GRID': 'inferred native MERRA-2 grid centre; one verified-equal NASA value per grid'},
                'bridge_definitions': 'A=Final A 1981–2025; B=same A 1991–2025; C=A+B 1991–2025. Associated sensitivity, not causal decomposition.',
                'duplication_operational_rule': 'sign change HIGH; otherwise p<.05 change or abs(delta_I)>.1 MODERATE; else LOW. Not an academic standard.',
                'FDR': 'Local BH within variable×weight stations; coastal BH within threshold across 9 metrics. Global/association raw p exploratory.',
                'grid_daily_series_verified': True, 'grid_coordinate_caveat': 'inferred official native grid geometry, not API-returned metadata',
                'threshold_caveat': 'Stage16 matched-valid-day proxy Sen slopes retained; every same-grid slope checked equal before collapse; not official event counts'}
    _atomic_json(manifest, root/MANIFEST)
    print('Stage17: verified cached sources; computing fixed-weight spatial comparisons', flush=True)
    tables = build_products(inputs, config, master, grids)
    validate_products(tables, plan)
    generated = []
    for name in sorted(tables):
        path = root/TABLE_DIR/f'{PREFIX}{name}.csv'
        _atomic_csv(tables[name], path)
        generated.append(path.relative_to(root).as_posix())
    saved = {name: pd.read_csv(root/TABLE_DIR/f'{PREFIX}{name}.csv', dtype={'station_id': str}) for name in tables}
    from src.common_period_spatial.artifacts import save_charts, write_reports
    generated += save_charts(saved, root) + write_reports(saved, root)
    changed = check_snapshot(root, protected)
    processing = sorted((root/'src/common_period_spatial').glob('*.py'))
    processing += [root/p for p in ('src/spatial/autocorrelation.py', 'src/spatial/weights.py', 'src/spatial/robustness.py',
        'src/spatial/associations.py', 'src/spatial/coastal_analysis.py', 'src/spatial/distances.py',
        'src/spatial_numerical/weights.py', 'src/statistical_analysis.py', 'src/common_period/grid.py') if (root/p).exists()]
    manifest.update(status='completed' if not changed else 'protection_failed',
                    protected_files_count=len(protected), protected_files_changed=changed,
                    output_files=generated, output_hashes={p: sha256(root/p) for p in generated},
                    processing_hashes={p.relative_to(root).as_posix(): sha256(p) for p in processing})
    _atomic_json(manifest, root/MANIFEST)
    if changed:
        raise ValueError('Prior-stage files changed; publication withheld')
    return manifest
