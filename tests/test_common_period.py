"""Stage16 offline tests; fixtures contain synthetic values only in temporary test storage."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from test_tier_b import station, raw, nasa_raw, item
from src.common_period import data, grid, analysis, artifacts, workflow
from src.tier_b.data import preprocess, quality, calendar
from src.nationwide.tier_a_pipeline import _atomic_csv, _atomic_json
from src.nationwide.tier_a_analysis import calculate_station_annual_temperature
from src.statistical_analysis import analyze_trend_series, apply_fdr_correction


@pytest.fixture
def cohort(station):
    """Two synthetic stations, one per origin, sharing a native grid."""
    a = station.copy(); a['cohort_origin'] = 'TIER_A'; a['distance_to_coast_km'] = 10.
    b = a.copy(); b['station_id'] = '997'; b['station_name'] = 'SYNTHETIC2'; b['cohort_origin'] = 'TIER_B'
    return pd.DataFrame([a, b])


@pytest.fixture
def prepared(item):
    """Prepared synthetic union fixture, preserving both station IDs."""
    return [item, replace(item, station_id='997', station_name='SYNTHETIC2')]


@pytest.fixture
def products(cohort, prepared, tmp_path):
    """Common products from actual pipeline functions with no historical files required."""
    master, mapping = grid.build_grid_mapping(cohort, prepared)
    tables = analysis.build_products(prepared, master, pd.DataFrame({'analysis_review_required': [False, False]}),
                                     mapping, tmp_path, verify_history=False)
    tables['common_period_1991_2025_station_master'] = master
    tables['common_period_data_quality'] = pd.DataFrame({'station_id': ['999'], 'cohort_origin': ['TIER_A'], 'passed': [True]})
    return tables


def selection_sources(root, cohort):
    """Create only the four membership and two coastal inputs consumed by selection."""
    for group, paths in [('TIER_A', data.SELECTION_INPUTS[2:4]), ('TIER_B', data.SELECTION_INPUTS[4:6])]:
        for path in paths:
            _atomic_csv(cohort.loc[cohort.cohort_origin.eq(group)], root/path)
    for group, path in zip(('TIER_A', 'TIER_B'), data.SELECTION_INPUTS[6:]):
        _atomic_csv(cohort.loc[cohort.cohort_origin.eq(group)], root/path)
    _atomic_csv(cohort.assign(eligibility_tier=cohort.cohort_origin.str[-1]), root/data.shared.SHORTLIST)


@pytest.mark.parametrize('origin', ['TIER_A', 'TIER_B'])
def test_selection_union(tmp_path, monkeypatch, cohort, origin):
    selection_sources(tmp_path, cohort)
    monkeypatch.setattr(data, 'load_tier_a_stations', lambda *args: cohort.query('cohort_origin=="TIER_A"').copy())
    monkeypatch.setattr(data.shared, 'load_stations', lambda *args: cohort.query('cohort_origin=="TIER_B"').copy())
    cohort['actual_data_start_date'], cohort['actual_data_end_date'] = '1991-01-01', '2025-12-31'
    result = data.load_stations(tmp_path)
    assert len(result) == 2 and result.cohort_origin.eq(origin).sum() == 1
    assert result.station_id.is_unique and not result.manual_review_required.any()


def test_overlap_rejected(tmp_path, monkeypatch, cohort):
    a = cohort.iloc[:1].copy()
    monkeypatch.setattr(data, 'load_tier_a_stations', lambda *args: a.copy())
    monkeypatch.setattr(data.shared, 'load_stations', lambda *args: a.copy())
    with pytest.raises(ValueError, match='intersection'):
        data.load_stations(tmp_path)


def test_manual_review_selection_failclosed(tmp_path, monkeypatch, cohort):
    selection_sources(tmp_path, cohort)
    monkeypatch.setattr(data, 'load_tier_a_stations', lambda *args: cohort.iloc[:0].copy())
    monkeypatch.setattr(data.shared, 'load_stations', lambda *args: cohort.iloc[1:].copy())
    with pytest.raises(ValueError, match='membership'):
        data.load_stations(tmp_path)


@pytest.mark.parametrize('year,count', [(1991,365),(1992,366),(2000,366),(2024,366),(2025,365)])
def test_common_calendar(year,count):
    assert sum(calendar().year==year)==count
    assert len(calendar())==(data.END-data.START).days+1


@pytest.mark.parametrize('source', ['KMA','NASA'])
def test_cache_subset(tmp_path, station, raw, nasa_raw, source):
    station['cohort_origin']='TIER_A'
    frame=raw.copy() if source=='KMA' else nasa_raw.copy()
    earlier=frame.iloc[:1].copy(); earlier['tm' if source=='KMA' else 'DATE']='1981-01-01' if source=='KMA' else '19810101'
    frame=pd.concat([earlier,frame],ignore_index=True)
    path=(tmp_path/'data/nationwide_asos_raw/stations/999/999_asos_daily_1981_2025.csv' if source=='KMA'
          else tmp_path/'data/nationwide_nasa_raw/999_nasa_power_temperature_1981_2025.csv')
    _atomic_csv(frame,path)
    session=Mock()
    result,chosen=data.acquire(station,source,tmp_path,session)
    clean=preprocess(result,station,source)
    assert chosen==path and len(clean)==12784 and clean.date.min().year==1991
    session.get.assert_not_called()


def test_tier_b_cache_reuse(tmp_path, station, nasa_raw):
    station['cohort_origin']='TIER_B'
    path=data.shared.nasa_path(tmp_path,'999'); _atomic_csv(nasa_raw,path)
    before=(path.read_bytes(),path.stat().st_mtime_ns)
    data.acquire(station,'NASA',tmp_path,Mock())
    assert before==(path.read_bytes(),path.stat().st_mtime_ns)


@pytest.mark.parametrize('source', ['KMA','NASA'])
def test_missing_calendar_not_zero(station,raw,nasa_raw,source):
    frame=raw if source=='KMA' else nasa_raw
    result=preprocess(frame.drop(index=4),station,source)
    assert result.iloc[4][list(data.shared.MAPS[source].values())].isna().all()


def test_prepare_matching(tmp_path,monkeypatch,station,raw,nasa_raw):
    station['cohort_origin']='TIER_A'
    paths={s:tmp_path/f'{s}.csv' for s in ['KMA','NASA']}
    monkeypatch.setattr(data,'acquire',lambda st,s,root,session:((raw if s=='KMA' else nasa_raw),paths[s]))
    item,q,annual,cache=data.prepare(station,tmp_path,{'KMA':Mock(),'NASA':Mock()})
    saved=pd.read_csv(item.matched_path)
    assert len(saved)==12784 and saved.cohort_origin.eq('TIER_A').all()
    assert set(data.MATCH_NAMES.values()).issubset(saved)
    assert len(pd.concat(annual))==35*6 and not any(r['common_period_review_required'] for r in q)


def test_quality_recheck(station,raw):
    missing=raw.drop(index=range(90))
    q,annual=quality(missing,preprocess(missing,station,'KMA'),'KMA')
    assert q['analysis_review_required'] and q['longest_temperature_gap_days']==90


@pytest.mark.parametrize('metric', ['TAVG','TMAX','TMIN'])
@pytest.mark.parametrize('source', ['KMA','NASA'])
def test_annual_aggregation(prepared,cohort,metric,source):
    annual=calculate_station_annual_temperature(prepared,cohort)
    frame=annual.loc[annual.source.eq(source)&annual.metric.eq(metric)&annual.station_id.eq('999')]
    assert frame.year.tolist()==list(range(1991,2026))
    assert frame.moving_average_5yr.isna().sum()==4 and frame.moving_average_10yr.isna().sum()==9


def test_tier_a_actual_recalculation(prepared,cohort):
    annual=calculate_station_annual_temperature(prepared,cohort)
    f=annual.query('station_id=="999" and source=="KMA" and metric=="TAVG"')
    slope=analyze_trend_series(f.year,f.annual_mean)['sen_slope_per_decade']
    assert slope==pytest.approx(.4,abs=.002)
    assert slope!=pytest.approx(9.9)  # An old-period fixture value must never be reused.


@pytest.mark.parametrize('field,expected', [('sen_slope_per_decade',1.),('linear_slope_per_decade',1.),('mk_trend','increasing')])
def test_trend_statistics(field,expected):
    result=analyze_trend_series(range(1991,2026),np.arange(35)*.1)
    assert result[field]==(pytest.approx(expected) if isinstance(expected,float) else expected)


def test_common_fdr_rejects_old_merged_q():
    frame=pd.DataFrame({'source':['KMA']*3,'metric':['TAVG']*3,'mk_p_value':[.01,.04,.05], 'fdr_q_value':[.02,.04,.05]})
    with pytest.raises(ValueError,match='union'):
        analysis.verify_common_fdr(frame,['source','metric'])
    corrected=apply_fdr_correction(frame)
    analysis.verify_common_fdr(corrected,['source','metric'])
    assert corrected.fdr_q_value.tolist()==pytest.approx([.03,.05,.05])


@pytest.mark.parametrize('source', ['KMA','NASA'])
def test_common_family_size(products,source):
    frame=products['common_period_temperature_trends']
    assert frame.fdr_family_size.eq(2).all()
    assert frame.fdr_family.str.contains('common-period union').all()
    assert len(frame.loc[frame.source.eq(source)])==6


def test_normal_anomaly(products):
    n=products['common_period_temperature_normals_1991_2020']
    a=products['common_period_temperature_anomalies_1991_2025']
    assert n.n_years.eq(30).all() and n.normal_start_year.eq(1991).all()
    assert np.allclose(a.anomaly,a.annual_mean-a.normal_mean)


def test_seasons(products):
    s=products['common_period_seasonal_temperature_trends']
    assert s.loc[s.season.eq('DJF'),'n_years'].eq(34).all()
    assert len(products['common_period_dominant_warming_season'])==4


@pytest.mark.parametrize('threshold',['TMAX_GE_30','TMAX_GE_33','TMIN_GE_25'])
def test_thresholds(products,threshold):
    t=products['common_period_threshold_annual']
    assert len(t.loc[t.threshold.eq(threshold)])==70
    assert t.valid_pair_days.ge(365).all()


@pytest.mark.parametrize('metric,expected',[('bias',1),('mae',1),('rmse',1),('pearson_r',1),('spearman_rho',1)])
def test_validation(products,metric,expected):
    f=products['common_period_nasa_kma_temperature_validation'].query('metric=="TAVG"')
    assert np.allclose(f[metric],expected) and f.n_pairs.eq(12784).all()


def test_summary_consistency_rankings(products):
    summary=products['common_period_station_temperature_summary']
    assert len(summary)==2 and summary.nasa_grid_group_size.eq(2).all()
    assert products['common_period_nasa_kma_trend_consistency'].same_direction.all()
    ranks=products['common_period_temperature_rankings']
    assert not ranks.is_climate_risk_ranking.any() and 'absolute TAVG Bias' in set(ranks.ranking)


@pytest.mark.parametrize('name',['regional_temperature','elevation','coastal','cohort_origin_comparison'])
def test_descriptive_summaries(products,name):
    key=f'common_period_{name}'+('' if name=='cohort_origin_comparison' else '_summary')
    frame=products[key]
    assert {'n','mean','median','iqr','tier_a_count','tier_b_count'}.issubset(frame)


@pytest.mark.parametrize('lat,lon,expected',[(37.1704,128.9893,(37.,128.75)),(36.9436,128.9145,(37.,128.75)),(37.5714,126.9658,(37.5,126.875))])
def test_grid_coordinate_id(lat,lon,expected):
    point=grid.grid_coordinates(lat,lon)
    assert point==expected and grid.grid_id(*point)==grid.grid_id(*expected)


def test_grid_tie_failclosed():
    with pytest.raises(ValueError,match='tie'):
        grid.grid_coordinates(37.25,127.0)


def test_shared_grid_and_cross_cohort(cohort,prepared):
    master,mapping=grid.build_grid_mapping(cohort,prepared)
    assert len(mapping)==1 and master.nasa_grid_shared.all()
    assert mapping.station_count.sum()==len(cohort) and mapping.grid_series_identical.all()
    assert mapping.cohort_origins.iloc[0]=='TIER_A|TIER_B'


def test_single_grid(cohort,prepared):
    master,mapping=grid.build_grid_mapping(cohort.iloc[:1],prepared[:1])
    assert master.nasa_grid_group_size.eq(1).all() and not master.nasa_grid_shared.any()


def test_series_mismatch(cohort,prepared):
    frame=prepared[1].nasa.copy(); frame.loc[0,'T2M']+=1
    prepared[1]=replace(prepared[1],nasa=frame)
    _,mapping=grid.build_grid_mapping(cohort,prepared)
    assert mapping.grid_mapping_mismatch.all()


def test_unique_grid_and_weighting(products):
    assert len(products['common_period_nasa_unique_grid_summary'])==1
    f=products['common_period_nasa_station_vs_grid_summary']
    assert f.n.tolist()==[2,1] and f['median'].iloc[0]==f['median'].iloc[1]


def test_shared_grid_dashboard_filter(products):
    from dashboard.pages.common_period import filter_summary
    f=products['common_period_station_temperature_summary']
    selections=[f[c].unique() for c in ['cohort_origin','region_level1','station_id','elevation_band','coastal_class']]
    assert len(filter_summary(f,*selections,'공유 grid'))==2
    assert filter_summary(f,*selections,'단독 grid').empty


def test_reports_and_manifest(products,tmp_path):
    files=artifacts.write_reports(products,tmp_path)
    hashes=[data.sha256(tmp_path/p) for p in files]
    artifacts.write_reports(products,tmp_path)
    assert hashes==[data.sha256(tmp_path/p) for p in files]
    assert 'NASA unique grids = 1' in (tmp_path/files[1]).read_text()
    output_hashes={}
    for name,frame in products.items():
        path=tmp_path/data.TABLE_DIR/f'{name}.csv';_atomic_csv(frame,path)
        output_hashes[path.relative_to(tmp_path).as_posix()]=data.sha256(path)
    _atomic_json({'status':'completed','output_hashes':output_hashes},tmp_path/data.MANIFEST)
    assert len(artifacts.load_tables(tmp_path))==len(products)


def test_dry_run_no_api_no_writes(tmp_path,monkeypatch,cohort):
    monkeypatch.setattr(workflow,'load_stations',lambda root:cohort)
    monkeypatch.setattr(data,'valid_cache',lambda *args:True)
    monkeypatch.setattr(data,'cache_path',lambda root,station,source:root/'cached.csv')
    http=Mock(side_effect=AssertionError('HTTP forbidden')); monkeypatch.setattr('requests.sessions.Session.request',http)
    before=list(tmp_path.rglob('*')); plan=workflow.run_analysis(tmp_path,dry_run=True)
    assert plan['expected_NASA_calls']==plan['expected_KMA_calls_upper_bound']==0
    assert before==list(tmp_path.rglob('*')); http.assert_not_called()


def test_previous_stages_protected(tmp_path):
    path=tmp_path/'output/tables/tier_b/old.csv'; _atomic_csv(pd.DataFrame({'x':[1]}),path)
    _atomic_csv(pd.DataFrame({'x':[2]}),tmp_path/data.TABLE_DIR/'new.csv')
    before=data.snapshot(tmp_path)
    assert list(before)==['output/tables/tier_b/old.csv']
    assert workflow.check_snapshot(tmp_path,before)==[]


def test_state_resume(tmp_path):
    for stage in ['processed','matched','analyzed','validated']:
        data.state_update(tmp_path,'999',stage)
        assert json.loads((tmp_path/data.STATE).read_text())['stations']['999']['status']==stage


def test_tier_b_reproduction_and_mismatch(products,tmp_path):
    old_schema={key.replace('common_period_','tier_b_',1):frame for key,frame in products.items()}
    old_schema['tier_b_annual_temperature_1991_2025']=pd.concat([
        products['common_period_kma_annual_temperature'],products['common_period_nasa_annual_temperature']],ignore_index=True)
    for name,frame in old_schema.items():
        if 'station_id' in frame:
            _atomic_csv(frame.loc[frame.station_id.eq('997')],tmp_path/f'output/tables/tier_b/{name}.csv')
    result=analysis.reproduce_tier_b(old_schema,tmp_path)
    assert result.passed.all() and len(result)==8
    path=tmp_path/'output/tables/tier_b/tier_b_temperature_trends.csv'
    altered=pd.read_csv(path); altered.loc[0,'sen_slope_per_decade']+=1; _atomic_csv(altered,path)
    with pytest.raises(ValueError,match='reproduction'):
        analysis.reproduce_tier_b(old_schema,tmp_path)


def test_period_comparison_preparation(products,cohort,tmp_path):
    new=products['common_period_temperature_trends']
    old=new.loc[new.station_id.eq('999') & new.source.eq('KMA'),['station_id','metric']].copy()
    old['kma_sen_slope_per_decade'],old['nasa_sen_slope_per_decade']=9.9,8.8
    _atomic_csv(old,tmp_path/'output/tables/nationwide/nationwide_station_temperature_trends.csv')
    result=analysis.period_comparison(new,cohort,tmp_path)
    assert result.cohort_origin.eq('TIER_A').all() and len(result)==6
    assert np.allclose(result.difference,result.sen_1991_2025-result.sen_1981_2025)


def test_grid_nan_not_zero_fingerprint(prepared):
    frame=prepared[0].nasa.copy(); frame.loc[0,'T2M']=np.nan
    other=frame.copy(); other.loc[0,'T2M']=0
    assert grid.series_fingerprint(frame)!=grid.series_fingerprint(other)
