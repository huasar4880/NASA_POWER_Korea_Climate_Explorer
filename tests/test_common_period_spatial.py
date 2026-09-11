"""Stage17 synthetic offline regression tests; no observations fabricated in project storage."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

from src.common_period_spatial import data, statistics as stats, workflow, artifacts
from src.spatial.autocorrelation import GLOBAL_VARIABLES, moran_i
from src.spatial.robustness import classify_robustness
from src.spatial.robustness_audit import sha256, check_snapshot
from src.nationwide.tier_a_pipeline import _atomic_csv, _atomic_json
from src.spatial.coastal_analysis import METRICS


@pytest.fixture(autouse=True)
def no_http():
    """All new tests explicitly prohibit requests HTTP."""
    with patch('requests.sessions.Session.request', side_effect=AssertionError('Stage17 HTTP forbidden')):
        yield


@pytest.fixture(scope='module')
def config():
    """Small test permutations only; production reads the unchanged 999 configuration."""
    return dict(random_seed=123, moran_permutations=19, local_moran_permutations=19, alpha=.05,
                robust_fraction=.75, coastal_thresholds_km=[20, 30, 50])


@pytest.fixture(scope='module')
def master():
    """Twelve hypothetical stations sharing six hypothetical grids, for unit tests only."""
    rng = np.random.default_rng(17)
    n = 12
    d = pd.DataFrame({'station_id': [str(900+i) for i in range(n)], 'station_name': [f'TEST{i}' for i in range(n)],
        'region_level1': ['R1']*5+['R2']*5+['R3']*2, 'region_level2': ['R']*n,
        'latitude': np.linspace(34, 38, n), 'longitude': 126+np.sin(np.arange(n))*.4,
        'elevation_m': np.arange(n)*55., 'distance_to_coast_km': np.arange(n)*9.,
        'cohort_origin': ['TIER_A']*10+['TIER_B']*2, 'continuity_risk': ['low']*n,
        'annual_completeness': [1.]*n, 'nasa_grid_id': [f'grid{i//2}' for i in range(n)],
        'nasa_grid_group_size': [2]*n, 'nasa_grid_shared': [True]*n, 'nasa_series_sha256': ['synthetic']*n,
        'data_quality_flag': ['synthetic_fixture']*n, 'tavg_mae': [1.]*n, 'tavg_pearson': [.9]*n, 'tavg_spearman': [.9]*n})
    d['nasa_grid_latitude'] = 34+(np.arange(n)//2)*.5
    d['nasa_grid_longitude'] = 126+(np.arange(n)//2%2)*.625
    d['elevation_band'] = pd.cut(d.elevation_m, [-np.inf, 50, 200, 500, np.inf], right=False,
        labels=['<50m', '50–200m', '200–500m', '>=500m']).astype(str)
    for column in sorted(set(stats.KMA_VARIABLES) | set(METRICS)):
        d[column] = rng.normal(.3, .15, n)
    for column in stats.NASA_VARIABLES:
        d[column] = np.repeat(rng.normal(.3, .15, n//2), 2)
    for source in ['kma', 'nasa']:
        for short, old in [('33c', 'days_tmax_ge_33'), ('25c', 'days_tmin_ge_25')]:
            if source == 'kma':
                d[f'{source}_{short}_sen_slope'] = d[f'{old}_kma_slope']
    return d


@pytest.fixture(scope='module')
def inputs(master, config):
    """Small source tables and historical baseline generated from synthetic station fixtures."""
    trends, thresholds, annual, seasonal = [], [], [], []
    for r in master.itertuples():
        for source in ('KMA', 'NASA'):
            for metric in ('TAVG', 'TMAX', 'TMIN'):
                slope = getattr(r, f'{source.lower()}_{metric.lower()}_sen_slope')
                trends.append(dict(station_id=r.station_id, source=source, metric=metric, sen_slope_per_decade=slope))
                for year in range(1991, 2026):
                    annual.append(dict(station_id=r.station_id, source=source, metric=metric, year=year,
                        annual_mean={'TAVG': 12, 'TMAX': 17, 'TMIN': 8}[metric]+slope*(year-1991)/10+.01*np.sin(year)))
                for i, season in enumerate(('DJF', 'MAM', 'JJA', 'SON')):
                    seasonal.append(dict(station_id=r.station_id, source=source, metric=metric, season=season,
                                         sen_slope_per_decade=slope*(i+1)/2))
            for short, threshold in [('33c', 'TMAX_GE_33'), ('25c', 'TMIN_GE_25')]:
                thresholds.append(dict(station_id=r.station_id, source=source, threshold=threshold,
                                       sen_slope_per_decade=getattr(r, f'{source.lower()}_{short}_sen_slope')))
    a = pd.DataFrame(annual)
    baseline_master = master.loc[master.cohort_origin.eq('TIER_A')]
    _, networks, _ = stats.build_networks(baseline_master, 'STATION_LINKED')
    historical = stats.global_results(baseline_master, networks, list(GLOBAL_VARIABLES), 'OLD', 'STATION_LINKED', config)
    old_global = historical.loc[historical.weight_variant.eq('directed_knn_k4')].assign(n_stations=len(baseline_master))
    old_summary = stats.robustness(historical, config)
    from src.spatial.coastal_analysis import coastal_comparisons, threshold_consistency
    old_coast = threshold_consistency(coastal_comparisons(baseline_master, [20, 30, 50], .05))
    f = {'1991_2025_station_master': master.copy(), 'station_temperature_summary': master.copy(),
         'temperature_trends': pd.DataFrame(trends), 'threshold_trends': pd.DataFrame(thresholds),
         'nasa_grid_mapping': master.groupby('nasa_grid_id').size().rename('station_count').reset_index(),
         'kma_annual_temperature': a.loc[a.source.eq('KMA')], 'nasa_annual_temperature': a.loc[a.source.eq('NASA')],
         'seasonal_temperature_trends': pd.DataFrame(seasonal),
         'dominant_warming_season': master[['station_id']].assign(source='KMA', dominant_season='SON'),
         'old_global': old_global, 'old_weights': historical, 'old_robustness': old_summary,
         'old_local': baseline_master[['station_id', 'station_name']].assign(stable_local_pattern=False),
         'old_coastal': old_coast, 'data_quality': master[['station_id']].assign(source='KMA', missing_dates=0, tavg_missing=0, tmax_missing=0, tmin_missing=0)}
    for x in ('latitude', 'longitude', 'elevation_m'):
        f[f'old_{x}'] = pd.DataFrame([stats.calculate_association(baseline_master, x, y) for y in ['kma_tavg_sen_slope', 'kma_tmax_sen_slope', 'kma_tmin_sen_slope', 'tavg_bias', 'tavg_rmse']])
    return f


@pytest.fixture(scope='module')
def products(inputs, config):
    """End-to-end pure products on synthetic inputs; never writes outside test directories."""
    m, g = data.build_masters(inputs)
    return workflow.build_products(inputs, config, m, g)


def test_master_membership(inputs):
    m, g = data.build_masters(inputs)
    assert len(m) == 12 and len(g) == 6 and m.station_id.is_unique


def test_grid_membership_integrity(inputs):
    m, g = data.build_masters(inputs)
    assert g.nasa_grid_id.is_unique and g.station_count.sum() == len(m)
    assert set('|'.join(g.station_ids).split('|')) == set(m.station_id)


def test_grid_metric_mismatch_rejected(inputs):
    import copy
    bad = copy.deepcopy(inputs)
    bad['temperature_trends'].loc[0, 'source'] = 'NASA'
    with pytest.raises((ValueError, pd.errors.InvalidIndexError)):
        data.build_masters(bad)


def test_no_arbitrary_threshold_selection(inputs):
    import copy
    bad = copy.deepcopy(inputs)
    row = bad['threshold_trends'].query('source=="NASA"').index[0]
    bad['threshold_trends'].loc[row, 'sen_slope_per_decade'] += 1
    with pytest.raises(ValueError, match='metrics differ within grid'):
        data.build_masters(bad)


@pytest.mark.parametrize('representation', ['STATION_LINKED', 'UNIQUE_GRID'])
def test_distance_matrices(inputs, representation):
    m, g = data.build_masters(inputs)
    selected = m if representation == 'STATION_LINKED' else data.grid_coordinates(g)
    d, _, _ = stats.build_networks(selected, representation)
    assert np.allclose(d, d.T) and np.allclose(np.diag(d), 0) and np.isfinite(d).all().all()
    assert list(d.index) == list(d.columns)


@pytest.mark.parametrize('name', ['directed_knn_k3', 'directed_knn_k4', 'directed_knn_k5', 'directed_knn_k6', 'symmetric_knn_k4',
 'inverse_distance_p2_row', 'inverse_distance_p1_cutoff_row', 'inverse_distance_p2_cutoff_row', 'distance_band_x1'])
def test_recommended_weights(master, name):
    _, networks, summaries = stats.build_networks(master, 'STATION_LINKED')
    weight, _ = networks[name]
    assert np.allclose(weight.matrix.sum(axis=1), 1) and not np.diag(weight.matrix).any()
    assert summaries.isolates.eq(0).all() and summaries.weak_components.eq(1).all()
    if name.startswith('directed'):
        assert (np.count_nonzero(weight.matrix, axis=1) == int(name[-1])).all()
    if name.startswith('symmetric'):
        assert np.array_equal(weight.matrix > 0, weight.matrix.T > 0)


def test_banned_weights_excluded(master):
    _, networks, _ = stats.build_networks(master, 'STATION_LINKED')
    assert not any(k.endswith('_raw') for k in networks)
    assert 'inverse_distance_p1_row' not in networks


@pytest.mark.parametrize('variable', stats.KMA_VARIABLES+stats.NASA_VARIABLES)
def test_global_moran_variables(products, variable):
    d = products['global_morans_i'].loc[lambda d: d.variable.eq(variable)]
    assert not d.empty and np.isfinite(d.Moran_I).all() and d.permutation_p.between(0, 1).all()
    if variable.startswith('nasa_'):
        assert set(d.representation) == {'STATION_LINKED', 'UNIQUE_GRID'}


def test_moran_matches_direct_formula(products):
    m = products['spatial_station_master']; _, networks, _ = stats.build_networks(m, 'STATION_LINKED')
    value = moran_i(m.kma_tavg_sen_slope.to_numpy(), networks['directed_knn_k4'][0].matrix)
    row = products['global_morans_i'].query('variable=="kma_tavg_sen_slope" and weight_variant=="directed_knn_k4"').iloc[0]
    assert value == pytest.approx(row.Moran_I)


@pytest.mark.parametrize('values,expected', [((.4,.42,.01,.02),'LOW'), ((.4,.55,.01,.02),'MODERATE'),
 ((.4,.42,.01,.2),'MODERATE'), ((.4,-.2,.01,.2),'HIGH')])
def test_duplication_classification(values, expected):
    assert stats.duplication_class(*values) == 'DUPLICATION_'+expected+'_IMPACT'


def test_duplication_deltas(products):
    d = products['nasa_grid_duplication_spatial_sensitivity']
    assert np.allclose(d.difference_I, d.unique_grid_Moran_I-d.station_linked_Moran_I)
    assert np.allclose(d.absolute_difference_I, abs(d.difference_I))


@pytest.mark.parametrize('values,p,expected', [([.1,.2,.3,.4],[.01]*4,'ROBUST_POSITIVE'),
 ([.1,.2,.3,.4],[.9]*4,'ROBUST_NON_SIGNIFICANT'), ([-.1,.2,.3,.4],[.01]*4,'INCONSISTENT_DIRECTION'),
 ([.1,.2,.3,.4],[.01,.01,.9,.9],'WEIGHT_SENSITIVE')])
def test_historical_robustness_rule(values, p, expected):
    assert classify_robustness(pd.DataFrame({'moran_i':values,'permutation_p':p})) == expected


def test_old_new_comparison(products):
    d = products['vs_1981_spatial_comparison']
    assert len(d) == 8 and np.allclose(d.delta_I, d.new_Moran_I-d.old_Moran_I)


def test_bridge_membership_and_accounting(products):
    d = products['spatial_bridge_comparison']
    assert d.n_bridge.eq(10).all() and d.n_new.eq(12).all()
    assert np.allclose(d.delta_period+d.delta_station_addition, d.I_51_1991-d.I_45_1981)


def test_local_fdr_family(products):
    from statsmodels.stats.multitest import multipletests
    d = products['local_moran_results']
    for _, g in d.groupby('weight_variant'):
        assert len(g) == 12 and np.allclose(g.local_fdr_q, multipletests(g.local_p, method='fdr_bh')[1])


def test_stable_local_pattern_rule():
    local = pd.DataFrame({'station_id': ['A']*3+['B']*3, 'weight_variant': ['a','b','c']*2,
        'local_significant_fdr': [True]*5+[False], 'cluster_type_fdr': ['High-High']*6})
    stable = stats.stable_local_patterns(local)
    assert stable['A'] and not stable['B']


def test_contrast(products):
    d = products['tmax_tmin_warming_contrast']
    assert np.allclose(d.tmin_minus_tmax, d.tmin_slope-d.tmax_slope)


def test_dtr_refitted_from_annual(inputs, products):
    from scipy.stats import theilslopes
    annual = inputs['kma_annual_temperature'].query('station_id=="900"').pivot(index='year', columns='metric', values='annual_mean')
    expected = theilslopes(annual.TMAX-annual.TMIN, annual.index).slope*10
    row = products['dtr_trends'].query('station_id=="900" and source=="KMA"').iloc[0]
    assert row.sen_slope_per_decade == pytest.approx(expected)
    assert 'common-period' in row.fdr_family


@pytest.mark.parametrize('season', ['DJF','MAM','JJA','SON'])
def test_seasonal_moran(products, season):
    d = products['seasonal_spatial_analysis'].loc[lambda d: d.season.eq(season)]
    assert len(d) == 3 and d.permutation_p.between(0,1).all()


def test_coast_associations(products):
    d = products['coastal_distance_associations']
    assert len(d) == 9 and d.spearman_rho.between(-1,1).all()


@pytest.mark.parametrize('threshold', [20,30,50])
def test_coastal_threshold_fdr(products, threshold):
    from statsmodels.stats.multitest import multipletests
    d = products['coastal_threshold_sensitivity'].loc[lambda d: d.threshold_km.eq(threshold)]
    assert len(d) == 9 and np.allclose(d.fdr_q, multipletests(d.raw_p, method='fdr_bh')[1])
    assert d.rank_biserial.between(-1,1).all() and (d.coastal_n+d.inland_n).eq(12).all()


@pytest.mark.parametrize('coordinate', ['latitude', 'longitude', 'elevation_m'])
def test_coordinate_associations(products, coordinate):
    d = products['coordinate_associations'].loc[lambda d: d.spatial_variable.eq(coordinate)]
    assert len(d) == 5 and d.pearson_r.between(-1,1).all()


@pytest.mark.parametrize('name', ['spatial_regional_summary', 'spatial_elevation_summary', 'bias_rmse_shared_grid_sensitivity'])
def test_descriptive_groups(products, name):
    d = products[name]
    assert d.station_count.sum() == 12 and 'tavg_bias_median' in d


def test_small_region_flag(products):
    assert products['spatial_regional_summary'].query('region_level1=="R3"').small_sample_region.item()


def test_loader_checksum(tmp_path, products):
    names = ['spatial_station_master', 'nasa_unique_grid_spatial_master']
    hashes = {}
    for name in names:
        p = tmp_path/data.TABLE_DIR/f'common_period_{name}.csv'; _atomic_csv(products[name], p)
        hashes[p.relative_to(tmp_path).as_posix()] = sha256(p)
    _atomic_json({'status':'completed','output_hashes':hashes}, tmp_path/data.MANIFEST)
    assert len(artifacts.load_tables(tmp_path)) == 2
    p.write_text('changed')
    with pytest.raises(ValueError, match='checksum'):
        artifacts.load_tables(tmp_path)


def test_loader_incomplete(tmp_path):
    _atomic_json({'status':'pending'}, tmp_path/data.MANIFEST)
    with pytest.raises(ValueError, match='incomplete'):
        artifacts.load_tables(tmp_path)


def test_report_deterministic(tmp_path, products):
    paths = artifacts.write_reports(products, tmp_path)
    before = {p: sha256(tmp_path/p) for p in paths}
    artifacts.write_reports(products, tmp_path)
    assert before == {p: sha256(tmp_path/p) for p in paths}
    text = (tmp_path/paths[1]).read_text()
    assert 'causal' in text and '45/1981' in text and '19. Next step' in text


def test_dry_run_no_writes(tmp_path, monkeypatch, inputs, config):
    m, g = data.build_masters(inputs)
    monkeypatch.setattr(workflow, 'prepare_plan', lambda root: (inputs,config,{},m,g,{'status':'dry_run','NASA_API_calls':0,'KMA_API_calls':0}))
    assert workflow.run_analysis(tmp_path, dry_run=True)['status'] == 'dry_run'
    assert not list(tmp_path.rglob('*'))


def test_protected_files(tmp_path):
    (tmp_path/'VERSION').write_text('1.0.0')
    p = tmp_path/'data/raw/old.csv'; p.parent.mkdir(parents=True); p.write_text('original')
    before = data.snapshot(tmp_path)
    new = tmp_path/data.TABLE_DIR/'new.csv'; new.parent.mkdir(parents=True); new.write_text('new')
    assert not check_snapshot(tmp_path,before) and data.snapshot(tmp_path) == before


def test_reproducibility(master, config):
    _, networks, _ = stats.build_networks(master, 'STATION_LINKED')
    args = (master,networks,['kma_tavg_sen_slope'],'KMA','STATION_LINKED',config)
    pd.testing.assert_frame_equal(stats.global_results(*args), stats.global_results(*args))


@pytest.mark.parametrize('unique', [False,True])
def test_point_map_geometry(products, unique):
    d = products['nasa_unique_grid_spatial_master'] if unique else products['spatial_station_master']
    fig = artifacts.point_map(d, 'nasa_tavg_sen_slope', 'TEST', unique_grid=unique)
    assert len(fig.data[0].lat) == (6 if unique else 12)
    assert 'station_names' in fig.data[0].text[0] if unique else 'cohort_origin' in fig.data[0].text[0]


def test_dashboard_selector_scoped_to_nasa(monkeypatch, products):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(artifacts, 'load_tables', lambda: products)
    app = AppTest.from_string('from dashboard.pages.common_period_spatial import render\nrender()').run(timeout=30)
    assert not app.exception
    app.selectbox(key='stage17_representation').set_value('Unique-grid').run(timeout=30)
    assert not app.exception
    app.selectbox(key='stage17_kma_metric').set_value('tavg_bias').run(timeout=30)
    assert not app.exception and app.selectbox(key='stage17_representation').label.startswith('NASA-only')


@pytest.mark.parametrize('change', ['none', 'value', 'missing_day', 'duplicate_day'])
def test_daily_grid_series_validation(tmp_path, change):
    """Full synthetic calendar verification rejects changed values, missing dates and duplicates."""
    from src.common_period.grid import series_fingerprint
    days = pd.date_range('1991-01-01', '2025-12-31')
    values = np.round(np.sin(np.arange(len(days))), 4)
    frame = pd.DataFrame({'date': days, 'T2M': values,
                          'T2M_MAX': np.round(values+5, 4), 'T2M_MIN': np.round(values-5, 4)})
    master = pd.DataFrame({'station_id': ['999'], 'nasa_grid_id': ['synthetic_grid'],
                           'nasa_series_sha256': [series_fingerprint(frame)]})
    if change == 'value':
        frame.loc[0, 'T2M'] += 1
    elif change == 'missing_day':
        frame = frame.drop(index=4)
    elif change == 'duplicate_day':
        frame = pd.concat([frame, frame.iloc[:1]])
    path = tmp_path/'data/common_period/nasa_processed/999_nasa_temperature_1991_2025.csv'
    _atomic_csv(frame.rename(columns={'T2M':'nasa_t2m','T2M_MAX':'nasa_tmax','T2M_MIN':'nasa_tmin'}), path)
    if change == 'none':
        assert len(data.validate_grid_series(master, tmp_path)) == 1
    else:
        with pytest.raises(ValueError):
            data.validate_grid_series(master, tmp_path)


def test_missing_duplication_result_not_classified():
    with pytest.raises(ValueError, match='finite'):
        stats.duplication_class(.4, np.nan, .01, np.nan)


def test_only_mutually_supported_grid_weights_compared(products):
    result = products['nasa_grid_duplication_spatial_sensitivity']
    assert 'directed_knn_k6' not in set(result.weight_variant)
    assert np.isfinite(result[['difference_I','unique_grid_p']]).all().all()


def test_map_independent_of_process_theme(products):
    """Importing Streamlit or another caller must not change deterministic HTML figure content."""
    import plotly.io as pio
    original = pio.templates.default
    try:
        pio.templates.default = 'plotly'
        a = artifacts.point_map(products['spatial_station_master'], 'nasa_tavg_sen_slope', 'TEST').to_json()
        pio.templates.default = 'plotly_dark'
        b = artifacts.point_map(products['spatial_station_master'], 'nasa_tavg_sen_slope', 'TEST').to_json()
        assert a == b
    finally:
        pio.templates.default = original


def test_offline_workflow_manifest_protection(tmp_path, monkeypatch, inputs, config, products):
    """Actual isolated exports produce traceable manifest while old raw/processed bytes and mtimes persist."""
    (tmp_path/'VERSION').write_text('1.0.0')
    for folder in ('raw', 'processed'):
        p = tmp_path/'data'/folder/'existing.csv'; p.parent.mkdir(parents=True); p.write_text('unchanged')
    before = data.snapshot(tmp_path)
    m,g = data.build_masters(inputs)
    plan = dict(status='dry_run',station_count=len(m),unique_NASA_grid_count=len(g),
        NASA_API_calls=0,KMA_API_calls=0,expected_global_rows=len(products['global_morans_i']),expected_local_rows=len(m)*3)
    monkeypatch.setattr(workflow,'prepare_plan',lambda root:(inputs,config,{},m,g,plan))
    monkeypatch.setattr(artifacts,'save_charts',lambda tables,root:[])
    result = workflow.run_analysis(tmp_path)
    assert result['status']=='completed' and not result['protected_files_changed']
    assert not check_snapshot(tmp_path,before) and result['NASA_API_calls']==result['KMA_API_calls']==0
    assert result['grid_daily_series_verified'] and result['representation_definitions']['UNIQUE_GRID']
    assert all(sha256(tmp_path/p)==digest for p,digest in result['output_hashes'].items())
    assert str(tmp_path) not in (tmp_path/data.MANIFEST).read_text()
    json.loads((tmp_path/data.MANIFEST).read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
