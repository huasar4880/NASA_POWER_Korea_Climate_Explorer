"""Read-only saved-result access and deterministic scientific figures/reports for Stage18."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from src.config import PROJECT_ROOT
from src.period_sensitivity.data import TABLE_DIR,CHART_DIR,REPORT_DIR,MANIFEST,WARNING,TABLE_NAMES
from src.spatial.robustness_audit import sha256
from src.spatial.robustness_reporting import markdown_table
from src.common_period_spatial.artifacts import point_map as established_point_map

PREFIX='period_sensitivity_'
PNGS=['kma_tavg_median_slope_by_start_year','kma_tmax_tmin_median_slope_by_start_year',
      'tavg_slope_range_distribution','tavg_slope_heatmap','dtr_median_slope_by_start_year',
      'seasonal_median_slope_by_start_year','threshold_33c_by_start_year','threshold_25c_by_start_year',
      'nasa_kma_tavg_trend_by_start_year','bias_rmse_by_start_year','kma_tavg_moran_trajectory',
      'spatial_moran_trajectory_heatmap','bias_rmse_moran_trajectory','coast_association_trajectory',
      'significance_stability_heatmap']
MAPS=[f'{metric}_start_{year}_map' for year in (1981,1991,2001) for metric in ('kma_tavg','bias','rmse')]
LIMITS=('시작연도와 기간 길이가 함께 변하며 모든 window가 강하게 중첩됩니다. 유의 window 수는 독립 반복실험의 확률이 아닙니다. '
        '차이를 가속화·인과효과·예측력으로 해석하지 않습니다. 관측소별 중앙값은 면적가중 전국 평균이 아닙니다. '
        'NASA 격자 평균과 ASOS 지점관측은 대표성이 다르고, 지형·고도·시각체계·관측소 이력·잔여 결측이 영향을 줄 수 있습니다. '
        'Original MK의 BH-FDR를 주 결과로 사용하며 modified MK는 보조 통계입니다. Global Moran 및 해안 상관의 p는 탐색적 raw p입니다. '
        'NASA 고유격자는 프로젝트에서 추정한 native 중심과 매 기간 동일 일자료 검증에 근거하며 전 기간 제품 불변을 보장하지 않습니다. '
        '고온일수는 유효 matched pair 기반 proxy이지 공식 폭염·열대야 통계가 아닙니다. 종료연도 민감성은 검증하지 않았습니다.')


def load_tables(root: Path=PROJECT_ROOT) -> dict:
    """Load only manifest-allowlisted checksummed tables; incomplete publication fails closed."""
    m=json.loads((root/MANIFEST).read_text())
    if m.get('status')!='completed':
        raise ValueError('Stage18 incomplete; saved tables withheld')
    if set(m['table_names'])!=set(TABLE_NAMES):
        raise ValueError('Stage18 table inventory incomplete')
    result={}
    for name in m['table_names']:
        if not name.replace('_','').isalnum():
            raise ValueError('Invalid table name')
        path=TABLE_DIR/f'{PREFIX}{name}.csv'
        if sha256(root/path)!=m['output_hashes'][path.as_posix()]:
            raise ValueError(f'Stage18 checksum mismatch: {path.name}')
        result[name]=pd.read_csv(root/path,dtype={'station_id':str})
    required={'station_master','temperature_trends','global_morans_i','nasa_kma_validation','trend_stability'}
    if not required.issubset(result):
        raise ValueError('Stage18 required tables missing')
    return result


def compare_windows(t: dict, start_a: int, start_b: int) -> dict:
    """Read-only A/B differences and FDR transitions from stored estimates, never refit in the UI."""
    results={}
    specs=[('temperature_trends',['station_id','source','metric'],['sen_slope_per_decade','significant_fdr']),
           ('global_morans_i',['source','representation','variable','weight_variant'],['Moran_I','permutation_p']),
           ('nasa_kma_validation',['station_id','metric'],['bias','rmse'])]
    for name,keys,columns in specs:
        frame=t[name]
        if not {start_a,start_b}.issubset(set(frame.start_year)):
            raise ValueError('Requested window not available')
        a=frame.loc[frame.start_year.eq(start_a),keys+columns]; b=frame.loc[frame.start_year.eq(start_b),keys+columns]
        merged=a.merge(b,on=keys,suffixes=('_A','_B'),validate='one_to_one')
        for column in columns:
            if column=='significant_fdr':
                merged['FDR_status_changed']=merged.significant_fdr_A!=merged.significant_fdr_B
            else:
                merged[f'{column}_B_minus_A']=merged[f'{column}_B']-merged[f'{column}_A']
        results[name]=merged
    return results


def trajectory_figure(trends: pd.DataFrame) -> go.Figure:
    """Thin station curves and bold median, with an optional station picker and fixed template."""
    data=trends.loc[trends.source.eq('KMA')&trends.metric.eq('TAVG')]
    fig=go.Figure(layout={'template':'plotly_white'}); labels=[]
    for sid,g in data.groupby('station_id',sort=True):
        g=g.sort_values('start_year'); label=f'{sid} {g.station_name.iloc[0]}' if 'station_name' in g else str(sid)
        labels.append(label)
        fig.add_scatter(x=g.start_year,y=g.sen_slope_per_decade,name=label,mode='lines+markers',line=dict(width=1),opacity=.3)
    median=data.groupby('start_year').sen_slope_per_decade.median()
    fig.add_scatter(x=median.index,y=median.values,name='Station median',mode='lines+markers',line=dict(color='#111827',width=4))
    buttons=[dict(label='All stations',method='update',args=[{'visible':[True]*(len(labels)+1)}])]
    buttons += [dict(label=label,method='update',args=[{'visible':[j==i for j in range(len(labels))]+[True]}]) for i,label in enumerate(labels)]
    fig.update_layout(template='plotly_white',title='KMA TAVG station slopes | fixed end 2025',
        xaxis_title='Start year (nested windows)',yaxis_title='Sen slope (°C/decade)',height=660,
        updatemenus=[dict(buttons=buttons,x=0,y=1.15)],showlegend=False)
    return fig


def point_map(data: pd.DataFrame,column: str,start: int,color_range: tuple[float,float]) -> go.Figure:
    """Reuse established point-only maps, overriding their old period label explicitly."""
    fig=established_point_map(data,column,column,color_range=color_range)
    # Replace, rather than recursively merge, any process-wide template inherited by the old helper.
    fig.layout.template=None
    fig.update_layout(title=f'{column} | {start}–2025 | fixed Final Tier A',template='plotly_white')
    return fig


def line_plot(ax: plt.Axes,frame: pd.DataFrame,value: str,groups: list[str],unit: str,title: str) -> None:
    """Draw ordered start-year trajectories with explicit units and a legible legend."""
    for key,g in frame.groupby(groups,sort=True):
        g=g.sort_values('start_year'); label=' / '.join(map(str,key if isinstance(key,tuple) else (key,)))
        ax.plot(g.start_year,g[value],marker='o',label=label.replace('_sen_slope',''))
    ax.set(title=title,xlabel='Start year (end fixed at 2025)',ylabel=unit,xticks=[1981,1986,1991,1996,2001])
    ax.grid(alpha=.2); ax.legend(fontsize=8,loc='best')


def heat_plot(ax: plt.Axes,frame: pd.DataFrame,index: str,value: str,title: str,unit: str) -> None:
    """Render a station/metric by start-year heatmap with complete numeric station labels."""
    pivot=frame.pivot(index=index,columns='start_year',values=value).sort_index()
    artist=ax.imshow(pivot.to_numpy(float),aspect='auto',cmap='viridis')
    ax.set(xticks=range(len(pivot.columns)),xticklabels=pivot.columns,yticks=range(len(pivot)),yticklabels=pivot.index,
           xlabel='Start year (end fixed at 2025)',title=title)
    ax.tick_params(axis='y',labelsize=7)
    ax.figure.colorbar(artist,ax=ax,label=unit,shrink=.85)


def save_charts(t: dict,root: Path=PROJECT_ROOT) -> list[str]:
    """Export fifteen deterministic PNGs, an interactive trajectory and nine comparable-scale point maps."""
    directory=root/CHART_DIR; directory.mkdir(parents=True,exist_ok=True); generated=[]
    tr=t['temperature_trends']; ws=t['window_summary']; kma=ws.loc[ws.source.eq('KMA')]
    main=t['global_morans_i'].loc[lambda d:d.weight_variant.eq('directed_knn_k4')&d.representation.eq('STATION_LINKED')]
    val=t['validation_window_summary'].loc[lambda d:d.metric.eq('TAVG')]
    for name in PNGS:
        tall=name in ('tavg_slope_heatmap','significance_stability_heatmap')
        fig,ax=plt.subplots(figsize=(10,12 if tall else 6),layout='constrained')
        if name=='tavg_slope_range_distribution':
            data=t['trend_stability'].loc[lambda d:d.source.eq('KMA')&d.metric.eq('TAVG')]
            ax.hist(data.slope_range,bins=12,color='#256b86',edgecolor='white')
            ax.set(title='KMA TAVG absolute slope range across five windows',xlabel='max slope − min slope (°C/decade)',ylabel='Stations')
        elif name in ('tavg_slope_heatmap','significance_stability_heatmap'):
            f=tr.loc[tr.source.eq('KMA')&tr.metric.eq('TAVG')]
            heat_plot(ax,f,'station_id','sen_slope_per_decade' if name=='tavg_slope_heatmap' else 'significant_fdr',
                      'KMA TAVG | '+('Sen slope' if name=='tavg_slope_heatmap' else 'BH-FDR significance'),
                      '°C/decade' if name=='tavg_slope_heatmap' else '1 = significant; 0 = not significant')
        elif name=='spatial_moran_trajectory_heatmap':
            heat_plot(ax,main,'variable','Moran_I','Main directed K4 Moran trajectories','Moran I')
        elif name.startswith('threshold_'):
            proxy='TMAX_GE_33' if '33c' in name else 'TMIN_GE_25'
            line_plot(ax,t['threshold_window_summary'].loc[lambda d:d.threshold.eq(proxy)],'median',['source'],'days/decade',proxy+' proxy slope median')
        elif name=='seasonal_median_slope_by_start_year':
            line_plot(ax,t['seasonal_summary'].loc[lambda d:d.source.eq('KMA')],'median',['season'],'°C/decade','KMA seasonal TAVG median Sen slope')
        elif name=='dtr_median_slope_by_start_year':
            line_plot(ax,t['dtr_summary'],'median',['source'],'°C/decade','Annual DTR median Sen slope')
        elif name=='nasa_kma_tavg_trend_by_start_year':
            line_plot(ax,ws.loc[ws.metric.eq('TAVG')],'median',['source'],'°C/decade','TAVG median Sen slope')
        elif name=='bias_rmse_by_start_year':
            f=val.melt(id_vars=['start_year'],value_vars=['bias_median','rmse_median'],var_name='metric',value_name='value')
            line_plot(ax,f,'value',['metric'],'°C','TAVG validation: station medians')
        elif name in ('kma_tavg_moran_trajectory','bias_rmse_moran_trajectory'):
            variables=['kma_tavg_sen_slope'] if name.startswith('kma') else ['tavg_bias','tavg_rmse']
            f=main.loc[main.variable.isin(variables)]
            line_plot(ax,f,'Moran_I',['variable'],'Moran I','Fixed directed K4 | filled star: raw p < .05')
            sig=f.loc[f.significant_0_05]; ax.scatter(sig.start_year,sig.Moran_I,marker='*',s=130,c='#e98920',zorder=5)
        elif name=='coast_association_trajectory':
            f=t['coastal_associations'].loc[lambda d:d.variable.isin(['kma_tavg_sen_slope','tavg_bias','tavg_rmse'])]
            line_plot(ax,f,'spearman_rho',['variable'],'Spearman rho','Coast-distance associations (exploratory)')
        else:
            selected=['TAVG'] if name=='kma_tavg_median_slope_by_start_year' else ['TMAX','TMIN']
            line_plot(ax,kma.loc[kma.metric.isin(selected)],'median',['metric'],'°C/decade','KMA median Sen slope')
        path=directory/f'{name}.png'; fig.savefig(path,dpi=150,metadata={'Software':'NASA POWER Korea Climate Explorer Stage18'}); plt.close(fig)
        generated.append(path.relative_to(root).as_posix())
    path=directory/'tavg_station_slope_trajectories.html'
    trajectory_figure(tr).write_html(path,include_plotlyjs='cdn',div_id='period-sensitivity-station-trajectories')
    generated.append(path.relative_to(root).as_posix())
    values=t['spatial_station_values']
    for year in (1981,1991,2001):
        for metric,column in [('kma_tavg','kma_tavg_sen_slope'),('bias','tavg_bias'),('rmse','tavg_rmse')]:
            name=f'{metric}_start_{year}_map'; path=directory/f'{name}.html'
            point_map(values.loc[values.start_year.eq(year)],column,year,(values[column].min(),values[column].max())).write_html(
                path,include_plotlyjs='cdn',div_id=name)
            generated.append(path.relative_to(root).as_posix())
    return generated


def report_sections(t: dict) -> list[tuple[str,str,pd.DataFrame|None]]:
    """Twenty requested sections with actual computed tables, no causal or acceleration claims."""
    kma=t['window_summary'].loc[lambda d:d.source.eq('KMA')]
    main=t['global_morans_i'].loc[lambda d:d.weight_variant.eq('directed_knn_k4')]
    stable=t['national_stability_summary'].loc[lambda d:d.source.eq('KMA')&d.metric.eq('TAVG')].iloc[0]
    n=t['station_master'].station_id.nunique()
    return [
        ('1. Executive summary',f'동일 Final Tier A {n}개. KMA TAVG 모든 기간 양수 {int(stable.positive_all_count)}개, 모든 기간 FDR 유의 {int(stable.significant_all_count)}개. 관측소 slope range 중앙값 {stable["median"]:.6f} °C/decade.',kma.loc[kma.metric.eq('TAVG')]),
        ('2. Why period sensitivity',WARNING+' 시작연도 변화와 window 길이 변화를 함께 점검합니다.',None),
        ('3. Fixed network','Final Tier A 목록을 Stage10/16/17과 대조, Tier B 제외. 품질 실패 시 관측소를 자동 탈락시키지 않고 분석을 중단합니다.',t['station_master'].loc[lambda d:d.start_year.eq(1981),['station_id','station_name','latitude','longitude','nasa_grid_id']]),
        ('4. Analysis windows','끝은 2025-12-31로 고정. 윤년을 포함하는 실제 달력.',t['windows']),
        ('5. Data quality','기온 결측은 NaN 유지, 일자료를 새 namespace에만 저장. 원자료/과거 결과를 덮어쓰지 않습니다.',t['data_quality'].groupby(['start_year','source']).agg(stations=('station_id','size'),tavg_missing=('tavg_missing','sum'),tmax_missing=('tmax_missing','sum'),tmin_missing=('tmin_missing','sum')).reset_index()),
        ('6. TAVG trend stability','OLS/MK/조건부 modified MK/Sen 95% CI. BH는 window×source×metric 내 45개 raw original MK p. 5/5 유의는 독립 검정 반복이 아닙니다.',t['national_stability_summary']),
        ('7. TMAX / TMIN','각 window에서 매년 유효 관측의 산술평균에 직접 추세를 적합합니다. 이동평균에 적합하지 않습니다.',kma.loc[kma.metric.ne('TAVG')]),
        ('8. TMIN−TMAX contrast','각각의 Sen slope 차이. 양수는 Tmin 기울기가 더 큰 것일 뿐 원인 설명이 아닙니다.',t['contrast_summary']),
        ('9. DTR','연평균 Tmax−연평균 Tmin 시계열 자체에 다시 Sen 적합. Sen(Tmax)−Sen(Tmin)과 일반적으로 다릅니다.',t['dtr_summary']),
        ('10. Seasonal TAVG','December는 다음 DJF; 완전한 달력 계절, 유효일 >=95%. 양 끝 불완전 DJF 제외; dominant tie DJF/MAM/JJA/SON 순.',t['seasonal_summary']),
        ('11. Threshold proxies','Tmax≥30/33, Tmin≥25°C. 같은 유효 pair 날짜만 세며 미관측일을 보정/생성하지 않습니다. 단위 days/decade.',t['threshold_window_summary']),
        ('12. NASA-KMA trend consistency','같은 방향 및 양측 FDR 유의를 분리합니다. NASA와 KMA가 같은 자료라는 의미가 아닙니다.',t['trend_consistency_window_summary']),
        ('13. Bias / RMSE','Bias=NASA−KMA, °C. 기간별 Bias/RMSE 변화가 정확도 향상을 증명하지 않습니다.',t['validation_window_summary']),
        ('14. Moran trajectories','주 directed K4; K3/K5/symmetric K4/row-IDW p2 민감도. 각 geometry의 동일 행렬을 모든 기간에 재사용. 999 양측 순열, 고정 seed와 기존 변수 offset. 유의성 전환 또는 I range>0.2는 PERIOD_SENSITIVE; 부호반전 우선 DIRECTION_SENSITIVE.',main[['start_year','source','representation','variable','Moran_I','permutation_p']]),
        ('15. NASA spatial representation',f'Station-linked {n}개와 native-centre unique-grid {t["grid_series_equality"].nasa_grid_id.nunique()}개를 분리. 매 window 3변수 전체 일자료 동일성 재확인. API 반환 격자좌표가 아닙니다.',t['nasa_grid_spatial'].loc[lambda d:d.weight_variant.eq('directed_knn_k4')]),
        ('16. Coast distance / groups','연속거리 상관은 raw p 탐색적. Coastal ≤30 km 주분석, 20/50 km는 1981/1991/2001만. BH는 window×거리 threshold별 9개 metric. Rank-biserial 양수는 Coastal 쪽이 높음.',t['coastal_association_stability']),
        ('17. Station sensitivity','관측소별 절대 slope range °C/decade 순서이며 기후 위험도나 관측소 품질 점수가 아닙니다. 아래 상위·하위 각 5개.',pd.concat([t['station_metric_summary'].loc[lambda d:d.source.eq('KMA')&d.metric.eq('TAVG')].nlargest(5,'slope_range'),t['station_metric_summary'].loc[lambda d:d.source.eq('KMA')&d.metric.eq('TAVG')].nsmallest(5,'slope_range')])),
        ('18. Methodological implications','부호 안정성과 크기/유의성 민감성을 구분. 0 기울기는 별도 표시하고 비영 부호의 순차 반전만 센다. 절대 slope range를 쓰고 1981 대비 차이를 제시합니다. 공간 기간분류는 weight 강건성 분류와 다릅니다.',t['spatial_robustness_summary'].loc[lambda d:d.weight_variant.eq('directed_knn_k4')]),
        ('19. Limitations',LIMITS,None),
        ('20. Conclusions / reproducibility','앞 단계와 공통인 1981/1991 기울기·Moran를 수치 재현했습니다. 1991 BH는 이전 51개가 아니라 고정 45개로 재계산. 최종 구현·회귀·보호 검증은 period_sensitivity_verification.json에서 확인하세요. 대화형 그래프는 브라우저에서 Plotly CDN/지형 리소스 연결이 필요할 수 있습니다.',t['historical_reproduction'])]


def write_reports(t: dict,root: Path=PROJECT_ROOT) -> list[str]:
    """Deterministic twenty-section HTML/Markdown with links to every table/chart and actual values."""
    title='Trend Period Sensitivity & Start-Year Robustness | Final Tier A'
    md=[f'# {title}\n']; html=[f'<h1>{escape(title)}</h1>']
    for heading,narrative,frame in report_sections(t):
        md.append(f'\n## {heading}\n\n{narrative}\n'); html.append(f'<h2>{escape(heading)}</h2><p>{escape(narrative)}</p>')
        if frame is not None:
            notice=f'Showing {min(len(frame),80)} / {len(frame)} rows; full CSV below.'
            md.extend([notice,markdown_table(frame.head(80))]); html.extend([f'<p>{notice}</p>','<div class="table">'+frame.head(80).to_html(index=False,float_format=lambda v:f'{v:.6g}')+'</div>'])
    md.append('\n## Complete results\n'); html.append('<h2>Complete results</h2>')
    for name in sorted(t):
        url=f'../../tables/period_sensitivity/{PREFIX}{name}.csv'
        md.append(f'- [{name}]({url})'); html.append(f'<p><a href="{url}">{escape(name)}</a></p>')
    for name in PNGS:
        url=f'../../charts/period_sensitivity/{name}.png'
        md.append(f'\n![{name}]({url})'); html.append(f'<img src="{url}" alt="{name}">')
    for name in [*MAPS,'tavg_station_slope_trajectories']:
        url=f'../../charts/period_sensitivity/{name}.html'
        md.append(f'\n[{name}]({url})'); html.append(f'<p><a href="{url}">{name}</a></p>')
    directory=root/REPORT_DIR; directory.mkdir(parents=True,exist_ok=True)
    paths=[directory/'trend_period_sensitivity_report.html',directory/'trend_period_sensitivity_report.md']
    paths[0].write_text('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>'+escape(title)+
        '</title><style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:16px;color:#193449}'+
        '.table{overflow:auto}table{border-collapse:collapse;font-size:12px}td,th{padding:5px;border:1px solid #ccd}'+
        'h2{margin-top:40px}p{line-height:1.7}img{max-width:100%}</style></head><body>'+'\n'.join(html)+'</body></html>\n',encoding='utf-8')
    paths[1].write_text('\n'.join(md)+'\n',encoding='utf-8')
    return [p.relative_to(root).as_posix() for p in paths]


def report_from_saved(root: Path=PROJECT_ROOT) -> list[str]:
    """Regenerate only Stage18 reports from validated saved tables, without fitting or API calls."""
    return write_reports(load_tables(root),root)
