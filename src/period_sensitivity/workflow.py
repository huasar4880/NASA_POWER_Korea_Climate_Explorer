"""Fail-closed Stage18 orchestration over immutable saved observations, with no network path."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from src.config import PROJECT_ROOT
from src.period_sensitivity.data import (load_config,load_inputs,load_daily,windows,snapshot,subset_window,
    prepared_station,quality_by_window,verify_grid_equality,DATA_DIR,TABLE_DIR,MANIFEST,TABLE_NAMES,STATION_SOURCE)
from src.period_sensitivity.analysis import analyze_window,summarize,tag,correct_families
from src.period_sensitivity.spatial import networks,spatial_master,analyze_spatial,summarize_spatial
from src.nationwide.tier_a_pipeline import _atomic_csv,_atomic_json
from src.spatial.robustness_audit import sha256,check_snapshot

PREFIX='period_sensitivity_'


def prepare_plan(root: Path=PROJECT_ROOT) -> tuple:
    """Check all caches and fixed station/grid networks without writes, fitting or HTTP requests."""
    config=load_config(root); stations,old,hashes=load_inputs(root); daily,cache_hashes=load_daily(stations,root)
    hashes.update(cache_hashes); win=windows(config); sn,gn,network_summary=networks(stations,config)
    n=len(stations); w=len(win)
    plan={'status':'dry_run','station_source':str(STATION_SOURCE),'station_count':n,'tier_b_count':0,'unique_NASA_grid_count':stations.nasa_grid_id.nunique(),
          'windows':win.to_dict('records'),'end_year':config['end_year'],'NASA_API_calls':0,'KMA_API_calls':0,
          'cache_files':sorted(cache_hashes),'expected_daily_subsets':n*w,
          'fit_counts':{'temperature':n*2*3*w,'seasonal_TAVG':n*2*4*w,'threshold':n*2*3*w,'DTR':n*2*w},
          'expected_global_rows':(10*len(sn)+len(gn))*w,'station_weights':list(sn),'grid_weights':list(gn),
          'output_directories':[str(DATA_DIR),str(TABLE_DIR),'output/charts/period_sensitivity','output/reports/period_sensitivity'],
          'expected_outputs':{'tables':[f'{PREFIX}{name}.csv' for name in TABLE_NAMES],'PNG_charts':15,'HTML_trajectories':1,'HTML_maps':9,
                              'reports':['trend_period_sensitivity_report.md','trend_period_sensitivity_report.html'],
                              'manifest':str(MANIFEST)}}
    plan['total_trend_fits']=sum(plan['fit_counts'].values())
    return config,stations,old,hashes,daily,win,sn,gn,network_summary,plan


def reproduction(tables: dict,old: dict,alpha: float) -> pd.DataFrame:
    """Check old overlapping estimates, while 1991 FDR is freshly recomputed on 45 rather than 51."""
    rows=[]
    def compare(label: str,a: np.ndarray,b: np.ndarray) -> None:
        """Record numeric reproduction with strict tolerances and stop on a changed established result."""
        a=np.asarray(a,float); b=np.asarray(b,float)
        ok=a.shape==b.shape and np.allclose(a,b,rtol=0,atol=1e-10,equal_nan=True)
        rows.append({'check':label,'n_values':a.size,'max_absolute_difference':float(np.nanmax(np.abs(a-b))) if a.size else 0,'passed':ok})
        if not ok:
            raise ValueError(f'Existing result reproduction failed: {label}')
    keys=['station_id','metric']; new=tables['temperature_trends']
    old81=old['trends_1981'].sort_values(keys)
    for source in ('KMA','NASA'):
        a=new.loc[new.start_year.eq(1981)&new.source.eq(source)].sort_values(keys)
        for name,oldname in [('sen_slope_per_decade','sen_slope_per_decade'),('sen_ci_lower','sen_ci_lower'),
            ('sen_ci_upper','sen_ci_upper'),('mk_p_value','mk_p'),('fdr_q_value','fdr_q')]:
            compare(f'1981_{source}_{name}',a[name],old81[f'{source.lower()}_{oldname}'])
    a=new.loc[new.start_year.eq(1991)].sort_values(['station_id','source','metric'])
    b=old['trends_1991'].sort_values(['station_id','source','metric'])
    for name in ('sen_slope_per_decade','sen_ci_lower','sen_ci_upper','mk_p_value'):
        compare(f'1991_{name}',a[name],b[name])
    fresh=correct_families(b,['source','metric'],alpha).sort_values(['station_id','source','metric'])
    compare('1991_BH_recomputed_on_45_not_saved_51',a.fdr_q_value,fresh.fdr_q_value)
    val=tables['nasa_kma_validation'].loc[lambda d:d.start_year.eq(1981)].sort_values(keys)
    for name,oldname in [('bias','bias'),('mae','mae'),('rmse','rmse'),('pearson_r','pearson'),('spearman_rho','spearman')]:
        compare(f'1981_validation_{name}',val[name],old81[f'nasa_kma_{oldname}'])
    g=tables['global_morans_i'].loc[lambda d:d.weight_variant.eq('directed_knn_k4')&d.representation.eq('STATION_LINKED')]
    for year,ref,icol,pcol in [(1981,old['moran_1981'],'moran_i','permutation_p'),(1991,old['bridge_1991'],'I_45_1991','p_45_1991')]:
        a=g.loc[g.start_year.eq(year)].set_index('variable').loc[ref.variable]
        compare(f'{year}_Moran_I',a.Moran_I,ref[icol]); compare(f'{year}_Moran_p',a.permutation_p,ref[pcol])
    return pd.DataFrame(rows)


def validate_products(t: dict,plan: dict) -> None:
    """Gate fixed membership, complete families, valid statistics and all table inventories."""
    if set(t)!=set(TABLE_NAMES):
        raise ValueError('Expected Stage18 table inventory differs from generated products')
    n=plan['station_count']; master=t['station_master']
    if len(master)!=n*5 or master.duplicated(['station_id','window_id']).any():
        raise ValueError('Station/window master dimensions failed')
    sets=master.groupby('window_id').station_id.agg(set).tolist()
    if any(s!=sets[0] for s in sets) or not master.data_quality_flag.eq('PASS').all():
        raise ValueError('Fixed cohort / quality gate failed')
    for name,count in [('temperature_trends',n*30),('seasonal_trends',n*40),('threshold_trends',n*30),('dtr_trends',n*10)]:
        frame=t[name]
        if len(frame)!=count or not frame.fdr_family_n.eq(n).all() or not frame.fdr_q_value.between(0,1).all():
            raise ValueError(f'Fit count / BH family gate failed: {name}')
        if not np.isfinite(frame[['sen_slope_per_decade','sen_ci_lower','sen_ci_upper','mk_p_value']]).all().all():
            raise ValueError(f'Nonfinite trend statistic: {name}')
    v=t['nasa_kma_validation']
    if not ((v.n_pairs>0)&(v.rmse+1e-12>=v.mae)).all() or not v[['pearson_r','spearman_rho']].apply(lambda a:a.between(-1,1)).all().all():
        raise ValueError('Validation metric sanity failed')
    g=t['global_morans_i']
    if len(g)!=plan['expected_global_rows'] or not np.isfinite(g.Moran_I).all() or not g.permutation_p.between(0,1).all():
        raise ValueError('Moran count/value sanity failed')
    if not t['grid_series_equality'].series_equal.all():
        raise ValueError('NASA grid equality failed')


def run_analysis(root: Path=PROJECT_ROOT, *, dry_run: bool=False) -> dict:
    """Recompute five windows and publish only isolated outputs after all gates pass."""
    config,stations,old,hashes,daily,win,sn,gn,ns,plan=prepare_plan(root)
    if dry_run:
        return plan
    protected=snapshot(root)
    manifest={**plan,'status':'pending','input_hashes':hashes,'configuration':config,
        'FDR':'BH from original MK p within window x source x metric (season / proxy adds family dimension); 45 stations each. Coastal BH within window x threshold across 9 metrics.',
        'methods':'OLS, original MK, conditional Hamed-Rao, Sen slope and 95% CI; °C/decade or proxy days/decade. DTR fit on annual Tmax minus Tmin. No smoothing before trend fits.',
        'missing_rule':'NaN unchanged; no inf or sentinel; no scaling or zero fill; zero valid threshold pairs becomes NaN.',
        'grid_definition':'Fixed project-inferred native MERRA-2 centres, separately reverified daily equality each window; not API-returned metadata or a claim of global product invariance.',
        'period_class_rule':'Sign reversal first; any significance transition or I range >0.2 PERIOD_SENSITIVE; otherwise >=80% positive significant SPATIALLY_STABLE_POSITIVE or >=80% nonsignificant ROBUST_NON_SIGNIFICANT.',
        'scope':'Fixed Final A; start year and window length confounded; nested nonindependent windows; no causality/acceleration/end-year conclusion.'}
    _atomic_json(manifest,root/MANIFEST)
    collected={}; generated=[]
    for window in win.to_dict('records'):
        print(f'Stage18 {window["window_id"]}: cache subset, quality, fresh trends and spatial tests',flush=True)
        prepared=[]; masters=[]; quality=[]; annual_quality=[]; subsets={}
        for _,station in stations.iterrows():
            frame=subset_window(daily[station.station_id],window); subsets[station.station_id]=frame
            q,aq=quality_by_window(frame,window); quality.append(tag(q,window)); annual_quality.append(tag(aq,window))
            if not q.data_quality_flag.eq('PASS').all():
                raise ValueError(f'Window quality needs review; fixed station set not reduced: {station.station_id}/{window["window_id"]}')
            row={**station.to_dict(),**window,'data_quality_flag':'PASS'}
            for item in q.to_dict('records'):
                for metric in ('tavg','tmax','tmin'):
                    row[f'{item["source"].lower()}_{metric}_valid_days']=item[f'{metric}_valid_days']
            masters.append(row)
            path=root/DATA_DIR/window['window_id']/f'{station.station_id}_nasa_kma_temperature_{window["start_year"]}_2025.csv'
            _atomic_csv(frame,path); generated.append(path.relative_to(root).as_posix())
            prepared.append(prepared_station(frame,station,path))
        products=analyze_window(prepared,stations,window,config['alpha'])
        products.update(station_master=pd.DataFrame(masters),data_quality=pd.concat(quality,ignore_index=True),
                        annual_completeness=pd.concat(annual_quality,ignore_index=True),grid_series_equality=verify_grid_equality(stations,subsets,window))
        products.update(analyze_spatial(spatial_master(stations,products),sn,gn,config,window))
        for name,frame in products.items():
            collected.setdefault(name,[]).append(frame)
    tables={name:pd.concat(frames,ignore_index=True) for name,frames in collected.items()}
    tables.update(windows=win,network_summary=ns)
    tables.update(summarize(tables,stations)); tables.update(summarize_spatial(tables,config))
    tables['historical_reproduction']=reproduction(tables,old,config['alpha'])
    validate_products(tables,plan)
    for name in sorted(tables):
        path=root/TABLE_DIR/f'{PREFIX}{name}.csv'; _atomic_csv(tables[name],path); generated.append(path.relative_to(root).as_posix())
    saved={name:pd.read_csv(root/TABLE_DIR/f'{PREFIX}{name}.csv',dtype={'station_id':str}) for name in tables}
    from src.period_sensitivity.artifacts import save_charts,write_reports
    generated+=save_charts(saved,root)+write_reports(saved,root)
    changed=check_snapshot(root,protected)
    processing=sorted((root/'src/period_sensitivity').glob('*.py'))
    processing += [root/p for p in ('src/nationwide/tier_a_analysis.py','src/statistical_analysis.py','src/validation.py',
        'src/spatial/associations.py','src/spatial/autocorrelation.py','src/spatial/coastal_analysis.py',
        'src/common_period_spatial/statistics.py','src/spatial_numerical/weights.py','src/common_period/grid.py')]
    manifest.update(status='completed' if not changed else 'protection_failed',table_names=sorted(tables),
        table_rows={name:len(frame) for name,frame in tables.items()},
        protected_files_count=len(protected),protected_files_changed=changed,output_files=generated,
        output_hashes={p:sha256(root/p) for p in generated},processing_hashes={p.relative_to(root).as_posix():sha256(p) for p in processing})
    _atomic_json(manifest,root/MANIFEST)
    if changed:
        raise ValueError('Prior-stage files changed; publication withheld')
    return manifest
