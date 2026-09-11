"""Stage18 offline synthetic tests; synthetic observations exist only in test fixtures/tmp paths."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from src.period_sensitivity import data,analysis,spatial,workflow,artifacts
from src.nationwide.tier_a_pipeline import _atomic_csv,_atomic_json
from src.spatial.robustness_audit import sha256,check_snapshot


@pytest.fixture(autouse=True)
def no_http():
    """New tests cannot call NASA, KMA or any requests endpoint."""
    with patch('requests.sessions.Session.request',side_effect=AssertionError('Stage18 forbids HTTP')):
        yield


@pytest.fixture
def config():
    """Production configuration, with no file modification."""
    return data.load_config()


@pytest.fixture(scope='module')
def station():
    """One explicitly hypothetical station matching the established metadata interface."""
    return pd.Series(dict(station_id='TEST',station_name='Synthetic',region_level1='Test',region_level2='Test',
        latitude=37.,longitude=127.,elevation_m=100.,temperature_missing_rate=0.,annual_completeness=1.,
        continuity_risk='low',cohort_origin='TIER_A',distance_to_coast_km=35.,nasa_grid_id='test_grid',
        nasa_grid_latitude=37.,nasa_grid_longitude=126.875,nasa_grid_group_size=1,nasa_grid_shared=False))


@pytest.fixture(scope='module')
def daily():
    """Synthetic daily series with known annual trend; never written to project observations."""
    dates=pd.date_range('1981-01-01','2025-12-31'); base=10+(dates.year-1981)*.1
    frame=pd.DataFrame({'date':dates,'station_id':'TEST','station_name':'Synthetic'})
    for col,offset in [('kma_T2M',0),('kma_TMAX',5),('kma_TMIN',-5),('nasa_T2M',1),('nasa_T2M_MAX',6),('nasa_T2M_MIN',-4)]:
        frame[col]=base+offset
    return frame


@pytest.fixture(scope='module')
def products(daily,station):
    """A complete one-station production-math window, used by independent numeric assertions."""
    window=data.windows(data.load_config()).iloc[0].to_dict()
    item=data.prepared_station(daily,station,Path('/private/tmp/stage18-test-unused.csv'))
    return analysis.analyze_window([item],station.to_frame().T,window,.05)


@pytest.mark.parametrize('year,days,length',[(1981,16436,45),(1986,14610,40),(1991,12784,35),(1996,10958,30),(2001,9131,25)])
def test_windows_calendar(config,year,days,length):
    """Inclusive lengths and leap days match independent known calendars."""
    w=data.windows(config).set_index('start_year').loc[year]
    assert w.expected_days==days and w.window_years==length and w.end_date=='2025-12-31'


@pytest.mark.parametrize('year',[1981,1986,1991,1996,2001])
def test_subsets_preserve_calendar_nan(daily,config,year):
    """Subset never shifts dates or substitutes missing observations."""
    f=daily.copy(); f.loc[f.date.eq(f'{year}-02-01'),'kma_T2M']=np.nan
    w=data.windows(config).set_index('start_year',drop=False).loc[year].to_dict()
    result=data.subset_window(f,w)
    assert len(result)==w['expected_days'] and result.kma_T2M.isna().sum()==1
    assert result.date.iloc[0]==pd.Timestamp(w['start_date'])


@pytest.mark.parametrize('corruption',['duplicate','missing','reordered','foreign'])
def test_calendar_rejects(daily,corruption):
    """Duplicate/missing/reordered calendars and foreign IDs cannot silently pass."""
    f=daily.copy()
    if corruption=='duplicate': f=pd.concat([f,f.iloc[:1]])
    elif corruption=='missing': f=f.iloc[1:]
    elif corruption=='reordered': f=f.iloc[::-1]
    else: f.loc[0,'station_id']='WRONG'
    with pytest.raises(ValueError): data.validate_calendar(f,'TEST','1981-01-01','2025-12-31')


def test_minimum_window(config):
    """Shorter-than-prespecified windows fail before any computation."""
    with pytest.raises(ValueError): data.windows({**config,'start_years':[2002]})


@pytest.mark.parametrize('field,value',[('start_years',[1981,1991]),('end_year',2024),('minimum_window_years',20)])
def test_config_rejects_changes(tmp_path,config,field,value):
    """Prespecified window design cannot drift silently."""
    _atomic_json({**config,field:value},tmp_path/data.CONFIG_PATH)
    with pytest.raises(ValueError): data.load_config(tmp_path)


def test_quality_missing_retained(daily,config):
    """Actual missing temperature remains counted, with independent source validity."""
    f=daily.copy(); f.loc[0,'kma_T2M']=np.nan
    q,a=data.quality_by_window(f,data.windows(config).iloc[0].to_dict())
    assert q.set_index('source').loc['KMA','tavg_missing']==1
    assert q.set_index('source').loc['NASA','tavg_missing']==0
    assert q.data_quality_flag.eq('PASS').all() and len(a)==90


def test_quality_long_gap_review(daily,config):
    """A long missing interval flags review rather than silently reducing the fixed station set."""
    f=daily.copy(); f.loc[:100,'kma_T2M']=np.nan
    q,_=data.quality_by_window(f,data.windows(config).iloc[0].to_dict())
    assert q.loc[q.source.eq('KMA'),'data_quality_flag'].iloc[0]=='REVIEW_REQUIRED'


@pytest.mark.parametrize('source,metric',[(s,m) for s in ('KMA','NASA') for m in ('TAVG','TMAX','TMIN')])
def test_known_annual_trend(products,source,metric):
    """OLS and Sen recover the known 1°C/decade synthetic annual trend in all six series."""
    row=products['temperature_trends'].set_index(['source','metric']).loc[(source,metric)]
    assert row.sen_slope_per_decade==pytest.approx(1.)
    assert row.linear_slope_per_decade==pytest.approx(1.)
    assert row.n_years==45 and row.fdr_family_n==1 and row.significant_fdr


def test_season_boundary(products):
    """DJF is one year shorter; incomplete first/last DJF is not mixed into a partial season."""
    a=products['seasonal_annual']; djf=a.loc[a.season.eq('DJF')]
    assert djf.season_year.min()==1982 and djf.season_year.max()==2025
    assert products['seasonal_trends'].loc[lambda d:d.season.eq('DJF'),'n_years'].eq(44).all()
    assert products['seasonal_trends'].metric.eq('TAVG').all()


def test_dtr_fresh_fit(products):
    """Constant annual DTR has zero fitted trend, separate from the contrast calculation."""
    assert np.allclose(products['dtr_trends'].sen_slope_per_decade,0)
    assert np.allclose(products['dtr_trends'].mean_dtr,10)
    assert np.allclose(products['tmax_tmin_contrast'].tmin_minus_tmax,0)


@pytest.mark.parametrize('proxy,nasa,kma,threshold',[('TMAX_GE_30','nasa_T2M_MAX','kma_TMAX',30.),('TMAX_GE_33','nasa_T2M_MAX','kma_TMAX',33.),('TMIN_GE_25','nasa_T2M_MIN','kma_TMIN',25.)])
def test_threshold_inclusive_missing(daily,station,proxy,nasa,kma,threshold):
    """Equality counts; unmatched days excluded; all-missing year stays NaN not zero."""
    f=daily.iloc[:3].copy(); f[nasa]=[threshold,threshold,np.nan]; f[kma]=[threshold,threshold-1,threshold]
    item=data.prepared_station(f,station,Path('/private/tmp/unused'))
    row=analysis.threshold_annual([item]).set_index('threshold').loc[proxy]
    assert (row.nasa_count,row.kma_count,row.valid_pair_days)==(2,1,2)
    f[nasa]=np.nan
    row=analysis.threshold_annual([data.prepared_station(f,station,Path('/private/tmp/unused'))]).set_index('threshold').loc[proxy]
    assert pd.isna(row.nasa_count) and pd.isna(row.kma_count) and row.valid_pair_days==0


def test_validation_actual_pair_math(products):
    """Known NASA offset retains exact positive Bias, MAE/RMSE and correlations."""
    v=products['nasa_kma_validation']
    assert np.allclose(v.bias,1) and np.allclose(v.mae,1) and np.allclose(v.rmse,1)
    assert np.allclose(v.pearson_r,1) and v.n_pairs.eq(16436).all()


def test_fdr_families_recomputed():
    """Discard intentionally bogus old q; windows, sources and metrics remain separate families."""
    raw=pd.DataFrame([{'window_id':w,'source':s,'metric':m,'station_id':str(i),'mk_p_value':p,'fdr_q_value':.999}
        for w in ['A','B'] for s in ['KMA','NASA'] for m in ['TAVG','TMIN'] for i,p in enumerate([.01,.03,.2])])
    corrected=analysis.correct_families(raw,['window_id','source','metric'],.05)
    assert corrected.fdr_family.nunique()==8 and corrected.fdr_family_n.eq(3).all()
    assert np.allclose(corrected.fdr_q_value,np.tile([.03,.045,.2],8))


@pytest.mark.parametrize('a,label,changes',[([1,2,3,4,5],'POSITIVE_ALL_WINDOWS',0),([-1,-2,-3,-4,-5],'NEGATIVE_ALL_WINDOWS',0),
    ([1,-1,1,-1,1],'SIGN_SENSITIVE',4),([0,0,0,0,0],'ZERO_ALL_WINDOWS',0),([0,1,1,1,1],'NONNEGATIVE_WITH_ZERO',0),
    ([0,-1,-1,-1,-1],'NONPOSITIVE_WITH_ZERO',0),([1,0,-1,0,1],'SIGN_SENSITIVE',2)])
def test_signs(a,label,changes):
    """Zeros cannot be silently relabeled as strictly positive or as opposite-sign observations."""
    result=analysis.sign_summary(a)
    assert result['direction_stability']==label and result['sign_change_count']==changes


@pytest.mark.parametrize('n,label',[(0,'NEVER_SIGNIFICANT'),(1,'SOME_WINDOWS_SIGNIFICANT'),(2,'SOME_WINDOWS_SIGNIFICANT'),(3,'MOST_WINDOWS_SIGNIFICANT'),(4,'MOST_WINDOWS_SIGNIFICANT'),(5,'SIGNIFICANT_ALL_WINDOWS')])
def test_significance_categories(n,label):
    """Discovery counts have the specified descriptive five-window categories."""
    assert analysis.significance_class(n,5)==label


def test_stability_differences():
    """Absolute range and both requested reference differences use ordered window starts."""
    f=pd.DataFrame({'station_id':'A','start_year':[2001,1996,1991,1986,1981],
        'sen_slope_per_decade':[5,4,3,2,1],'significant_fdr':[True]*5,'sen_ci_lower':[.1]*5,'sen_ci_upper':[6]*5})
    r=analysis.stability(f,['station_id']).iloc[0]
    assert r.slope_range==4 and r.difference_1991_minus_1981==2 and r.difference_2001_minus_1981==4
    assert r.fdr_significant_window_count==5 and r.ci_excludes_zero_count==5


@pytest.mark.parametrize('a',[[1,np.nan,2],[1,np.inf,2],[]])
def test_invalid_stability(a):
    """Unavailable estimates cannot be silently dropped when computing period stability."""
    with pytest.raises(ValueError): analysis.sign_summary(a)


def test_missing_window_stability():
    """A station with fewer windows does not receive a misleading stability label."""
    with pytest.raises(ValueError): analysis.stability(pd.DataFrame({'station_id':['A'],'start_year':[1981],'sen_slope_per_decade':[1]}),['station_id'])


def test_dominant_season_tie():
    """Equal seasonal slopes resolve by fixed chronological season order, not significance."""
    f=pd.DataFrame([dict(station_id='A',source='KMA',start_year=y,season=s,sen_slope_per_decade=1.) for y in [1981,1986,1991,1996,2001] for s in analysis.SEASONS])
    r=analysis.dominant_seasons(f).iloc[0]
    assert r.most_common_season=='DJF' and r.most_common_window_count==5


@pytest.mark.parametrize('a,p,label',[([.3]*5,[.01]*5,'SPATIALLY_STABLE_POSITIVE'),([.03]*5,[.5]*5,'ROBUST_NON_SIGNIFICANT'),
    ([.3]*5,[.01,.01,.1,.01,.01],'PERIOD_SENSITIVE'),([-.1,.1,.1,.1,.1],[.1]*5,'DIRECTION_SENSITIVE'),
    ([.1,.2,.3,.4,.5],[.01]*5,'PERIOD_SENSITIVE')])
def test_period_class(config,a,p,label):
    """Period rules are sign-first and never hide mixed significance within overlapping windows."""
    assert spatial.period_class(a,p,config)==label


def test_moran_transitions_both_directions(config):
    """Adjacent transitions retain both significant-to-nonsignificant and the reverse."""
    f=pd.DataFrame({'source':'KMA','representation':'STATION_LINKED','variable':'tavg','weight_variant':'K4',
        'start_year':[1981,1986,1991,1996,2001],'Moran_I':[.1]*5,'permutation_p':[.01,.2,.01,.01,.2]})
    traj,trans=spatial.trajectories(f,config)
    assert len(trans)==4 and trans.significance_changed.sum()==3
    assert 'NON_SIGNIFICANT_TO_SIGNIFICANT' in set(trans.transition)
    assert traj.significant_window_count.iloc[0]==3


def test_grid_equality_and_mismatch(daily,station,config):
    """Shared grids require all three full daily series to be equal including missing positions."""
    stations=pd.DataFrame([station,station.copy()]); stations.loc[1,'station_id']='B'
    frames={'TEST':daily,'B':daily.copy()}
    w=data.windows(config).iloc[0].to_dict()
    assert data.verify_grid_equality(stations,frames,w).station_count.iloc[0]==2
    frames['B'].loc[0,'nasa_T2M_MAX']+=.1
    with pytest.raises(ValueError): data.verify_grid_equality(stations,frames,w)


def test_distribution_unweighted():
    """National summary is a station distribution, preserving increases and decreases."""
    f=pd.DataFrame({'source':'KMA','sen_slope_per_decade':[-1,1,2,4],'significant_fdr':[True,False,True,True]})
    r=analysis.distribution_summary(f,['source']).iloc[0]
    assert r['median']==1.5 and r.fdr_increasing_count==2 and r.fdr_decreasing_count==1


def test_validation_ranges(products):
    """Bias/MAE/RMSE/correlation ranges are separate, never collapsed into a composite score."""
    v=pd.concat([products['nasa_kma_validation'].assign(start_year=y,bias=y-1981) for y in [1981,1986,1991,1996,2001]])
    r=analysis.validation_stability(v)
    assert r.bias_range.eq(20).all() and r.rmse_range.eq(0).all()


def test_trend_consistency(products):
    """Known equal positive NASA/KMA slopes have full direction and discovery agreement."""
    r=analysis.trend_consistency(products['temperature_trends'])
    assert r.same_direction.all() and r.both_positive.all() and r.both_significant.all()


def test_window_comparison_no_refit(products):
    """A/B comparisons subtract saved results and do not call statistical fitting."""
    t={key:pd.concat([products[key].assign(start_year=y) for y in (1981,2001)]) for key in ('temperature_trends','nasa_kma_validation')}
    t['global_morans_i']=pd.DataFrame({'start_year':[1981,2001],'source':'KMA','representation':'STATION_LINKED',
        'variable':'TAVG','weight_variant':'K4','Moran_I':[.1,.3],'permutation_p':[.1,.01]})
    with patch('src.statistical_analysis.analyze_trend_series',side_effect=AssertionError('no refit')):
        r=artifacts.compare_windows(t,1981,2001)
    assert r['global_morans_i'].Moran_I_B_minus_A.iloc[0]==pytest.approx(.2)
    assert not r['temperature_trends'].FDR_status_changed.any()


def test_plotly_global_template_independent(products):
    """Streamlit importing a global Plotly template cannot alter deterministic HTML content."""
    import plotly.io as pio
    original=pio.templates.default
    try:
        pio.templates.default='plotly_dark'; a=artifacts.trajectory_figure(products['temperature_trends']).to_json()
        pio.templates.default='plotly_white'; b=artifacts.trajectory_figure(products['temperature_trends']).to_json()
    finally: pio.templates.default=original
    assert a==b


def test_loader_pending(tmp_path):
    """A partially generated run never serves stale tables as current results."""
    _atomic_json({'status':'pending'},tmp_path/data.MANIFEST)
    with pytest.raises(ValueError): artifacts.load_tables(tmp_path)


def test_loader_tampering(tmp_path):
    """Checksum corruption fails closed before any report/dashboard rendering."""
    path=tmp_path/data.TABLE_DIR/'period_sensitivity_station_master.csv'
    _atomic_csv(pd.DataFrame({'station_id':['TEST']}),path)
    _atomic_json({'status':'completed','table_names':['station_master'],
        'output_hashes':{path.relative_to(tmp_path).as_posix():'wrong'}},tmp_path/data.MANIFEST)
    with pytest.raises(ValueError): artifacts.load_tables(tmp_path)


def test_prior_protection(tmp_path):
    """New namespace is excluded but raw, old output and VERSION are immutable protected inputs."""
    for folder in ['data/raw','output/tables','data/period_sensitivity','output/charts/period_sensitivity']:
        (tmp_path/folder).mkdir(parents=True)
    _atomic_json({'version':'test'},tmp_path/'VERSION')
    _atomic_csv(pd.DataFrame({'x':[1]}),tmp_path/'data/raw/test.csv')
    before=data.snapshot(tmp_path)
    _atomic_csv(pd.DataFrame({'x':[2]}),tmp_path/'data/period_sensitivity/test.csv')
    assert not check_snapshot(tmp_path,before) and len(before)==2


def test_cli_flags():
    """Both requested entry points remain separate from old modes."""
    import main
    with patch('sys.argv',['main.py','--analyze-period-sensitivity','--dry-run']):
        args=main.parse_args()
    assert args.analyze_period_sensitivity and args.dry_run
    with patch('sys.argv',['main.py','--report-period-sensitivity']):
        assert main.parse_args().report_period_sensitivity


def test_dry_run_no_writes(tmp_path):
    """Orchestration returns the checked plan before manifest/output writes or fits."""
    plan={'status':'dry_run','station_count':3}
    with patch.object(workflow,'prepare_plan',return_value=(None,)*9+(plan,)),patch.object(workflow,'_atomic_json',side_effect=AssertionError('no write')):
        assert workflow.run_analysis(tmp_path,dry_run=True)==plan


def test_static_inventory():
    """Every requested scientific PNG and nine representative-window maps has a distinct name."""
    assert len(artifacts.PNGS)==len(set(artifacts.PNGS))==15
    assert len(artifacts.MAPS)==9
    assert {int(x.split('_start_')[1][:4]) for x in artifacts.MAPS}=={1981,1991,2001}


@pytest.fixture
def spatial_fixture(station):
    """Twelve hypothetical stations in six shared cells; no project observation files involved."""
    frame=pd.DataFrame([station.to_dict() for _ in range(12)])
    frame['station_id']=[str(900+i) for i in range(12)]
    frame['latitude']=np.linspace(34,38,12); frame['longitude']=126+np.sin(np.arange(12))*.4
    frame['nasa_grid_id']=[f'grid{i//2}' for i in range(12)]
    frame['nasa_grid_latitude']=34+np.arange(12)//2*.5
    frame['nasa_grid_longitude']=126+(np.arange(12)//2%2)*.625
    frame['distance_to_coast_km']=np.arange(12)*8.
    rng=np.random.default_rng(18)
    for variable in spatial.VARIABLES: frame[variable]=rng.normal(.3,.1,12)
    frame['nasa_tavg_sen_slope']=np.repeat(rng.normal(.3,.1,6),2)
    return frame


@pytest.mark.parametrize('weight',['directed_knn_k4','directed_knn_k3','directed_knn_k5','symmetric_knn_k4','inverse_distance_p2_row'])
def test_fixed_spatial_geometry(config,spatial_fixture,weight):
    """Every specified matrix is normalized with fixed IDs and unique native grid units."""
    sn,gn,summary=spatial.networks(spatial_fixture,config)
    for net,n in [(sn,12),(gn,6)]:
        matrix=net[weight][0].matrix
        assert matrix.shape==(n,n) and np.allclose(matrix.sum(axis=1),1) and not np.diag(matrix).any()
    assert set(sn)==set(gn) and summary.isolates.eq(0).all()


def test_spatial_window_seed_and_coast(config,spatial_fixture):
    """Same window values produce identical I/p; representative windows add 20/50km only."""
    c={**config,'moran_permutations':19}; sn,gn,_=spatial.networks(spatial_fixture,c)
    windows=data.windows(c)
    a=spatial.analyze_spatial(spatial_fixture,sn,gn,c,windows.iloc[0].to_dict())
    b=spatial.analyze_spatial(spatial_fixture,sn,gn,c,windows.iloc[1].to_dict())
    assert np.array_equal(a['global_morans_i'].Moran_I,b['global_morans_i'].Moran_I)
    assert np.array_equal(a['global_morans_i'].permutation_p,b['global_morans_i'].permutation_p)
    assert len(a['global_morans_i'])==55 and len(a['nasa_grid_spatial'])==5
    assert set(a['coastal_inland_comparison'].threshold_km)=={20,30,50}
    assert set(b['coastal_inland_comparison'].threshold_km)=={30}
    assert a['coastal_inland_comparison'].fdr_q.between(0,1).all()
    assert a['coastal_inland_comparison'].groupby('fdr_family').size().eq(9).all()


def test_coastal_stability(config):
    """Coastal group effect changes remain separate from continuous correlation summaries."""
    frame=pd.DataFrame({'variable':'test','start_year':[1981,1986,1991,1996,2001],
        'median_difference':[1,1,-1,-1,1],'fdr_q':[.01,.02,.2,.2,.01]})
    r=spatial.association_stability(frame,'median_difference','fdr_q',['variable'],config['alpha']).iloc[0]
    assert r.sign_change_count==2 and r.significant_window_count==3 and r.period_interpretation=='DIRECTION_SENSITIVE'


@pytest.mark.parametrize('case',['valid','tier_b_overlap','stage16_mismatch','stage17_mismatch'])
def test_fixed_cohort_crosschecks(tmp_path,station,case):
    """Fixed selection comes from saved Final A and is checked against both subsequent origin sets."""
    # The Stage10 selector has no coast/grid columns; those come only from the later spatial master.
    selected=station.to_frame().T.drop(columns=['distance_to_coast_km','nasa_grid_id','nasa_grid_latitude',
                                               'nasa_grid_longitude','nasa_grid_group_size','nasa_grid_shared'])
    for path,frame in [(data.STATION_SOURCE,selected),
        (Path('output/tables/tier_b/tier_b_analysis_stations.csv'),pd.DataFrame({'station_id':['TEST' if case=='tier_b_overlap' else 'B']})),
        (Path('output/tables/nationwide/nationwide_station_temperature_trends.csv'),pd.DataFrame({'station_id':['TEST']})),
        (Path('output/tables/spatial/nationwide_global_morans_i.csv'),pd.DataFrame({'variable':['test']}))]:
        _atomic_csv(frame,tmp_path/path)
    stage17=station.to_frame().T; stage16=selected.copy()
    if case=='stage16_mismatch': stage16['station_id']='OTHER'
    if case=='stage17_mismatch': stage17['station_id']='OTHER'
    with patch.object(data,'load_tier_a_stations',return_value=selected),patch.object(data,'load_stage17',return_value={
        'spatial_station_master':stage17,'spatial_bridge_comparison':pd.DataFrame()}),patch.object(data,'load_stage16',return_value={
        'common_period_temperature_trends':stage16}),patch.object(data,'sha256',return_value='test_hash'):
        if case=='valid':
            s,_,_=data.load_inputs(tmp_path)
            assert set(s.station_id)=={'TEST'} and s.nasa_grid_group_size.eq(1).all()
        else:
            with pytest.raises(ValueError): data.load_inputs(tmp_path)


def test_point_map_period_and_template(spatial_fixture):
    """New point maps replace the reused helper's historical period and global dark template."""
    import plotly.io as pio
    previous=pio.templates.default
    try:
        pio.templates.default='plotly_dark'; a=artifacts.point_map(spatial_fixture,'kma_tavg_sen_slope',2001,(0,1))
        pio.templates.default='plotly_white'; b=artifacts.point_map(spatial_fixture,'kma_tavg_sen_slope',2001,(0,1))
    finally: pio.templates.default=previous
    assert a.to_json()==b.to_json() and '2001–2025' in a.layout.title.text and '1991–2025' not in a.layout.title.text


def test_station_national_threshold_summary(products,station,config):
    """Five synthetic identical windows yield zero ranges and preserve all station/metric families."""
    tables={key:pd.concat([analysis.tag(frame,w) for w in data.windows(config).to_dict('records')],ignore_index=True)
            for key,frame in products.items()}
    result=analysis.summarize(tables,station.to_frame().T)
    assert len(result['trend_stability'])==6 and result['trend_stability'].slope_range.eq(0).all()
    assert result['national_stability_summary'].n.eq(1).all()
    assert result['station_metric_summary'].range_rank_descending.eq(1).all()
    assert len(result['threshold_stability'])==6 and result['threshold_stability'].slope_range.eq(0).all()


def test_report_rendering_deterministic(tmp_path):
    """Report serializer escapes prose, renders tables, links every artifact and is byte-stable."""
    sections=[(f'{i}. Section','Synthetic <test>',pd.DataFrame({'value':[1.2345]})) for i in range(1,21)]
    tables={'test_table':pd.DataFrame({'value':[1]})}
    with patch.object(artifacts,'report_sections',return_value=sections):
        paths=artifacts.write_reports(tables,tmp_path)
        first={p:sha256(tmp_path/p) for p in paths}
        artifacts.write_reports(tables,tmp_path)
    assert all(sha256(tmp_path/p)==d for p,d in first.items())
    html=(tmp_path/paths[0]).read_text()
    assert 'Synthetic &lt;test&gt;' in html and '<h2>20. Section</h2>' in html
    assert 'period_sensitivity_test_table.csv' in html
