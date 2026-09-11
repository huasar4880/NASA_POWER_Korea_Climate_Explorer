"""OLS/HC3 and audited Gaussian ML spatial fits with explicit residual semantics."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import contextlib
import io
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm, t
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import jarque_bera
from statsmodels.stats.outliers_influence import variance_inflation_factor
from src.spatial.weights import SpatialWeights, align_values
from src.spatial.autocorrelation import GLOBAL_VARIABLES, global_moran_permutation


@dataclass
class Fit:
    """Common, original-scale result; covariance includes spatial parameter last."""
    family: str
    terms: list[str]
    beta: np.ndarray
    covariance: np.ndarray
    residual: np.ndarray
    structural: np.ndarray
    metrics: dict
    warnings: str = ''
    ols: object = None


def ordering_hash(ids: list[str] | tuple[str, ...]) -> str:
    """Hash unambiguous ordered station IDs, not an unordered set."""
    return hashlib.sha256('\n'.join(ids).encode()).hexdigest()


def design(data: pd.DataFrame, predictors: list[str]) -> np.ndarray:
    """Build a full-rank, finite design including intercept; never drop rows."""
    x = sm.add_constant(data[predictors].to_numpy(float), has_constant='add')
    if not np.isfinite(x).all() or np.linalg.matrix_rank(x) != x.shape[1] or len(x) <= x.shape[1] + 1:
        raise ValueError('Invalid or rank-deficient design')
    return x


def fit_metrics(n: int, terms: int, logll: float, residual: np.ndarray) -> dict:
    """Comparable full Gaussian likelihood ICs count ALL parameters, including sigma²."""
    count = terms + 1
    return {'n': n, 'likelihood_parameter_count': count, 'log_likelihood': float(logll),
            'AIC': float(-2 * logll + 2 * count), 'BIC': float(-2 * logll + np.log(n) * count),
            'residual_variance': float(residual @ residual / n)}


def fit_ols(data: pd.DataFrame, outcome: str, predictors: list[str]) -> Fit:
    """Fit classical OLS; retain the fit for HC3, influence and diagnostics."""
    x, y = design(data, predictors), data[outcome].to_numpy(float)
    if not np.isfinite(y).all():
        raise ValueError('Nonfinite outcome')
    result = sm.OLS(y, x).fit()
    metrics = fit_metrics(len(y), len(result.params), result.llf, result.resid)
    metrics.update(r_squared=float(result.rsquared), adjusted_r_squared=float(result.rsquared_adj),
                   pseudo_r_squared=np.nan, native_AIC=float(result.aic), native_BIC=float(result.bic),
                   rho=np.nan, **{'lambda': np.nan}, converged=True, convergence_check='closed_form_full_rank')
    return Fit('OLS', ['const', *predictors], result.params, result.cov_params(), result.resid,
               result.resid, metrics, ols=result)


def pysal_weight(weight: SpatialWeights):
    """Create PySAL W while verifying exact numeric matrix and station ordering."""
    from libpysal.weights import full2W
    result = full2W(weight.matrix.copy(), ids=list(weight.station_ids))
    matrix, ids = result.full()
    if tuple(ids) != weight.station_ids or not np.array_equal(matrix, weight.matrix):
        raise ValueError('PySAL weight alignment mismatch')
    return result


def audit_optimum(y: np.ndarray, x: np.ndarray, matrix: np.ndarray, family: str,
                  parameter: float, logll: float) -> dict:
    """Independently verify ML optimum: spreg does not retain optimizer success flags."""
    def objective(value: float) -> float:
        """Profile negative Gaussian likelihood without its constant term."""
        a = np.eye(len(y)) - value * matrix
        target = a @ y
        transformed = x if family == 'SAR' else a @ x
        residual = target - transformed @ np.linalg.lstsq(transformed, target, rcond=None)[0]
        sign, determinant = np.linalg.slogdet(a)
        variance = residual @ residual / len(y)
        return float(len(y) / 2 * np.log(variance) - determinant) if sign > 0 and variance > 0 else np.inf

    audit = minimize_scalar(objective, bounds=(-1., 1.), method='bounded', options={'xatol': 1e-8})
    audited_ll = -objective(parameter) - len(y) / 2 * (np.log(2 * np.pi) + 1)
    if not audit.success or not np.isfinite(audit.fun) or abs(audit.x - parameter) > 2e-4:
        raise ValueError('Independent optimizer audit failed')
    if not np.isclose(audited_ll, logll, atol=1e-5, rtol=1e-7):
        raise ValueError('Gaussian likelihood audit failed')
    if abs(parameter) > .999:
        raise ValueError(f'Spatial estimate at optimization boundary: unstable (parameter={parameter:.9f})')
    return {'converged': True, 'convergence_check': 'independent_profile_ML_success_and_likelihood_agreement',
            'optimizer_success': bool(audit.success), 'optimizer_parameter_difference': float(abs(audit.x - parameter))}


def fit_spatial(data: pd.DataFrame, outcome: str, predictors: list[str],
                weight: SpatialWeights, family: str) -> Fit:
    """Fit SAR or SEM; failures propagate to per-model workflow isolation."""
    import spreg
    if family not in ('SAR', 'SEM'):
        raise ValueError('Unknown model family')
    if tuple(data.station_id.astype(str)) != weight.station_ids:
        raise ValueError('Station ordering mismatch')
    x, y = design(data, predictors), align_values(data, outcome, weight)
    w = pysal_weight(weight)
    with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter('always')
        if family == 'SAR':
            model = spreg.ML_Lag(y[:, None], x[:, 1:], w, method='full',
                                 spat_impacts=None, spat_diag=False, name_x=predictors)
        else:
            model = spreg.ML_Error(y[:, None], x[:, 1:], w, method='full', name_x=predictors)
    parameter = float(model.rho if family == 'SAR' else model.lam)
    beta, covariance = model.betas.ravel(), np.asarray(model.vm)
    structural = y - x @ beta[:-1]
    residual = structural - parameter * (weight.matrix @ (y if family == 'SAR' else structural))
    library_residual = model.u.ravel() if family == 'SAR' else model.e_filtered.ravel()
    if not np.isfinite(beta).all() or not np.isfinite(covariance).all() or (np.diag(covariance) <= 0).any():
        raise ValueError('Nonfinite coefficients or invalid covariance')
    if not np.allclose(residual, library_residual, atol=1e-7):
        raise ValueError('Spatial residual definition mismatch')
    audit = audit_optimum(y, x, weight.matrix, family, parameter, float(model.logll))
    metrics = fit_metrics(len(y), len(beta), float(model.logll), residual)
    metrics.update(r_squared=np.nan, adjusted_r_squared=np.nan, pseudo_r_squared=float(model.pr2),
                   native_AIC=float(model.aic), native_BIC=float(model.schwarz),
                   rho=parameter if family == 'SAR' else np.nan,
                   **{'lambda': parameter if family == 'SEM' else np.nan}, **audit)
    messages = sorted(set(str(item.message) for item in caught))
    if getattr(model, 'warning', ''):
        messages.append(str(model.warning))
    return Fit(family, ['const', *predictors, 'rho' if family == 'SAR' else 'lambda'],
               beta, covariance, residual, structural, metrics, '; '.join(messages))


def coefficient_rows(fit: Fit, data: pd.DataFrame, predictors: list[str],
                     scale: str = 'original', hc3: bool = False) -> list[dict]:
    """Exact affine predictor z-score reparameterization (outcome stays original units)."""
    covariance = np.asarray(fit.ols.get_robustcov_results(cov_type='HC3', use_t=True).cov_params()) if hc3 else fit.covariance
    transform = np.eye(len(fit.beta))
    if scale == 'standardized_predictors':
        for j, name in enumerate(predictors, start=1):
            transform[0, j] = data[name].mean()
            transform[j, j] = data[name].std(ddof=0)
    elif scale != 'original':
        raise ValueError('Unknown scaling')
    beta = transform @ fit.beta
    errors = np.sqrt(np.diag(transform @ covariance @ transform.T))
    distribution = t(df=len(data)-len(fit.beta)) if fit.family == 'OLS' else norm
    statistic = beta / errors
    quantile = distribution.ppf(.975)
    return [{**fit.metrics, 'model_type': 'OLS-HC3' if hc3 else fit.family, 'predictor': name,
             'scale': scale, 'coefficient': float(beta[i]), 'std_error': float(errors[i]),
             'z_or_t': float(statistic[i]), 'p_value': float(2 * distribution.sf(abs(statistic[i]))),
             'ci_lower': float(beta[i]-quantile*errors[i]), 'ci_upper': float(beta[i]+quantile*errors[i]),
             'warning': fit.warnings, 'numerical_issue': ''} for i, name in enumerate(fit.terms)]


def residual_moran(residuals: pd.DataFrame, weight: SpatialWeights, outcome: str, config: dict) -> dict:
    """Align residuals by ID and reuse Stage-13 seeds and two-sided permutation method."""
    values = align_values(residuals, 'residual', weight)
    seed = config['random_seed'] + list(GLOBAL_VARIABLES).index(outcome)
    result = global_moran_permutation(values, weight.matrix, config['moran_permutations'], seed)
    return {'residual_moran_I': result.moran_i, 'residual_moran_p': result.permutation_p,
            'random_seed': seed, 'permutations': result.permutations,
            'ordering_hash': ordering_hash(weight.station_ids)}


def ols_diagnostics(fit: Fit, data: pd.DataFrame, predictors: list[str]) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Compute JB, Koenker studentized BP, predictor VIF and Cook D without removal."""
    x = design(data, predictors)
    jb, jb_p, skew, kurtosis = jarque_bera(fit.residual)
    bp, bp_p, f_stat, f_p = het_breuschpagan(fit.residual, x, robust=True)
    diag = dict(jarque_bera=jb, jb_p=jb_p, skew=skew, kurtosis=kurtosis,
                breusch_pagan=bp, bp_p=bp_p, bp_f=f_stat, bp_f_p=f_p, n=len(data))
    vif = pd.DataFrame([{'predictor': name, 'VIF': variance_inflation_factor(x, j),
                          'high_vif': variance_inflation_factor(x, j) > 5} for j, name in enumerate(predictors, start=1)])
    influence = data[['station_id', 'station_name']].copy()
    influence['cooks_distance'] = fit.ols.get_influence().cooks_distance[0]
    influence['threshold'] = 4 / len(data)
    influence['influential'] = influence.cooks_distance > influence.threshold
    influence['automatically_removed'] = False
    return diag, vif, influence


def lm_diagnostics(data: pd.DataFrame, outcome: str, predictors: list[str], weight: SpatialWeights) -> list[dict]:
    """Classical and robust LM lag/error diagnostics; robust refers to alternative spatial model, not HC3."""
    import spreg
    if tuple(data.station_id.astype(str)) != weight.station_ids:
        raise ValueError('LM station ordering mismatch')
    model = spreg.OLS(data[outcome].to_numpy(float)[:, None], data[predictors].to_numpy(float), nonspat_diag=False)
    tests = spreg.LMtests(model, pysal_weight(weight), tests=['lme', 'lml', 'rlme', 'rlml'])
    return [{'test': name, 'statistic': float(getattr(tests, name)[0]),
             'p_value': float(getattr(tests, name)[1]), 'status': 'ok'} for name in ('lme', 'lml', 'rlme', 'rlml')]
