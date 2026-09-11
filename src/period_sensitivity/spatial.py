"""Fixed-geometry spatial and coastal period sensitivity; explicit operational classifications."""
from __future__ import annotations

import numpy as np
import pandas as pd
from src.common_period_spatial.statistics import build_networks, global_results, duplication_sensitivity, KMA_VARIABLES
from src.spatial.coastal_analysis import continuous_associations, coastal_comparisons
from src.period_sensitivity.analysis import sign_summary, tag

VARIABLES = [*KMA_VARIABLES, 'nasa_tavg_sen_slope']
TRAJECTORY_KEYS = ['source','representation','variable','weight_variant']


def networks(stations: pd.DataFrame, config: dict) -> tuple[dict, dict, pd.DataFrame]:
    """Build two geometries once, then reuse exactly the same matrices for all five windows."""
    grids=stations.drop_duplicates('nasa_grid_id').sort_values('nasa_grid_id')[['nasa_grid_id','nasa_grid_latitude','nasa_grid_longitude']].rename(
        columns={'nasa_grid_id':'station_id','nasa_grid_latitude':'latitude','nasa_grid_longitude':'longitude'})
    chosen=[config['main_weight'],*config['sensitivity_weights']]
    outputs=[]; summaries=[]
    for data,representation in [(stations,'STATION_LINKED'),(grids,'UNIQUE_GRID')]:
        _, all_weights, summary=build_networks(data,representation)
        outputs.append({key:all_weights[key] for key in chosen})
        summaries.append(summary.loc[summary.weight_variant.isin(chosen)])
    return outputs[0],outputs[1],pd.concat(summaries,ignore_index=True)


def spatial_master(stations: pd.DataFrame, products: dict) -> pd.DataFrame:
    """Align window-specific station estimates with fixed metadata, never change the station set."""
    master=stations.set_index('station_id').copy()
    trends=products['temperature_trends']
    for source in ('KMA','NASA'):
        for metric in ('TAVG','TMAX','TMIN'):
            group=trends.loc[trends.source.eq(source)&trends.metric.eq(metric)].set_index('station_id')
            master[f'{source.lower()}_{metric.lower()}_sen_slope']=group.sen_slope_per_decade
    val=products['nasa_kma_validation'].loc[lambda d:d.metric.eq('TAVG')].set_index('station_id')
    for name in ('bias','rmse'):
        master[f'tavg_{name}']=val[name]
    for proxy,dest in [('TMAX_GE_33','days_tmax_ge_33_kma_slope'),('TMIN_GE_25','days_tmin_ge_25_kma_slope')]:
        master[dest]=products['threshold_trends'].loc[lambda d:d.source.eq('KMA')&d.threshold.eq(proxy)].set_index('station_id').sen_slope_per_decade
    master['tmin_minus_tmax']=master.kma_tmin_sen_slope-master.kma_tmax_sen_slope
    master['dtr_slope']=products['dtr_trends'].loc[lambda d:d.source.eq('KMA')].set_index('station_id').sen_slope_per_decade
    if not np.isfinite(master[VARIABLES].to_numpy()).all():
        raise ValueError('Missing spatial estimate: cannot reduce the fixed cohort')
    return master.reset_index()


def analyze_spatial(master: pd.DataFrame, sn: dict, gn: dict, config: dict, window: dict) -> dict:
    """Evaluate fixed weights with historical metric seeds, separate unique-grid NASA TAVG."""
    if master.groupby('nasa_grid_id').nasa_tavg_sen_slope.nunique().gt(1).any():
        raise ValueError('Shared grid slopes disagree')
    grids=master.drop_duplicates('nasa_grid_id').sort_values('nasa_grid_id')
    grids=grids.drop(columns=['station_id','latitude','longitude']).rename(columns={
        'nasa_grid_id':'station_id','nasa_grid_latitude':'latitude','nasa_grid_longitude':'longitude'})
    g=pd.concat([global_results(master,sn,VARIABLES,'KMA','STATION_LINKED',config),
                 global_results(grids,gn,['nasa_tavg_sen_slope'],'NASA','UNIQUE_GRID',config)],ignore_index=True)
    g.loc[g.variable.eq('nasa_tavg_sen_slope'),'source']='NASA'
    g.loc[g.variable.isin(['tavg_bias','tavg_rmse']),'source']='NASA-KMA'
    thresholds=[config['main_coastal_threshold_km']]
    if window['start_year'] in config['representative_start_years']:
        thresholds+=config['coastal_sensitivity_thresholds_km']
    coast=coastal_comparisons(master,thresholds,config['alpha'])
    coast['fdr_family']=coast.threshold_km.map(lambda t:f'{window["window_id"]}|coast_{t}|9_metrics')
    return {name:tag(frame,window) for name,frame in {'spatial_station_values':master,'global_morans_i':g,
        'nasa_grid_spatial':duplication_sensitivity(g),'coastal_associations':continuous_associations(master),
        'coastal_inland_comparison':coast}.items()}


def period_class(values: np.ndarray, pvalues: np.ndarray, config: dict) -> str:
    """Prespecified sign-first rule; partial significance transitions always flagged as period-sensitive."""
    a=np.asarray(values,float); p=np.asarray(pvalues,float)
    signs=sign_summary(a)
    if not np.isfinite(p).all() or len(a)!=len(p):
        raise ValueError('Invalid paired period statistics')
    sig=p<config['alpha']; fraction=config['spatial_stable_fraction']
    if signs['sign_change_count']:
        return 'DIRECTION_SENSITIVE'
    if (sig.any() and not sig.all()) or np.ptp(a)>config['spatial_large_I_range']:
        return 'PERIOD_SENSITIVE'
    if ((a>0)&sig).mean()>=fraction:
        return 'SPATIALLY_STABLE_POSITIVE'
    if (~sig).mean()>=fraction:
        return 'ROBUST_NON_SIGNIFICANT'
    return 'PERIOD_SENSITIVE'


def trajectories(table: pd.DataFrame, config: dict) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Store five I/p estimates and every adjacent-start significance transition in both directions."""
    rows=[]; transitions=[]
    for key,g in table.groupby(TRAJECTORY_KEYS,sort=True):
        g=g.sort_values('start_year')
        if len(g)!=5 or g.start_year.nunique()!=5:
            raise ValueError('Moran trajectory missing/duplicated windows')
        meta=dict(zip(TRAJECTORY_KEYS,key)); a=g.Moran_I.to_numpy(); p=g.permutation_p.to_numpy()
        row={**meta,**{f'I_{y}':v for y,v in zip(g.start_year,a)},**{f'p_{y}':v for y,v in zip(g.start_year,p)},
             'I_min':a.min(),'I_max':a.max(),'I_range':np.ptp(a),'significant_window_count':int((p<config['alpha']).sum()),
             **sign_summary(a),'period_robustness':period_class(a,p,config)}
        rows.append(row)
        records=g.to_dict('records')
        for left,right in zip(records,records[1:]):
            before=left['permutation_p']<config['alpha']; after=right['permutation_p']<config['alpha']
            transitions.append({**meta,'from_start_year':left['start_year'],'to_start_year':right['start_year'],
                'from_I':left['Moran_I'],'to_I':right['Moran_I'],'from_p':left['permutation_p'],'to_p':right['permutation_p'],
                'significance_changed':before!=after,'transition':f'{"SIGNIFICANT" if before else "NON_SIGNIFICANT"}_TO_{"SIGNIFICANT" if after else "NON_SIGNIFICANT"}'})
    return pd.DataFrame(rows),pd.DataFrame(transitions)


def association_stability(table: pd.DataFrame, value: str, p: str, keys: list[str], alpha: float) -> pd.DataFrame:
    """Descriptive coastal association/effect direction and significance changes across windows."""
    rows=[]
    for key,g in table.groupby(keys,sort=True):
        g=g.sort_values('start_year'); a=g[value].to_numpy(float); significant=g[p]<alpha
        n=int(significant.sum()); signs=sign_summary(a)
        label='DIRECTION_SENSITIVE' if signs['sign_change_count'] else 'PERIOD_SENSITIVE' if 0<n<len(g) else 'DIRECTION_CONSISTENT_SIGNIFICANT' if n==len(g) else 'ROBUST_NON_SIGNIFICANT'
        rows.append(dict(zip(keys,key if isinstance(key,tuple) else (key,)))|{
            **{f'{value}_{y}':v for y,v in zip(g.start_year,a)},
            **{f'{p}_{y}':v for y,v in zip(g.start_year,g[p])},
            'minimum':a.min(),'median':np.median(a),'maximum':a.max(),'range':np.ptp(a),
            'significant_window_count':n,'period_interpretation':label,**signs})
    return pd.DataFrame(rows)


def summarize_spatial(tables: dict, config: dict) -> dict:
    """Separate period robustness from weight sensitivity; main coastal 30 km stays prespecified."""
    trajectory,transitions=trajectories(tables['global_morans_i'],config)
    coast=tables['coastal_inland_comparison'].loc[lambda d:d.threshold_km.eq(config['main_coastal_threshold_km'])]
    return {'moran_trajectory':trajectory,'spatial_significance_transitions':transitions,
        'spatial_robustness_summary':trajectory.copy(),
        'coastal_association_stability':association_stability(tables['coastal_associations'],'spearman_rho','spearman_p',['variable'],config['alpha']),
        'coastal_group_period_stability':association_stability(coast,'median_difference','fdr_q',['variable','threshold_km'],config['alpha'])}
