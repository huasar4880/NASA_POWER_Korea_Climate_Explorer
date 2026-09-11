"""Validated saved inputs and protected-artifact inventory; no network access."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.config import PROJECT_ROOT
from src.spatial.robustness_audit import sha256
from src.spatial.spatial_data import validate_tier_a_station_set

OUTCOMES = ['kma_tavg_sen_slope', 'tavg_bias', 'tavg_rmse']
PREDICTORS = ['distance_to_coast_km', 'latitude', 'elevation_m']
BASE_WEIGHT = 'directed_knn_k4'
INPUTS = {
    'master': 'output/tables/spatial/nationwide_spatial_station_master.csv',
    'coast': 'output/tables/coastal/nationwide_station_coastal_distance.csv',
    'old_ols': 'output/tables/coastal/nationwide_coastal_multivariable_models.csv',
    'weights': 'output/tables/robustness/nationwide_spatial_weight_robustness.csv',
    'robustness': 'output/tables/robustness/nationwide_spatial_robustness_summary.csv',
    'combined': 'output/tables/spatial_robustness_and_coastal_summary.csv',
    'stations': 'output/tables/nationwide_tier_a_analysis_stations.csv',
    'shortlist': 'output/tables/nationwide_asos_longterm_shortlist.csv',
}


def protected_snapshot(root: Path = PROJECT_ROOT) -> dict:
    """Include every prior data/output file, including Stage-13 coastline binaries."""
    paths = [root / 'VERSION'] + [p for folder in ('data', 'output') for p in (root / folder).rglob('*') if p.is_file()]
    return {p.relative_to(root).as_posix(): {'sha256': sha256(p), 'mtime_ns': p.stat().st_mtime_ns}
            for p in sorted(paths) if 'spatial_models' not in p.relative_to(root).parts
            and p.name != 'spatial_modeling_manifest.json'}


def build_master(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Enforce exact Final A membership and complete covariates before any fit."""
    stations = frames['stations']
    validate_tier_a_station_set(stations)
    ids = set(stations.station_id)
    selected = frames['shortlist'].loc[frames['shortlist'].station_id.isin(ids)]
    if set(selected.station_id) != ids or not selected.eligibility_tier.eq('A').all():
        raise ValueError('Only Final Tier A stations are allowed')
    if selected.continuity_risk.isin(['high', 'unresolved', 'manual_review']).any():
        raise ValueError('Unresolved continuity station')
    for name in ('master', 'coast'):
        frame = frames[name]
        if frame.station_id.duplicated().any() or set(frame.station_id) != ids:
            raise ValueError(f'{name}: station membership mismatch')
    master = frames['master'].merge(frames['coast'][['station_id', 'distance_to_coast_km']],
                                    on='station_id', validate='one_to_one')
    master = master.set_index('station_id').loc[stations.station_id].reset_index()
    coords = ['latitude', 'longitude', 'elevation_m']
    if not np.allclose(master[coords], stations[coords]):
        raise ValueError('Coordinates differ from Final A')
    if not np.isfinite(master[[*PREDICTORS, 'longitude', *OUTCOMES]].to_numpy(float)).all():
        raise ValueError('Incomplete/nonfinite predictors or outcomes; no automatic imputation/drop')
    if (master.distance_to_coast_km < 0).any():
        raise ValueError('Negative coastline distance')
    return master


def load_inputs(root: Path = PROJECT_ROOT) -> tuple[pd.DataFrame, dict, dict, dict]:
    """Load saved source-of-truth tables and Stage-13 permutation settings."""
    frames = {k: pd.read_csv(root / p, dtype={'station_id': str}) for k, p in INPUTS.items()}
    config_path = root / 'config/spatial_robustness.json'
    config = json.loads(config_path.read_text())
    hashes = {p: sha256(root / p) for p in [*INPUTS.values(), 'config/spatial_robustness.json']}
    return build_master(frames), config, hashes, frames
