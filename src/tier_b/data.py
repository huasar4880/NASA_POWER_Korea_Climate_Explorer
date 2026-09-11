"""Tier B selection, immutable caches, resumable downloads and calendar preparation."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd
import requests

from src.config import PROJECT_ROOT, SETTINGS
from src.nasa_power import fetch_daily_data, load_raw_csv
from src.kma_asos import KmaAsosClient, chunk_date_ranges, get_kma_api_key
from src.nationwide.tier_a_pipeline import PreparedStation, _atomic_csv, _atomic_json, _to_bool
from src.nationwide.completeness import longest_missing_streak
from src.nationwide.eligibility import evaluate_period_quality, load_screening_config
from src.spatial.robustness_audit import sha256

START, END = date(1991, 1, 1), date(2025, 12, 31)
PERIOD = '1991_2025'
SHORTLIST = 'output/tables/nationwide_asos_longterm_shortlist.csv'
MASTER = 'output/tables/nationwide_asos_station_master.csv'
TABLE_DIR = 'output/tables/tier_b'
CHART_DIR = 'output/charts/tier_b'
REPORT_DIR = 'output/reports/tier_b'
MANIFEST = 'output/manifests/tier_b_analysis_manifest.json'
WARNING = 'Tier B는 1991–2025 공통기간 cohort이며, Tier A 1981–2025 결과와 추세 크기를 직접 비교하면 기간 차이의 영향을 받을 수 있습니다.'
MAPS = {'KMA': {'avgTa': 'avg_temperature', 'maxTa': 'max_temperature', 'minTa': 'min_temperature'},
        'NASA': {'T2M': 'T2M', 'T2M_MAX': 'T2M_MAX', 'T2M_MIN': 'T2M_MIN'}}
SAVED_NAMES = {'avg_temperature': 'kma_tavg', 'max_temperature': 'kma_tmax', 'min_temperature': 'kma_tmin',
               'T2M': 'nasa_t2m', 'T2M_MAX': 'nasa_tmax', 'T2M_MIN': 'nasa_tmin'}


def calendar() -> pd.DatetimeIndex:
    """Inclusive common-period calendar, including leap days."""
    return pd.date_range(START, END, freq='D')


def snapshot(root: Path = PROJECT_ROOT) -> dict:
    """Protect all prior data/output/VERSION, excluding only this new namespace."""
    paths = [root/'VERSION'] + [p for d in ('data', 'output') for p in (root/d).rglob('*') if p.is_file()]
    return {p.relative_to(root).as_posix(): {'sha256': sha256(p), 'mtime_ns': p.stat().st_mtime_ns}
            for p in sorted(paths) if p.is_file() and not any(part.startswith('tier_b') for part in p.relative_to(root).parts)}


def load_stations(root: Path = PROJECT_ROOT) -> pd.DataFrame:
    """Select Final B only; reject unresolved metadata instead of silently dropping it."""
    shortlist = pd.read_csv(root/SHORTLIST, dtype={'station_id': str})
    master = pd.read_csv(root/MASTER, dtype={'station_id': str})
    if shortlist.station_id.duplicated().any() or master.station_id.duplicated().any():
        raise ValueError('Duplicate station metadata')
    selected = shortlist.loc[shortlist.eligibility_tier.eq('B')].copy()
    cols = ['station_id', 'region_level1', 'region_level2', 'actual_data_start_date', 'actual_data_end_date',
            'eligible_1991_2025', 'manual_review_required']
    selected = selected.merge(master[cols], on='station_id', how='left', validate='one_to_one')
    valid = (_to_bool(selected.eligible_1991_2025) & selected.manual_review_required.notna()
             & ~_to_bool(selected.manual_review_required)
             & selected.continuity_risk.isin(['low', 'medium'])
             & pd.to_datetime(selected.actual_data_start_date).le(pd.Timestamp(START))
             & pd.to_datetime(selected.actual_data_end_date).ge(pd.Timestamp(END)))
    if selected.empty or not valid.all():
        raise ValueError('Final B eligibility/continuity/availability requires review')
    if set(selected.station_id) & set(shortlist.loc[shortlist.eligibility_tier.eq('A'), 'station_id']):
        raise ValueError('Tier A overlap')
    for col in ('latitude', 'longitude', 'elevation_m'):
        if not np.isfinite(pd.to_numeric(selected[col], errors='coerce')).all():
            raise ValueError('Missing station coordinate/elevation')
    if not selected.latitude.between(-90, 90).all() or not selected.longitude.between(-180, 180).all():
        raise ValueError('Invalid station coordinates')
    selected['recommended_analysis_period'] = f'{START}~{END}'
    return selected.sort_values('station_id', key=lambda x: x.astype(int)).reset_index(drop=True)


def nasa_path(root: Path, sid: str) -> Path:
    """Return isolated station-specific NASA raw path."""
    return root/f'data/tier_b_nasa_raw/{sid}_nasa_power_temperature_{PERIOD}.csv'


def valid_cache(path: Path, source: str, sid: str) -> bool:
    """Validate schema, unique dates and boundary coverage without requiring no missing days."""
    if not path.is_file():
        return False
    try:
        raw = pd.read_csv(path, dtype={'stnId': str, 'DATE': str}, low_memory=False)
        if not set(MAPS[source]).issubset(raw.columns):
            return False
        dates = pd.to_datetime(raw['tm'] if source == 'KMA' else raw['DATE'],
                               format='%Y-%m-%d' if source == 'KMA' else '%Y%m%d', errors='raise')
        if source == 'KMA' and not raw.stnId.astype(str).eq(sid).all():
            return False
        return bool(not dates.duplicated().any() and dates.min() <= pd.Timestamp(START)
                    and dates.max() >= pd.Timestamp(END)
                    and (source == 'KMA' or len(dates) == len(calendar())))
    except (ValueError, KeyError, OSError):
        return False


def kma_path(root: Path, sid: str) -> Path:
    """Find a sufficient old cache read-only, otherwise use a new isolated cache."""
    candidates = sorted((root/f'data/nationwide_asos_raw/stations/{sid}').glob(f'{sid}_asos_daily_*.csv'))
    for path in candidates:
        if valid_cache(path, 'KMA', sid):
            return path
    return root/f'data/tier_b_kma_raw/{sid}/{sid}_asos_daily_{PERIOD}.csv'


def download_plan(stations: pd.DataFrame, root: Path = PROJECT_ROOT) -> dict:
    """Read-only plan; NASA one full-period request per missing station, excluding retries."""
    rows = [{'station_id': sid, 'KMA_cache': valid_cache(kma_path(root, sid), 'KMA', sid),
             'NASA_cache': valid_cache(nasa_path(root, sid), 'NASA', sid)} for sid in stations.station_id]
    return {'station_count': len(rows), 'expected_dates': len(calendar()), 'stations': rows,
            'KMA_cache_hits': sum(r['KMA_cache'] for r in rows),
            'NASA_cache_hits': sum(r['NASA_cache'] for r in rows),
            'estimated_NASA_requests': sum(not r['NASA_cache'] for r in rows),
            'outputs': [TABLE_DIR, CHART_DIR, REPORT_DIR, MANIFEST]}


class CountingSession:
    """Count every real attempt including retries and throttle consecutive requests."""
    def __init__(self, interval: float = 1.0, session: Any = None) -> None:
        self.calls = 0
        self.interval = max(1.0, interval)
        self.session = session or requests.Session()
        self.last = 0.0

    def get(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate one GET without logging URL or authentication parameters."""
        if self.calls:
            time.sleep(max(0.0, self.interval - (time.monotonic() - self.last)))
        self.calls += 1
        self.last = time.monotonic()
        return self.session.get(*args, **kwargs)


def record_state(root: Path, source: str, sid: str, status: str, calls: int = 0,
                 error: str | None = None) -> None:
    """Persist only safe status and cumulative real request counts."""
    path = root/f'data/tier_b_{source.lower()}_raw/download_state.json'
    state = json.loads(path.read_text()) if path.exists() else {'stations': {}}
    prior = state['stations'].get(sid, {})
    state['stations'][sid] = {'status': status, 'api_attempts': prior.get('api_attempts', 0) + calls,
                             'error_type': error}
    _atomic_json(state, path)


def download_station(station: pd.Series, source: str, root: Path,
                     session: CountingSession) -> tuple[pd.DataFrame, Path]:
    """Cache first; preserve old/complete raw and resume isolated KMA chunks on failure."""
    sid = str(station.station_id)
    path = nasa_path(root, sid) if source == 'NASA' else kma_path(root, sid)
    if valid_cache(path, source, sid):
        record_state(root, source, sid, 'completed')
        return pd.read_csv(path, dtype={'stnId': str, 'DATE': str}, low_memory=False), path
    if path.exists():
        raise ValueError(f'{source} station {sid}: existing raw invalid; preserved for review')
    before = session.calls
    record_state(root, source, sid, 'pending')
    try:
        if source == 'NASA':
            result = fetch_daily_data(float(station.latitude), float(station.longitude), START, END,
                                     settings=replace(SETTINGS, parameters=('T2M', 'T2M_MAX', 'T2M_MIN')),
                                     session=session)
            raw = result.dataframe
        else:
            client = KmaAsosClient(get_kma_api_key(), session=session)
            frames = []
            for start, end in chunk_date_ranges(START, END):
                chunk = path.parent/f'chunks/{sid}_{start}_{end}.csv'
                if chunk.exists():
                    part = pd.read_csv(chunk, dtype={'stnId': str})
                else:
                    part = pd.DataFrame(client.fetch_period(sid, start, end, rows_per_page=999))
                    if part.empty or not {'tm', 'stnId', *MAPS['KMA']}.issubset(part.columns):
                        raise ValueError('KMA empty/invalid chunk; not cached')
                    _atomic_csv(part, chunk)
                frames.append(part)
            raw = pd.concat(frames, ignore_index=True)
        # Validate before committing any full raw file; a failed response is never a cache hit.
        daily = preprocess(raw, station, source)
        if any(daily[c].notna().sum() == 0 for c in MAPS[source].values()):
            raise ValueError(f'{source} has no valid temperature observations')
        raw_dates = pd.to_datetime(raw['DATE'], format='%Y%m%d') if source == 'NASA' else pd.to_datetime(raw.tm)
        if raw_dates.min().date() > START or raw_dates.max().date() < END:
            raise ValueError('Downloaded period incomplete')
        if source == 'NASA' and len(raw) != len(calendar()):
            raise ValueError('NASA response calendar incomplete')
        _atomic_csv(raw, path)
        record_state(root, source, sid, 'completed', session.calls-before)
        return raw, path
    except Exception as exc:
        record_state(root, source, sid, 'failed', session.calls-before, type(exc).__name__)
        raise


def preprocess(raw: pd.DataFrame, station: pd.Series, source: str) -> pd.DataFrame:
    """Preserve raw; mask fill/range errors and reindex both sources to the full calendar."""
    mapping = MAPS[source]
    if not set(mapping).issubset(raw.columns):
        raise ValueError('Temperature raw schema missing')
    if source == 'KMA' and not raw.stnId.astype(str).eq(str(station.station_id)).all():
        raise ValueError('Wrong KMA station ID')
    dates = pd.to_datetime(raw['tm'] if source == 'KMA' else raw['DATE'].astype(str),
                           format='%Y-%m-%d' if source == 'KMA' else '%Y%m%d', errors='raise')
    if dates.duplicated().any():
        raise ValueError('Duplicate raw dates require manual review')
    frame = pd.DataFrame({'date': dates})
    for src, dst in mapping.items():
        values = pd.to_numeric(raw[src], errors='coerce').replace(SETTINGS.missing_values, np.nan)
        frame[dst] = values.where(values.between(-90, 70))
    frame = frame.set_index('date').reindex(calendar()).rename_axis('date').reset_index()
    frame.insert(1, 'station_id', str(station.station_id))
    frame.insert(2, 'station_name', str(station.station_name))
    return frame


def quality(raw: pd.DataFrame, daily: pd.DataFrame, source: str) -> tuple[dict, pd.DataFrame]:
    """Reapply screening thresholds and retain per-variable yearly completeness."""
    sid = str(daily.station_id.iloc[0])
    dates = pd.to_datetime(raw.tm if source == 'KMA' else raw.DATE.astype(str),
                           format='%Y-%m-%d' if source == 'KMA' else '%Y%m%d')
    dates = dates[dates.between(pd.Timestamp(START), pd.Timestamp(END))]
    row = {'station_id': sid, 'source': source, 'expected_dates': len(calendar()),
           'actual_rows': len(dates), 'actual_kma_rows': len(dates) if source == 'KMA' else None,
           'missing_dates': len(calendar().difference(dates)), 'duplicate_dates': int(dates.duplicated().sum()),
           'start_date': str(START), 'end_date': str(END)}
    columns = list(MAPS[source].values())
    annual = pd.DataFrame({'year': daily.date.dt.year, 'expected_days': 1,
                           'valid_core': daily[columns].notna().all(axis=1).astype(int)})
    for label, col in zip(('tavg', 'tmax', 'tmin'), columns):
        row[f'{label}_missing'] = int(daily[col].isna().sum())
        row[f'{label}_missing_rate'] = float(daily[col].isna().mean())
        annual[f'valid_{label}'] = daily[col].notna().astype(int)
    annual = annual.groupby('year', as_index=False).sum()
    annual['completeness_ratio'] = annual.valid_core/annual.expected_days
    for label in ('tavg', 'tmax', 'tmin'):
        annual[f'{label}_completeness'] = annual[f'valid_{label}']/annual.expected_days
    annual['station_id'], annual['source'] = sid, source
    row['longest_temperature_gap_days'] = longest_missing_streak(
        pd.Series(np.where(daily[columns].isna().any(axis=1), np.nan, 1.0)))
    row['annual_completeness_median'] = float(annual.completeness_ratio.median())
    check = {f'{old}_temp_missing_rate': row[f'{new}_missing_rate']
             for old, new in zip(('avg', 'max', 'min'), ('tavg', 'tmax', 'tmin'))}
    check['longest_temperature_gap_days'] = row['longest_temperature_gap_days']
    passed, reasons = evaluate_period_quality(check, annual, load_screening_config())
    row['analysis_review_required'] = not passed or row['duplicate_dates'] > 0
    row['quality_reasons'] = ';'.join(reasons)
    return row, annual


def prepare(station: pd.Series, root: Path, sessions: dict) -> tuple[PreparedStation, list, list, list]:
    """Prepare one station, retaining existing Tier A internal schema only in memory."""
    sid = str(station.station_id)
    frames, paths, quality_rows, annual_rows, inputs = {}, {}, [], [], []
    for source in ('KMA', 'NASA'):
        raw, path = download_station(station, source, root, sessions[source])
        daily = preprocess(raw, station, source)
        row, annual = quality(raw, daily, source)
        quality_rows.append(row); annual_rows.append(annual); inputs.append(path)
        target = root/f'data/tier_b_{source.lower()}_processed/{sid}_{source.lower()}_temperature_{PERIOD}.csv'
        _atomic_csv(daily.rename(columns=SAVED_NAMES), target)
        frames[source], paths[source] = daily, target
    nasa = frames['NASA'].rename(columns={'T2M': 'nasa_T2M', 'T2M_MAX': 'nasa_T2M_MAX', 'T2M_MIN': 'nasa_T2M_MIN'})
    kma = frames['KMA'].rename(columns={'avg_temperature': 'kma_T2M', 'max_temperature': 'kma_TMAX', 'min_temperature': 'kma_TMIN'})
    matched = nasa.merge(kma.drop(columns=['station_id', 'station_name']), on='date', validate='one_to_one')
    pair_path = root/f'data/tier_b_matched/{sid}_nasa_kma_temperature_{PERIOD}.csv'
    _atomic_csv(matched, pair_path)
    return (PreparedStation(sid, str(station.station_name), 'tier_b', nasa_path(root, sid), paths['NASA'],
                            paths['KMA'], pair_path, frames['NASA'], frames['KMA'], matched),
            quality_rows, annual_rows, inputs)
