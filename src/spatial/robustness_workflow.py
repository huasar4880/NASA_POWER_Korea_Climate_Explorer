"""API-free Stage-13 orchestration with protected artifact audit."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.spatial.distances import calculate_distance_matrix
from src.spatial.robustness import calculate_robustness, weight_configurations
from src.spatial.robustness_audit import check_snapshot, sha256, snapshot
from src.spatial.spatial_data import STATION_PATH, load_spatial_config, validate_tier_a_station_set
from src.spatial.spatial_workflow import TABLE_PATHS

CONFIG_PATH = PROJECT_ROOT / 'config/spatial_robustness.json'
MANIFEST_PATH = PROJECT_ROOT / 'output/manifests/spatial_robustness_manifest.json'
SHORTLIST_PATH = PROJECT_ROOT / 'output/tables/nationwide_asos_longterm_shortlist.csv'
NAMES = {'weights': 'nationwide_spatial_weight_robustness', 'summary': 'nationwide_spatial_robustness_summary',
         'local': 'nationwide_local_moran_robustness', 'network': 'nationwide_weight_network_summary',
         'validation': 'nationwide_bias_rmse_robustness_summary'}


def load_inputs() -> tuple[pd.DataFrame, dict, dict[str, str]]:
    """Read and validate Final A and preserved Stage-12 inputs, without APIs."""
    config = json.loads(CONFIG_PATH.read_text())
    old_config = load_spatial_config()
    for key in ('moran_permutations', 'local_moran_permutations'):
        if config[key] < old_config[key]:
            raise ValueError('Stage-13 permutations cannot be below Stage 12')
    stations = pd.read_csv(STATION_PATH, dtype={'station_id': str})
    validate_tier_a_station_set(stations)
    shortlist = pd.read_csv(SHORTLIST_PATH, dtype={'station_id': str})
    selected = shortlist[shortlist.station_id.isin(stations.station_id)]
    if set(selected.station_id) != set(stations.station_id) or not selected.eligibility_tier.eq('A').all():
        raise ValueError('Final A selection includes non-A or unknown station')
    if selected.continuity_risk.isin(['high', 'unresolved', 'manual_review']).any():
        raise ValueError('Unresolved continuity station in Final A')
    tables = {key: pd.read_csv(path, dtype={'station_id': str}) for key, path in TABLE_PATHS.items()}
    master = tables['master']
    if master.station_id.duplicated().any() or set(master.station_id) != set(stations.station_id):
        raise ValueError('Stage-12 station set differs from Final A')
    coords = master.set_index('station_id').loc[stations.station_id, ['latitude','longitude','elevation_m']]
    if not np.allclose(coords.to_numpy(), stations[['latitude','longitude','elevation_m']].to_numpy()):
        raise ValueError('Stage-12 coordinates differ from Final A')
    contrast = tables['contrast'][['station_id', 'tmin_minus_tmax']]
    dtr = tables['dtr'].loc[tables['dtr'].source.eq('KMA'), ['station_id', 'sen_slope_per_decade']]
    master = master.merge(contrast, on='station_id', validate='one_to_one').merge(
        dtr.rename(columns={'sen_slope_per_decade': 'dtr_slope'}), on='station_id', validate='one_to_one')
    if len(master) != len(stations):
        raise ValueError('Missing contrast/DTR stations')
    files = [*TABLE_PATHS.values(), STATION_PATH, SHORTLIST_PATH, CONFIG_PATH,
             PROJECT_ROOT / 'config/spatial_analysis.json']
    hashes = {p.relative_to(PROJECT_ROOT).as_posix(): sha256(p) for p in files}
    return master, config, hashes


def run_robustness(dry_run: bool = False) -> dict:
    """Validate first; dry-run writes nothing, production writes only Stage 13."""
    master, config, hashes = load_inputs()
    distances = calculate_distance_matrix(master)
    plan = {'station_count': len(master), 'config': config, 'input_hashes': hashes,
            'weight_configurations': weight_configurations(distances, config),
            'NASA_API_calls': 0, 'KMA_API_calls': 0, 'dry_run': dry_run}
    if dry_run:
        return plan
    before = snapshot(PROJECT_ROOT)
    tables = calculate_robustness(master, distances, config)
    # Imports kept here so dry-run needs no coastline/plotting dependencies.
    from src.spatial.coastline import load_coastline
    from src.spatial.coastal_analysis import calculate_coastal
    from src.spatial.robustness_visualization import create_charts
    from src.spatial.robustness_reporting import write_reports

    coast = load_coastline(config['analysis_crs'])
    coastal = calculate_coastal(master, coast, config) if coast['available'] else {}
    paths = {}
    for key, table in tables.items():
        path = PROJECT_ROOT / f'output/tables/robustness/{NAMES[key]}.csv'
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path, index=False)
        paths[key] = path.relative_to(PROJECT_ROOT).as_posix()
    for name, table in coastal.items():
        path = PROJECT_ROOT / f'output/tables/coastal/nationwide_{name}.csv'
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path, index=False)
        paths[name] = path.relative_to(PROJECT_ROOT).as_posix()
    combined = tables['summary'].copy()
    if coastal:
        extra = coastal['coastal_continuous_associations'].loc[
            ~coastal['coastal_continuous_associations'].variable.isin(combined.variable), ['variable']].copy()
        extra['robustness_class'] = 'NOT_TESTED_GLOBAL_MORAN'
        combined = pd.concat([combined, extra], ignore_index=True)
    base = tables['weights'].query("weight_variant == 'directed_knn_k4'")[['variable', 'moran_i', 'permutation_p']]
    combined = combined.merge(base.rename(columns={'moran_i':'baseline_moran', 'permutation_p':'baseline_p'}), on='variable', how='left')
    combined['coastal_available'] = coast['available']
    for col in ('coastal_distance_spearman','coastal_distance_p','coastal_inland_median_difference','coastal_inland_fdr_q'):
        combined[col] = np.nan
    if coastal:
        assoc = coastal['coastal_continuous_associations'].set_index('variable')
        comparison = coastal['coastal_inland_comparison'].set_index('variable')
        for target, source, frame in [('coastal_distance_spearman','spearman_rho',assoc), ('coastal_distance_p','spearman_p',assoc),
                                      ('coastal_inland_median_difference','median_difference',comparison), ('coastal_inland_fdr_q','fdr_q',comparison)]:
            combined[target] = combined.variable.map(frame[source])
    combined['interpretation_flag'] = combined.robustness_class + ('; exploratory association, not causation' if coastal else '; COASTAL_UNAVAILABLE')
    path = PROJECT_ROOT / 'output/tables/spatial_robustness_and_coastal_summary.csv'
    combined.to_csv(path, index=False)
    paths['combined'] = path.relative_to(PROJECT_ROOT).as_posix()
    charts = create_charts(master, tables, coastal, coast, config)
    coast_meta = {k:v for k,v in coast.items() if k not in ('geometries','tree','source_geometry_ids')}
    plan.update({'coastline': coast_meta, 'generated_tables': paths, 'generated_charts': charts,
                 'main_coastal_threshold_km': float(coastal['coastal_inland_comparison'].threshold_km.iloc[0]) if coastal else None,
                 'coastal_thresholds_km': config['coastal_thresholds_km']})
    reports = write_reports(tables, coastal, plan)
    plan['generated_reports'] = reports
    changes = check_snapshot(PROJECT_ROOT, before)
    plan['protected_files_count'] = len(before)
    plan['protected_files_changed'] = changes
    if changes:
        raise RuntimeError(f'Protected artifacts changed: {changes}')
    output_files = [*paths.values(), *charts, *reports]
    plan['output_hashes'] = {name:sha256(PROJECT_ROOT/name) for name in output_files}
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    return plan


def report_from_saved() -> list[str]:
    """Regenerate only Stage-13 reports after verifying saved result checksums."""
    from src.spatial.robustness_reporting import write_reports
    manifest = json.loads(MANIFEST_PATH.read_text())
    for name, digest in manifest['output_hashes'].items():
        if name in manifest['generated_reports']:
            continue
        if sha256(PROJECT_ROOT/name) != digest:
            raise ValueError(f'Stage-13 output checksum mismatch: {name}')
    frames = {key:pd.read_csv(PROJECT_ROOT/path) for key,path in manifest['generated_tables'].items()}
    coastal = {key:frame for key,frame in frames.items() if key.startswith('coastal_') or key == 'station_coastal_distance'}
    return write_reports(frames, coastal, manifest)
