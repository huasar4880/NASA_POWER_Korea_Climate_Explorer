"""Bounded Stage-14 comparisons; failure isolation and operational robustness flags."""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
from src.spatial.distances import calculate_distance_matrix
from src.spatial.robustness import build_weight, weight_configurations
from src.spatial_models.data import OUTCOMES, PREDICTORS, BASE_WEIGHT
from src.spatial_models.models import (fit_ols, fit_spatial, coefficient_rows, residual_moran,
                                       ols_diagnostics, lm_diagnostics)


def selected_weights(master: pd.DataFrame, config: dict) -> tuple:
    """Select exactly the four existing Stage-13 main/robustness definitions."""
    distances = calculate_distance_matrix(master)
    variants = [BASE_WEIGHT, 'symmetric_knn_k4', 'distance_band_x1', 'inverse_distance_p1']
    settings = [s for s in weight_configurations(distances, config) if s['weight_variant'] in variants]
    if [s['weight_variant'] for s in settings] != variants:
        raise ValueError('Required four Stage-13 weight settings unavailable')
    return settings, {s['weight_variant']: build_weight(distances, s) for s in settings}


def leave_one_out(master: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """Temporarily omit each station once; retain all original data and full-sample analysis."""
    baseline = fit_ols(master, outcome, PREDICTORS).beta[1]
    rows = []
    for index, station in master.iterrows():
        sample = master.drop(index)
        fit = fit_ols(sample, outcome, PREDICTORS)
        row = coefficient_rows(fit, sample, PREDICTORS)[1]
        rows.append({'outcome': outcome, 'excluded_station_id': station.station_id,
                     'excluded_station_name': station.station_name, 'n': len(sample),
                     'coefficient': row['coefficient'], 'p_value': row['p_value'],
                     'same_sign_as_full': bool(np.sign(row['coefficient']) == np.sign(baseline))})
    return pd.DataFrame(rows)


def add_fdr(summary: pd.DataFrame) -> pd.DataFrame:
    """BH only three coastal hypotheses, separately per baseline model/SE family."""
    result = summary.copy()
    result['fdr_q'] = np.nan
    result['fdr_family'] = ''
    for model in ('OLS', 'OLS-HC3', 'SAR', 'SEM'):
        mask = (result.model_type.eq(model) & result.weight_type.eq(BASE_WEIGHT)
                & result.specification.eq('main') & result.scale.eq('original')
                & result.predictor.eq(PREDICTORS[0]) & result.converged)
        if mask.sum() == len(OUTCOMES) and result.loc[mask, 'p_value'].notna().all():
            result.loc[mask, 'fdr_q'] = multipletests(result.loc[mask, 'p_value'], method='fdr_bh')[1]
            result.loc[mask, 'fdr_family'] = f'{model}:baseline_main_coast_across_three_outcomes'
    return result


def classify_coefficients(group: pd.DataFrame, expected: int = 12) -> dict:
    """Report overlapping sensitivity flags; precedence failure > sign > weight > model > significance."""
    valid = group.converged & np.isfinite(group.coefficient) & np.isfinite(group.p_value)
    if len(group) != expected or not valid.all():
        return dict(robustness_class='INCOMPLETE_MODELS', robust_direction=False,
                    robust_significant=False, model_sensitive=False, weight_sensitive=False,
                    significant_fraction=np.nan, coefficient_min=np.nan, coefficient_max=np.nan)
    same = np.sign(group.coefficient).nunique() == 1 and not group.coefficient.eq(0).any()
    significant = group.p_value < .05
    temp = group.assign(significant=significant, direction=np.sign(group.coefficient))
    weight_sensitive = any(g.significant.nunique() > 1 or g.direction.nunique() > 1
                           for _, g in temp.groupby('model_type'))
    model_sensitive = any(g.significant.nunique() > 1 or g.direction.nunique() > 1
                          for _, g in temp.groupby('weight_type'))
    robust_sig = same and significant.mean() >= .75
    label = ('NON_ROBUST' if not same else 'WEIGHT_SENSITIVE' if weight_sensitive else
             'MODEL_SENSITIVE' if model_sensitive else 'ROBUST_SIGNIFICANT' if robust_sig else 'ROBUST_DIRECTION')
    return dict(robustness_class=label, robust_direction=bool(same), robust_significant=bool(robust_sig),
                model_sensitive=bool(model_sensitive), weight_sensitive=bool(weight_sensitive),
                significant_fraction=float(significant.mean()), coefficient_min=group.coefficient.min(),
                coefficient_max=group.coefficient.max())


def outcome_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    """Conservative descriptive preference; diagnostic evidence always accompanies AIC."""
    base = summary.query("specification == 'main' and scale == 'original'")
    base = base[base.weight_type.eq(BASE_WEIGHT) & base.predictor.eq(PREDICTORS[0])]
    rows = []
    for outcome in OUTCOMES:
        sample = base[base.outcome.eq(outcome)].set_index('model_type')
        row = {'outcome': outcome}
        for model in ('OLS', 'SAR', 'SEM'):
            for name in ('coefficient', 'p_value', 'AIC', 'BIC', 'residual_moran_I', 'residual_moran_p'):
                row[f'{model}_{name}'] = sample.loc[model, name]
        row['OLS_HC3_p'] = sample.loc['OLS-HC3', 'p_value']
        candidates = sample.loc[['OLS', 'SAR', 'SEM']]
        if not candidates.converged.all():
            preferred, note = 'UNDETERMINED', 'Failed/unstable model; do not rank incomplete evidence.'
        elif sample.loc['OLS', 'residual_moran_p'] >= .05:
            preferred, note = 'OLS_baseline', 'No significant baseline residual Moran; spatial adjustment necessity is weak. Review HC3/LM/weights; AIC alone is not selection.'
        else:
            eligible = candidates[candidates.residual_moran_p >= .05]
            if eligible.empty:
                preferred, note = 'UNDETERMINED', 'Residual dependence remains in every family.'
            else:
                best = eligible.AIC.min()
                near = eligible[eligible.AIC <= best + 2].index.tolist()
                preferred = ' / '.join(near)
                note = 'Descriptive candidates with nonsignificant innovation Moran; delta AIC <2 treated as similar. Check HC3, LM and sensitivity; not a truth model.'
        row.update(preferred_descriptive_model=preferred, selection_note=note)
        rows.append(row)
    return pd.DataFrame(rows)


def calculate(master: pd.DataFrame, config: dict) -> dict[str, pd.DataFrame]:
    """27 unique main fits +9 longitude fits; 135 LOO fits for 45 stations; no grid search."""
    _, weights = selected_weights(master, config)
    rows, diagnostics, vifs, influences, lm, failures, residuals, loo = [], [], [], [], [], [], [], []
    for outcome in OUTCOMES:
        for specification, predictors in [('main', PREDICTORS), ('longitude_sensitivity', [*PREDICTORS, 'longitude'])]:
            ols = fit_ols(master, outcome, predictors)
            diagnostic, vif, influence = ols_diagnostics(ols, master, predictors)
            meta = {'outcome': outcome, 'specification': specification}
            diagnostics.append({**meta, **diagnostic})
            vifs.append(vif.assign(**meta))
            influences.append(influence.assign(**meta))
            active = weights if specification == 'main' else {BASE_WEIGHT: weights[BASE_WEIGHT]}
            for weight_name, weight in active.items():
                context = {**meta, 'weight_type': weight_name}
                try:
                    lm.extend([{**context, **item} for item in lm_diagnostics(master, outcome, predictors, weight)])
                except Exception as exc:
                    lm.append({**context, 'test': 'unavailable', 'statistic': np.nan, 'p_value': np.nan, 'status': type(exc).__name__})
                for family in ('OLS', 'SAR', 'SEM'):
                    try:
                        fit = ols if family == 'OLS' else fit_spatial(master, outcome, predictors, weight, family)
                        residual_frame = pd.DataFrame({'station_id': master.station_id, 'residual': fit.residual})
                        moran = residual_moran(residual_frame, weight, outcome, config)
                        structural_moran = residual_moran(residual_frame.assign(residual=fit.structural), weight, outcome, config)
                        residuals.append(residual_frame.assign(**context, model_type=family, structural_residual=fit.structural))
                        extra = {**context, **moran, 'structural_residual_moran_I': structural_moran['residual_moran_I'],
                                 'structural_residual_moran_p': structural_moran['residual_moran_p'],
                                 'residual_definition': 'innovation; SEM spatially filtered, SAR y-rhoWy-Xbeta, OLS y-Xbeta'}
                        for scale in ('original', 'standardized_predictors'):
                            for hc3 in ([False, True] if family == 'OLS' else [False]):
                                rows.extend([{**extra, **item} for item in coefficient_rows(fit, master, predictors, scale, hc3)])
                    except Exception as exc:
                        failure = {**context, 'model_type': family, 'converged': False,
                                   'warning': '', 'numerical_issue': f'{type(exc).__name__}: {exc}'}
                        failures.append(failure)
                        for scale in ('original', 'standardized_predictors'):
                            for name in ['const', *predictors, *([] if family == 'OLS' else ['rho' if family == 'SAR' else 'lambda'])]:
                                rows.append({**failure, 'scale': scale, 'predictor': name, 'n': len(master),
                                             **{key: np.nan for key in ('coefficient','std_error','z_or_t','p_value','ci_lower','ci_upper',
                                                 'rho','lambda','AIC','BIC','log_likelihood','residual_moran_I','residual_moran_p')}})
        loo.append(leave_one_out(master, outcome))
    summary = add_fdr(pd.DataFrame(rows))
    main = summary.query("specification == 'main' and scale == 'original'")
    stability = []
    for (outcome, predictor), group in main[main.predictor.isin(PREDICTORS) & main.model_type.ne('OLS-HC3')].groupby(['outcome', 'predictor'], sort=False):
        result = {'outcome': outcome, 'predictor': predictor, **classify_coefficients(group)}
        baseline = main[main.outcome.eq(outcome) & main.predictor.eq(predictor) & main.weight_type.eq(BASE_WEIGHT)]
        for _, row in baseline.iterrows():
            result[f'{row.model_type}_coefficient'] = row.coefficient
            result[f'{row.model_type}_p'] = row.p_value
        stability.append(result)
    loo_table = pd.concat(loo, ignore_index=True)
    loo_summary = loo_table.groupby('outcome', sort=False).agg(
        iterations=('coefficient','size'), coefficient_min=('coefficient','min'),
        coefficient_median=('coefficient','median'), coefficient_max=('coefficient','max'),
        sign_consistency=('same_sign_as_full','mean')).reset_index()
    tables = {
        'spatial_modeling_master': master, 'spatial_ols_results': summary[summary.model_type.isin(['OLS','OLS-HC3'])],
        'spatial_ols_diagnostics': pd.DataFrame(diagnostics), 'spatial_model_vif': pd.concat(vifs, ignore_index=True),
        'spatial_lm_diagnostics': pd.DataFrame(lm), 'spatial_model_summary': summary,
        'spatial_model_outcome_comparison': outcome_comparison(summary),
        'spatial_model_coefficient_stability': pd.DataFrame(stability),
        'spatial_model_weight_sensitivity': main[main.predictor.eq(PREDICTORS[0]) & main.model_type.ne('OLS-HC3')],
        'spatial_model_leave_one_out_sensitivity': loo_table,
        'spatial_model_loo_summary': loo_summary,
        'spatial_model_influence_diagnostics': pd.concat(influences, ignore_index=True),
        'spatial_model_residuals': pd.concat(residuals, ignore_index=True),
        'spatial_model_failures': pd.DataFrame(failures, columns=['outcome','specification','weight_type','model_type','converged','warning','numerical_issue']),
    }
    for outcome, prefix in zip(OUTCOMES, ['tavg','bias','rmse']):
        tables[f'{prefix}_spatial_model_comparison'] = summary[summary.outcome.eq(outcome)]
    return tables
