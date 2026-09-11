"""Stage-13 point/line maps and statistical charts; no spatial interpolation."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from pyproj import Transformer
from shapely.ops import transform

from src.config import PROJECT_ROOT
from src.spatial.autocorrelation import GLOBAL_VARIABLES
from src.spatial.coastal_analysis import METRICS


def heatmap_input(results: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Aligned I and p matrices, maintaining configured input order."""
    order = list(results.weight_variant.unique())
    variables = list(results.variable.unique())
    return tuple(results.pivot(index='variable',columns='weight_variant',values=v).reindex(index=variables,columns=order)
                 for v in ('moran_i','permutation_p'))


def _save(fig: plt.Figure, name: str, family: str, paths: list) -> None:
    """Save a new Stage-13 PNG and close its matplotlib figure."""
    path = PROJECT_ROOT / f'output/charts/{family}/{name}.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches='tight')
    plt.close(fig)
    paths.append(path.relative_to(PROJECT_ROOT).as_posix())


def coastline_map(master: pd.DataFrame, coast: dict, color: pd.Series | None, title: str) -> go.Figure:
    """Plotly Cartesian lon/lat display of official lines; distances use full geometry."""
    inverse = Transformer.from_crs(coast['analysis_crs'],'EPSG:4326',always_xy=True)
    x,y = [],[]
    for geometry in coast['geometries']:
        # Display-only 250 m simplification; distance computation never uses this geometry.
        display = transform(inverse.transform,geometry.simplify(250,preserve_topology=True))
        parts = list(display.geoms) if display.geom_type == 'MultiLineString' else [display]
        for part in parts:
            coords = np.asarray(part.coords)
            x.extend([*coords[:,0],None]); y.extend([*coords[:,1],None])
    fig = go.Figure(go.Scattergl(x=x,y=y,mode='lines',line=dict(color='#92a3af',width=.7),name='KHOA coastline',hoverinfo='skip'))
    marker = dict(size=9,color='#d4623c',line=dict(width=.8,color='white'))
    if color is not None:
        marker.update(color=color, colorscale='Viridis', showscale=True, colorbar=dict(title='km'))
    fig.add_trace(go.Scattergl(x=master.longitude,y=master.latitude,mode='markers',marker=marker,
                               text=master.station_name,customdata=master.station_id, name='Final A stations',
                               hovertemplate='%{text} (%{customdata})<br>%{x:.4f}, %{y:.4f}<extra></extra>'))
    fig.update_layout(title=title,xaxis_title='Longitude (°E)',yaxis_title='Latitude (°N)',height=720,
                      template='plotly_white',legend=dict(orientation='h',y=1.04),
                      yaxis=dict(scaleanchor='x',scaleratio=1/np.cos(np.deg2rad(36))))
    return fig


def create_charts(master: pd.DataFrame, tables: dict, coastal: dict, coast: dict, config: dict) -> list[str]:
    """Generate robustness charts always and coastal outputs only from validated geometry."""
    paths = []
    results = tables['weights']
    values, pvalues = heatmap_input(results)
    fig,ax = plt.subplots(figsize=(14,6),layout='constrained')
    limit = max(.01,float(np.abs(values.to_numpy()).max()))
    im=ax.imshow(values,cmap='RdBu_r',vmin=-limit,vmax=limit,aspect='auto')
    ax.set_yticks(range(len(values)),[GLOBAL_VARIABLES[v] for v in values.index],fontsize=9)
    ax.set_xticks(range(len(values.columns)),values.columns,rotation=45,ha='right',fontsize=8)
    for i in range(len(values)):
        for j in range(len(values.columns)):
            ax.text(j,i,f'{values.iloc[i,j]:.2f}'+('*' if pvalues.iloc[i,j]<config['alpha'] else ''),ha='center',va='center',fontsize=8,
                    color='white' if abs(values.iloc[i,j])>.65*limit else 'black')
    ax.set_title("Spatial weight robustness | * permutation p < 0.05 (unadjusted)")
    fig.colorbar(im,ax=ax,label="Moran's I")
    _save(fig,'spatial_weight_moran_robustness_heatmap','robustness',paths)
    selections = {'tavg':['kma_tavg_sen_slope'],'bias':['tavg_bias'],'rmse':['tavg_rmse'],
                  'threshold_proxy':['days_tmax_ge_33_kma_slope','days_tmin_ge_25_kma_slope']}
    for short, variables in selections.items():
        fig,ax=plt.subplots(figsize=(12,4.8),layout='constrained')
        for variable in variables:
            g=results[results.variable.eq(variable)]
            positions=np.arange(len(g))
            line,=ax.plot(positions,g.moran_i,alpha=.6,label=GLOBAL_VARIABLES[variable])
            significant=g.permutation_p.to_numpy()<config['alpha']
            ax.scatter(positions[significant],g.moran_i.to_numpy()[significant],color=line.get_color(),marker='*',s=90)
            ax.scatter(positions[~significant],g.moran_i.to_numpy()[~significant],edgecolor=line.get_color(),facecolor='white',s=28)
        ax.axhline(0,color='gray',lw=.7)
        ax.set_xticks(positions,g.weight_variant,rotation=45,ha='right',fontsize=8)
        ax.set_ylabel("Moran's I"); ax.set_title('Weight sensitivity | filled star: p < 0.05'); ax.legend(fontsize=8)
        name='threshold_proxy_weight_sensitivity' if short=='threshold_proxy' else f'{short}_moran_weight_sensitivity'
        _save(fig,name,'robustness',paths)
    if not coastal:
        return paths
    distances=coastal['station_coastal_distance']
    data=master.merge(distances[['station_id','distance_to_coast_km']],on='station_id',validate='one_to_one')
    main=float(coastal['coastal_inland_comparison'].threshold_km.iloc[0])
    directory=PROJECT_ROOT/'output/charts/coastal'; directory.mkdir(parents=True,exist_ok=True)
    base=coastline_map(data,coast,None,'Final A stations and official KHOA coastline (2025 reference)')
    for name,color,title in [('station_coastline_map',None,'Final A stations + official coastline'),
                             ('distance_to_coast_map',data.distance_to_coast_km,'Distance to official coastline (km)'),
                             ('coastal_inland_classification_map',None,f'Operational Coastal / Inland: {main:g} km')]:
        fig=go.Figure(base)
        fig.update_layout(title=title)
        if name=='coastal_inland_classification_map':
            fig.data[1].marker.color=np.where(data.distance_to_coast_km<=main,'#147d92','#df8244')
            fig.data[1].text=data.station_name + np.where(data.distance_to_coast_km<=main,' · Coastal',' · Inland')
        elif color is not None:
            fig.data[1].marker.update(color=color,colorscale='Viridis',showscale=True,colorbar=dict(title='km'))
        path=directory/f'{name}.html'; fig.write_html(path,include_plotlyjs='cdn',div_id=f'stage13-{name}')
        paths.append(path.relative_to(PROJECT_ROOT).as_posix())
    fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained')
    ax.hist(data.distance_to_coast_km,bins=15,color='#287d8e',edgecolor='white')
    for threshold in config['coastal_thresholds_km']:
        ax.axvline(threshold,ls='--',label=f'{threshold:g} km')
    ax.set(xlabel='Distance to coast (km)',ylabel='Station count',title='Coastal distance distribution'); ax.legend()
    _save(fig,'coastal_distance_distribution','coastal',paths)
    for short,var in {'tavg':'kma_tavg_sen_slope','contrast':'tmin_minus_tmax','dtr':'dtr_slope','bias':'tavg_bias','rmse':'tavg_rmse'}.items():
        fig,ax=plt.subplots(figsize=(7,4.5),layout='constrained')
        ax.scatter(data.distance_to_coast_km,data[var],s=28,color='#287d8e',alpha=.8)
        ax.set(xlabel='Distance to coast (km)',ylabel=METRICS[var],title=f'Coastal distance vs {short.upper()} | exploratory')
        _save(fig,f'coastal_distance_vs_{short}','coastal',paths)
    for short,var in {'tavg':'kma_tavg_sen_slope','tmax':'kma_tmax_sen_slope','tmin':'kma_tmin_sen_slope','dtr':'dtr_slope','bias':'tavg_bias','rmse':'tavg_rmse'}.items():
        groups=[data.loc[data.distance_to_coast_km<=main,var].dropna(),data.loc[data.distance_to_coast_km>main,var].dropna()]
        fig,ax=plt.subplots(figsize=(6,4.5),layout='constrained')
        ax.boxplot(groups,tick_labels=[f'Coastal (n={len(groups[0])})',f'Inland (n={len(groups[1])})'])
        ax.set(ylabel=METRICS[var],title=f'{short.upper()} | operational threshold {main:g} km')
        _save(fig,f'coastal_inland_{short}_boxplot','coastal',paths)
    return paths
