"""Common-period selection, cache acquisition, calendar and provenance."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT, SETTINGS
from src.tier_b import data as shared
from src.nationwide.tier_a_pipeline import load_tier_a_stations, PreparedStation, _atomic_csv, _atomic_json
from src.nasa_power import fetch_daily_data
from src.kma_asos import KmaAsosClient, get_kma_api_key, chunk_date_ranges
from src.spatial.robustness_audit import sha256

START, END = shared.START, shared.END
TABLE_DIR = 'output/tables/common_period'
CHART_DIR = 'output/charts/common_period'
REPORT_DIR = 'output/reports/common_period'
MANIFEST = 'output/manifests/common_period_51station_manifest.json'
STATE = 'data/common_period/workflow_state.json'
SELECTION_INPUTS = [shared.SHORTLIST, shared.MASTER, 'output/tables/nationwide_tier_a_analysis_stations.csv',
                    'output/tables/nationwide/nationwide_station_temperature_summary.csv',
                    'output/tables/tier_b/tier_b_analysis_stations.csv',
                    'output/tables/tier_b/tier_b_station_temperature_summary.csv',
                    'output/tables/coastal/nationwide_station_coastal_distance.csv',
                    'output/tables/tier_b/tier_b_station_coastal_distance.csv']
WARNING = '본 페이지의 Tier A와 Tier B는 모두 1991–2025로 재계산되었으므로 추세기간은 동일합니다. 다만 cohort_origin은 원래 관측기간 eligibility 이력을 나타냅니다.'
GRID_WARNING = '여러 ASOS station이 동일 NASA POWER grid를 공유할 수 있으므로, NASA station-level 결과가 모두 독립적인 공간 grid 표본을 의미하지는 않습니다.'
MATCH_NAMES = {'nasa_T2M': 'nasa_t2m', 'nasa_T2M_MAX': 'nasa_tmax', 'nasa_T2M_MIN': 'nasa_tmin',
               'kma_T2M': 'kma_tavg', 'kma_TMAX': 'kma_tmax', 'kma_TMIN': 'kma_tmin'}


def snapshot(root: Path = PROJECT_ROOT) -> dict:
    """Protect all existing data/output/VERSION, including Tier B and coastline."""
    paths = [root/'VERSION'] + [p for d in ('data', 'output') for p in (root/d).rglob('*') if p.is_file()]
    return {p.relative_to(root).as_posix(): {'sha256': sha256(p), 'mtime_ns': p.stat().st_mtime_ns}
            for p in sorted(paths) if p.is_file() and 'common_period' not in p.relative_to(root).parts
            and p.name != Path(MANIFEST).name}


def load_stations(root: Path = PROJECT_ROOT) -> pd.DataFrame:
    """Build disjoint Final A+B membership and cross-check saved cohort sources."""
    a = load_tier_a_stations(root/shared.SHORTLIST, root/shared.MASTER)
    b = shared.load_stations(root)
    a['cohort_origin'], b['cohort_origin'] = 'TIER_A', 'TIER_B'
    if set(a.station_id) & set(b.station_id):
        raise ValueError('Tier A/B intersection must be empty')
    for selected, paths in [(a, SELECTION_INPUTS[2:4]), (b, SELECTION_INPUTS[4:6])]:
        for name in paths:
            saved = pd.read_csv(root/name, dtype={'station_id': str})
            if saved.station_id.duplicated().any() or set(saved.station_id) != set(selected.station_id):
                raise ValueError(f'Final cohort membership differs from {name}')
    cols = ['station_id', 'station_name', 'region_level1', 'region_level2', 'latitude', 'longitude',
            'elevation_m', 'actual_data_start_date', 'actual_data_end_date', 'temperature_missing_rate',
            'annual_completeness', 'continuity_risk', 'cohort_origin']
    stations = pd.concat([a[cols], b[cols]], ignore_index=True).sort_values('station_id', key=lambda x: x.astype(int))
    shortlist = pd.read_csv(root/shared.SHORTLIST, dtype={'station_id': str})
    expected = shortlist.loc[shortlist.eligibility_tier.isin(['A', 'B']), 'station_id']
    if stations.station_id.duplicated().any() or set(expected) != set(stations.station_id):
        raise ValueError('Invalid or unresolved Final A/B candidate; selection withheld')
    stations['original_eligibility_tier'] = stations.cohort_origin.str.removeprefix('TIER_')
    stations['manual_review_required'] = False
    stations['common_analysis_start'], stations['common_analysis_end'] = str(START), str(END)
    distances = pd.concat([pd.read_csv(root/p, dtype={'station_id': str}) for p in SELECTION_INPUTS[6:]])
    stations = stations.merge(distances[['station_id', 'distance_to_coast_km']], on='station_id', how='left', validate='one_to_one')
    if stations.distance_to_coast_km.isna().any() or (stations.distance_to_coast_km < 0).any():
        raise ValueError('Missing verified coastal distance')
    return stations.reset_index(drop=True)


def valid_cache(path: Path, source: str, sid: str) -> bool:
    """Accept complete-period subsets of older raw without modifying them."""
    if not path.exists():
        return False
    try:
        raw = pd.read_csv(path, dtype={'DATE': str, 'stnId': str}, low_memory=False)
        if not set(shared.MAPS[source]).issubset(raw):
            return False
        dates = pd.to_datetime(raw.tm if source == 'KMA' else raw.DATE,
                               format='%Y-%m-%d' if source == 'KMA' else '%Y%m%d')
        if source == 'KMA' and not raw.stnId.eq(sid).all():
            return False
        if dates.duplicated().any() or dates.min().date() > START or dates.max().date() < END:
            return False
        return source == 'KMA' or shared.calendar().difference(dates).empty
    except (OSError, ValueError, KeyError):
        return False


def cache_path(root: Path, station: pd.Series, source: str) -> Path:
    """Choose old cache first; missing cache is downloaded only into common_period."""
    sid = str(station.station_id)
    if source == 'NASA':
        old = (root/f'data/nationwide_nasa_raw/{sid}_nasa_power_temperature_1981_2025.csv'
               if station.cohort_origin == 'TIER_A' else shared.nasa_path(root, sid))
    else:
        old = shared.kma_path(root, sid)
    if valid_cache(old, source, sid):
        return old
    return root/f'data/common_period/{source.lower()}_raw/{sid}/{sid}_temperature_1991_2025.csv'


def download_plan(stations: pd.DataFrame, root: Path = PROJECT_ROOT) -> dict:
    """No writes/HTTP; estimate missing-cache requests without counting retries."""
    from src.common_period.grid import grid_coordinates
    rows = []
    for _, station in stations.iterrows():
        row = {'station_id': station.station_id, 'cohort_origin': station.cohort_origin}
        for source in ('KMA', 'NASA'):
            path = cache_path(root, station, source)
            row[f'{source}_cache'] = valid_cache(path, source, station.station_id)
        rows.append(row)
    hits = {s: sum(r[f'{s}_cache'] for r in rows) for s in ('KMA', 'NASA')}
    return {'tier_a_count': int(stations.cohort_origin.eq('TIER_A').sum()),
            'tier_b_count': int(stations.cohort_origin.eq('TIER_B').sum()), 'station_count': len(stations),
            'intersection_count': 0, 'expected_dates': len(shared.calendar()), 'stations': rows,
            'KMA_cache_hits': hits['KMA'], 'NASA_cache_hits': hits['NASA'],
            'KMA_cache_misses': len(rows)-hits['KMA'], 'NASA_cache_misses': len(rows)-hits['NASA'],
            'expected_NASA_calls': len(rows)-hits['NASA'],
            'expected_KMA_calls_upper_bound': (len(rows)-hits['KMA'])*sum(
                ((end-start).days+999)//999 for start, end in chunk_date_ranges(START, END)),
            'estimated_NASA_unique_grids': len({grid_coordinates(r.latitude, r.longitude) for r in stations.itertuples()}),
            'grid_method': 'official native-grid inference; series validation performed during analysis',
            'expected_outputs': [TABLE_DIR, CHART_DIR, REPORT_DIR, MANIFEST]}


def state_update(root: Path, sid: str, status: str, error_type: str | None = None) -> None:
    """Write isolated per-station workflow checkpoint, never an HTTP message or key."""
    path = root/STATE
    state = json.loads(path.read_text()) if path.exists() else {'stations': {}}
    state['stations'][sid] = {'status': status, 'error_type': error_type}
    _atomic_json(state, path)


def acquire(station: pd.Series, source: str, root: Path, session: shared.CountingSession) -> tuple[pd.DataFrame, Path]:
    """Use existing clients only for missing raw, retaining KMA completed chunks on failure."""
    sid = str(station.station_id)
    path = cache_path(root, station, source)
    if valid_cache(path, source, sid):
        return pd.read_csv(path, dtype={'DATE': str, 'stnId': str}, low_memory=False), path
    if path.exists():
        raise ValueError('Invalid common-period raw preserved for manual review')
    if source == 'NASA':
        raw = fetch_daily_data(float(station.latitude), float(station.longitude), START, END,
                               settings=replace(SETTINGS, parameters=tuple(shared.MAPS['NASA'])), session=session).dataframe
    else:
        client = KmaAsosClient(get_kma_api_key(), session=session)
        frames = []
        for start, end in chunk_date_ranges(START, END):
            chunk = path.parent/f'chunks/{start}_{end}.csv'
            if chunk.exists():
                frame = pd.read_csv(chunk, dtype={'stnId': str}, low_memory=False)
            else:
                frame = pd.DataFrame(client.fetch_period(sid, start, end, rows_per_page=999))
                shared.preprocess(frame, station, 'KMA')
                _atomic_csv(frame, chunk)
            frames.append(frame)
        raw = pd.concat(frames, ignore_index=True)
    daily = shared.preprocess(raw, station, source)
    if any(daily[c].notna().sum() == 0 for c in shared.MAPS[source].values()):
        raise ValueError('No temperature observations')
    _atomic_csv(raw, path)
    if not valid_cache(path, source, sid):
        raise ValueError('Incomplete raw cache; preserved for review')
    return raw, path


def prepare(station: pd.Series, root: Path, sessions: dict) -> tuple[PreparedStation, list, list, dict]:
    """Use identical pure Stage15 preprocessing/quality functions for both original cohorts."""
    sid, origin = str(station.station_id), str(station.cohort_origin)
    frames, paths, quality_rows, annual_rows, cache = {}, {}, [], [], {}
    state_update(root, sid, 'pending')
    for source in ('KMA', 'NASA'):
        raw, path = acquire(station, source, root, sessions[source])
        daily = shared.preprocess(raw, station, source)
        q, annual = shared.quality(raw, daily, source)
        q.update(cohort_origin=origin, common_period_review_required=q['analysis_review_required'])
        quality_rows.append(q)
        for metric, label in zip(('TAVG', 'TMAX', 'TMIN'), ('tavg', 'tmax', 'tmin')):
            frame = annual[['station_id', 'source', 'year', 'expected_days', f'valid_{label}', f'{label}_completeness']].rename(
                columns={f'valid_{label}': 'valid_days', f'{label}_completeness': 'completeness_ratio'})
            frame['metric'], frame['cohort_origin'] = metric, origin
            annual_rows.append(frame)
        target = root/f'data/common_period/{source.lower()}_processed/{sid}_{source.lower()}_temperature_1991_2025.csv'
        _atomic_csv(daily.rename(columns=shared.SAVED_NAMES).assign(cohort_origin=origin), target)
        frames[source], paths[source], cache[source] = daily, target, path.relative_to(root).as_posix()
    state_update(root, sid, 'processed')
    nasa = frames['NASA'].rename(columns={'T2M': 'nasa_T2M', 'T2M_MAX': 'nasa_T2M_MAX', 'T2M_MIN': 'nasa_T2M_MIN'})
    kma = frames['KMA'].rename(columns={'avg_temperature': 'kma_T2M', 'max_temperature': 'kma_TMAX', 'min_temperature': 'kma_TMIN'})
    matched = nasa.merge(kma.drop(columns=['station_id', 'station_name']), on='date', validate='one_to_one')
    pair_path = root/f'data/common_period/matched/{sid}_nasa_kma_temperature_1991_2025.csv'
    _atomic_csv(matched.rename(columns=MATCH_NAMES).assign(cohort_origin=origin), pair_path)
    state_update(root, sid, 'matched')
    return PreparedStation(sid, str(station.station_name), 'cache', root/cache['NASA'], paths['NASA'], paths['KMA'],
                           pair_path, frames['NASA'], frames['KMA'], matched), quality_rows, annual_rows, cache
