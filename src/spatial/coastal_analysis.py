"""Continuous coastal-distance associations and operational group sensitivity."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from src.spatial.associations import calculate_association
from src.spatial.coastline import station_distances

METRICS = {'kma_tavg_sen_slope':'TAVG (°C/decade)', 'kma_tmax_sen_slope':'TMAX (°C/decade)',
           'kma_tmin_sen_slope':'TMIN (°C/decade)', 'tmin_minus_tmax':'TMIN−TMAX contrast (°C/decade)',
           'dtr_slope':'DTR (°C/decade)', 'days_tmax_ge_33_kma_slope':'33°C proxy (days/decade)',
           'days_tmin_ge_25_kma_slope':'25°C proxy (days/decade)', 'tavg_bias':'Bias (°C)', 'tavg_rmse':'RMSE (°C)'}


def classify_coastal(distances: pd.Series, threshold: float) -> pd.Series:
    """Coastal includes equality; nonfinite/negative distances cannot be classified."""
    if threshold <= 0 or not np.isfinite(distances).all() or (distances < 0).any():
        raise ValueError('Invalid coastal threshold or distances')
    return pd.Series(np.where(distances <= threshold, 'Coastal', 'Inland'), index=distances.index)


def compare_groups(coastal: np.ndarray, inland: np.ndarray) -> dict:
    """Two-sided asymptotic tie-corrected MWU; positive rank-biserial means coastal higher."""
    coastal, inland = np.asarray(coastal,float), np.asarray(inland,float)
    coastal, inland = coastal[np.isfinite(coastal)], inland[np.isfinite(inland)]
    if not len(coastal) or not len(inland):
        return {'raw_p':np.nan, 'rank_biserial':np.nan, 'u_statistic':np.nan, 'status':'insufficient_groups'}
    u, p = mannwhitneyu(coastal, inland, alternative='two-sided', method='asymptotic', use_continuity=True)
    return {'raw_p':float(p), 'rank_biserial':float(2*u/(len(coastal)*len(inland))-1),
            'u_statistic':float(u), 'status':'ok'}


def fdr_comparisons(table: pd.DataFrame, alpha: float = .05) -> pd.DataFrame:
    """BH within the nine metric tests at each threshold (not pooled discoveries)."""
    result = table.copy()
    result['fdr_q'] = np.nan
    result['fdr_significant'] = False
    for _, indices in result.groupby('threshold_km').groups.items():
        valid = result.loc[indices,'raw_p'].dropna()
        if len(valid):
            reject, q, _, _ = multipletests(valid, alpha=alpha, method='fdr_bh')
            result.loc[valid.index, 'fdr_q'] = q
            result.loc[valid.index, 'fdr_significant'] = reject
    return result


def coastal_comparisons(data: pd.DataFrame, thresholds: list, alpha: float) -> pd.DataFrame:
    """Summarize both station groups per metric with valid n, means, medians and IQRs."""
    rows = []
    for threshold in thresholds:
        groups = classify_coastal(data.distance_to_coast_km, threshold)
        for variable in METRICS:
            row = {'variable':variable, 'threshold_km':threshold}
            arrays = []
            for group in ('Coastal','Inland'):
                values = pd.to_numeric(data.loc[groups.eq(group),variable], errors='coerce').dropna().to_numpy()
                arrays.append(values)
                prefix = group.lower()
                row.update({f'{prefix}_n':len(values), f'{prefix}_mean':float(values.mean()) if len(values) else np.nan,
                            f'{prefix}_median':float(np.median(values)) if len(values) else np.nan,
                            f'{prefix}_iqr':float(np.ptp(np.quantile(values,[.25,.75]))) if len(values) else np.nan})
            row.update(compare_groups(*arrays))
            row['median_difference'] = row['coastal_median'] - row['inland_median']
            rows.append(row)
    return fdr_comparisons(pd.DataFrame(rows), alpha)


def select_main_threshold(classification: pd.DataFrame, config: dict) -> float:
    """Prefer 30 km if both n>=5; otherwise choose best balance, without outcome tests."""
    sizes = classification.groupby(['threshold_km','coastal_group']).size().unstack(fill_value=0).reindex(columns=['Coastal','Inland'],fill_value=0)
    eligible = sizes[sizes.min(axis=1) >= config['minimum_group_n']]
    if eligible.empty:
        raise ValueError('No coastal threshold has adequate group size')
    preferred = config['preferred_main_threshold_km']
    if preferred in eligible.index:
        return float(preferred)
    balance = eligible.min(axis=1).sort_values(ascending=False, kind='stable')
    return float(balance.index[0])


def threshold_consistency(comparison: pd.DataFrame) -> pd.DataFrame:
    """Flag threshold sensitivity using FDR; never select thresholds by significance."""
    result = comparison.copy()
    for variable, group in result.groupby('variable'):
        signs = np.sign(group.median_difference)
        same_direction = (signs > 0).all() or (signs < 0).all()
        significant_count = int(group.fdr_significant.sum())
        if 0 < significant_count < len(group):
            flag = 'threshold-sensitive'
        elif same_direction:
            flag = 'threshold-robust tendency' if significant_count == len(group) else 'direction-consistent; not FDR significant'
        else:
            flag = 'inconsistent direction'
        result.loc[group.index,'threshold_interpretation'] = flag
    return result


def continuous_associations(data: pd.DataFrame) -> pd.DataFrame:
    """Pearson/Spearman and simple OLS with 95% slope CI (station independence assumption)."""
    rows = []
    for variable in METRICS:
        pair = data[['distance_to_coast_km',variable]].replace([np.inf,-np.inf],np.nan).dropna()
        result = calculate_association(pair, 'distance_to_coast_km', variable)
        result['variable'] = variable
        if len(pair) >= 3 and pair.distance_to_coast_km.nunique() > 1:
            fit = sm.OLS(pair[variable].to_numpy(), sm.add_constant(pair.distance_to_coast_km.to_numpy())).fit()
            ci = fit.conf_int(alpha=.05)[1]
            result.update({'slope_ci_lower':float(ci[0]),'slope_ci_upper':float(ci[1]),'slope_unit':f'{METRICS[variable]} per km'})
        rows.append(result)
    return pd.DataFrame(rows)


def multivariable_models(data: pd.DataFrame) -> pd.DataFrame:
    """Prespecified TAVG, TMIN and Bias OLS; no automated feature selection or causal claim."""
    rows = []
    predictors = ['distance_to_coast_km','latitude','elevation_m']
    for variable in ('kma_tavg_sen_slope','kma_tmin_sen_slope','tavg_bias'):
        usable = data[[variable,*predictors]].replace([np.inf,-np.inf],np.nan).dropna()
        design = sm.add_constant(usable[predictors], has_constant='add')
        if len(usable) <= len(design.columns) or np.linalg.matrix_rank(design) < len(design.columns):
            rows.append({'variable':variable,'status':'insufficient sample or singular design','n':len(usable)})
            continue
        fit = sm.OLS(usable[variable], design).fit()
        ci = fit.conf_int()
        for term in fit.params.index:
            rows.append({'variable':variable,'term':term,'coefficient':fit.params[term],
                         'ci_lower':ci.loc[term,0],'ci_upper':ci.loc[term,1],'p_value':fit.pvalues[term],
                         'r_squared':fit.rsquared,'n':len(usable),'status':'exploratory OLS; spatially independent errors assumed'})
    return pd.DataFrame(rows)


def calculate_coastal(master: pd.DataFrame, coast: dict, config: dict) -> dict[str,pd.DataFrame]:
    """Compose distance, 20/30/50 km sensitivity, association and confounding summaries."""
    distances = station_distances(master, coast)
    data = master.merge(distances[['station_id','distance_to_coast_km']], on='station_id', validate='one_to_one')
    classes = []
    for threshold in config['coastal_thresholds_km']:
        frame = distances.copy()
        frame['threshold_km'] = threshold
        frame['coastal_group'] = classify_coastal(frame.distance_to_coast_km, threshold)
        classes.append(frame)
    classification = pd.concat(classes,ignore_index=True)
    main = select_main_threshold(classification,config)
    sensitivity = threshold_consistency(coastal_comparisons(data,config['coastal_thresholds_km'],config['alpha']))
    chars = []
    for (threshold,group), frame in classification.groupby(['threshold_km','coastal_group']):
        for region, n in frame.groupby('region_level1').size().items():
            chars.append({'threshold_km':threshold,'group':group,'characteristic':'region','category':region,'n':n})
        for column in ('latitude','elevation_m','distance_to_coast_km'):
            chars.append({'threshold_km':threshold,'group':group,'characteristic':column,'category':'all',
                          'n':len(frame),'mean':frame[column].mean(),'median':frame[column].median(),
                          'iqr':frame[column].quantile(.75)-frame[column].quantile(.25)})
    return {'station_coastal_distance':distances,'coastal_classification_sensitivity':classification,
            'coastal_continuous_associations':continuous_associations(data),
            'coastal_inland_comparison':sensitivity[sensitivity.threshold_km.eq(main)].copy(),
            'coastal_threshold_sensitivity':sensitivity,'coastal_group_characteristics':pd.DataFrame(chars),
            'coastal_multivariable_models':multivariable_models(data)}
