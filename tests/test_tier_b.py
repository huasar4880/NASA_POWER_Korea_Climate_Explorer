"""Offline Stage15 regression tests with explicitly synthetic test-only observations."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json

import numpy as np
import pandas as pd
import pytest

from src.tier_b import data, analysis, artifacts, workflow
from src.nationwide.tier_a_pipeline import PreparedStation, _atomic_csv
from src.nationwide import tier_a_analysis as shared
from src.statistical_analysis import analyze_trend_series


@pytest.fixture
def station() -> pd.Series:
    """Single imaginary station for offline tests, not a production observation."""
    return pd.Series({'station_id': '999', 'station_name': 'SYNTHETIC', 'region': 'TEST',
                      'region_level1': 'TEST', 'region_level2': 'TEST', 'latitude': 36.0,
                      'longitude': 127.0, 'elevation_m': 10., 'temperature_missing_rate': 0.,
                      'annual_completeness': 1., 'continuity_risk': 'low'})


@pytest.fixture
def raw(station: pd.Series) -> pd.DataFrame:
    """Deterministic test series; never saved to production paths."""
    dates = data.calendar()
    values = 12 + .04*(dates.year-1991) + 10*np.sin(dates.dayofyear/365.25*2*np.pi)
    return pd.DataFrame({'tm': dates.strftime('%Y-%m-%d'), 'stnId': station.station_id,
                         'avgTa': values, 'maxTa': values+10, 'minTa': values-5})


@pytest.fixture
def nasa_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """Test NASA analog with known one-degree mean offset."""
    return raw.rename(columns={'tm': 'DATE', 'avgTa': 'T2M', 'maxTa': 'T2M_MAX', 'minTa': 'T2M_MIN'}).assign(
        DATE=pd.to_datetime(raw.tm).dt.strftime('%Y%m%d'), T2M=raw.avgTa+1).drop(columns='stnId')


@pytest.fixture
def item(station: pd.Series, raw: pd.DataFrame, nasa_raw: pd.DataFrame) -> PreparedStation:
    """Prepared calendar fixture using the production preprocessing path."""
    kma, nasa = data.preprocess(raw, station, 'KMA'), data.preprocess(nasa_raw, station, 'NASA')
    matched = nasa.rename(columns={'T2M': 'nasa_T2M', 'T2M_MAX': 'nasa_T2M_MAX', 'T2M_MIN': 'nasa_T2M_MIN'}).merge(
        kma[['date', 'avg_temperature', 'max_temperature', 'min_temperature']].rename(
            columns={'avg_temperature': 'kma_T2M', 'max_temperature': 'kma_TMAX', 'min_temperature': 'kma_TMIN'}), on='date')
    return PreparedStation(str(station.station_id), str(station.station_name), 'test', *([Path('unused')]*4), nasa, kma, matched)


def make_metadata(root: Path) -> None:
    """Write two synthetic candidates only under pytest temporary storage."""
    target = root/'output/tables'; target.mkdir(parents=True)
    common = {'station_id': ['998', '999'], 'station_name': ['A-test', 'B-test'], 'latitude': [36., 36.],
              'longitude': [127., 127.], 'elevation_m': [1., 1.], 'continuity_risk': ['low', 'low'],
              'temperature_missing_rate': [0., 0.], 'annual_completeness': [1., 1.], 'eligibility_tier': ['A', 'B']}
    pd.DataFrame(common).to_csv(root/data.SHORTLIST, index=False)
    pd.DataFrame({'station_id': ['998', '999'], 'region_level1': ['TEST']*2, 'region_level2': ['TEST']*2,
                  'actual_data_start_date': ['1991-01-01']*2, 'actual_data_end_date': ['2025-12-31']*2,
                  'eligible_1991_2025': [True]*2, 'manual_review_required': [False]*2}).to_csv(root/data.MASTER, index=False)


def test_b_only(tmp_path: Path) -> None:
    make_metadata(tmp_path)
    selected = data.load_stations(tmp_path)
    assert selected.station_id.tolist() == ['999']
    assert selected.eligibility_tier.eq('B').all()


@pytest.mark.parametrize('column,value', [('manual_review_required', True), ('eligible_1991_2025', False),
                                         ('actual_data_start_date', '1991-01-02'), ('actual_data_end_date', '2025-12-30')])
def test_selection_rejects_metadata(tmp_path: Path, column: str, value: object) -> None:
    make_metadata(tmp_path)
    frame = pd.read_csv(tmp_path/data.MASTER)
    frame.loc[1, column] = value; frame.to_csv(tmp_path/data.MASTER, index=False)
    with pytest.raises(ValueError):
        data.load_stations(tmp_path)


@pytest.mark.parametrize('risk', ['high', 'unknown', 'unresolved', 'manual_review'])
def test_unresolved_continuity(tmp_path: Path, risk: str) -> None:
    make_metadata(tmp_path)
    frame = pd.read_csv(tmp_path/data.SHORTLIST)
    frame.loc[1, 'continuity_risk'] = risk; frame.to_csv(tmp_path/data.SHORTLIST, index=False)
    with pytest.raises(ValueError):
        data.load_stations(tmp_path)


def test_calendar_period() -> None:
    dates = data.calendar()
    assert len(dates) == 12784 and str(dates[0].date()) == '1991-01-01' and str(dates[-1].date()) == '2025-12-31'


@pytest.mark.parametrize('year,expected', [(1991, 365), (1992, 366), (2000, 366), (2024, 366), (2025, 365)])
def test_leap_calendar(year: int, expected: int) -> None:
    assert sum(data.calendar().year == year) == expected


def test_kma_cache(tmp_path: Path, raw: pd.DataFrame) -> None:
    path = tmp_path/'data/nationwide_asos_raw/stations/999/999_asos_daily_1991_2025.csv'
    _atomic_csv(raw, path)
    assert data.kma_path(tmp_path, '999') == path
    assert data.valid_cache(path, 'KMA', '999')


def test_nasa_cache(tmp_path: Path, nasa_raw: pd.DataFrame) -> None:
    path = data.nasa_path(tmp_path, '999'); _atomic_csv(nasa_raw, path)
    assert data.valid_cache(path, 'NASA', '999')


def test_dry_run_no_writes_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_metadata(tmp_path)
    monkeypatch.setattr('requests.sessions.Session.request', Mock(side_effect=AssertionError('HTTP forbidden')))
    before = {str(p) for p in tmp_path.rglob('*')}
    result = workflow.run_analysis(tmp_path, dry_run=True)
    assert result['estimated_NASA_requests'] == 1 and result['KMA_cache_hits'] == 0
    assert before == {str(p) for p in tmp_path.rglob('*')}


@pytest.mark.parametrize('source', ['KMA', 'NASA'])
def test_processed_full_calendar(station: pd.Series, raw: pd.DataFrame, nasa_raw: pd.DataFrame, source: str) -> None:
    frame = raw if source == 'KMA' else nasa_raw
    result = data.preprocess(frame.drop(index=5), station, source)
    assert len(result) == 12784
    assert result.loc[5, list(data.MAPS[source].values())].isna().all()


@pytest.mark.parametrize('value', [-999, -999.0, -100, 99, np.nan])
def test_missing_not_zero(station: pd.Series, raw: pd.DataFrame, value: float) -> None:
    raw.loc[0, 'avgTa'] = value
    assert pd.isna(data.preprocess(raw, station, 'KMA').avg_temperature.iloc[0])


def test_duplicate_rejected(station: pd.Series, raw: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match='Duplicate'):
        data.preprocess(pd.concat([raw, raw.iloc[:1]]), station, 'KMA')


def test_wrong_station_rejected(station: pd.Series, raw: pd.DataFrame) -> None:
    raw.loc[0, 'stnId'] = '998'
    with pytest.raises(ValueError, match='station'):
        data.preprocess(raw, station, 'KMA')


def test_quality_gap(station: pd.Series, raw: pd.DataFrame) -> None:
    daily = data.preprocess(raw.drop(index=range(90)), station, 'KMA')
    quality, annual = data.quality(raw.drop(index=range(90)), daily, 'KMA')
    assert quality['missing_dates'] == 90 and quality['analysis_review_required']
    assert quality['longest_temperature_gap_days'] == 90 and len(annual) == 35


def test_quality_complete(station: pd.Series, raw: pd.DataFrame) -> None:
    daily = data.preprocess(raw, station, 'KMA')
    quality, annual = data.quality(raw, daily, 'KMA')
    assert not quality['analysis_review_required'] and annual.tavg_completeness.eq(1).all()


def test_annual_moving(item: PreparedStation, station: pd.Series) -> None:
    annual = shared.calculate_station_annual_temperature([item], pd.DataFrame([station]))
    selected = annual.loc[annual.source.eq('KMA') & annual.metric.eq('TAVG')]
    assert len(annual) == 210
    assert selected.moving_average_5yr.isna().sum() == 4
    assert selected.moving_average_10yr.isna().sum() == 9
    assert selected.annual_mean.iloc[0] == pytest.approx(item.kma.loc[item.kma.date.dt.year.eq(1991), 'avg_temperature'].mean())


def test_sen_and_mk() -> None:
    result = analyze_trend_series(range(1991, 2026), np.arange(35)*.1)
    assert result['sen_slope_per_decade'] == pytest.approx(1)
    assert result['mk_p_value'] < .05 and result['mk_trend'] == 'increasing'


def test_fdr_local(item: PreparedStation, station: pd.Series) -> None:
    stations = pd.DataFrame([station])
    annual = shared.calculate_station_annual_temperature([item], stations)
    result = analysis.cohort_family(shared.calculate_station_trends(annual, stations))
    assert result.fdr_family.str.contains('Tier B').all()
    assert result.fdr_q_value.to_numpy() == pytest.approx(result.mk_p_value.to_numpy())
    assert len(result.groupby(['source', 'metric'])) == 6


def test_normal_anomaly(item: PreparedStation, station: pd.Series) -> None:
    annual = shared.calculate_station_annual_temperature([item], pd.DataFrame([station]))
    normal, anomaly = shared.calculate_normals_and_anomalies(annual)
    assert normal.n_years.eq(30).all()
    assert (anomaly.annual_mean - anomaly.normal_mean).to_numpy() == pytest.approx(anomaly.anomaly.to_numpy())


def test_season_boundaries(item: PreparedStation, station: pd.Series) -> None:
    result = shared.calculate_seasonal_temperature([item], pd.DataFrame([station]))
    assert result.loc[result.season.eq('DJF'), 'n_years'].eq(34).all()
    assert result.loc[result.season.ne('DJF'), 'n_years'].eq(35).all()


@pytest.mark.parametrize('threshold,column,value', [('TMAX_GE_30', 'kma_TMAX', 30), ('TMAX_GE_33', 'kma_TMAX', 33), ('TMIN_GE_25', 'kma_TMIN', 25)])
def test_threshold(item: PreparedStation, threshold: str, column: str, value: float) -> None:
    result = shared.calculate_threshold_annual([item])
    observed = result.loc[result.threshold.eq(threshold), 'kma_count'].sum()
    assert observed == (item.matched[column] >= value).sum()


@pytest.mark.parametrize('metric,expected', [('bias', 1), ('mae', 1), ('rmse', 1), ('pearson_r', 1), ('spearman_rho', 1)])
def test_validation(item: PreparedStation, station: pd.Series, metric: str, expected: float) -> None:
    row = shared.calculate_temperature_validation([item], pd.DataFrame([station])).query('metric == "TAVG"').iloc[0]
    assert row[metric] == pytest.approx(expected) and row.n_pairs == 12784


def test_summary_rank_consistency(item: PreparedStation, station: pd.Series) -> None:
    result = analysis.build_products([item], pd.DataFrame([station]), pd.DataFrame({'analysis_review_required': [False]}))
    summary = result['tier_b_station_temperature_summary']
    assert len(summary) == 1 and summary.data_quality_flag.eq('passed_screening_recheck').all()
    assert summary.kma_last_10yr_mean.iloc[0] > summary.kma_first_10yr_mean.iloc[0]
    assert result['tier_b_temperature_rankings'].ranking_scope.str.startswith('Tier B').all()
    assert result['tier_b_nasa_kma_trend_consistency'].same_direction.all()
    assert result['tier_b_nasa_kma_trend_consistency'].kma_trend_direction.eq('increasing').all()
    assert result['tier_b_nasa_kma_trend_consistency'].nasa_trend_direction.eq('increasing').all()


def test_review_withholds_analysis(item: PreparedStation, station: pd.Series) -> None:
    with pytest.raises(ValueError, match='withheld'):
        analysis.build_products([item], pd.DataFrame([station]), pd.DataFrame({'analysis_review_required': [True]}))


def test_resume_nasa_cache_zero_api(tmp_path: Path, nasa_raw: pd.DataFrame, station: pd.Series) -> None:
    _atomic_csv(nasa_raw, data.nasa_path(tmp_path, '999'))
    session = Mock(calls=0)
    frame, path = data.download_station(station, 'NASA', tmp_path, session)
    session.get.assert_not_called()
    assert len(frame) == 12784
    assert json.loads((path.parent/'download_state.json').read_text())['stations']['999']['status'] == 'completed'


def test_failed_state_and_resume(tmp_path: Path, station: pd.Series, nasa_raw: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(data, 'fetch_daily_data', Mock(side_effect=RuntimeError('offline')))
    session = Mock(calls=0)
    with pytest.raises(RuntimeError):
        data.download_station(station, 'NASA', tmp_path, session)
    state = tmp_path/'data/tier_b_nasa_raw/download_state.json'
    assert json.loads(state.read_text())['stations']['999']['status'] == 'failed'
    monkeypatch.setattr(data, 'fetch_daily_data', Mock(return_value=SimpleNamespace(dataframe=nasa_raw)))
    frame, path = data.download_station(station, 'NASA', tmp_path, session)
    assert path.exists() and len(frame) == 12784
    assert json.loads(state.read_text())['stations']['999']['status'] == 'completed'


def test_invalid_existing_raw_preserved(tmp_path: Path, station: pd.Series) -> None:
    path = data.nasa_path(tmp_path, '999'); _atomic_csv(pd.DataFrame({'bad': [1]}), path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='preserved'):
        data.download_station(station, 'NASA', tmp_path, Mock(calls=0))
    assert path.read_bytes() == before


def test_protection_includes_old_stage145(tmp_path: Path) -> None:
    path = tmp_path/'output/tables/spatial_models_numerical/old.csv'; _atomic_csv(pd.DataFrame({'a': [1]}), path)
    _atomic_csv(pd.DataFrame({'a': [1]}), tmp_path/'output/tables/tier_b/new.csv')
    before = data.snapshot(tmp_path)
    assert list(before) == ['output/tables/spatial_models_numerical/old.csv']
    assert workflow.check_snapshot(tmp_path, before) == []


def test_coastal_join(station: pd.Series, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workflow, 'load_coastline', lambda *args: {'available': True})
    monkeypatch.setattr(workflow, 'station_distances', lambda stations, coast: stations.assign(distance_to_coast_km=5.))
    result = workflow.coastal_distances(pd.DataFrame([station]), tmp_path)
    assert result.station_id.tolist() == ['999'] and result.distance_to_coast_km.iloc[0] == 5


def test_loader_allowlist(tmp_path: Path) -> None:
    for name in artifacts.TABLES:
        _atomic_csv(pd.DataFrame({'station_id': ['999']}), tmp_path/data.TABLE_DIR/f'{name}.csv')
    assert len(artifacts.load_tables(tmp_path)) == 15


def test_saved_report_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(artifacts, 'load_tables', lambda root: {'saved': True})
    write = Mock(return_value=['report.html', 'report.md'])
    monkeypatch.setattr(artifacts, 'write_reports', write)
    assert len(artifacts.report_from_saved(tmp_path)) == 2
    write.assert_called_once_with({'saved': True}, tmp_path)


def test_manifest_json(tmp_path: Path) -> None:
    payload = {'station_ids': ['999'], 'analysis_period': ['1991-01-01', '2025-12-31'], 'input_hashes': {'data/file.csv': 'digest'}}
    data._atomic_json(payload, tmp_path/data.MANIFEST)
    assert json.loads((tmp_path/data.MANIFEST).read_text()) == payload


def test_pending_manifest_blocks_stale_tables(tmp_path: Path) -> None:
    data._atomic_json({'status': 'pending'}, tmp_path/data.MANIFEST)
    with pytest.raises(ValueError, match='incomplete'):
        artifacts.load_tables(tmp_path)


def test_manifest_detects_modified_table(tmp_path: Path) -> None:
    for name in artifacts.TABLES:
        _atomic_csv(pd.DataFrame({'station_id': ['999']}), tmp_path/data.TABLE_DIR/f'{name}.csv')
    hashes = {f'{data.TABLE_DIR}/{name}.csv': data.sha256(tmp_path/data.TABLE_DIR/f'{name}.csv') for name in artifacts.TABLES}
    data._atomic_json({'status': 'completed', 'output_hashes': hashes}, tmp_path/data.MANIFEST)
    assert len(artifacts.load_tables(tmp_path)) == 15
    _atomic_csv(pd.DataFrame({'station_id': ['998']}), tmp_path/data.TABLE_DIR/f'{artifacts.TABLES[0]}.csv')
    with pytest.raises(ValueError, match='checksum'):
        artifacts.load_tables(tmp_path)


def test_multiple_stations_independent(item: PreparedStation, station: pd.Series) -> None:
    from dataclasses import replace
    other = station.copy(); other.station_id = '997'; other.station_name = 'SYNTHETIC2'
    other_item = replace(item, station_id='997', station_name='SYNTHETIC2')
    result = analysis.build_products([item, other_item], pd.DataFrame([station, other]),
                                    pd.DataFrame({'analysis_review_required': [False, False]}))
    assert len(result['tier_b_temperature_trends']) == 12
    assert len(result['tier_b_station_temperature_summary']) == 2
    assert result['tier_b_temperature_rankings']['rank'].eq(1).all()


def test_report_reproducible(item: PreparedStation, station: pd.Series, tmp_path: Path) -> None:
    products = analysis.build_products([item], pd.DataFrame([station]), pd.DataFrame({'analysis_review_required': [False]}))
    products.update({'tier_b_analysis_stations': pd.DataFrame([station]), 'tier_b_data_quality': pd.DataFrame({'passed': [True]}),
                     'tier_b_station_coastal_distance': pd.DataFrame({'station_id': ['999'], 'distance_to_coast_km': [5.]})})
    files = artifacts.write_reports(products, tmp_path)
    hashes = [data.sha256(tmp_path/p) for p in files]
    artifacts.write_reports(products, tmp_path)
    assert hashes == [data.sha256(tmp_path/p) for p in files]
    assert data.WARNING in (tmp_path/files[1]).read_text()
