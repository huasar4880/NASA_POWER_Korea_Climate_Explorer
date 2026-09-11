"""Read-only inputs, identity checks and immutable prior-stage evidence."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.common_period.artifacts import load_tables as load_common_tables
from src.common_period.grid import series_fingerprint
from src.spatial.robustness_audit import sha256

NAMESPACE = 'common_period_spatial'
TABLE_DIR = Path('output/tables')/NAMESPACE
CHART_DIR = Path('output/charts')/NAMESPACE
REPORT_DIR = Path('output/reports')/NAMESPACE
MANIFEST = Path('output/manifests/common_period_spatial_reanalysis_manifest.json')
PREFIX = 'common_period_'
TABLE_NAMES = (
    'spatial_station_master', 'nasa_unique_grid_spatial_master', 'station_distance_matrix', 'nasa_grid_distance_matrix',
    'spatial_weight_network_summary', 'global_morans_i', 'spatial_robustness_summary',
    'nasa_grid_duplication_spatial_sensitivity', 'vs_1981_spatial_comparison', 'spatial_bridge_comparison',
    'local_moran_results', 'stable_local_patterns', 'tmax_tmin_warming_contrast', 'dtr_trends',
    'seasonal_spatial_analysis', 'coastal_distance_associations', 'coastal_threshold_sensitivity',
    'bias_rmse_shared_grid_sensitivity', 'spatial_regional_summary', 'spatial_elevation_summary',
    'coastal_old_new_comparison', 'coordinate_associations', 'data_quality', 'dominant_season',
    'inje_local_continuity', 'seasonal_station_trends')
GRID_WARNING = ('51개 ASOS station은 더 적은 수의 NASA POWER grid에 대응할 수 있으므로 station-linked NASA 공간통계는 동일 grid의 반복표현 영향을 받을 수 있습니다. Unique-grid 결과를 함께 확인해야 합니다.')
BRIDGE_WARNING = ('45/1981→45/1991은 기간 변경, 45/1991→51/1991은 station 구성 변경과 연관된 sensitivity 비교이며 인과분해가 아닙니다.')
OLD_INPUTS = {
    'old_global': 'output/tables/spatial/nationwide_global_morans_i.csv',
    'old_weights': 'output/tables/robustness/nationwide_spatial_weight_robustness.csv',
    'old_robustness': 'output/tables/robustness/nationwide_spatial_robustness_summary.csv',
    'old_local': 'output/tables/robustness/nationwide_local_moran_robustness.csv',
    'old_coastal': 'output/tables/coastal/nationwide_coastal_threshold_sensitivity.csv',
    'old_latitude': 'output/tables/spatial/nationwide_latitude_associations.csv',
    'old_longitude': 'output/tables/spatial/nationwide_longitude_associations.csv',
    'old_elevation_m': 'output/tables/spatial/nationwide_elevation_associations.csv',
    'weight_recommendations': 'output/tables/spatial_models_numerical/spatial_model_final_specification_recommendation.csv',
}


def snapshot(root: Path = PROJECT_ROOT) -> dict:
    """Hash and timestamp every existing data/output file except Stage17 itself."""
    paths = [root/'VERSION'] + [p for folder in ('data', 'output') for p in (root/folder).rglob('*') if p.is_file()]
    return {p.relative_to(root).as_posix(): {'sha256': sha256(p), 'mtime_ns': p.stat().st_mtime_ns}
            for p in sorted(paths) if NAMESPACE not in p.relative_to(root).parts and p != root/MANIFEST}


def load_inputs(root: Path = PROJECT_ROOT) -> tuple[dict, dict, dict]:
    """Verify Stage16 checksums and read historical sources without requesting HTTP."""
    frames = {k.removeprefix(PREFIX): v for k, v in load_common_tables(root).items()}
    manifest_path = root/'output/manifests/common_period_51station_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    hashes = {p: sha256(root/p) for p in manifest['output_hashes'] if p.endswith('.csv')}
    hashes[manifest_path.relative_to(root).as_posix()] = sha256(manifest_path)
    for name, path in OLD_INPUTS.items():
        frames[name] = pd.read_csv(root/path, dtype={'station_id': str})
        hashes[path] = sha256(root/path)
    config_path = 'config/spatial_robustness.json'
    config = json.loads((root/config_path).read_text())
    hashes[config_path] = sha256(root/config_path)
    return frames, config, hashes


def validate_grid_series(master: pd.DataFrame, root: Path = PROJECT_ROOT) -> dict:
    """Recheck all daily NASA temperatures including dates/NaNs against saved fingerprints."""
    hashes, fingerprints = {}, {}
    for row in master.itertuples():
        path = root/f'data/common_period/nasa_processed/{row.station_id}_nasa_temperature_1991_2025.csv'
        frame = pd.read_csv(path, parse_dates=['date'])
        expected = pd.date_range('1991-01-01', '2025-12-31')
        if frame.date.duplicated().any() or not pd.DatetimeIndex(frame.date).equals(expected):
            raise ValueError(f'NASA daily calendar mismatch: {row.station_id}')
        digest = series_fingerprint(frame.rename(columns={'nasa_t2m': 'T2M', 'nasa_tmax': 'T2M_MAX', 'nasa_tmin': 'T2M_MIN'}))
        if digest != row.nasa_series_sha256:
            raise ValueError(f'NASA daily fingerprint mismatch: {row.station_id}')
        fingerprints.setdefault(row.nasa_grid_id, set()).add(digest)
        hashes[path.relative_to(root).as_posix()] = sha256(path)
    if any(len(values) != 1 for values in fingerprints.values()):
        raise ValueError('Shared-grid NASA daily series differ; no grid aggregation permitted')
    return hashes


def build_masters(frames: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join common-period station metrics and collapse only identical NASA metrics by grid."""
    master = frames['1991_2025_station_master'].copy()
    summary = frames['station_temperature_summary']
    extra = ['station_id'] + [c for c in summary if c not in master]
    master = master.merge(summary[extra], on='station_id', validate='one_to_one')
    for source in ('KMA', 'NASA'):
        for metric in ('TAVG', 'TMAX', 'TMIN'):
            data = frames['temperature_trends'].loc[lambda d: d.source.eq(source) & d.metric.eq(metric)]
            master[f'{source.lower()}_{metric.lower()}_sen_slope'] = master.station_id.map(data.set_index('station_id').sen_slope_per_decade)
        for short, threshold, old in [('33c', 'TMAX_GE_33', 'days_tmax_ge_33'), ('25c', 'TMIN_GE_25', 'days_tmin_ge_25')]:
            data = frames['threshold_trends'].loc[lambda d: d.source.eq(source) & d.threshold.eq(threshold)]
            master[f'{source.lower()}_{short}_sen_slope'] = master.station_id.map(data.set_index('station_id').sen_slope_per_decade)
            master[f'{old}_{source.lower()}_slope'] = master[f'{source.lower()}_{short}_sen_slope']
    master['coastal_30km_class'] = np.where(master.distance_to_coast_km.le(30), 'Coastal', 'Inland')
    master = master.sort_values('station_id', key=lambda s: pd.to_numeric(s)).reset_index(drop=True)
    if master.station_id.duplicated().any() or master.empty:
        raise ValueError('Empty or duplicate common-period stations')
    if not np.isfinite(master[['latitude', 'longitude']].to_numpy(float)).all():
        raise ValueError('Nonfinite station coordinates')
    metrics = [f'nasa_{m}_sen_slope' for m in ('tavg', 'tmax', 'tmin', '33c', '25c')]
    rows = []
    for grid_id, group in master.groupby('nasa_grid_id', sort=True):
        values = group[metrics].to_numpy(float)
        if not np.isfinite(values).all() or not np.allclose(values, values[0], rtol=0, atol=1e-12):
            raise ValueError(f'NASA metrics differ within grid: {grid_id}; cannot choose an arbitrary station')
        rows.append({'nasa_grid_id': grid_id, 'nasa_grid_latitude': group.nasa_grid_latitude.iloc[0],
                     'nasa_grid_longitude': group.nasa_grid_longitude.iloc[0], 'station_count': len(group),
                     'station_ids': '|'.join(group.station_id), 'station_names': '|'.join(group.station_name),
                     'cohort_origins': '|'.join(sorted(group.cohort_origin.unique())),
                     **dict(zip(metrics, values[0]))})
    grids = pd.DataFrame(rows)
    if grids.nasa_grid_id.duplicated().any() or grids.station_count.sum() != len(master):
        raise ValueError('Grid membership integrity failed')
    expected = frames['nasa_grid_mapping'].set_index('nasa_grid_id').station_count.sort_index()
    if not grids.set_index('nasa_grid_id').station_count.equals(expected):
        raise ValueError('Grid composition differs from Stage16')
    return master, grids


def grid_coordinates(grids: pd.DataFrame) -> pd.DataFrame:
    """Expose native-centre geometry using the existing station-distance function schema."""
    return grids.rename(columns={'nasa_grid_id': 'station_id', 'nasa_grid_latitude': 'latitude', 'nasa_grid_longitude': 'longitude'})
