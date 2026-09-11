"""Instrument unmodified PySAL fits; diagnostic candidates never rescue failed estimates."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import threading
import warnings
from unittest.mock import patch
import numpy as np
import pandas as pd
from src.spatial_models.data import PREDICTORS
from src.spatial_models.models import design, residual_moran
from src.spatial.weights import SpatialWeights
from src.spatial_numerical.weights import boundary_distance

_INSTRUMENT_LOCK=threading.RLock()


def profile_nll(parameter: float, y: np.ndarray, x: np.ndarray, w: np.ndarray, family: str) -> float:
    """Concentrated negative log likelihood, diagnostic only, excluding common constant."""
    if family not in ('SAR','SEM'):
        raise ValueError('Unsupported family')
    a=np.eye(len(y))-parameter*w
    sign,logdet=np.linalg.slogdet(a)
    if sign<=0:
        return np.nan
    target=a@y; transformed=x if family=='SAR' else a@x
    error=target-transformed@np.linalg.lstsq(transformed,target,rcond=None)[0]
    variance=float(error@error/len(y))
    return float(len(y)/2*np.log(variance)-logdet) if variance>0 else np.nan


def numerical_classification(returned: bool, finite: bool, optimum_success: bool,
                             boundary_hit: bool, near_boundary: bool, outside: bool=False,
                             supported: bool=True, reproducible: bool=True) -> str:
    """Conservative operational status; never equate optimizer success with validity."""
    if not supported:
        return 'NOT_SUPPORTED'
    if not returned:
        return 'FAILED'
    if not finite or not optimum_success or boundary_hit or outside or not reproducible:
        return 'NUMERICALLY_UNSTABLE'
    return 'CONVERGED_NEAR_BOUNDARY' if near_boundary else 'STABLE'


def diagnostic_hash(row: dict) -> str:
    """Stable same-input result fingerprint, independent of row traversal order."""
    fields=['outcome','model_type','weight_type','diagnostic_estimate','library_returned',
            'solver_success','solver_iterations','solver_evaluations','numerical_class',
            'residual_moran_I','residual_moran_p','failure_reason','warning']
    text=json.dumps({k:row.get(k) for k in fields},sort_keys=True,ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def review_fit(master: pd.DataFrame, outcome: str, family: str, item: dict, config: dict) -> dict:
    """Run original library once while observing optimizer calls without altering arguments."""
    import spreg
    from libpysal.weights import full2W
    import spreg.ml_lag as lag_module
    import spreg.ml_error as error_module
    w=item['matrix']; setting=item['setting']; spectrum=item['spectral']
    ids=tuple(master.station_id.astype(str)); x=design(master,PREDICTORS); y=master[outcome].to_numpy(float)
    row=dict(outcome=outcome,model_type=family,weight_type=setting['weight_type'],n_stations=len(y),
             row_standardized=setting['row_standardized'],solver_method='PySAL FULL / scipy bounded (unchanged)',
             solver_lower=-1.,solver_upper=1.,library_returned=False,solver_success=False,
             solver_iterations=np.nan,solver_evaluations=np.nan,diagnostic_estimate=np.nan,
             estimate=np.nan,residual_moran_I=np.nan,residual_moran_p=np.nan,
             warning='',exception='',failure_reason='',power_expansion_failure=False,
             profile_derivative_at_lower=np.nan,likelihood_audit_difference=np.nan,
             autoregressive_matrix_condition=np.nan,min_singular_value=np.nan,
             neumann_radius_at_candidate=np.nan,first_power_norm_increase_iteration=np.nan,
             series_increment_ratio_at_failure=np.nan,
             lower_admissible_bound=spectrum['lower_admissible_bound'],
             upper_admissible_bound=spectrum['upper_admissible_bound'])
    calls=[]; model=None; finite=False; collected=[]
    # The fixed library window is only safe when wholly inside the zero-connected interval.
    supported=(spectrum['lower_admissible_bound'] <= -1+1e-8 and spectrum['upper_admissible_bound'] >= 1-1e-8)
    if supported:
        module=lag_module if family=='SAR' else error_module
        with _INSTRUMENT_LOCK:
            original=module.minimize_scalar

            def observe(*args,**kwargs):
                """Record native solver diagnostics; forward every argument untouched."""
                result=original(*args,**kwargs)
                calls.append(result)
                return result

            with warnings.catch_warnings(record=True) as caught,contextlib.redirect_stdout(io.StringIO()),patch.object(module,'minimize_scalar',observe):
                warnings.simplefilter('always')
                try:
                    weight=full2W(w.copy(),ids=list(ids))
                    if tuple(weight.id_order)!=ids or not np.array_equal(weight.full()[0],w):
                        raise ValueError('Weight conversion/order mismatch')
                    if family=='SAR':
                        model=spreg.ML_Lag(y[:,None],x[:,1:],weight,method='full',spat_impacts=None,spat_diag=False,name_x=PREDICTORS)
                    else:
                        model=spreg.ML_Error(y[:,None],x[:,1:],weight,method='full',name_x=PREDICTORS)
                    row['library_returned']=True
                except Exception as exc:
                    row['exception']=f'{type(exc).__name__}: {exc}'
                collected=[str(warning.message) for warning in caught]
        if calls:
            result=calls[-1]
            candidate=float(np.asarray(result.x).item())
            row.update(diagnostic_estimate=candidate,solver_success=bool(result.success),
                       solver_iterations=int(result.nit) if hasattr(result,'nit') else np.nan,
                       solver_evaluations=int(result.nfev),solver_message=str(result.message))
            a=np.eye(len(y))-candidate*w
            row['autoregressive_matrix_condition']=float(np.linalg.cond(a))
            row['min_singular_value']=float(np.linalg.svd(a,compute_uv=False).min())
            row['neumann_radius_at_candidate']=abs(candidate)*spectrum['spectral_radius']
            step=1e-4
            row['profile_derivative_at_lower']=(profile_nll(-1+step,y,x,w,family)-profile_nll(-1,y,x,w,family))/step
            if model is not None:
                beta=np.asarray(model.betas).ravel(); covariance=np.asarray(model.vm)
                innovation=np.asarray(model.u if family=='SAR' else model.e_filtered).ravel()
                finite=bool(np.isfinite(beta).all() and np.isfinite(covariance).all()
                            and (np.diag(covariance)>0).all() and np.isfinite(innovation).all())
                audit=-profile_nll(candidate,y,x,w,family)-len(y)/2*(np.log(2*np.pi)+1)
                row['likelihood_audit_difference']=abs(float(model.logll)-audit)
                finite=finite and bool(np.isclose(model.logll,audit,atol=1e-5,rtol=1e-7))
                if finite and innovation.std()>0:
                    residuals=pd.DataFrame({'station_id':ids,'residual':innovation})
                    weight_record=SpatialWeights(ids,w,pd.DataFrame(),setting['family'],int(setting.get('k',0)),np.zeros_like(w))
                    moran=residual_moran(residuals,weight_record,outcome,config)
                    row.update({k:moran[k] for k in ('residual_moran_I','residual_moran_p')})
                else:
                    finite=False
            if family=='SAR':
                # Reproduce only the series norm diagnostic, not an alternative prediction.
                beta=np.linalg.lstsq(x,y-candidate*(w@y),rcond=None)[0]
                increment=x@beta; previous=1e7
                for iteration in range(1,1001):
                    increment=candidate*(w@increment); current=float(np.linalg.norm(increment))
                    if current>previous:
                        row['first_power_norm_increase_iteration']=iteration
                        row['series_increment_ratio_at_failure']=current/previous
                        break
                    if current<=1e-7:
                        break
                    previous=current
    row['warning']='; '.join(sorted(set(collected)))
    row['power_expansion_failure']='power expansion' in row['exception']
    candidate=row['diagnostic_estimate']
    admissible=boundary_distance(candidate,spectrum['lower_admissible_bound'],spectrum['upper_admissible_bound'],.01)
    solver=boundary_distance(candidate,-1,1,.05)
    row.update(admissible)
    row.update({f'solver_{k}':v for k,v in solver.items()})
    hit=bool(np.isfinite(candidate) and min(candidate+1,1-candidate)<=1e-6)
    row['solver_boundary_hit']=hit
    row['finite_result']=finite
    row['numerical_class']=numerical_classification(row['library_returned'],finite,row['solver_success'],hit,
        admissible['near_boundary'] or solver['near_boundary'],admissible['outside_interval'],supported)
    if row['numerical_class']=='STABLE':
        row['estimate']=candidate
    if not supported:
        reason='UNSUPPORTED_FIXED_LIBRARY_WINDOW'
    elif hit:
        reason='FIXED_SOLVER_BOUNDARY_NOT_ADMISSIBLE_BOUNDARY'
    elif admissible['near_boundary'] or solver['near_boundary']:
        reason='BOUNDARY_PROXIMITY'
    else:
        reason='INVALID_RESULT_OR_AUDIT' if not finite else ''
    row['failure_reason']=row['exception'] or reason
    row['result_hash']=diagnostic_hash(row)
    return row


def likelihood_profiles(master: pd.DataFrame, item: dict) -> pd.DataFrame:
    """Fixed 81-point profiles of the three failed combinations; NEVER refit outside (-1,1)."""
    x=design(master,PREDICTORS); w=item['matrix']; spectrum=item['spectral']
    lower,upper=spectrum['lower_admissible_bound'],spectrum['upper_admissible_bound']
    grids={'library_window':np.linspace(-1+1e-6,1-1e-6,81),
           'nonsingular_component_diagnostic_only':np.linspace(lower+.001*(upper-lower),upper-.001*(upper-lower),81)}
    rows=[]
    for outcome,family in [('tavg_bias','SEM'),('tavg_rmse','SAR'),('tavg_rmse','SEM')]:
        y=master[outcome].to_numpy(float)
        for scope,grid in grids.items():
            for parameter in grid:
                rows.append(dict(outcome=outcome,model_type=family,scope=scope,parameter=float(parameter),
                    negative_log_likelihood=profile_nll(parameter,y,x,w,family),
                    diagnostic_only=True,accepted_estimate=False))
    return pd.DataFrame(rows)
