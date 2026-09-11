"""Common-period point maps, scientific plots and deterministic saved-result reports."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.config import PROJECT_ROOT
from src.common_period.data import TABLE_DIR, CHART_DIR, REPORT_DIR, MANIFEST, WARNING, GRID_WARNING
from src.spatial.robustness_audit import sha256

MAPS = {'common_period_kma_tavg_map': 'kma_tavg_sen_slope', 'common_period_kma_tmax_map': 'kma_tmax_sen_slope',
        'common_period_kma_tmin_map': 'kma_tmin_sen_slope', 'common_period_nasa_tavg_map': 'nasa_tavg_sen_slope',
        'common_period_bias_map': 'tavg_bias', 'common_period_rmse_map': 'tavg_rmse',
        'common_period_cohort_origin_map': 'cohort_origin', 'common_period_nasa_grid_sharing_map': 'nasa_grid_id'}
PNGS = ['common_period_anomaly_heatmap', 'common_period_kma_nasa_tavg_scatter', 'common_period_tmax_tmin_trends',
        'common_period_threshold_33c', 'common_period_threshold_25c', 'common_period_bias_rmse']


def load_tables(root: Path = PROJECT_ROOT) -> dict:
    """Read manifest-allowlisted tables and verify hashes; never fit or request data."""
    manifest = json.loads((root/MANIFEST).read_text())
    if manifest.get('status') != 'completed':
        raise ValueError('Common-period analysis incomplete; stale results withheld')
    result = {}
    for name, digest in manifest['output_hashes'].items():
        path = root/name
        if path.parent != root/TABLE_DIR or path.suffix != '.csv':
            continue
        if sha256(path) != digest:
            raise ValueError(f'Common-period checksum mismatch: {path.name}')
        result[path.stem] = pd.read_csv(path, dtype={'station_id': str})
    if 'common_period_1991_2025_station_master' not in result:
        raise ValueError('Common-period station master absent')
    return result


def point_map(summary: pd.DataFrame, column: str, master: pd.DataFrame) -> go.Figure:
    """Interactive station points; grid map overlays inferred native centres and connections."""
    figure = go.Figure()
    text = (summary.station_id.astype(str)+' '+summary.station_name+'<br>'+summary.cohort_origin+
            '<br>NASA grid: '+summary.nasa_grid_id+'<br>group size: '+summary.nasa_grid_group_size.astype(str))
    categorical = column in ('cohort_origin', 'nasa_grid_id')
    groups = summary.groupby(column, sort=True) if categorical else [('stations', summary)]
    for label, group in groups:
        marker = {'size': 9, 'opacity': .85}
        if not categorical:
            marker.update(color=group[column], colorscale='RdBu_r', showscale=True,
                          colorbar={'title': '°C/decade' if 'slope' in column else '°C'})
        figure.add_trace(go.Scattergeo(lat=group.latitude, lon=group.longitude, mode='markers',
                                       marker=marker, name=str(label), text=text.loc[group.index],
                                       customdata=group[column].astype(str), hovertemplate='%{text}<br>%{customdata}<extra></extra>'))
    if column == 'nasa_grid_id':
        used = master.loc[master.station_id.isin(summary.station_id)]
        centres = used.drop_duplicates('nasa_grid_id')
        figure.add_trace(go.Scattergeo(lat=centres.nasa_grid_latitude, lon=centres.nasa_grid_longitude,
                                       mode='markers', marker={'symbol': 'star', 'size': 12, 'color': 'black'},
                                       text=centres.nasa_grid_id, name='Inferred native grid centres'))
        lat, lon = [], []
        for row in used.itertuples():
            lat.extend([row.latitude, row.nasa_grid_latitude, None]); lon.extend([row.longitude, row.nasa_grid_longitude, None])
        figure.add_trace(go.Scattergeo(lat=lat, lon=lon, mode='lines', line={'color': 'gray', 'width': .6},
                                       name='Station → inferred grid', hoverinfo='skip'))
    figure.update_geos(projection_type='mercator', center={'lat': 36, 'lon': 128},
                       lataxis_range=[32.7, 39], lonaxis_range=[125, 131.5], showcoastlines=True, showcountries=True)
    figure.update_layout(title=f'Common period 1991–2025 | {column}', height=680, template='plotly_white',
                         margin={'l': 10, 'r': 10, 't': 60, 'b': 10}, showlegend=categorical)
    return figure


def trend_scatter(summary: pd.DataFrame) -> go.Figure:
    """Cohort-marked interactive Sen comparison with shared grid hover information."""
    fig = go.Figure()
    for i, (origin, group) in enumerate(summary.groupby('cohort_origin')):
        fig.add_trace(go.Scatter(x=group.kma_tavg_sen_slope, y=group.nasa_tavg_sen_slope, mode='markers', name=origin,
                                 marker={'symbol': 'circle' if i == 0 else 'diamond', 'size': 10},
                                 text=group.station_id+' '+group.station_name+'<br>'+group.nasa_grid_id+
                                 '<br>grid group size: '+group.nasa_grid_group_size.astype(str),
                                 hovertemplate='%{text}<br>KMA %{x:.3f}<br>NASA %{y:.3f}<extra></extra>'))
    fig.update_layout(title='TAVG Sen slopes | 1991–2025', xaxis_title='KMA °C/decade', yaxis_title='NASA °C/decade', template='plotly_white')
    return fig


def save_charts(tables: dict, root: Path) -> list[str]:
    """Create eight point maps, six PNGs and an extra hover-enabled trend scatter."""
    directory = root/CHART_DIR; directory.mkdir(parents=True, exist_ok=True)
    summary = tables['common_period_station_temperature_summary'].sort_values('station_id', key=lambda x: x.astype(int)).reset_index(drop=True)
    master = tables['common_period_1991_2025_station_master']
    paths = []
    figures = {name: point_map(summary, column, master) for name, column in MAPS.items()}
    figures['common_period_kma_nasa_tavg_scatter'] = trend_scatter(summary)
    for name, fig in figures.items():
        path = directory/f'{name}.html'
        fig.write_html(path, include_plotlyjs='cdn', div_id=name)
        paths.append(path.relative_to(root).as_posix())
    for name in PNGS:
        fig, ax = plt.subplots(figsize=(12, 15) if name != 'common_period_kma_nasa_tavg_scatter' else (8, 6), layout='constrained')
        ids = summary.station_id.tolist()
        if name.endswith('anomaly_heatmap'):
            anomaly = tables['common_period_temperature_anomalies_1991_2025']
            order = master.sort_values(['latitude', 'station_id'], ascending=[False, True]).station_id
            matrix = anomaly.loc[anomaly.source.eq('KMA') & anomaly.metric.eq('TAVG')].pivot(index='station_id', columns='year', values='anomaly').reindex(order)
            limit = max(abs(matrix.to_numpy()).max(), .01)
            im = ax.imshow(matrix, aspect='auto', cmap='RdBu_r', vmin=-limit, vmax=limit)
            ax.set_yticks(range(len(matrix)), matrix.index, fontsize=8)
            ax.set_xticks(range(0, len(matrix.columns), 4), matrix.columns[::4], rotation=45)
            ax.set(title='KMA TAVG anomaly | north to south station order', xlabel='Year', ylabel='Station ID')
            fig.colorbar(im, ax=ax, label='°C relative to 1991–2020 normal', shrink=.65)
        elif name.endswith('tavg_scatter'):
            for origin, group in summary.groupby('cohort_origin'):
                ax.scatter(group.kma_tavg_sen_slope, group.nasa_tavg_sen_slope, label=origin,
                           marker='o' if origin == 'TIER_A' else 'D', alpha=.8)
            lower = min(summary.kma_tavg_sen_slope.min(), summary.nasa_tavg_sen_slope.min())
            upper = max(summary.kma_tavg_sen_slope.max(), summary.nasa_tavg_sen_slope.max())
            ax.plot([lower, upper], [lower, upper], '--', color='gray')
            ax.set(xlabel='KMA TAVG Sen (°C/decade)', ylabel='NASA TAVG Sen (°C/decade)', title='Common period 1991–2025')
            ax.legend()
        else:
            labels = [f'{r.station_id} [{r.cohort_origin.removeprefix("TIER_")}]' for r in summary.itertuples()]
            y = np.arange(len(ids)); width = .36
            if name.endswith('tmax_tmin_trends'):
                first, second = summary.kma_tmax_sen_slope, summary.kma_tmin_sen_slope
                legend, unit, title = ['KMA TMAX', 'KMA TMIN'], '°C/decade', 'KMA TMAX/TMIN Sen trends'
            elif name.endswith('bias_rmse'):
                first, second = summary.tavg_bias, summary.tavg_rmse
                legend, unit, title = ['NASA − KMA Bias', 'RMSE'], '°C', 'Daily TAVG Bias/RMSE'
            else:
                threshold = 'TMAX_GE_33' if name.endswith('33c') else 'TMIN_GE_25'
                frame = tables['common_period_threshold_trends']
                frame = frame.loc[frame.threshold.eq(threshold)].pivot(index='station_id', columns='source', values='sen_slope_per_decade').reindex(ids)
                first, second = frame.KMA, frame.NASA
                legend, unit, title = ['KMA', 'NASA'], 'days/decade', f'{threshold} | analysis proxy, not official KMA statistic'
            ax.barh(y-width/2, first, height=width, label=legend[0], color='#0072B2')
            ax.barh(y+width/2, second, height=width, label=legend[1], color='#D55E00')
            ax.set_yticks(y, labels, fontsize=8); ax.invert_yaxis()
            ax.set(xlabel=unit, ylabel='Station ID [cohort origin]', title=title)
            ax.axvline(0, color='gray', lw=.6); ax.legend(loc='lower right')
        ax.grid(alpha=.15)
        path = directory/f'{name}.png'; fig.savefig(path, dpi=150, metadata={'Software': 'NASA POWER Korea Climate Explorer'}); plt.close(fig)
        paths.append(path.relative_to(root).as_posix())
    return paths


def report_sections(tables: dict) -> list[tuple[str, str, pd.DataFrame | None]]:
    """Eighteen compact evidence-linked sections with explicit limitations."""
    t = lambda name: tables[f'common_period_{name}']
    master, grids = t('1991_2025_station_master'), t('nasa_grid_mapping')
    trend = t('temperature_trends')
    columns = ['station_id', 'cohort_origin', 'metric', 'sen_slope_per_decade', 'sen_ci_lower', 'sen_ci_upper', 'fdr_q_value']
    summary = f'KMA stations = {len(master)}; NASA unique grids = {len(grids)}. All daily calendars: 1991–2025; normal: 1991–2020.'
    return [
        ('1. Executive Summary', summary, t('nasa_station_vs_grid_summary')),
        ('2. Why common period?', WARNING+' Tier A daily data were subset and all annual series/statistics refitted; no old slope conversion.', None),
        ('3. Station cohort', 'Origin records historical eligibility, not climate class or quality superiority.', master),
        ('4. Data quality', 'Missing observations remain NaN. Screening thresholds reapplied; any failure withholds the full cohort. Long-form yearly completeness is saved separately.', t('data_quality')),
        ('5. KMA TAVG/TMAX/TMIN', 'Sen and 95% CI in °C/decade; 5/10-year trailing averages use full windows.', trend.loc[trend.source.eq('KMA'), columns]),
        ('6. NASA TAVG/TMAX/TMIN', GRID_WARNING, trend.loc[trend.source.eq('NASA'), columns]),
        ('7. FDR common family', 'Fresh BH correction of original MK p-values across all common-period stations, separately by source×metric; seasonal adds season, threshold adds proxy. Prior q-values are never merged. Modified MK is sensitivity, not the FDR input.', None),
        ('8. 1991–2020 normal', 'Equal-weight mean of 30 annual means per station/source/metric, °C.', t('temperature_normals_1991_2020')),
        ('9. 2025 anomaly', 'Annual mean minus normal, °C.', t('temperature_anomalies_1991_2025').loc[lambda d:d.year.eq(2025)&d.metric.eq('TAVG'), ['station_id', 'cohort_origin', 'source', 'normal_mean', 'anomaly']]),
        ('10. Seasonal trends', 'December assigned to next DJF. Full boundary calendar required, ≥95% valid days: DJF1992–2025, other seasons1991–2025.', t('seasonal_temperature_trends').loc[lambda d:d.metric.eq('TAVG'), columns+['source', 'season']]),
        ('11. Threshold proxy', 'TMAX≥30/33°C, TMIN≥25°C; counts only matched valid days. No zero-fill or missing-day scaling; not official heatwave/tropical-night statistics. Sparse counts can yield zero Sen slopes even with significant MK.', t('threshold_trends')[['station_id', 'cohort_origin', 'source', 'threshold', 'mean_annual_count', 'sen_slope_per_decade', 'fdr_q_value']]),
        ('12. NASA–KMA validation', 'Bias=NASA−KMA, MAE/RMSE °C; Pearson/Spearman dimensionless. Correlation ≠ accuracy. Descriptive errors have no invented significance tests.', t('nasa_kma_temperature_validation')[['station_id', 'cohort_origin', 'metric', 'bias', 'mae', 'rmse', 'pearson_r', 'spearman_rho', 'n_pairs']]),
        ('13. NASA grid duplication', 'Native MERRA-2 origin (-90,-180), spacing(.5,.625) and nearest-centre inference; old CSV caches contain no returned cell metadata. Coordinates are inferred, not claimed as API-returned. Full three-variable daily equality checked within each shared group; mismatches withhold grid summaries. Stations are retained.', grids),
        ('14. Tier-origin descriptive comparison', 'Small Tier B-origin sample; origin is historical eligibility, not a climatological grouping. No MWU or causal test.', t('cohort_origin_comparison')),
        ('15. Regional/elevation/coastal summaries', 'Unweighted station distributions, not national area means. Regions with fewer than three stations flagged. Elevation/coastal tables are separate; 30km coastal label is descriptive.', t('regional_temperature_summary')),
        ('16. Period-comparison preparation', 'Separate table only: difference = new1991–2025 Sen − old1981–2025 Sen. Deep sensitivity analysis deferred to Stage18.', tables.get('tier_a_period_comparison_preparation')),
        ('17. Limitations', WARNING+' '+GRID_WARNING+' Native cell inference lacks returned metadata for singleton confirmation. Shared series verified, but grid independence and spatial representativeness are not established. NASA LST vs station daily conventions, point/grid elevation, station history and missing observations remain limitations.', None),
        ('18. Next step', 'Stage17 spatial reanalysis requires separate authorization, common-period data and explicit grid dependence handling. No Moran/SAR/SEM, interpolation, forecasting or composite climate-risk score was fitted here.', None)]


def write_reports(tables: dict, root: Path = PROJECT_ROOT) -> list[str]:
    """Deterministic reports from saved CSVs; show up to 80 rows per section explicitly."""
    from src.spatial.robustness_reporting import markdown_table
    count = len(tables['common_period_1991_2025_station_master'])
    title = f'{count}-Station Common-Period Temperature Analysis, 1991–2025'
    md, html = [f'# {title}\n'], [f'<h1>{title}</h1>']
    for heading, text, frame in report_sections(tables):
        md.append(f'\n## {heading}\n\n{text}\n'); html.append(f'<h2>{escape(heading)}</h2><p>{escape(text)}</p>')
        if frame is not None:
            notice = f'Showing {min(80, len(frame))} of {len(frame)} rows; complete results in linked CSV tables below.'
            md.extend([notice, markdown_table(frame.head(80))])
            html.extend([f'<p>{notice}</p>', '<div class="table">'+frame.head(80).to_html(index=False, float_format=lambda x:f'{x:.6g}')+'</div>'])
    md.append('\n## Complete tables\n'); html.append('<h2>Complete tables</h2>')
    for name in sorted(tables):
        url = f'../../tables/common_period/{name}.csv'
        md.append(f'- [{name}]({url})'); html.append(f'<p><a href="{url}">{name}</a></p>')
    for name in MAPS:
        url = f'../../charts/common_period/{name}.html'
        md.append(f'\n[{name}]({url})'); html.append(f'<p><a href="{url}">{name}</a></p>')
    for name in PNGS:
        url = f'../../charts/common_period/{name}.png'
        md.append(f'\n![{name}]({url})'); html.append(f'<img src="{url}" alt="{name}">')
    directory = root/REPORT_DIR; directory.mkdir(parents=True, exist_ok=True)
    paths = [directory/'common_period_51station_temperature_report.html', directory/'common_period_51station_temperature_report.md']
    paths[0].write_text('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>'+title+
                        '</title><style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:16px;color:#193449}'
                        '.table{overflow:auto}table{border-collapse:collapse;font-size:12px}td,th{padding:5px;border:1px solid #ccd}'
                        'h2{margin-top:40px}p{line-height:1.7}img{max-width:100%}</style></head><body>'+'\n'.join(html)+'</body></html>\n', encoding='utf-8')
    paths[1].write_text('\n'.join(md)+'\n', encoding='utf-8')
    return [p.relative_to(root).as_posix() for p in paths]


def report_from_saved(root: Path = PROJECT_ROOT) -> list[str]:
    """Public report-only entry point with manifest checksum checks."""
    return write_reports(load_tables(root), root)
