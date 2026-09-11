"""Predeclared numerical comparisons and interpretation metadata, not climate reanalysis."""
from __future__ import annotations
import numpy as np
import pandas as pd
from src.spatial_models.data import OUTCOMES, PREDICTORS, BASE_WEIGHT
from src.spatial_models.models import ordering_hash
from src.spatial_numerical.weights import canonical, diagnose_weights, matrix_hash
from src.spatial_numerical.solver import review_fit, likelihood_profiles, diagnostic_hash


def recommend(group: pd.DataFrame) -> dict:
    """Recommend by numerical diagnostics, never by coefficient p-values."""
    key=group.weight_type.iloc[0]
    counts=group.numerical_class.value_counts()
    complete=len(group)==len(OUTCOMES)*2
    hard=group.numerical_class.isin(['FAILED','NUMERICALLY_UNSTABLE','NOT_SUPPORTED']).any()
    if hard or not complete:
        status='NOT_RECOMMENDED_NUMERICAL'
        reason='Failure/solver boundary/incomplete comparison in this fixed library specification; no forced rescue.'
    elif key==BASE_WEIGHT and group.numerical_class.eq('STABLE').all():
        status='RECOMMENDED_MAIN'
        reason='Existing directed KNN baseline; all primary numerical checks stable. Scientific validity remains separate.'
    else:
        status='RECOMMENDED_SENSITIVITY'
        reason='Sensitivity only; no promotion from numerical success. Near-boundary fits must remain flagged and unused as normal estimates.'
    return dict(weight_type=key,recommended_status=status,reason=reason,n_model_combinations=len(group),
                stable_count=int(counts.get('STABLE',0)),near_boundary_count=int(counts.get('CONVERGED_NEAR_BOUNDARY',0)),
                unstable_count=int(counts.get('NUMERICALLY_UNSTABLE',0)),failed_count=int(counts.get('FAILED',0)),
                unsupported_count=int(counts.get('NOT_SUPPORTED',0)))


def interpretation_status(old: pd.DataFrame, stability: pd.DataFrame) -> pd.DataFrame:
    """Reprioritize existing HC3 inference without recalculating climate coefficients/p-values."""
    old=old[old.specification.eq('main') & old.scale.eq('original') & old.predictor.eq(PREDICTORS[0])]
    rows=[]
    controls=[BASE_WEIGHT,'symmetric_knn_k4','distance_band_x1']
    for outcome in OUTCOMES:
        subset=old[old.outcome.eq(outcome)]
        baseline=subset[subset.weight_type.eq(BASE_WEIGHT)].set_index('model_type')
        hc3=float(baseline.loc['OLS-HC3','p_value']); classical=float(baseline.loc['OLS','p_value'])
        control=subset[subset.weight_type.isin(controls) & subset.model_type.isin(['OLS','SAR','SEM'])]
        valid=control.converged & control.coefficient.notna()
        same=valid.all() and np.sign(control.coefficient).nunique()==1
        sig=valid.all() and control.p_value.lt(.05).all()
        idw=stability[stability.outcome.eq(outcome) & stability.weight_type.eq('inverse_distance_p1_row')]
        excluded=not idw.numerical_class.eq('STABLE').all()
        if same and classical<.05<=hc3:
            status='DIRECTIONALLY_STABLE_HETEROSKEDASTICITY_SENSITIVE'
            note='Direction retained in existing results; HC3 does not support the classical significance claim.'
        elif same and hc3<.05 and sig and excluded:
            status='ROBUST_ASSOCIATION_WITH_UNSUPPORTED_INVERSE_DISTANCE_SPECIFICATION'
            note='Existing HC3/KNN/control-direction evidence retained; IDW p1 excluded numerically. Control near-boundary estimates remain caveated.'
        elif control.p_value.lt(.05).nunique()>1 or (classical<.05)!=(hc3<.05):
            status='MODEL_SENSITIVE_NOT_UPGRADED'
            note='Existing significance differs by model; improved numerical behavior does not upgrade climate inference.'
        else:
            status='EXPLORATORY_INCONCLUSIVE'
            note='No additional climate conclusion derived from numerical diagnostics.'
        rows.append(dict(outcome=outcome,primary_ols_inference='HC3 robust standard errors',
            classical_ols_role='descriptive/reference',classical_p=classical,hc3_p=hc3,
            interpretation_status=status,existing_control_direction_consistent=bool(same),
            inference_values_recomputed=False,note=note))
    return pd.DataFrame(rows)


def calculate_review(master: pd.DataFrame, config: dict, old_frames: dict) -> tuple[dict,dict]:
    """54 fixed diagnostics; exact repeat and canonical reordering, no precision/data perturbation."""
    master=canonical(master)
    inventory,tables=diagnose_weights(master)
    shuffled=canonical(master.sample(frac=1,random_state=config['random_seed']))
    rebuilt,_=diagnose_weights(shuffled)
    runs=[]; reproducibility=[]
    for key,item in inventory.items():
        for outcome in OUTCOMES:
            for family in ('SAR','SEM'):
                result=review_fit(master,outcome,family,item,config)
                repeated=review_fit(master,outcome,family,item,config)
                reordered=review_fit(shuffled,outcome,family,rebuilt[key],config)
                same_repeat=result['result_hash']==repeated['result_hash']
                same_order=result['result_hash']==reordered['result_hash']
                same_weight=matrix_hash(item['matrix'])==matrix_hash(rebuilt[key]['matrix'])
                reproducibility.append(dict(weight_type=key,outcome=outcome,model_type=family,
                    canonical_ordering_hash=ordering_hash(tuple(master.station_id)),
                    reordered_ordering_hash=ordering_hash(tuple(shuffled.station_id)),
                    result_hash=result['result_hash'],repeated_result_hash=repeated['result_hash'],
                    reordered_result_hash=reordered['result_hash'],same_seed_repeat=same_repeat,
                    ordering_invariant=same_order,canonical_weight_hash_equal=same_weight))
                if not (same_repeat and same_order and same_weight):
                    result.update(numerical_class='NUMERICALLY_UNSTABLE',estimate=np.nan,
                                  failure_reason='Repeat/ordering sensitivity')
                runs.append(result)
    results=pd.DataFrame(runs)
    tables['spatial_solver_diagnostics']=results
    tables['spatial_model_numerical_stability']=results[['weight_type','outcome','model_type','estimate','diagnostic_estimate',
        'numerical_class','failure_reason','library_returned','solver_success','residual_moran_I','residual_moran_p']].copy()
    diag=tables['inverse_distance_weight_diagnostics']
    tables['spatial_weight_spectral_properties']=diag[['weight_type','n_stations','row_standardized','spectral_radius',
        'eigenvalue_min_real_part','eigenvalue_max_real_part','max_eigenvalue_imaginary','matrix_rank','condition_number']].copy()
    tables['spatial_parameter_admissible_ranges']=pd.DataFrame([{**row,'model_type':family,'parameter':'rho' if family=='SAR' else 'lambda',
        'interval_definition':'open zero-connected nonsingularity component, not full real line nor Neumann convergence domain'}
        for row in diag[['weight_type','lower_admissible_bound','upper_admissible_bound','neumann_lower','neumann_upper','solver_lower','solver_upper']].to_dict('records') for family in ('SAR','SEM')])
    columns=['weight_type','outcome','model_type','estimate','diagnostic_estimate','lower_admissible_bound','upper_admissible_bound',
             'distance_to_lower_bound','distance_to_upper_bound','relative_boundary_distance','near_boundary','outside_interval',
             'solver_lower','solver_upper','solver_relative_boundary_distance','solver_near_boundary','solver_boundary_hit',
             'autoregressive_matrix_condition','min_singular_value','numerical_class']
    tables['spatial_boundary_diagnostics']=results[columns].copy()
    tables['inverse_distance_power_sensitivity']=results[results.weight_type.isin(['inverse_distance_p1_row','inverse_distance_p2_row'])].copy()
    tables['inverse_distance_cutoff_sensitivity']=results[results.weight_type.str.startswith('inverse_distance') & ~results.weight_type.str.endswith('_raw')].merge(
        diag[['weight_type','density','spectral_radius','cutoff_km']],on='weight_type',validate='many_to_one')
    tables['spatial_model_final_specification_recommendation']=pd.DataFrame([recommend(group) for _,group in results.groupby('weight_type',sort=False)])
    tables['stage14_model_interpretation_status']=interpretation_status(old_frames['spatial_model_summary'],results)
    tables['spatial_model_ordering_reproducibility']=pd.DataFrame(reproducibility)
    tables['spatial_likelihood_profiles']=likelihood_profiles(master,inventory['inverse_distance_p1_row'])
    old=old_frames['spatial_model_summary']
    old=old[old.specification.eq('main') & old.scale.eq('original') & old.predictor.eq(PREDICTORS[0]) & old.model_type.isin(['SAR','SEM'])].copy()
    old['old_parameter']=np.where(old.model_type.eq('SAR'),old.rho,old['lambda'])
    old['weight_type']=old.weight_type.replace({'inverse_distance_p1':'inverse_distance_p1_row'})
    compared=old[['outcome','model_type','weight_type','converged','old_parameter']].merge(
        results[['outcome','model_type','weight_type','diagnostic_estimate','numerical_class']],on=['outcome','model_type','weight_type'],validate='one_to_one')
    compared['successful_old_estimate_reproduced']=np.where(compared.converged,
        np.isclose(compared.old_parameter,compared.diagnostic_estimate,atol=1e-8),False)
    compared['original_failure_preserved']=~compared.converged & compared.numerical_class.isin(['FAILED','NUMERICALLY_UNSTABLE'])
    if not (compared.successful_old_estimate_reproduced | compared.original_failure_preserved).all():
        raise ValueError('Stage14 numerical reproduction mismatch')
    tables['stage14_numerical_reproduction']=compared
    return tables,inventory
