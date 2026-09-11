"""Stage-13 regression tests: synthetic fixtures only; external network forbidden."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point, Polygon, MultiLineString
from shapely.strtree import STRtree

from src.spatial.robustness import (build_weight, row_standardize, weight_configurations, distance_band_limits,
    network_summary, classify_robustness, stable_local_patterns, calculate_robustness)
from src.spatial.distances import calculate_distance_matrix
from src.spatial.autocorrelation import GLOBAL_VARIABLES
from src.spatial.coastline import validate_components, detect_crs, validate_geometries, load_coastline, station_distances, include_official_coast, repair_projected_line
from src.spatial.coastal_analysis import (METRICS, classify_coastal, compare_groups, fdr_comparisons,
    coastal_comparisons, threshold_consistency, continuous_associations, select_main_threshold, multivariable_models)
from src.spatial.robustness_audit import sha256, check_snapshot
from src.spatial.robustness_visualization import heatmap_input


@pytest.fixture(autouse=True)
def no_network():
    """Block requests for every new test, including imports and UI tests."""
    with patch('requests.sessions.Session.request',side_effect=AssertionError('Network forbidden')):
        yield


@pytest.fixture
def data():
    """Deterministic small station sample, never saved as observations."""
    rng=np.random.default_rng(52)
    frame=pd.DataFrame({'station_id':[str(i) for i in range(12)],'station_name':[f'S{i}' for i in range(12)],
                        'region_level1':['R1']*6+['R2']*6,'latitude':rng.uniform(34,38,12),
                        'longitude':rng.uniform(126,129,12),'elevation_m':rng.uniform(0,400,12),
                        'distance_to_coast_km':np.arange(12)*8.})
    for key in set(GLOBAL_VARIABLES)|set(METRICS):
        frame[key]=rng.normal(size=12)
    return frame


@pytest.fixture
def config():
    """Fast permutations in unit tests; actual CLI retains 999."""
    return {'knn_values':[3,4,5,6],'distance_band_multipliers':[1.,1.1,1.25],
            'inverse_distance_powers':[1,2],'moran_permutations':19,'local_moran_permutations':19,
            'random_seed':15,'alpha':.05,'robust_fraction':.75,'coastal_thresholds_km':[20,30,50],
            'preferred_main_threshold_km':30,'minimum_group_n':2}


def test_archive_checksum(tmp_path):
    """Byte changes change checksum."""
    p=tmp_path/'archive.zip'; p.write_bytes(b'a'); a=sha256(p); p.write_bytes(b'b')
    assert a!=sha256(p) and len(a)==64


@pytest.mark.parametrize('extension',['.shp','.shx','.dbf','.prj'])
def test_component_missing(tmp_path,extension):
    """Every required shapefile sidecar is mandatory."""
    for e in {'.shp','.shx','.dbf','.prj'}-{extension}: (tmp_path/f'coast{e}').touch()
    with pytest.raises(ValueError): validate_components(tmp_path/'coast.shp')


def test_crs_detection(tmp_path):
    """CRS comes from PRJ, not a guessed coordinate range."""
    p=tmp_path/'coast.prj'; p.write_text(CRS.from_epsg(5186).to_wkt())
    assert detect_crs(p).to_epsg()==5186


@pytest.mark.parametrize('geometry',[None,LineString(),Point(0,0),Polygon([(0,0),(1,0),(0,1)]),LineString([(0,0),(0,0)])])
def test_bad_geometry(geometry):
    """Reject empty/invalid/non-coastal geometry."""
    with pytest.raises(ValueError): validate_geometries([geometry])


def test_valid_geometry_duplicate_count():
    """Duplicate lines are counted explicitly."""
    g=LineString([(0,0),(1,1)])
    assert validate_geometries([g,g])['duplicate_geometry_count']==1


def test_repair_redundant_collapsed_fragment():
    """Repair only a zero-length component already on another line; no distance change."""
    geometry=MultiLineString([[(0,0),(0,0)],[(0,0),(1,1)]])
    repaired=repair_projected_line(geometry)
    assert repaired.is_valid and repaired.distance(Point(3,4))==geometry.distance(Point(3,4))
    with pytest.raises(ValueError):
        repair_projected_line(MultiLineString([[(2,2),(2,2)],[(0,0),(1,1)]]))


@pytest.mark.parametrize('code,status,expected',[(1,'Y',True),(2,'Y',True),(3,'N',False),(4,'N',False),(1,'N',False)])
def test_official_coast_selection(code,status,expected):
    """Only official statistical natural/artificial coastline; no bridge/river endpoint."""
    assert include_official_coast({'GRP_CON':code,'GRP_STA':status}) is expected


def test_station_to_line_distance(data):
    """Analytic projected point-line distance; not degree distance."""
    point=Transformer.from_crs(4326,5179,always_xy=True).transform(data.longitude[0],data.latitude[0])
    g=LineString([(point[0]+3000,point[1]-1000),(point[0]+3000,point[1]+1000)])
    coast={'analysis_crs':'EPSG:5179','geometries':[g],'tree':STRtree([g]),'source_name':'test','reference_year':2025}
    result=station_distances(data.iloc[:1],coast)
    assert result.distance_to_coast_km.iloc[0]==pytest.approx(3)
    assert (result.distance_to_coast_km>=0).all()


@pytest.mark.parametrize('threshold',[20,30,50])
def test_coastal_threshold(threshold):
    """Coastal includes the exact threshold."""
    result=classify_coastal(pd.Series([0,threshold,threshold+.01]),threshold)
    assert list(result)==['Coastal','Coastal','Inland']


@pytest.mark.parametrize('value',[-1,np.nan,np.inf])
def test_invalid_distance(value):
    """Missing distances are never implicitly inland."""
    with pytest.raises(ValueError): classify_coastal(pd.Series([value]),30)


def test_continuous_association(data):
    """Known perfectly increasing relation gives r=rho=1."""
    data['kma_tavg_sen_slope']=data.distance_to_coast_km*2
    r=continuous_associations(data).set_index('variable').loc['kma_tavg_sen_slope']
    assert r.pearson_r==pytest.approx(1) and r.spearman_rho==pytest.approx(1)
    assert r.regression_slope==pytest.approx(2)


def test_mann_whitney_effect_size():
    """Completely ordered groups have positive/negative rank-biserial ±1."""
    r=compare_groups(np.arange(10,20),np.arange(10))
    assert r['rank_biserial']==1 and r['raw_p']<.01
    assert compare_groups(np.arange(10),np.arange(10,20))['rank_biserial']==-1


def test_coastal_summary_sensitivity(data):
    """Three thresholds × nine metrics with valid counts and finite effect sizes."""
    result=threshold_consistency(coastal_comparisons(data,[20,30,50],.05))
    assert len(result)==27
    assert ((result.coastal_n+result.inland_n)==len(data)).all()
    assert result.rank_biserial.between(-1,1).all()
    assert result.fdr_q.between(0,1).all()
    assert result.threshold_interpretation.notna().all()


def test_fdr_known():
    """BH matches a simple known family and does not mix thresholds."""
    frame=pd.DataFrame({'threshold_km':[20]*3+[30]*3,'raw_p':[.01,.04,.2,.01,.04,.2]})
    result=fdr_comparisons(frame)
    np.testing.assert_allclose(result.fdr_q,[.03,.06,.2]*2)


def test_select_main_independent_of_outcome(data,config):
    """Main threshold uses n only, no p or climate metric."""
    frames=[]
    for threshold in [20,30,50]:
        frames.append(pd.DataFrame({'threshold_km':threshold,'coastal_group':classify_coastal(data.distance_to_coast_km,threshold)}))
    assert select_main_threshold(pd.concat(frames),config)==30


def test_multivariable(data):
    """Prespecified models retain all three predictors and CI."""
    result=multivariable_models(data)
    assert len(result)==12 and (result.ci_lower<=result.ci_upper).all()


@pytest.mark.parametrize('family',['directed_knn','symmetric_knn','distance_band','inverse_distance'])
def test_weight_families(data,family):
    """Finite, row standardized, no-isolate weights for each family."""
    d=calculate_distance_matrix(data); _,connected=distance_band_limits(d)
    setting={'weight_family':family,'k':4,'distance_threshold_km':connected*1.01,'inverse_distance_power':2}
    w=build_weight(d,setting); net=network_summary(w,setting)
    np.testing.assert_allclose(w.matrix.sum(axis=1),1)
    assert net['isolates']==0 and net['finite_weights']
    if family=='symmetric_knn': assert np.array_equal(w.matrix>0,w.matrix.T>0)
    if family=='directed_knn': assert (np.count_nonzero(w.matrix,axis=1)==4).all()
    if family=='distance_band': assert net['weak_components']==1
    if family=='inverse_distance': assert (np.count_nonzero(w.matrix,axis=1)==11).all()


def test_no_isolate_not_same_as_connected():
    """Two separated pairs: no isolates at 1 km, connectivity requires 9 km."""
    d=pd.DataFrame([[0,1,10,11],[1,0,9,10],[10,9,0,1],[11,10,1,0]],index=list('abcd'),columns=list('abcd'))
    assert distance_band_limits(d)==(1.,9.)
    w=build_weight(d,{'weight_family':'distance_band','distance_threshold_km':1})
    assert network_summary(w,{})['weak_components']==2


def test_row_normalization_rejects_isolates():
    """Do not conceal isolate by divide-by-zero fill."""
    with pytest.raises(ValueError): row_standardize(np.zeros((3,3)))


def test_configurations(data,config):
    """Thirteen distinct settings including baseline."""
    settings=weight_configurations(calculate_distance_matrix(data),config)
    assert len(settings)==13 and len({s['weight_variant'] for s in settings})==13


@pytest.mark.parametrize('values,p,expected',[([.2]*4,[.01]*3+[.2],'ROBUST_POSITIVE'),([.2]*4,[.2]*4,'ROBUST_NON_SIGNIFICANT'),([.2]*4,[.01,.01,.2,.2],'WEIGHT_SENSITIVE'),([.2,-.1],[.01,.3],'INCONSISTENT_DIRECTION')])
def test_robustness_rules(values,p,expected):
    """Operational threshold and sign priority are explicit."""
    assert classify_robustness(pd.DataFrame({'moran_i':values,'permutation_p':p}))==expected


def test_moran_reproducibility_all_metrics(data,config):
    """Bias/RMSE/33/25 included; global and local exact rerun equality."""
    d=calculate_distance_matrix(data)
    a=calculate_robustness(data,d,config); b=calculate_robustness(data,d,config)
    for key in a: pd.testing.assert_frame_equal(a[key],b[key])
    assert set(a['weights'].variable)==set(GLOBAL_VARIABLES)
    assert a['weights'].permutation_p.between(0,1).all()
    assert a['local'].local_fdr_q.between(0,1).all()
    values,p=heatmap_input(a['weights']); assert values.shape==p.shape==(8,13)


def test_stable_cluster_requires_all():
    """One significant variant is not stable."""
    frame=pd.DataFrame({'station_id':['a','a','b','b'],'weight_variant':['x','y']*2,
                        'local_significant_fdr':[True,True,True,False], 'cluster_type_fdr':['Low-High']*3+['Not Significant']})
    stable=stable_local_patterns(frame)
    assert stable['a'] and not stable['b']


def test_coastal_unavailable(tmp_path):
    """No file/network fallback cannot silently invent coastline."""
    assert load_coastline('EPSG:5179',tmp_path)['available'] is False


def test_previous_artifact_audit(tmp_path):
    """Detect content and mtime changes independently."""
    p=tmp_path/'raw.csv'; p.write_text('original')
    before={'raw.csv':{'sha256':sha256(p),'mtime_ns':p.stat().st_mtime_ns}}
    assert check_snapshot(tmp_path,before)==[]
    p.write_text('changed'); assert check_snapshot(tmp_path,before)==['raw.csv']


def test_dashboard_empty_loader(tmp_path):
    """No outputs should render empty state, without exceptions."""
    from dashboard.robustness_loader import load_robustness_manifest,load_robustness_table
    assert load_robustness_manifest(tmp_path)=={}
    assert load_robustness_table('summary',tmp_path).empty


def test_dry_run_no_nasa_kma_api():
    """Production dry-run uses saved CSVs, generates no artifacts, retains permutation count."""
    from src.spatial.robustness_workflow import run_robustness
    with patch('src.spatial.robustness_workflow.snapshot',side_effect=AssertionError('dry run should not write')):
        plan=run_robustness(dry_run=True)
    assert plan['NASA_API_calls']==plan['KMA_API_calls']==0
    assert plan['config']['moran_permutations']>=999
    assert len(plan['input_hashes'])>=17


def test_report_and_manifest_without_coast(data,config,tmp_path,monkeypatch):
    """Unavailable coastal state still produces complete deterministic report and manifest."""
    import src.spatial.robustness_workflow as workflow
    import src.spatial.robustness_reporting as reporting
    import src.spatial.coastline as coastline
    import src.spatial.robustness_visualization as visualization
    monkeypatch.setattr(workflow,'PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(reporting,'PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(workflow,'MANIFEST_PATH',tmp_path/'output/manifests/spatial_robustness_manifest.json')
    monkeypatch.setattr(workflow,'load_inputs',lambda:(data,config,{}))
    monkeypatch.setattr(coastline,'load_coastline',lambda crs:{'available':False,'reason':'fixture no official geometry'})
    monkeypatch.setattr(visualization,'create_charts',lambda *args:[])
    config['analysis_crs']='EPSG:5179'
    (tmp_path/'VERSION').write_text('1.0.0')
    result=workflow.run_robustness()
    assert result['coastline']['available'] is False and result['protected_files_changed']==[]
    assert len(result['generated_tables'])==6 and len(result['generated_reports'])==2
    before={name:sha256(tmp_path/name) for name in result['generated_reports']}
    workflow.report_from_saved()
    assert before=={name:sha256(tmp_path/name) for name in before}
    text=(tmp_path/result['generated_reports'][0]).read_text()
    assert 'Coastal/Inland 분석을 표시할 수 없습니다' in text
    assert json.loads(workflow.MANIFEST_PATH.read_text())['station_count']==12


def test_dashboard_unavailable_renders(data,config,monkeypatch):
    """Coastal warning must not hide Global/Local robustness UI."""
    from streamlit.testing.v1 import AppTest
    import dashboard.pages.spatial_robustness_coastal as page
    tables=calculate_robustness(data,calculate_distance_matrix(data),config)
    monkeypatch.setattr(page,'load_robustness_manifest',lambda:{'coastline':{'available':False}})
    monkeypatch.setattr(page,'load_robustness_table',lambda key:tables.get(key,pd.DataFrame()))
    app=AppTest.from_string('from dashboard.pages.spatial_robustness_coastal import render\nrender()').run(timeout=30)
    assert not app.exception
    assert any('geometry' in w.value for w in app.warning)
    assert len(app.dataframe)>=3


def test_dashboard_loader_mtime(tmp_path):
    """New data invalidate a prior cached CSV load."""
    from dashboard.robustness_loader import load_robustness_table
    table=tmp_path/'result.csv'; table.write_text('station_id,value\n1,2\n')
    folder=tmp_path/'output/manifests'; folder.mkdir(parents=True)
    (folder/'spatial_robustness_manifest.json').write_text(json.dumps({'generated_tables':{'summary':'result.csv'}}))
    assert load_robustness_table('summary',tmp_path).value.iloc[0]==2
    table.write_text('station_id,value\n1,99\n')
    assert load_robustness_table('summary',tmp_path).value.iloc[0]==99


def test_stage12_page_station_id_regression():
    """Original Stage-12 seasonal join supports numeric IDs from persisted CSVs."""
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('from dashboard.pages.nationwide_spatial_patterns import render\nrender()').run(timeout=30)
    assert not app.exception
