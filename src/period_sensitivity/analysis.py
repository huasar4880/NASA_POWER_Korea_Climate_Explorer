"""Fresh window fits and descriptive sensitivity summaries; no I/O or downloads."""
from __future__ import annotations

import numpy as np
import pandas as pd
from src.statistical_analysis import analyze_trend_series, apply_fdr_correction
from src.nationwide.tier_a_analysis import (calculate_station_annual_temperature, calculate_station_trends,
    calculate_temperature_validation, calculate_threshold_annual, SOURCE_DAILY_COLUMNS,
    _season_definition, _expected_season_days)
from src.spatial.associations import calculate_dtr_trends

SEASONS = ['DJF', 'MAM', 'JJA', 'SON']


def correct_families(raw: pd.DataFrame, keys: list[str], alpha: float) -> pd.DataFrame:
    """Always recompute BH from original MK p, explicitly retaining family membership and n."""
    frames = []
    for key, group in raw.groupby(keys, sort=True):
        frame = apply_fdr_correction(group, 'mk_p_value', alpha)
        frame['fdr_family'] = '|'.join(map(str, key if isinstance(key, tuple) else (key,)))
        frame['fdr_family_n'] = len(group)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def fit_groups(annual: pd.DataFrame, keys: list[str], value: str, year: str, alpha: float) -> pd.DataFrame:
    """Fit each annual series afresh with the established OLS/MK/modified-MK/Sen implementation."""
    rows = []
    for key, group in annual.groupby(keys, sort=True):
        group = group.sort_values(year)
        rows.append(dict(zip(keys, key if isinstance(key, tuple) else (key,))) |
                    {'series_mean': group[value].mean(), **analyze_trend_series(group[year], group[value], alpha=alpha)})
    return pd.DataFrame(rows)


def seasonal_annual(prepared: list) -> pd.DataFrame:
    """TAVG only, December to next DJF; incomplete boundary seasons excluded, >=95% valid required."""
    rows = []
    for item in prepared:
        for source, daily in [('KMA', item.kma), ('NASA', item.nasa)]:
            data = daily.join(_season_definition(daily.date))
            column = SOURCE_DAILY_COLUMNS[source]['TAVG']
            for (season, year), group in data.groupby(['season', 'season_year'], sort=True):
                expected = _expected_season_days(season, int(year))
                if len(group) != expected:
                    continue
                valid = group[column].notna().sum()
                rows.append(dict(station_id=item.station_id, source=source, metric='TAVG', season=season,
                                 season_year=year, valid_days=valid, expected_days=expected,
                                 seasonal_mean=group[column].mean() if valid/expected >= .95 else np.nan))
    return pd.DataFrame(rows)


def threshold_annual(prepared: list) -> pd.DataFrame:
    """Preserve the inclusive matched-valid-day proxy; zero valid pairs is missing, never zero events."""
    result = calculate_threshold_annual(prepared)
    result.loc[result.valid_pair_days.eq(0), ['kma_count', 'nasa_count', 'difference']] = np.nan
    return result


def tag(frame: pd.DataFrame, window: dict) -> pd.DataFrame:
    """Attach window metadata without overwriting fit-specific valid n_years (notably DJF)."""
    return frame.assign(**{k:v for k,v in window.items() if k != 'n_years'})


def analyze_window(prepared: list, stations: pd.DataFrame, window: dict, alpha: float) -> dict:
    """Reuse pure prior-stage calculations on this window's daily subset; fresh BH for this cohort."""
    annual = calculate_station_annual_temperature(prepared, stations)
    trend = calculate_station_trends(annual, stations, alpha)
    seasonal = seasonal_annual(prepared)
    seasonal_fit = fit_groups(seasonal, ['station_id','source','metric','season'], 'seasonal_mean','season_year',alpha)
    threshold = threshold_annual(prepared)
    threshold_long = pd.concat([threshold.assign(source=s, count=threshold[f'{s.lower()}_count'])
                               for s in ('KMA','NASA')], ignore_index=True)
    threshold_fit = fit_groups(threshold_long,['station_id','source','threshold'],'count','year',alpha)
    dtr = calculate_dtr_trends(annual, stations, alpha).rename(columns={
        'dtr_fdr_q':'fdr_q_value','dtr_significant_fdr':'significant_fdr'}).assign(metric='DTR')
    result = {'annual_temperature':tag(annual,window), 'seasonal_annual':tag(seasonal,window),
              'threshold_annual':tag(threshold,window),
              'nasa_kma_validation':tag(calculate_temperature_validation(prepared,stations),window)}
    for name, frame, family in [('temperature_trends',trend,['source','metric']),
        ('seasonal_trends',seasonal_fit,['source','metric','season']),
        ('threshold_trends',threshold_fit,['source','threshold']),('dtr_trends',dtr,['source','metric'])]:
        result[name] = correct_families(tag(frame,window), ['window_id',*family], alpha)
    contrast = trend.pivot(index=['station_id','source'],columns='metric',values='sen_slope_per_decade').reset_index()
    contrast['tmin_minus_tmax'] = contrast.TMIN-contrast.TMAX
    result['tmax_tmin_contrast'] = tag(contrast,window)
    return result


def sign_summary(values: np.ndarray) -> dict:
    """Strict signs with zero reported separately; adjacent nonzero sign reversals counted in start order."""
    a = np.asarray(values,float)
    if not np.isfinite(a).all() or not len(a):
        raise ValueError('Stability requires complete finite window estimates')
    signs = np.sign(a); nonzero = signs[signs != 0]
    label = ('POSITIVE_ALL_WINDOWS' if (a>0).all() else 'NEGATIVE_ALL_WINDOWS' if (a<0).all()
             else 'SIGN_SENSITIVE' if (a>0).any() and (a<0).any() else 'ZERO_ALL_WINDOWS' if (a==0).all()
             else 'NONNEGATIVE_WITH_ZERO' if (a>=0).all() else 'NONPOSITIVE_WITH_ZERO')
    return dict(all_positive=bool((a>0).all()), all_negative=bool((a<0).all()), zero_window_count=int((a==0).sum()),
                sign_change_count=int((np.diff(nonzero)!=0).sum()), direction_stability=label)


def significance_class(count: int, total: int) -> str:
    """Five-window descriptive discovery counts, never a probability from independent windows."""
    return ('SIGNIFICANT_ALL_WINDOWS' if count==total else 'MOST_WINDOWS_SIGNIFICANT' if count/total>=.6
            else 'SOME_WINDOWS_SIGNIFICANT' if count else 'NEVER_SIGNIFICANT')


def stability(table: pd.DataFrame, keys: list[str], value: str='sen_slope_per_decade') -> pd.DataFrame:
    """Absolute slope range and reference-window differences; no composite scores or unstable ratios."""
    rows=[]
    for key,g in table.groupby(keys,sort=True):
        g=g.sort_values('start_year')
        if g.start_year.duplicated().any() or set(g.start_year)!={1981,1986,1991,1996,2001}:
            raise ValueError('Exactly five unique prespecified windows required')
        a=g[value].to_numpy(float); by=dict(zip(g.start_year,a))
        row=dict(zip(keys,key if isinstance(key,tuple) else (key,)))
        row.update({f'slope_{y}':v for y,v in by.items()})
        row.update(slope_min=a.min(),slope_median=np.median(a),slope_max=a.max(),slope_range=np.ptp(a),
                   max_abs_difference_from_1981=np.max(np.abs(a-by[1981])),
                   difference_1991_minus_1981=by[1991]-by[1981],difference_2001_minus_1981=by[2001]-by[1981],
                   **sign_summary(a))
        if 'significant_fdr' in g:
            n=int(g.significant_fdr.sum())
            row.update(fdr_significant_window_count=n,fdr_significant_window_fraction=n/len(g),
                       significance_stability=significance_class(n,len(g)))
        if 'sen_ci_lower' in g:
            row['ci_excludes_zero_count']=int(((g.sen_ci_lower>0)|(g.sen_ci_upper<0)).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def distribution_summary(table: pd.DataFrame, keys: list[str], value: str='sen_slope_per_decade') -> pd.DataFrame:
    """Unweighted station distribution per window, not an area-weighted national mean."""
    rows=[]
    for key,g in table.groupby(keys,sort=True):
        a=g[value]; row=dict(zip(keys,key if isinstance(key,tuple) else (key,)))
        row.update(n=len(a),minimum=a.min(),q1=a.quantile(.25),median=a.median(),q3=a.quantile(.75),maximum=a.max(),
                   iqr=a.quantile(.75)-a.quantile(.25),positive_count=int((a>0).sum()),negative_count=int((a<0).sum()))
        if 'significant_fdr' in g:
            row.update(fdr_increasing_count=int((g.significant_fdr & (a>0)).sum()),
                       fdr_decreasing_count=int((g.significant_fdr & (a<0)).sum()))
        rows.append(row)
    return pd.DataFrame(rows)


def validation_stability(table: pd.DataFrame) -> pd.DataFrame:
    """Summarize validation across overlapping windows; changes do not imply accuracy improvement."""
    rows=[]
    for key,g in table.groupby(['station_id','metric'],sort=True):
        row=dict(zip(['station_id','metric'],key))
        for name in ('bias','mae','rmse','pearson_r','spearman_rho'):
            a=g[name]; row.update({f'{name}_{stat}':v for stat,v in
                                  [('min',a.min()),('median',a.median()),('max',a.max()),('range',a.max()-a.min())]})
        rows.append(row)
    return pd.DataFrame(rows)


def trend_consistency(trends: pd.DataFrame) -> pd.DataFrame:
    """Pair NASA and KMA station/window fits without conflating agreement with truth."""
    keys=['station_id','window_id','start_year','metric']
    cols=['sen_slope_per_decade','significant_fdr']
    parts=[trends.loc[trends.source.eq(s),keys+cols].rename(columns={c:f'{s.lower()}_{c}' for c in cols}) for s in ('KMA','NASA')]
    r=parts[0].merge(parts[1],on=keys,validate='one_to_one')
    k,n=r.kma_sen_slope_per_decade,r.nasa_sen_slope_per_decade
    return r.assign(same_direction=np.sign(k)==np.sign(n),both_positive=(k>0)&(n>0),
                    both_significant=r.kma_significant_fdr&r.nasa_significant_fdr)


def dominant_seasons(seasonal: pd.DataFrame) -> pd.DataFrame:
    """Largest KMA TAVG Sen slope; deterministic DJF/MAM/JJA/SON tie order, no p-based selection."""
    data=seasonal.loc[seasonal.source.eq('KMA')].copy()
    data['season_order']=data.season.map({v:i for i,v in enumerate(SEASONS)})
    chosen=data.sort_values(['sen_slope_per_decade','season_order'],ascending=[False,True],kind='stable').drop_duplicates(['station_id','start_year'])
    rows=[]
    for sid,g in chosen.groupby('station_id',sort=True):
        by=dict(zip(g.start_year,g.season)); counts=g.season.value_counts()
        common=min(counts.index,key=lambda s:(-counts[s],SEASONS.index(s)))
        rows.append({'station_id':sid,**{f'dominant_{y}':s for y,s in sorted(by.items())},
                     'most_common_season':common,'most_common_window_count':int(counts[common]),
                     'unique_dominant_seasons':len(counts)})
    return pd.DataFrame(rows)


def summarize(tables: dict, stations: pd.DataFrame) -> dict:
    """Add requested station, national, threshold, seasonal, validation and consistency summaries."""
    result={}
    for name, dest, keys in [('temperature_trends','trend_stability',['station_id','source','metric']),
        ('threshold_trends','threshold_stability',['station_id','source','threshold']),
        ('dtr_trends','dtr_stability',['station_id','source','metric'])]:
        result[dest]=stability(tables[name],keys).merge(stations[['station_id','station_name']],on='station_id',validate='many_to_one')
    result['contrast_stability']=stability(tables['tmax_tmin_contrast'],['station_id','source'],'tmin_minus_tmax')
    result['station_metric_summary']=result['trend_stability'].copy()
    result['station_metric_summary']['range_rank_descending']=result['station_metric_summary'].groupby(['source','metric']).slope_range.rank(method='min',ascending=False)
    for src,dest,keys,value in [('temperature_trends','window_summary',['source','metric'],'sen_slope_per_decade'),
        ('dtr_trends','dtr_summary',['source'],'sen_slope_per_decade'),
        ('tmax_tmin_contrast','contrast_summary',['source'],'tmin_minus_tmax'),
        ('seasonal_trends','seasonal_summary',['source','metric','season'],'sen_slope_per_decade'),
        ('threshold_trends','threshold_window_summary',['source','threshold'],'sen_slope_per_decade')]:
        result[dest]=distribution_summary(tables[src],['window_id','start_year',*keys],value)
    result['national_stability_summary']=distribution_summary(result['trend_stability'],['source','metric'],'slope_range')
    counts=result['trend_stability'].assign(significant_all=lambda d:d.fdr_significant_window_count.eq(5)).groupby(['source','metric']).agg(
        positive_all_count=('all_positive','sum'),negative_all_count=('all_negative','sum'),
        significant_all_count=('significant_all','sum')).reset_index()
    result['national_stability_summary']=result['national_stability_summary'].merge(counts,on=['source','metric'])
    result['validation_stability']=validation_stability(tables['nasa_kma_validation'])
    result['validation_window_summary']=tables['nasa_kma_validation'].groupby(['window_id','start_year','metric']).agg(
        bias_min=('bias','min'),bias_median=('bias','median'),bias_max=('bias','max'),
        rmse_min=('rmse','min'),rmse_median=('rmse','median'),rmse_max=('rmse','max')).reset_index()
    result['nasa_kma_trend_consistency']=trend_consistency(tables['temperature_trends'])
    result['trend_consistency_window_summary']=result['nasa_kma_trend_consistency'].groupby(['window_id','start_year','metric']).agg(
        n=('station_id','size'),same_direction_count=('same_direction','sum'),both_positive_count=('both_positive','sum'),
        both_significant_count=('both_significant','sum')).reset_index()
    result['trend_consistency_window_summary']['direction_disagreement_count']=result['trend_consistency_window_summary'].n-result['trend_consistency_window_summary'].same_direction_count
    result['dominant_season_stability']=dominant_seasons(tables['seasonal_trends'])
    return result
