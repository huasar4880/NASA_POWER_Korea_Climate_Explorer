"""Stage18 configuration, fixed cohort, cache validation and window-level quality."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.nationwide.tier_a_pipeline import PreparedStation, load_tier_a_stations
from src.nationwide.completeness import longest_missing_streak
from src.nationwide.eligibility import evaluate_period_quality, load_screening_config
from src.common_period_spatial.artifacts import load_tables as load_stage17
from src.common_period.artifacts import load_tables as load_stage16
from src.common_period.grid import series_fingerprint
from src.spatial.robustness_audit import sha256

NAMESPACE = 'period_sensitivity'
DATA_DIR = Path('data')/NAMESPACE
TABLE_DIR = Path('output/tables')/NAMESPACE
CHART_DIR = Path('output/charts')/NAMESPACE
REPORT_DIR = Path('output/reports')/NAMESPACE
MANIFEST = Path('output/manifests/period_sensitivity_manifest.json')
CONFIG_PATH = Path('config/period_sensitivity.json')
STATION_SOURCE = Path('output/tables/nationwide_tier_a_analysis_stations.csv')
WARNING = '본 분석은 동일 45개 관측소에서 분석 시작연도와 window 길이를 변경한 민감도 분석입니다.'
SOURCE_COLUMNS = {
    'KMA': {'kma_T2M': 'avg_temperature', 'kma_TMAX': 'max_temperature', 'kma_TMIN': 'min_temperature'},
    'NASA': {'nasa_T2M': 'T2M', 'nasa_T2M_MAX': 'T2M_MAX', 'nasa_T2M_MIN': 'T2M_MIN'}}
TABLE_NAMES = ['annual_completeness','annual_temperature','coastal_association_stability','coastal_associations',
    'coastal_group_period_stability','coastal_inland_comparison','contrast_stability','contrast_summary',
    'data_quality','dominant_season_stability','dtr_stability','dtr_summary','dtr_trends','global_morans_i',
    'grid_series_equality','historical_reproduction','moran_trajectory','nasa_grid_spatial','nasa_kma_trend_consistency',
    'nasa_kma_validation','national_stability_summary','network_summary','seasonal_annual','seasonal_summary',
    'seasonal_trends','spatial_robustness_summary','spatial_significance_transitions','spatial_station_values',
    'station_master','station_metric_summary','temperature_trends','threshold_annual','threshold_stability',
    'threshold_trends','threshold_window_summary','tmax_tmin_contrast','trend_consistency_window_summary',
    'trend_stability','validation_stability','validation_window_summary','window_summary','windows']


def load_config(root: Path = PROJECT_ROOT) -> dict:
    """Validate the prespecified five windows and unchanged endpoint/minimum-length policy."""
    config = json.loads((root/CONFIG_PATH).read_text())
    starts = config['start_years']
    if starts != sorted(set(starts)) or starts != [1981, 1986, 1991, 1996, 2001]:
        raise ValueError('Stage18 requires the five prespecified start years')
    if config['end_year'] != 2025 or config['minimum_window_years'] != 25:
        raise ValueError('Stage18 endpoint/minimum-window policy changed')
    windows(config)
    return config


def windows(config: dict) -> pd.DataFrame:
    """Create inclusive calendar metadata, including leap days, without station-count constants."""
    rows = []
    for start in config['start_years']:
        end = config['end_year']; years = end-start+1
        if years < config['minimum_window_years']:
            raise ValueError('Window shorter than minimum 25-year policy')
        dates = pd.date_range(f'{start}-01-01', f'{end}-12-31')
        rows.append(dict(window_id=f'START_{start}', start_year=start, end_year=end,
                         start_date=str(dates[0].date()), end_date=str(dates[-1].date()),
                         window_years=years, n_years=years, expected_days=len(dates)))
    return pd.DataFrame(rows)


def snapshot(root: Path = PROJECT_ROOT) -> dict:
    """Protect every previous data/output file and stable VERSION, including all Stage17 results."""
    paths = [root/'VERSION']+[p for folder in ('data', 'output') for p in (root/folder).rglob('*') if p.is_file()]
    return {p.relative_to(root).as_posix(): {'sha256': sha256(p), 'mtime_ns': p.stat().st_mtime_ns}
            for p in sorted(paths) if NAMESPACE not in p.relative_to(root).parts and p != root/MANIFEST}


def load_inputs(root: Path = PROJECT_ROOT) -> tuple[pd.DataFrame, dict, dict]:
    """Cross-check Final A selection, saved cohorts and hash-validated Stage16/17 tables."""
    shortlist = 'output/tables/nationwide_asos_longterm_shortlist.csv'
    inventory = 'output/tables/nationwide_asos_station_master.csv'
    selected = load_tier_a_stations(root/shortlist, root/inventory)
    saved = pd.read_csv(root/STATION_SOURCE, dtype={'station_id': str})
    tier_b_path = 'output/tables/tier_b/tier_b_analysis_stations.csv'
    tier_b = pd.read_csv(root/tier_b_path, dtype={'station_id': str})
    if selected.station_id.duplicated().any() or saved.station_id.duplicated().any() or set(saved.station_id) != set(selected.station_id):
        raise ValueError('Final Tier A saved station set mismatch')
    if set(selected.station_id) & set(tier_b.station_id):
        raise ValueError('Tier B intersection must be zero')
    stage17 = load_stage17(root); stage16 = load_stage16(root)
    mapped = stage17['spatial_station_master'].loc[lambda d: d.cohort_origin.eq('TIER_A')]
    if set(mapped.station_id) != set(selected.station_id):
        raise ValueError('Stage17 A-origin membership differs from Final A')
    common = stage16['common_period_temperature_trends'].loc[lambda d: d.cohort_origin.eq('TIER_A')]
    if set(common.station_id) != set(selected.station_id):
        raise ValueError('Stage16 A-origin membership differs from Final A')
    extra = ['station_id','distance_to_coast_km','nasa_grid_id','nasa_grid_latitude','nasa_grid_longitude']
    stations = selected.merge(mapped[extra], on='station_id', validate='one_to_one')
    stations['cohort_origin'] = 'TIER_A'
    stations['nasa_grid_group_size'] = stations.groupby('nasa_grid_id').station_id.transform('size')
    stations['nasa_grid_shared'] = stations.nasa_grid_group_size.gt(1)
    old_path = 'output/tables/nationwide/nationwide_station_temperature_trends.csv'
    old_moran = 'output/tables/spatial/nationwide_global_morans_i.csv'
    old = {'trends_1981': pd.read_csv(root/old_path, dtype={'station_id':str}),
           'trends_1991': stage16['common_period_temperature_trends'].loc[lambda d: d.station_id.isin(stations.station_id)].copy(),
           'moran_1981': pd.read_csv(root/old_moran), 'bridge_1991': stage17['spatial_bridge_comparison']}
    names = [str(STATION_SOURCE), shortlist, inventory, tier_b_path, old_path, old_moran, str(CONFIG_PATH),
             'config/nationwide_screening.json', 'output/manifests/common_period_51station_manifest.json',
             'output/manifests/common_period_spatial_reanalysis_manifest.json',
             'output/tables/common_period/common_period_temperature_trends.csv',
             'output/tables/common_period_spatial/common_period_spatial_bridge_comparison.csv',
             'output/tables/common_period_spatial/common_period_spatial_station_master.csv']
    return stations, old, {name:sha256(root/name) for name in names}


def cache_paths(sid: str) -> dict[str, Path]:
    """Centralized saved Tier A cache paths; no fallback to downloads."""
    return {'matched': Path(f'data/nationwide_matched/{sid}_nasa_kma_temperature_1981_2025.csv'),
            'KMA': Path(f'data/nationwide_kma_processed/{sid}_asos_temperature_1981_2025.csv'),
            'NASA': Path(f'data/nationwide_nasa_processed/{sid}_nasa_temperature_1981_2025.csv')}


def validate_calendar(frame: pd.DataFrame, sid: str, start: str, end: str) -> None:
    """Reject duplicate/missing dates, reordered calendars and foreign station IDs."""
    expected = pd.date_range(start, end)
    if frame.date.duplicated().any() or not pd.DatetimeIndex(frame.date).equals(expected):
        raise ValueError(f'Exact daily calendar mismatch: {sid}')
    if 'station_id' not in frame or set(frame.station_id.astype(str)) != {str(sid)}:
        raise ValueError(f'Foreign or missing station ID: {sid}')


def load_daily(stations: pd.DataFrame, root: Path = PROJECT_ROOT) -> tuple[dict, dict]:
    """Verify matched values against both independent processed sources, preserving NaNs."""
    daily, hashes = {}, {}
    for sid in stations.station_id:
        paths = cache_paths(sid)
        frames = {name: pd.read_csv(root/path, dtype={'station_id':str}, parse_dates=['date']) for name,path in paths.items()}
        matched = frames['matched']
        for name, frame in frames.items():
            validate_calendar(frame, sid, '1981-01-01', '2025-12-31')
            hashes[paths[name].as_posix()] = sha256(root/paths[name])
        for source, mapping in SOURCE_COLUMNS.items():
            values = matched[list(mapping)].apply(pd.to_numeric, errors='raise').to_numpy(float)
            original = frames[source][list(mapping.values())].to_numpy(float)
            if not np.allclose(values, original, rtol=0, atol=1e-12, equal_nan=True):
                raise ValueError(f'Matched and processed values differ: {sid}/{source}')
            finite = values[np.isfinite(values)]
            if np.isinf(values).any() or (finite < -90).any() or (finite > 65).any():
                raise ValueError(f'Invalid temperature or unhandled missing code: {sid}/{source}')
        daily[sid] = matched
    return daily, hashes


def subset_window(daily: pd.DataFrame, window: dict) -> pd.DataFrame:
    """Subset saved daily rows without changing observations or filling missing values."""
    result = daily.loc[daily.date.between(window['start_date'],window['end_date'])].copy().reset_index(drop=True)
    validate_calendar(result, str(daily.station_id.iloc[0]),window['start_date'],window['end_date'])
    return result


def prepared_station(frame: pd.DataFrame, station: pd.Series, path: Path) -> PreparedStation:
    """Adapt the same subset to existing pure annual/validation/threshold functions."""
    meta = ['date','station_id','station_name']
    kma = frame[meta+list(SOURCE_COLUMNS['KMA'])].rename(columns=SOURCE_COLUMNS['KMA'])
    nasa = frame[meta+list(SOURCE_COLUMNS['NASA'])].rename(columns=SOURCE_COLUMNS['NASA'])
    return PreparedStation(station.station_id,station.station_name,'cache',path,path,path,path,nasa,kma,frame)


def quality_by_window(frame: pd.DataFrame, window: dict) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Reapply existing screening rules and expose valid days, missingness and annual completeness."""
    rows, yearly = [], []
    for source,mapping in SOURCE_COLUMNS.items():
        columns = list(mapping)
        annual = pd.DataFrame({'year':frame.date.dt.year,'expected_days':1,
                              'valid_core':frame[columns].notna().all(axis=1).astype(int)})
        row = {'station_id':str(frame.station_id.iloc[0]),'source':source,'expected_dates':window['expected_days'],
               'duplicate_dates':int(frame.date.duplicated().sum()),'start_date':window['start_date'],'end_date':window['end_date']}
        for metric,column in zip(('tavg','tmax','tmin'),columns):
            missing = frame[column].isna()
            row.update({f'{metric}_valid_days':int((~missing).sum()),f'{metric}_missing':int(missing.sum()),
                        f'{metric}_missing_rate':float(missing.mean()),f'{metric}_longest_gap':longest_missing_streak(frame[column])})
            annual[f'valid_{metric}'] = (~missing).astype(int)
        annual = annual.groupby('year',as_index=False).sum()
        annual['completeness_ratio'] = annual.valid_core/annual.expected_days
        for metric in ('tavg','tmax','tmin'):
            annual[f'{metric}_completeness'] = annual[f'valid_{metric}']/annual.expected_days
        gap = longest_missing_streak(pd.Series(np.where(frame[columns].isna().any(axis=1),np.nan,1.)))
        check = {f'{old}_temp_missing_rate':row[f'{new}_missing_rate'] for old,new in zip(('avg','max','min'),('tavg','tmax','tmin'))}
        passed,reasons = evaluate_period_quality({**check,'longest_temperature_gap_days':gap},annual,load_screening_config())
        row.update(longest_temperature_gap_days=gap,annual_completeness_min=float(annual.completeness_ratio.min()),
                   annual_completeness_median=float(annual.completeness_ratio.median()),data_quality_flag='PASS' if passed else 'REVIEW_REQUIRED',
                   quality_reasons=';'.join(reasons))
        rows.append(row); yearly.append(annual.assign(station_id=row['station_id'],source=source))
    return pd.DataFrame(rows),pd.concat(yearly,ignore_index=True)


def verify_grid_equality(stations: pd.DataFrame, subsets: dict, window: dict) -> pd.DataFrame:
    """Recheck full NASA daily series in every window under the project's fixed grid representation."""
    rows = []
    for gid,group in stations.groupby('nasa_grid_id',sort=True):
        fingerprints = [series_fingerprint(subsets[sid].rename(columns=SOURCE_COLUMNS['NASA'])) for sid in group.station_id]
        if len(set(fingerprints)) != 1:
            raise ValueError(f'NASA shared-grid series differ: {gid}/{window["window_id"]}')
        rows.append({'nasa_grid_id':gid,'latitude':group.nasa_grid_latitude.iloc[0], 'longitude':group.nasa_grid_longitude.iloc[0],
                     'station_count':len(group),'station_ids':'|'.join(group.station_id),'station_names':'|'.join(group.station_name),
                     'series_equal':True,'series_sha256':fingerprints[0],**window})
    return pd.DataFrame(rows)
