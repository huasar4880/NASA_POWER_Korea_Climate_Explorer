"""Offline Stage14.5 numerical diagnostics, synthetic matrices and immutable sources."""
from __future__ import annotations
import json
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from src.spatial.distances import calculate_distance_matrix
from src.spatial_models.data import OUTCOMES,PREDICTORS,BASE_WEIGHT
from src.spatial_models.models import ordering_hash,fit_ols,coefficient_rows
from src.spatial_numerical.weights import (canonical,matrix_hash,weight_settings,build_matrix,
    spectral_properties,boundary_distance,diagnose_weights)
from src.spatial_numerical.solver import review_fit,numerical_classification,profile_nll,likelihood_profiles
from src.spatial_numerical.review import recommend,interpretation_status,calculate_review
from src.spatial_numerical.data import snapshot
from src.spatial.robustness_audit import check_snapshot,sha256


@pytest.fixture(autouse=True)
def no_api():
    """Never allow NASA, KMA or any other HTTP call."""
    with patch('requests.sessions.Session.request',side_effect=AssertionError('API forbidden')):
        yield


@pytest.fixture(scope='module')
def sample():
    """Synthetic sample for numerical tests only, never mixed with observation products."""
    rng=np.random.default_rng(741);n=24
    frame=pd.DataFrame({'station_id':[str(i) for i in range(n)],'station_name':[f'S{i}' for i in range(n)],
        'latitude':rng.uniform(33,38,n),'longitude':rng.uniform(126,130,n),'elevation_m':rng.uniform(1,400,n),
        'distance_to_coast_km':rng.uniform(1,100,n)})
    noise=rng.normal(0,.2,n)
    for i,outcome in enumerate(OUTCOMES):
        frame[outcome]=.01*frame.distance_to_coast_km+.1*frame.latitude-.001*frame.elevation_m+noise*(1+.1*i)+i
    return canonical(frame)


@pytest.fixture(scope='module')
def config():
    """Fast test permutations; production still inherits Stage13 settings."""
    return {'random_seed':123,'moran_permutations':19}


@pytest.fixture(scope='module')
def inventory(sample):
    """Deterministic fixed nine weight configurations."""
    return diagnose_weights(sample)[0]


@pytest.fixture(scope='module')
def old_frames(sample,config,inventory):
    """Generate isolated synthetic prior-result fixtures with the same model definitions."""
    rows=[]
    with patch('requests.sessions.Session.request',side_effect=AssertionError('API forbidden')):
        for outcome in OUTCOMES:
            for key in [BASE_WEIGHT,'symmetric_knn_k4','distance_band_x1','inverse_distance_p1_row']:
                for family in ['SAR','SEM']:
                    result=review_fit(sample,outcome,family,inventory[key],config)
                    ok=result['library_returned'] and result['finite_result'] and not result['solver_boundary_hit']
                    rows.append(dict(outcome=outcome,model_type=family,weight_type=key.replace('inverse_distance_p1_row','inverse_distance_p1'),
                        specification='main',scale='original',predictor=PREDICTORS[0],converged=ok,
                        rho=result['diagnostic_estimate'] if ok and family=='SAR' else np.nan,
                        **{'lambda':result['diagnostic_estimate'] if ok and family=='SEM' else np.nan},
                        coefficient=.01 if ok else np.nan,p_value=.04 if ok else np.nan))
            fit=fit_ols(sample,outcome,PREDICTORS)
            for hc3 in [False,True]:
                row=coefficient_rows(fit,sample,PREDICTORS,hc3=hc3)[1]
                rows.append({**row,'outcome':outcome,'weight_type':BASE_WEIGHT,'specification':'main'})
    return {'spatial_model_summary':pd.DataFrame(rows)}


@pytest.fixture(scope='module')
def calculated(sample,config,old_frames):
    """Run the real limited review once on synthetic inputs, never APIs."""
    with patch('requests.sessions.Session.request',side_effect=AssertionError('API forbidden')):
        return calculate_review(sample,config,old_frames)[0]


def test_spectral_radius_known():
    """Complete triangle has eigenvalues 1,-1/2,-1/2 and radius one."""
    w=(np.ones((3,3))-np.eye(3))/2
    result,eigen=spectral_properties(w)
    assert result['spectral_radius']==pytest.approx(1)
    np.testing.assert_allclose(np.sort(eigen.real),[-.5,-.5,1])


@pytest.mark.parametrize('family',['SAR','SEM'])
def test_admissible_not_neumann(family):
    """Nonsingularity (-2,1) is wider than the sufficient series interval (-1,1)."""
    w=(np.ones((3,3))-np.eye(3))/2
    result,_=spectral_properties(w)
    assert result['lower_admissible_bound']==pytest.approx(-2)
    assert result['upper_admissible_bound']==pytest.approx(1)
    assert result['neumann_lower']==pytest.approx(-1)
    assert abs(np.linalg.det(np.eye(3)+1.5*w))>0


@pytest.mark.parametrize('name',['directed_knn_k4','symmetric_knn_k4','distance_band_x1',
    'inverse_distance_p1_row','inverse_distance_p2_row','inverse_distance_p1_raw',
    'inverse_distance_p2_raw','inverse_distance_p1_cutoff_row','inverse_distance_p2_cutoff_row'])
def test_weight_spectrum_and_rows(sample,inventory,name):
    """Every fixed configuration is finite, diagonal-zero, isolate-free and ordered."""
    item=inventory[name];w=item['matrix'];raw=item['raw']
    assert np.isfinite(w).all() and np.diag(w).sum()==0 and np.all(w.sum(axis=1)>0)
    result,eigen=spectral_properties(w)
    assert np.isfinite(eigen).all() and result['lower_admissible_bound']<result['upper_admissible_bound']
    if item['setting']['row_standardized']:
        np.testing.assert_allclose(w.sum(axis=1),1)
    else:
        np.testing.assert_array_equal(w,raw)


def test_inverse_distance_formula(sample,inventory):
    """Raw p2 equals squared raw p1, not squared normalized p1."""
    np.testing.assert_allclose(inventory['inverse_distance_p2_raw']['matrix'],inventory['inverse_distance_p1_raw']['matrix']**2)


def test_cutoff_reduces_density(inventory):
    """One cutoff prunes long links, keeps no isolates, and changes normalization."""
    a=inventory['inverse_distance_p1_row']['matrix'];b=inventory['inverse_distance_p1_cutoff_row']['matrix']
    assert np.count_nonzero(b)<np.count_nonzero(a) and (b.sum(axis=1)>0).all()
    assert np.array_equal(b>0,inventory['distance_band_x1']['matrix']>0)


def test_zero_distance_rejected(sample):
    """Distinct colocated stations cannot yield infinite inverse weights."""
    bad=sample.copy();bad.loc[1,['latitude','longitude']]=bad.loc[0,['latitude','longitude']]
    with pytest.raises(ValueError): diagnose_weights(bad)


@pytest.mark.parametrize('value,near,outside',[(0,False,False),(.99,True,False),(1,True,False),(1.1,True,True),(-1.99,True,False)])
def test_boundary_distance(value,near,outside):
    """Signed distances preserve exact/near/outside boundary information."""
    result=boundary_distance(value,-2,1)
    assert result['near_boundary']==near and result['outside_interval']==outside
    assert result['distance_to_lower_bound']==pytest.approx(value+2)


def test_boundary_missing():
    """A failed estimate stays missing, never zero or a bound."""
    assert np.isnan(boundary_distance(np.nan,-2,1)['relative_boundary_distance'])


@pytest.mark.parametrize('returned,finite,success,hit,near,expected',[
    (True,True,True,False,False,'STABLE'),(True,True,True,False,True,'CONVERGED_NEAR_BOUNDARY'),
    (True,True,True,True,False,'NUMERICALLY_UNSTABLE'),(True,False,True,False,False,'NUMERICALLY_UNSTABLE'),
    (False,False,True,True,False,'FAILED')])
def test_numerical_classification(returned,finite,success,hit,near,expected):
    """Native optimizer success alone never overrides a downstream failure/boundary."""
    assert numerical_classification(returned,finite,success,hit,near)==expected


def test_not_supported():
    """An unsafe fixed estimator window is not forced to fit."""
    assert numerical_classification(False,False,False,False,False,supported=False)=='NOT_SUPPORTED'


def test_failure_capture(sample,config,inventory):
    """Library exceptions are structured and accepted estimate remains NaN."""
    with patch('spreg.ML_Lag',side_effect=ValueError('test solver failure')):
        result=review_fit(sample,OUTCOMES[0],'SAR',inventory[BASE_WEIGHT],config)
    assert result['numerical_class']=='FAILED' and np.isnan(result['estimate'])
    assert 'test solver failure' in result['failure_reason']


def test_canonical_order_and_hash(sample):
    """Shuffled station rows reconstruct byte-identical weights and canonical ordering hash."""
    a=canonical(sample);b=canonical(sample.sample(frac=1,random_state=7))
    assert ordering_hash(tuple(a.station_id))==ordering_hash(tuple(b.station_id))
    wa,_=diagnose_weights(a);wb,_=diagnose_weights(b)
    assert all(matrix_hash(wa[k]['matrix'])==matrix_hash(wb[k]['matrix']) for k in wa)


def test_full_review_reproduction(calculated):
    """Every fixed fit has exact same-seed and canonical-order fingerprints."""
    frame=calculated['spatial_model_ordering_reproducibility']
    assert len(frame)==54 and frame[['same_seed_repeat','ordering_invariant','canonical_weight_hash_equal']].all().all()
    assert frame.result_hash.eq(frame.repeated_result_hash).all()


@pytest.mark.parametrize('key',[BASE_WEIGHT,'symmetric_knn_k4','distance_band_x1'])
def test_control_comparison(calculated,key):
    """All control fits are reviewed; genuine boundary cases are flagged, not hidden."""
    frame=calculated['spatial_model_numerical_stability'].query('weight_type == @key')
    assert len(frame)==6 and frame.numerical_class.notna().all()
    assert frame[frame.numerical_class.ne('STABLE')].estimate.isna().all()
    if key==BASE_WEIGHT:
        assert frame.numerical_class.eq('STABLE').all()


def test_no_forced_replacement(calculated):
    """All nonstable accepted estimates remain NaN; diagnostic candidates are separate."""
    f=calculated['spatial_model_numerical_stability']
    assert f[f.numerical_class.ne('STABLE')].estimate.isna().all()
    assert 'diagnostic_estimate' in f


@pytest.mark.parametrize('key,classes,expected',[
    (BASE_WEIGHT,['STABLE']*6,'RECOMMENDED_MAIN'),
    ('inverse_distance_p1_row',['STABLE']*5+['FAILED'],'NOT_RECOMMENDED_NUMERICAL'),
    ('inverse_distance_p2_row',['STABLE']*6,'RECOMMENDED_SENSITIVITY'),
    ('distance_band_x1',['STABLE']*2+['CONVERGED_NEAR_BOUNDARY']*4,'RECOMMENDED_SENSITIVITY')])
def test_recommendation(key,classes,expected):
    """Numerical success cannot automatically promote a new weight to main."""
    assert recommend(pd.DataFrame({'weight_type':[key]*6,'numerical_class':classes}))['recommended_status']==expected


@pytest.mark.parametrize('outcome,expected',list(zip(OUTCOMES,[
    'DIRECTIONALLY_STABLE_HETEROSKEDASTICITY_SENSITIVE',
    'ROBUST_ASSOCIATION_WITH_UNSUPPORTED_INVERSE_DISTANCE_SPECIFICATION','MODEL_SENSITIVE_NOT_UPGRADED'])))
def test_interpretation_hc3(outcome,expected):
    """Interpretation reads supplied old p-values; no new climate calculation."""
    rows=[]
    for y in OUTCOMES:
        for w in [BASE_WEIGHT,'symmetric_knn_k4','distance_band_x1']:
            for m in ['OLS','OLS-HC3','SAR','SEM']:
                p=.01
                if y==OUTCOMES[0] and m=='OLS-HC3':p=.2
                if y==OUTCOMES[2] and m in ['OLS','OLS-HC3','SEM']:p=.2
                rows.append(dict(outcome=y,weight_type=w,model_type=m,coefficient=1.,p_value=p,converged=True,
                    specification='main',scale='original',predictor=PREDICTORS[0]))
    stability=pd.DataFrame({'outcome':OUTCOMES,'weight_type':['inverse_distance_p1_row']*3,'numerical_class':['FAILED']*3})
    result=interpretation_status(pd.DataFrame(rows),stability).set_index('outcome').loc[outcome]
    assert result.interpretation_status==expected and result.primary_ols_inference=='HC3 robust standard errors'
    assert not result.inference_values_recomputed


def test_profile_diagnostic_only(sample,inventory):
    """The fixed profile evaluates likelihood shape, never produces replacement estimates."""
    frame=likelihood_profiles(sample,inventory['inverse_distance_p1_row'])
    assert len(frame)==3*2*81 and frame.diagnostic_only.all() and not frame.accepted_estimate.any()
    assert np.isfinite(frame.negative_log_likelihood).all()


def test_singular_profile():
    """Do not fake a likelihood at the singular upper boundary."""
    w=(np.ones((3,3))-np.eye(3))/2
    assert np.isnan(profile_nll(1,np.array([1.,2.,3.]),np.ones((3,1)),w,'SEM'))


def test_previous_stage14_protected(tmp_path):
    """Unlike Stage14 snapshot, the review MUST protect Stage14 tables/reports/manifest."""
    names=['VERSION','data/geospatial/coastline/a.bin','output/tables/spatial_models/a.csv',
           'output/reports/spatial_models/a.md','output/manifests/spatial_modeling_manifest.json']
    for name in names:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('before')
    before=snapshot(tmp_path)
    assert len(before)==len(names) and not check_snapshot(tmp_path,before)
    (tmp_path/names[2]).write_text('after')
    assert check_snapshot(tmp_path,before)==[names[2]]


def test_loader(tmp_path):
    """Read-only loader confines all reads to the new namespace."""
    from dashboard.numerical_review_loader import load_manifest,load_table
    assert load_manifest(tmp_path)=={} and load_table('x',tmp_path).empty
    path=tmp_path/'output/tables/spatial_models_numerical/x.csv';path.parent.mkdir(parents=True);path.write_text('value\n1\n')
    manifest=tmp_path/'output/manifests/spatial_model_numerical_review_manifest.json';manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'generated_tables':{'x':path.relative_to(tmp_path).as_posix(),'bad':'../bad.csv'}}))
    assert load_table('x',tmp_path).value.iloc[0]==1 and load_table('bad',tmp_path).empty


def test_saved_report_manifest(sample,config,old_frames,calculated,tmp_path):
    """Actual artifact rendering plus report regeneration and manifest integrity."""
    from src.spatial_numerical import workflow
    inventory,_=diagnose_weights(sample)
    (tmp_path/'VERSION').write_text('1.0.0')
    with patch.object(workflow,'load_inputs',return_value=(sample,config,{},old_frames)),patch.object(workflow,'calculate_review',return_value=(calculated,inventory)):
        result=workflow.run_review(root=tmp_path)
    assert result['protected_files_changed']==[] and result['NASA_API_calls']==result['KMA_API_calls']==0
    assert len(result['generated_tables'])==15 and len(result['generated_charts'])==7
    before={name:sha256(tmp_path/name) for name in result['generated_reports']}
    workflow.report_from_saved(tmp_path)
    assert all(sha256(tmp_path/name)==value for name,value in before.items())
    assert '11. Limitations' in (tmp_path/result['generated_reports'][0]).read_text()


def test_dry_run(sample,config,old_frames,tmp_path):
    """Execution plan needs no fit and writes no file."""
    from src.spatial_numerical import workflow
    with patch.object(workflow,'load_inputs',return_value=(sample,config,{},old_frames)),patch.object(workflow,'calculate_review',side_effect=AssertionError('No fit')):
        result=workflow.run_review(True,tmp_path)
    assert result['numerical_model_combinations']==54 and not list(tmp_path.iterdir())
