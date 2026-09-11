"""Isolated Tier B orchestration and auditable manifests."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT
from src.nationwide.tier_a_pipeline import _atomic_csv, _atomic_json
from src.nationwide.eligibility import load_screening_config
from src.spatial.coastline import load_coastline, station_distances
from src.spatial.robustness_audit import sha256, check_snapshot
from src.tier_b.data import (START, END, SHORTLIST, MASTER, TABLE_DIR, MANIFEST, CountingSession,
                             download_plan, load_stations, prepare, snapshot)
from src.tier_b.analysis import build_products
from src.tier_b.artifacts import save_charts, write_reports


def coastal_distances(stations: pd.DataFrame, root: Path) -> pd.DataFrame:
    """Use only the verified Stage13 coastline cache, with no download or coastal inference."""
    coast = load_coastline('EPSG:5179', root/'data/geospatial/coastline')
    if not coast['available']:
        raise ValueError('Verified coastline cache unavailable; Tier B coastal output withheld')
    result = station_distances(stations, coast)
    result['scope'] = 'Tier B descriptive distance only; no Coastal/Inland tests'
    return result


def run_analysis(root: Path = PROJECT_ROOT, *, dry_run: bool = False, interval: float = 1.0) -> dict:
    """Execute full independent cohort or a read-only request plan; never mutate prior artifacts."""
    stations = load_stations(root)
    plan = download_plan(stations, root)
    if dry_run:
        return plan
    protected = snapshot(root)
    _atomic_json({'status': 'pending', 'station_ids': stations.station_id.tolist()}, root/MANIFEST)
    sessions = {source: CountingSession(interval) for source in ('KMA', 'NASA')}
    prepared, quality, completeness, inputs, failures = [], [], [], [root/SHORTLIST, root/MASTER], []
    _atomic_csv(stations, root/TABLE_DIR/'tier_b_analysis_stations.csv')
    for station in stations.itertuples(index=False):
        record = pd.Series(station._asdict())
        try:
            item, rows, years, paths = prepare(record, root, sessions)
            prepared.append(item); quality.extend(rows); completeness.extend(years); inputs.extend(paths)
            print(f'Tier B {station.station_id} {station.station_name}: {len(item.matched)} calendar rows', flush=True)
        except Exception as exc:
            # Never emit HTTP exception text or key-bearing tracebacks.
            failures.append({'station_id': station.station_id, 'error_type': type(exc).__name__})
            print(f'Tier B {station.station_id}: failed ({type(exc).__name__}); cache preserved', flush=True)
    manifest = {'cohort': 'Final Tier B only', 'selection_source': SHORTLIST,
                'station_ids': stations.station_id.tolist(), 'analysis_period': [str(START), str(END)],
                'normal_period': [1991, 2020], 'plan_before_run': plan,
                'NASA_API_calls': sessions['NASA'].calls, 'KMA_API_calls': sessions['KMA'].calls,
                'screening_config': asdict(load_screening_config()),
                'statistics': {'alpha': .05, 'FDR': 'BH original MK; source × metric (×season or proxy), Tier B only',
                               'Sen_CI': .95, 'moving_averages': [5, 10], 'season_min_valid_fraction': .95,
                               'thresholds': ['TMAX>=30', 'TMAX>=33', 'TMIN>=25'],
                               'missing_policy': 'NaN; no imputation; quality failure withholds all cohort statistics'},
                'failures': failures, 'input_hashes': {p.relative_to(root).as_posix(): sha256(p) for p in inputs}}
    quality_frame = pd.DataFrame(quality)
    annual_quality = pd.concat(completeness, ignore_index=True) if completeness else pd.DataFrame()
    if not quality_frame.empty:
        _atomic_csv(quality_frame, root/TABLE_DIR/'tier_b_data_quality.csv')
        _atomic_csv(annual_quality, root/TABLE_DIR/'tier_b_annual_completeness.csv')
    if failures or quality_frame.empty or quality_frame.analysis_review_required.any():
        manifest['status'] = 'incomplete_or_review_required'
        manifest['protected_files_changed'] = check_snapshot(root, protected)
        _atomic_json(manifest, root/MANIFEST)
        raise ValueError('Tier B incomplete/review required; see isolated manifest and quality table; caches preserved')
    tables = build_products(prepared, stations, quality_frame)
    tables.update({'tier_b_analysis_stations': stations, 'tier_b_data_quality': quality_frame,
                   'tier_b_annual_completeness': annual_quality,
                   'tier_b_station_coastal_distance': coastal_distances(stations, root)})
    generated = []
    for name, frame in tables.items():
        path = root/TABLE_DIR/f'{name}.csv'
        _atomic_csv(frame, path); generated.append(path.relative_to(root).as_posix())
    # Reporting always uses persisted tables, so --report-tier-b is byte reproducible.
    from src.tier_b.artifacts import load_tables
    saved = load_tables(root, verify=False)
    charts = save_charts(saved, root)
    reports = write_reports(saved, root)
    generated += charts + reports
    for p in [root/'config/nationwide_screening.json', root/'data/geospatial/coastline/coastline_manifest.json']:
        manifest['input_hashes'][p.relative_to(root).as_posix()] = sha256(p)
    provenance = [p for item in prepared for p in (item.nasa_processed_path, item.kma_processed_path, item.matched_path)]
    provenance += list((root/'src/tier_b').glob('*.py'))
    provenance += [root/'src/nationwide/tier_a_analysis.py', root/'src/statistical_analysis.py', root/'src/validation.py']
    manifest['processing_hashes'] = {p.relative_to(root).as_posix(): sha256(p) for p in provenance if p.exists()}
    manifest.update({'status': 'completed', 'station_count': len(stations), 'output_files': generated,
                     'output_hashes': {name: sha256(root/name) for name in generated},
                     'protected_files_count': len(protected), 'protected_files_changed': check_snapshot(root, protected)})
    if manifest['protected_files_changed']:
        raise ValueError('Prior artifacts changed during Tier B run')
    _atomic_json(manifest, root/MANIFEST)
    return manifest
