"""Common-period orchestration; all writes are isolated and prior results protected."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import pandas as pd

from src.config import PROJECT_ROOT
from src.tier_b.data import CountingSession
from src.nationwide.eligibility import load_screening_config
from src.nationwide.tier_a_pipeline import _atomic_csv, _atomic_json
from src.spatial.robustness_audit import check_snapshot, sha256
from src.common_period.data import (TABLE_DIR, MANIFEST, START, END, SELECTION_INPUTS,
                                    load_stations, download_plan, prepare, snapshot, state_update)
from src.common_period.grid import build_grid_mapping, GRID_METHOD, GRID_SOURCE, GRID_ORIGIN_SOURCE
from src.common_period.analysis import build_products, distribution


def run_analysis(root: Path = PROJECT_ROOT, *, dry_run: bool = False) -> dict:
    """Recompute daily-to-trend statistics for the union; zero HTTP when caches suffice."""
    stations = load_stations(root)
    plan = download_plan(stations, root)
    if dry_run:
        return plan
    protected = snapshot(root)
    manifest = {'status': 'pending', 'selection_source': SELECTION_INPUTS, 'station_ids': stations.station_id.tolist(),
                'tier_a_count': plan['tier_a_count'], 'tier_b_count': plan['tier_b_count'], 'station_count': len(stations),
                'analysis_period': [str(START), str(END)], 'normal_period': [1991, 2020], 'plan_before_run': plan,
                'screening_config': asdict(load_screening_config()), 'FDR': 'fresh BH of union raw original-MK p; source×metric (×season/proxy)',
                'grid_method': GRID_METHOD, 'grid_sources': [GRID_SOURCE, GRID_ORIGIN_SOURCE]}
    _atomic_json(manifest, root/MANIFEST)
    sessions = {s: CountingSession() for s in ('KMA', 'NASA')}
    prepared, quality, completeness, caches, failed = [], [], [], {}, []
    for _, station in stations.iterrows():
        try:
            item, rows, years, cache = prepare(station, root, sessions)
            prepared.append(item); quality.extend(rows); completeness.extend(years); caches[station.station_id] = cache
            print(f'Common period {station.station_id} {station.station_name}: {len(item.matched)} calendar rows', flush=True)
        except Exception as exc:
            state_update(root, station.station_id, 'failed', type(exc).__name__)
            failed.append({'station_id': station.station_id, 'error_type': type(exc).__name__})
            print(f'Common period {station.station_id}: failed ({type(exc).__name__}); caches preserved', flush=True)
    manifest.update({'NASA_API_calls': sessions['NASA'].calls, 'KMA_API_calls': sessions['KMA'].calls,
                     'cache_sources': caches, 'failures': failed})
    _atomic_json(manifest, root/MANIFEST)
    q, years = pd.DataFrame(quality), pd.concat(completeness, ignore_index=True) if completeness else pd.DataFrame()
    if not q.empty:
        _atomic_csv(q, root/TABLE_DIR/'common_period_data_quality.csv')
        _atomic_csv(years, root/TABLE_DIR/'common_period_annual_completeness.csv')
    if failed or q.empty or q.common_period_review_required.any():
        manifest['status'] = 'review_required'; _atomic_json(manifest, root/MANIFEST)
        raise ValueError('Common-period quality/download review required; prior results unchanged')
    stations, mapping = build_grid_mapping(stations, prepared)
    _atomic_csv(mapping, root/TABLE_DIR/'common_period_nasa_grid_mapping.csv')
    if mapping.grid_mapping_mismatch.any() or stations.identical_series_across_different_grids.any():
        manifest['status'] = 'grid_review_required'; _atomic_json(manifest, root/MANIFEST)
        raise ValueError('Grid-series mapping mismatch; inspect common-period mapping')
    kma_quality = q.loc[q.source.eq('KMA')].set_index('station_id')
    stations['temperature_missing_rate_1991_2025'] = stations.station_id.map(kma_quality[['tavg_missing_rate', 'tmax_missing_rate', 'tmin_missing_rate']].mean(axis=1))
    stations['annual_completeness_1991_2025'] = stations.station_id.map(kma_quality.annual_completeness_median)
    stations['temperature_missing_rate'] = stations.temperature_missing_rate_1991_2025
    stations['annual_completeness'] = stations.annual_completeness_1991_2025
    stations['common_period_eligible'], stations['common_period_review_required'] = True, False
    products = build_products(prepared, stations, q, mapping, root)
    products.update({'common_period_1991_2025_station_master': stations, 'common_period_data_quality': q,
                     'common_period_annual_completeness': years})
    products['common_period_completeness_cohort_summary'] = pd.DataFrame([
        {'cohort_origin': origin, 'source': source, 'metric': metric,
         'station_count': group.station_id.nunique(), 'year_count': group.year.nunique(),
         **distribution(group.completeness_ratio), 'scope': 'station-year completeness, descriptive only'}
        for (origin, source, metric), group in years.groupby(['cohort_origin', 'source', 'metric'])])
    generated = []
    for item in prepared:
        state_update(root, item.station_id, 'analyzed')
    for name, frame in products.items():
        path = root/TABLE_DIR/f'{name}.csv'; _atomic_csv(frame, path); generated.append(path.relative_to(root).as_posix())
    saved = {name: pd.read_csv(root/TABLE_DIR/f'{name}.csv', dtype={'station_id': str}) for name in products}
    from src.common_period.artifacts import save_charts, write_reports
    generated += save_charts(saved, root)+write_reports(saved, root)
    inputs = set(SELECTION_INPUTS+['config/nationwide_screening.json', 'output/tables/nationwide/nationwide_station_temperature_trends.csv'])
    inputs.update(p for cache in caches.values() for p in cache.values())
    inputs.update(p.relative_to(root).as_posix() for p in (root/'output/tables/tier_b').glob('*.csv'))
    processing = [p for d in ('src/common_period', 'data/common_period/kma_processed', 'data/common_period/nasa_processed',
                              'data/common_period/matched') for p in (root/d).glob('*') if p.is_file()]
    processing += [root/p for p in ('src/tier_b/analysis.py', 'src/tier_b/data.py', 'src/nationwide/tier_a_analysis.py', 'src/statistical_analysis.py')]
    changed = check_snapshot(root, protected)
    manifest.update({'status': 'completed' if not changed else 'protection_failed',
                     'unique_NASA_grid_count': len(mapping), 'shared_grid_groups': int(mapping.station_count.gt(1).sum()),
                     'stations_in_shared_grids': int(mapping.loc[mapping.station_count.gt(1), 'station_count'].sum()),
                     'largest_grid_group': int(mapping.station_count.max()), 'grid_mapping_mismatch': False,
                     'tier_b_reproduction_passed': bool(products['common_period_tier_b_reproduction'].passed.all()),
                     'input_hashes': {name: sha256(root/name) for name in sorted(inputs)},
                     'processing_hashes': {p.relative_to(root).as_posix(): sha256(p) for p in processing},
                     'output_files': generated, 'output_hashes': {name: sha256(root/name) for name in generated},
                     'protected_files_count': len(protected), 'protected_files_changed': changed})
    _atomic_json(manifest, root/MANIFEST)
    if changed:
        raise ValueError('Protected files changed')
    for item in prepared:
        state_update(root, item.station_id, 'validated')
    return manifest
