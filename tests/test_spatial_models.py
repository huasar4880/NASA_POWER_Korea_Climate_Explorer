"""Stage-14 synthetic, offline regressions; never manufacture observation products."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from src.spatial_models.data import OUTCOMES, PREDICTORS, BASE_WEIGHT, build_master, protected_snapshot
from src.spatial_models.models import (fit_ols, fit_spatial, design, coefficient_rows, ols_diagnostics,
    ordering_hash, residual_moran, pysal_weight, audit_optimum, lm_diagnostics)
from src.spatial_models.analysis import (selected_weights, leave_one_out, calculate, add_fdr, classify_coefficients)
from src.spatial_models.workflow import execution_plan, validate_outputs
from src.spatial.robustness_audit import sha256, check_snapshot


@pytest.fixture(autouse=True)
def no_network():
    """No NASA, KMA or other HTTP request is permitted in new tests."""
    with patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden')):
        yield


@pytest.fixture(scope='module')
def sample():
    """Small synthetic regression fixture, isolated from actual output directories."""
    rng = np.random.default_rng(741)
    n = 24
    data = pd.DataFrame({'station_id':[str(i) for i in range(n)], 'station_name':[f'S{i}' for i in range(n)],
        'region_level1':['R']*n, 'latitude':rng.uniform(33,38,n), 'longitude':rng.uniform(126,130,n),
        'elevation_m':rng.uniform(1,400,n), 'distance_to_coast_km':rng.uniform(1,100,n),
        'actual_data_start_date':['1981-01-01']*n, 'actual_data_end_date':['2025-12-31']*n,
        'temperature_missing_rate':np.zeros(n), 'annual_completeness':np.ones(n), 'continuity_risk':['low']*n})
    noise = rng.normal(0,.2,n)
    for i, outcome in enumerate(OUTCOMES):
        data[outcome] = .01*data.distance_to_coast_km + .1*data.latitude - .001*data.elevation_m + noise*(1+.1*i) + i
    data['nasa_tavg_sen_slope'] = data[OUTCOMES[0]]+.02
    return data


@pytest.fixture(scope='module')
def config():
    """Unit tests use fewer permutations, while production inherits 999."""
    return {'knn_values':[3,4,5,6], 'distance_band_multipliers':[1.,1.1,1.25],
            'inverse_distance_powers':[1,2], 'moran_permutations':19, 'random_seed':123}


@pytest.fixture
def frames(sample):
    """Build self-consistent Final A source fixtures."""
    return {'stations':sample.copy(), 'shortlist':sample.assign(eligibility_tier='A'),
            'master':sample.drop(columns='distance_to_coast_km'),
            'coast':sample[['station_id','distance_to_coast_km']].copy()}


@pytest.fixture(scope='module')
def calculated(sample, config):
    """Reuse bounded actual synthetic model computations across assertions."""
    return calculate(sample, config)


def test_master(frames):
    """One row per Final A station, complete required columns."""
    result = build_master(frames)
    assert len(result) == len(frames['stations']) and not result.station_id.duplicated().any()
    assert set([*PREDICTORS, *OUTCOMES, 'nasa_tavg_sen_slope']) <= set(result)


@pytest.mark.parametrize('problem', ['tier_b','continuity','missing_predictor','duplicate','extra','coordinates','manual'])
def test_reject_invalid_master(frames, problem):
    """Ineligible/incomplete stations are not silently removed or imputed."""
    if problem == 'tier_b': frames['shortlist'].loc[0,'eligibility_tier'] = 'B'
    if problem == 'continuity': frames['shortlist'].loc[0,'continuity_risk'] = 'unresolved'
    if problem == 'missing_predictor': frames['coast'].loc[0,'distance_to_coast_km'] = np.nan
    if problem == 'duplicate': frames['master'].loc[0,'station_id'] = frames['master'].loc[1,'station_id']
    if problem == 'extra': frames['coast'].loc[0,'station_id'] = '999'
    if problem == 'coordinates': frames['master'].loc[0,'latitude'] += .1
    if problem == 'manual': frames['stations']['manual_review_required'] = True
    with pytest.raises(ValueError): build_master(frames)


def test_ols_known_coefficients(sample):
    """OLS equals an independently computed least-squares solution."""
    fit = fit_ols(sample, OUTCOMES[0], PREDICTORS)
    expected = np.linalg.lstsq(design(sample, PREDICTORS), sample[OUTCOMES[0]], rcond=None)[0]
    np.testing.assert_allclose(fit.beta, expected, atol=1e-12)
    assert np.isfinite(fit.metrics['r_squared'])


def test_ols_hc3(sample):
    """HC3 keeps coefficients and uses the explicit leverage-squared covariance."""
    fit = fit_ols(sample, OUTCOMES[0], PREDICTORS)
    x = design(sample, PREDICTORS)
    bread = np.linalg.inv(x.T@x)
    leverage = np.diag(x@bread@x.T)
    covariance = bread@x.T@np.diag((fit.residual/(1-leverage))**2)@x@bread
    rows = coefficient_rows(fit, sample, PREDICTORS, hc3=True)
    np.testing.assert_allclose([r['std_error'] for r in rows], np.sqrt(np.diag(covariance)), rtol=1e-8)


@pytest.mark.parametrize('diagnostic', ['VIF','BP','Cook','JB'])
def test_ols_diagnostics(sample, diagnostic):
    """Diagnostic ranges and no-removal influence rule."""
    diag,vif,influence = ols_diagnostics(fit_ols(sample,OUTCOMES[0],PREDICTORS),sample,PREDICTORS)
    if diagnostic == 'VIF': assert np.isfinite(vif.VIF).all() and vif.VIF.ge(1).all()
    if diagnostic == 'BP': assert 0 <= diag['bp_p'] <= 1
    if diagnostic == 'JB': assert 0 <= diag['jb_p'] <= 1
    if diagnostic == 'Cook':
        assert len(influence) == len(sample) and not influence.automatically_removed.any()
        assert influence.threshold.eq(4/len(sample)).all() and influence.cooks_distance.ge(0).all()


def test_moran_alignment_reproducibility(sample, config):
    """Shuffled residual rows explicitly realign; same seed yields identical values."""
    _,weights = selected_weights(sample,config)
    weight = weights[BASE_WEIGHT]
    fit = fit_ols(sample,OUTCOMES[0],PREDICTORS)
    residuals = pd.DataFrame({'station_id':sample.station_id,'residual':fit.residual})
    a = residual_moran(residuals,weight,OUTCOMES[0],config)
    assert a == residual_moran(residuals.sample(frac=1,random_state=3),weight,OUTCOMES[0],config)
    assert 0 <= a['residual_moran_p'] <= 1


def test_order_hash(sample):
    """Ordering changes must be detectable."""
    assert ordering_hash(tuple(sample.station_id)) != ordering_hash(tuple(sample.station_id[::-1]))


@pytest.mark.parametrize('family', ['SAR','SEM'])
@pytest.mark.parametrize('weight_name', [BASE_WEIGHT,'symmetric_knn_k4','distance_band_x1','inverse_distance_p1'])
def test_spatial_family_weights(sample, config, calculated, family, weight_name):
    """Both spatial families fit all required weights with finite spatial parameters and Moran."""
    summary = calculated['spatial_model_summary']
    rows = summary.query("specification == 'main' and scale == 'original'")
    rows = rows[rows.model_type.eq(family) & rows.weight_type.eq(weight_name)]
    assert rows.converged.all(), calculated['spatial_model_failures'].to_string()
    assert np.isfinite(rows['rho' if family=='SAR' else 'lambda']).all()
    assert np.isfinite(rows.residual_moran_I).all() and rows.residual_moran_p.between(0,1).all()
    _,weights = selected_weights(sample,config)
    np.testing.assert_array_equal(pysal_weight(weights[weight_name]).full()[0],weights[weight_name].matrix)


@pytest.mark.parametrize('outcome', OUTCOMES)
def test_outcomes_loo_and_summary(sample, calculated, outcome):
    """All three outcomes retain n stations and exactly n LOO iterations."""
    rows = calculated['spatial_model_summary'].query("specification == 'main' and scale == 'original'")
    assert rows[rows.outcome.eq(outcome)].n.eq(len(sample)).all()
    loo = calculated['spatial_model_leave_one_out_sensitivity']
    loo = loo[loo.outcome.eq(outcome)]
    assert len(loo)==len(sample) and loo.excluded_station_id.nunique()==len(sample)
    assert np.isfinite(loo.coefficient).all() and loo.n.eq(len(sample)-1).all()


@pytest.mark.parametrize('family',['OLS','SAR','SEM'])
def test_standardized_exact_reparameterization(sample,config,family):
    """Algebraic standardized coefficients equal independently refitted standardized models."""
    _,weights = selected_weights(sample,config)
    weight=weights[BASE_WEIGHT]
    fit = fit_ols(sample,OUTCOMES[0],PREDICTORS) if family=='OLS' else fit_spatial(sample,OUTCOMES[0],PREDICTORS,weight,family)
    transformed = sample.copy()
    transformed[PREDICTORS]=(sample[PREDICTORS]-sample[PREDICTORS].mean())/sample[PREDICTORS].std(ddof=0)
    refit = fit_ols(transformed,OUTCOMES[0],PREDICTORS) if family=='OLS' else fit_spatial(transformed,OUTCOMES[0],PREDICTORS,weight,family)
    rows = coefficient_rows(fit,sample,PREDICTORS,scale='standardized_predictors')
    np.testing.assert_allclose([r['coefficient'] for r in rows],refit.beta,rtol=2e-4,atol=1e-5)
    np.testing.assert_allclose([r['std_error'] for r in rows],np.sqrt(np.diag(refit.covariance)),rtol=2e-4,atol=1e-5)


def test_longitude_sensitivity(calculated):
    """Longitude is separate, baseline-weight-only, never silently in main."""
    s=calculated['spatial_model_summary']
    assert not s[s.specification.eq('main')].predictor.eq('longitude').any()
    sensitivity=s[s.specification.eq('longitude_sensitivity')]
    assert sensitivity.predictor.eq('longitude').any() and sensitivity.weight_type.eq(BASE_WEIGHT).all()


def test_sem_residual_definition(sample, config):
    """Filtered innovations differ from structural u and use (I-lambda W)u."""
    _,w=selected_weights(sample,config)
    fit=fit_spatial(sample,OUTCOMES[0],PREDICTORS,w[BASE_WEIGHT],'SEM')
    np.testing.assert_allclose(fit.residual,fit.structural-fit.metrics['lambda']*(w[BASE_WEIGHT].matrix@fit.structural))


def test_fit_ic_counts(sample, config):
    """Comparison IC includes variance and the spatial parameter for both SAR and SEM."""
    _,w=selected_weights(sample,config)
    for family in ('OLS','SAR','SEM'):
        fit=fit_ols(sample,OUTCOMES[0],PREDICTORS) if family=='OLS' else fit_spatial(sample,OUTCOMES[0],PREDICTORS,w[BASE_WEIGHT],family)
        k=5 if family=='OLS' else 6
        assert fit.metrics['likelihood_parameter_count']==k
        assert fit.metrics['AIC']==pytest.approx(-2*fit.metrics['log_likelihood']+2*k)


def test_lm_diagnostics(sample,config):
    """Four LM tests available with bounded probabilities."""
    _,w=selected_weights(sample,config)
    rows=lm_diagnostics(sample,OUTCOMES[0],PREDICTORS,w[BASE_WEIGHT])
    assert {r['test'] for r in rows}=={'lme','lml','rlme','rlml'}
    assert all(0<=r['p_value']<=1 for r in rows)


def test_failed_model_continues(sample,config):
    """Spatial failures remain NaN, other fits/LOO survive, classification is incomplete."""
    with patch('src.spatial_models.analysis.fit_spatial',side_effect=ValueError('test fit failure')):
        tables=calculate(sample,config)
    assert len(tables['spatial_model_failures'])==30
    rows=tables['spatial_model_summary']
    assert rows[rows.model_type.isin(['SAR','SEM'])].coefficient.isna().all()
    assert rows[rows.model_type.eq('OLS')].converged.all()
    assert tables['spatial_model_coefficient_stability'].robustness_class.eq('INCOMPLETE_MODELS').all()


def test_alignment_rejects_fit(sample,config):
    """No implicit model fitting against a mismatched station order."""
    _,w=selected_weights(sample,config)
    with pytest.raises(ValueError,match='ordering'):
        fit_spatial(sample.iloc[::-1],OUTCOMES[0],PREDICTORS,w[BASE_WEIGHT],'SAR')


def test_optimum_failure(sample,config):
    """Wrong likelihood/optimum cannot be labeled converged."""
    _,w=selected_weights(sample,config)
    with pytest.raises(ValueError):
        audit_optimum(sample[OUTCOMES[0]].to_numpy(),design(sample,PREDICTORS),w[BASE_WEIGHT].matrix,'SAR',.9999,0.)


def test_stability_and_fdr(calculated):
    """Nine outcome-predictor classifications and exactly four separate three-hypothesis FDR families."""
    assert len(calculated['spatial_model_coefficient_stability'])==9
    s=calculated['spatial_model_summary']
    q=s[s.fdr_q.notna()]
    assert len(q)==12 and q.groupby('fdr_family').size().eq(3).all()
    assert q.scale.eq('original').all() and q.weight_type.eq(BASE_WEIGHT).all()
    assert q.predictor.eq(PREDICTORS[0]).all()


@pytest.mark.parametrize('kind,expected',[('same','ROBUST_SIGNIFICANT'),('direction','NON_ROBUST'),('weight','WEIGHT_SENSITIVE'),('family','MODEL_SENSITIVE'),('weak','ROBUST_DIRECTION')])
def test_operational_classification(kind,expected):
    """Explicit precedence with overlapping flags is reproducible."""
    g=pd.DataFrame([{'model_type':m,'weight_type':str(w),'coefficient':1.,'p_value':.01,'converged':True} for m in ('OLS','SAR','SEM') for w in range(4)])
    if kind=='direction': g.loc[0,'coefficient']=-1
    if kind=='weight': g.loc[0,'p_value']=.5
    if kind=='family': g.loc[g.model_type.eq('SEM'),'p_value']=.5
    if kind=='weak': g['p_value']=.5
    assert classify_coefficients(g)['robustness_class']==expected


def test_validation(sample,calculated):
    """All emitted successful numeric results pass sanity checks."""
    validate_outputs(calculated,len(sample))


def test_dry_run_no_fit_no_write(sample,config,tmp_path):
    """Dry run checks input and weights only, no API or analysis/writes."""
    from src.spatial_models.workflow import run_modeling
    with patch('src.spatial_models.workflow.load_inputs',return_value=(sample,config,{},{})), patch('src.spatial_models.workflow.calculate',side_effect=AssertionError('Fit forbidden')):
        plan=run_modeling(True,tmp_path)
    assert plan['NASA_API_calls']==plan['KMA_API_calls']==0 and plan['main_unique_fits']==27
    assert plan['expected_model_count']==36+3*len(sample)
    assert len(plan['expected_output_files'])==34 and not list(tmp_path.iterdir())


def test_protected_stage13(tmp_path):
    """Stage-13 coastline and results ARE protected; only Stage14 output excluded."""
    for name in ['VERSION','data/geospatial/coastline/a.bin','output/tables/coastal/old.csv','output/tables/spatial_models/new.csv']:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('original')
    snapshot=protected_snapshot(tmp_path)
    assert len(snapshot)==3 and not check_snapshot(tmp_path,snapshot)
    (tmp_path/'output/tables/coastal/old.csv').write_text('changed')
    assert check_snapshot(tmp_path,snapshot)==['output/tables/coastal/old.csv']


def test_loader(tmp_path):
    """Loader reads manifested tables, respects namespace and handles empty state."""
    from dashboard.spatial_model_loader import load_manifest,load_table
    assert load_manifest(tmp_path)=={} and load_table('x',tmp_path).empty
    path=tmp_path/'output/tables/spatial_models/test.csv';path.parent.mkdir(parents=True);path.write_text('station_id,value\n1,3\n')
    manifest=tmp_path/'output/manifests/spatial_modeling_manifest.json';manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'generated_tables':{'x':path.relative_to(tmp_path).as_posix(),'bad':'VERSION'}}))
    assert load_table('x',tmp_path).station_id.iloc[0]=='1' and load_table('bad',tmp_path).empty


def test_reports_and_manifest(sample,config,calculated,tmp_path):
    """Manifest, report regeneration and saved read-only workflow remain deterministic."""
    from src.spatial_models import workflow
    old=pd.DataFrame([{'variable':o,'term':r['predictor'],'coefficient':r['coefficient']} for o in OUTCOMES[:2] for r in coefficient_rows(fit_ols(sample,o,PREDICTORS),sample,PREDICTORS)])
    frames={'old_ols':old,'robustness':pd.DataFrame({'variable':OUTCOMES,'robustness_class':['test']*3})}
    (tmp_path/'VERSION').write_text('1.0.0')
    with patch.object(workflow,'load_inputs',return_value=(sample,config,{},frames)), patch.object(workflow,'calculate',return_value=calculated):
        manifest=workflow.run_modeling(False,tmp_path)
    assert manifest['failed_models']==0 and manifest['protected_files_changed']==[]
    assert len(manifest['generated_tables'])==20 and len(manifest['generated_charts'])==11
    before={p:sha256(tmp_path/p) for p in manifest['generated_reports']}
    workflow.report_from_saved(tmp_path)
    assert before=={p:sha256(tmp_path/p) for p in before}
    text=(tmp_path/manifest['generated_reports'][0]).read_text()
    assert '17. Conclusions' in text and '인과' in text and 'coefficient uncertainty' in text
    assert not list(tmp_path.glob('data/**/*'))


def test_page_empty_state(monkeypatch):
    """New page is safe before analysis output exists."""
    from streamlit.testing.v1 import AppTest
    import dashboard.pages.spatial_models as page
    monkeypatch.setattr(page,'load_manifest',lambda: {})
    app=AppTest.from_string('from dashboard.pages.spatial_models import render\nrender()').run(timeout=30)
    assert not app.exception and len(app.info)==1
