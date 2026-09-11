"""Deterministic point maps, scientific figures and evidence-based saved-result reports."""
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
from src.spatial.robustness_audit import sha256
from src.spatial.robustness_reporting import markdown_table
from src.common_period_spatial.data import TABLE_DIR, CHART_DIR, REPORT_DIR, MANIFEST, PREFIX, GRID_WARNING, BRIDGE_WARNING, grid_coordinates

MAPS = {'kma_tavg_map': 'kma_tavg_sen_slope', 'kma_tmax_map': 'kma_tmax_sen_slope',
        'kma_tmin_map': 'kma_tmin_sen_slope', 'tmax_tmin_contrast_map': 'tmin_minus_tmax',
        'dtr_map': 'dtr_slope', 'kma_33c_map': 'kma_33c_sen_slope', 'kma_25c_map': 'kma_25c_sen_slope',
        'bias_map': 'tavg_bias', 'rmse_map': 'tavg_rmse', 'local_moran_tavg_map': 'cluster_type_fdr',
        'dominant_season_map': 'dominant_season', 'nasa_station_linked_tavg_map': 'nasa_tavg_sen_slope',
        'nasa_unique_grid_tavg_map': 'nasa_tavg_sen_slope', 'nasa_grid_sharing_map': 'nasa_grid_id'}
PNGS = ['spatial_robustness_heatmap', 'old_new_moran_comparison', 'bridge_moran_comparison',
        'nasa_station_vs_grid_moran', 'coastal_distance_vs_bias', 'coastal_distance_vs_rmse',
        'tmax_tmin_contrast', 'seasonal_moran_comparison', 'coastal_threshold_sensitivity']
LIMITS = ('Exploratory spatial association, not causality. No area-weighted national mean, interpolation, forecasting, SAR/SEM, '
          'automatic hotspot or risk score. Global Moran and correlation p-values are unadjusted multiple exploratory tests; '
          'spatial dependence weakens independent-station correlation/MWU inference. '
          'NASA grid centres are inferred from official MERRA-2 geometry, not API-returned metadata; singleton cells lack independent metadata confirmation. '
          'Fewer unique grid points do not establish independent observations. '
          'Representation differences combine duplicate removal, changed point geometry and rebuilt neighbors; they do not isolate a pure duplication effect. '
          'Thresholds retain Stage16 matched-valid-day proxies, not official heatwave/tropical-night counts; within-grid slope equality is required. '
          'Old/current robustness labels use the same rule but different weight inventories (13 versus 9). '
          'Local stability compares three current weights, versus six historical weights. '
          'Daily time conventions, elevation, station history and remaining missing observations limit interpretation.')


def load_tables(root: Path = PROJECT_ROOT) -> dict:
    """Allowlisted, checksum-validated read-only dashboard/report loader."""
    manifest = json.loads((root/MANIFEST).read_text())
    if manifest.get('status') != 'completed':
        raise ValueError('Stage17 analysis incomplete; stale tables withheld')
    result = {}
    for name, digest in manifest['output_hashes'].items():
        path = root/name
        if path.parent != root/TABLE_DIR or path.suffix != '.csv':
            continue
        if sha256(path) != digest:
            raise ValueError(f'Stage17 checksum mismatch: {path.name}')
        result[path.stem.removeprefix(PREFIX)] = pd.read_csv(path, dtype={'station_id': str})
    if 'spatial_station_master' not in result or 'nasa_unique_grid_spatial_master' not in result:
        raise ValueError('Stage17 spatial masters missing')
    return result


def display_master(tables: dict) -> pd.DataFrame:
    """Attach categorical display values by station ID with validated one-to-one joins."""
    data = tables['spatial_station_master'].copy()
    local = tables['local_moran_results'].loc[lambda d: d.weight_variant.eq('directed_knn_k4'), ['station_id', 'cluster_type_fdr']]
    season = tables['dominant_season'][['station_id', 'dominant_season']]
    return data.merge(local, on='station_id', validate='one_to_one').merge(season, on='station_id', validate='one_to_one')


def point_map(data: pd.DataFrame, column: str, title: str, *, unique_grid: bool = False,
              color_range: tuple[float, float] | None = None) -> go.Figure:
    """Point-only map with distinct native-grid geometry and complete traceable hover metadata."""
    data = data.copy()
    if unique_grid:
        data = grid_coordinates(data)
        fields = ['station_id', 'latitude', 'longitude', 'station_count', 'station_names', column]
    else:
        fields = ['station_id', 'station_name', 'cohort_origin', 'region_level1', 'elevation_m', 'distance_to_coast_km',
                  column, 'nasa_grid_id', 'nasa_grid_group_size']
    data['_hover'] = data[fields].apply(lambda r: '<br>'.join(f'{escape(str(k))}: {escape(str(v))}' for k, v in r.items()), axis=1)
    categorical = not pd.api.types.is_numeric_dtype(data[column])
    figure = go.Figure()
    groups = data.groupby(column, sort=True) if categorical else [('Unique grid' if unique_grid else 'Station', data)]
    unit = 'days/decade' if '33c' in column or '25c' in column else ('°C' if column in ('tavg_bias', 'tavg_rmse') else '°C/decade')
    for label, group in groups:
        marker = dict(size=10 if unique_grid else 8, opacity=.88, symbol='diamond' if unique_grid else 'circle', line=dict(width=.5, color='white'))
        if not categorical:
            marker.update(color=group[column], colorscale='RdBu_r', showscale=True, colorbar=dict(title=unit))
            if color_range is not None:
                marker.update(cmin=color_range[0], cmax=color_range[1])
        figure.add_trace(go.Scattergeo(lat=group.latitude, lon=group.longitude, mode='markers', name=str(label),
                                       marker=marker, text=group['_hover'], hovertemplate='%{text}<extra></extra>'))
    figure.update_geos(projection_type='mercator', lataxis_range=[32.5, 39], lonaxis_range=[124, 131.5],
                       showcountries=True, showcoastlines=True, showland=True, landcolor='#f0f3f3', bgcolor='#eef6fb')
    figure.update_layout(title=title+' | 1991–2025', template='plotly_white', height=680, margin=dict(l=10, r=10, t=65, b=25),
                         legend=dict(font=dict(size=10)), font=dict(family='Arial, sans-serif'))
    return figure


def _short(value: str) -> str:
    """Readable scientific chart labels without changing table identifiers."""
    return value.replace('_sen_slope', '').replace('days_tmax_ge_33_kma_slope', 'KMA ≥33°C').replace('days_tmin_ge_25_kma_slope', 'KMA Tmin ≥25°C').replace('_', ' ')


def save_static(tables: dict, root: Path) -> list[str]:
    """Nine fixed-layout figures; axes and comparison units are explicit."""
    outputs = []
    master = tables['spatial_station_master']
    for name in PNGS:
        fig, ax = plt.subplots(figsize=(11, 6.5), layout='constrained')
        if name == 'spatial_robustness_heatmap':
            d = tables['global_morans_i'].copy()
            d['label'] = d.source+' '+d.representation+' / '+d.variable.map(_short)
            pivot = d.pivot(index='label', columns='weight_variant', values='Moran_I')
            fig.set_size_inches(14, 10)
            color = ax.imshow(pivot, cmap='RdBu_r', aspect='auto', vmin=-1, vmax=1)
            fig.colorbar(color, ax=ax, label="Global Moran's I (unadjusted tests)")
            ax.set_xticks(range(len(pivot.columns)), pivot.columns, rotation=35, ha='right', fontsize=8)
            ax.set_yticks(range(len(pivot)), pivot.index, fontsize=8)
        elif name in ('old_new_moran_comparison', 'bridge_moran_comparison'):
            d = tables['spatial_bridge_comparison']; x = np.arange(len(d))
            choices = [('I_45_1981', '45 / 1981–2025'), ('I_51_1991', '51 / 1991–2025')]
            if name.startswith('bridge'):
                choices.insert(1, ('I_45_1991', '45 / 1991–2025'))
            for i, (column, label) in enumerate(choices):
                ax.bar(x+(i-(len(choices)-1)/2)*.25, d[column], width=.24, label=label)
            ax.set_xticks(x, d.variable.map(_short), rotation=25, ha='right'); ax.set_ylabel("Moran's I; directed K4"); ax.legend()
        elif name == 'nasa_station_vs_grid_moran':
            d = tables['nasa_grid_duplication_spatial_sensitivity'].loc[lambda d: d.weight_variant.eq('directed_knn_k4')]
            x = np.arange(len(d))
            ax.bar(x-.18, d.station_linked_Moran_I, .36, label=f'Station-linked N={len(master)}')
            ax.bar(x+.18, d.unique_grid_Moran_I, .36, label=f'Unique grid G={len(tables["nasa_unique_grid_spatial_master"])}')
            ax.set_xticks(x, d.variable.map(_short)); ax.set_ylabel("Moran's I; directed K4"); ax.legend()
        elif name.startswith('coastal_distance_vs_'):
            metric = 'tavg_'+name.split('_')[-1]
            ax.scatter(master.distance_to_coast_km, master[metric], c=np.where(master.nasa_grid_shared, '#c85c42', '#24728a'), alpha=.8)
            ax.axvline(30, color='gray', ls='--', label='Fixed main cutoff 30 km')
            ax.set(xlabel='Distance to official coastline (km)', ylabel=f'{metric} (°C; NASA−KMA Bias)'); ax.legend()
        elif name == 'tmax_tmin_contrast':
            d = master.sort_values('tmin_minus_tmax')
            ax.bar(np.arange(len(d)), d.tmin_minus_tmax, color=np.where(d.tmin_minus_tmax.ge(0), '#c85c42', '#24728a'))
            ax.set_xticks(range(len(d)), d.station_id, rotation=90, fontsize=7)
            ax.set(xlabel='Station ID', ylabel='TMIN Sen − TMAX Sen (°C/decade)')
        elif name == 'seasonal_moran_comparison':
            d = tables['seasonal_spatial_analysis']
            for weight, group in d.groupby('weight_variant', sort=False):
                ax.plot(group.season, group.Moran_I, 'o-', label=weight)
            ax.set(xlabel='Season', ylabel="KMA TAVG Moran's I"); ax.legend()
        else:
            d = tables['coastal_threshold_sensitivity']
            for variable, group in d.groupby('variable', sort=False):
                ax.plot(group.threshold_km, group.rank_biserial, 'o-', label=_short(variable))
            ax.set(xlabel='Prespecified coastal cutoff (km)', ylabel='Rank-biserial effect size (Coastal higher > 0)', xticks=[20, 30, 50])
            ax.legend(fontsize=8, bbox_to_anchor=(1.01, 1), loc='upper left')
        if name != 'spatial_robustness_heatmap':
            ax.axhline(0, color='gray', lw=.7); ax.grid(alpha=.12)
        ax.set_title(name.replace('_', ' ').title()+' | 1991–2025 comparison', fontsize=12)
        path = root/CHART_DIR/f'{name}.png'
        fig.savefig(path, dpi=150, metadata={'Software': 'NASA POWER Korea Climate Explorer'}); plt.close(fig)
        outputs.append(path.relative_to(root).as_posix())
    return outputs


def save_charts(tables: dict, root: Path = PROJECT_ROOT) -> list[str]:
    """Export fixed-ID interactive station/grid maps and deterministic PNGs."""
    (root/CHART_DIR).mkdir(parents=True, exist_ok=True)
    master = display_master(tables)
    grids = tables['nasa_unique_grid_spatial_master']
    bounds = (float(master.nasa_tavg_sen_slope.min()), float(master.nasa_tavg_sen_slope.max()))
    outputs = []
    for name, column in MAPS.items():
        unique = name == 'nasa_unique_grid_tavg_map'
        figure = point_map(grids if unique else master, column, name.replace('_', ' '), unique_grid=unique,
                           color_range=bounds if column == 'nasa_tavg_sen_slope' else None)
        if name == 'nasa_grid_sharing_map':
            for row in master.itertuples():
                figure.add_trace(go.Scattergeo(lat=[row.latitude, row.nasa_grid_latitude], lon=[row.longitude, row.nasa_grid_longitude],
                    mode='lines', line=dict(width=.7, color='#444'), showlegend=False, hoverinfo='skip'))
            figure.add_trace(go.Scattergeo(lat=grids.nasa_grid_latitude, lon=grids.nasa_grid_longitude, mode='markers',
                                           marker=dict(symbol='diamond', size=6, color='black'), name='Inferred grid centres', text=grids.nasa_grid_id))
        path = root/CHART_DIR/f'{name}.html'
        figure.write_html(path, include_plotlyjs='cdn', div_id='stage17-'+name)
        outputs.append(path.relative_to(root).as_posix())
    for season, data in tables['seasonal_station_trends'].groupby('season', sort=True):
        selected = master.merge(data[['station_id', 'sen_slope_per_decade']], on='station_id', validate='one_to_one')
        path = root/CHART_DIR/f'kma_tavg_{season.lower()}_map.html'
        point_map(selected, 'sen_slope_per_decade', f'KMA TAVG {season}').write_html(path, include_plotlyjs='cdn', div_id='stage17-season-'+season)
        outputs.append(path.relative_to(root).as_posix())
    return outputs+save_static(tables, root)


def report_sections(t: dict) -> list[tuple[str, str, pd.DataFrame | None]]:
    """Nineteen evidence sections, with narrative conclusions calculated from result tables."""
    master, grids = t['spatial_station_master'], t['nasa_unique_grid_spatial_master']
    main = t['global_morans_i'].loc[lambda d: d.weight_variant.eq('directed_knn_k4')]
    main = main.merge(t['spatial_robustness_summary'][['variable', 'source', 'representation', 'robustness_class']],
                      on=['variable', 'source', 'representation'], validate='one_to_one')
    columns = ['variable', 'source', 'representation', 'n_spatial_units', 'Moran_I', 'permutation_p', 'robustness_class']
    dup = t['nasa_grid_duplication_spatial_sensitivity'].loc[lambda d: d.weight_variant.eq('directed_knn_k4')]
    contrast = master.tmin_minus_tmax
    dtr = t['dtr_trends'].loc[lambda d: d.source.eq('KMA'), 'sen_slope_per_decade']
    local = t['local_moran_results'].loc[lambda d: d.weight_variant.eq('directed_knn_k4')]
    inje = t['inje_local_continuity']
    stable_n = int(t['stable_local_patterns'].stable_local_pattern.sum())
    local_text = f'BH within each variable×weight family. All three prespecified weights must retain the same FDR-significant quadrant. Stable stations={stable_n}. Main FDR categories: {local.cluster_type_fdr.value_counts().to_dict()}. Inje current stable={bool(inje.loc[inje.analysis.str.contains("1991"), "stable_local_pattern"].any())}; see separate old/new Inje CSV. These are not automatic hotspots.'
    bridge = t['spatial_bridge_comparison']
    comparison_text = BRIDGE_WARNING+' '+str(bridge.interpretation_flag.value_counts().to_dict())
    coastal = t['coastal_threshold_sensitivity']
    significant = {int(k): list(g.loc[g.fdr_significant, 'variable']) for k, g in coastal.groupby('threshold_km')}
    return [
        ('1. Executive summary', f'1991–2025: {len(master)} ASOS stations, {len(grids)} NASA grids, {int(grids.station_count.gt(1).sum())} shared groups. Main directed K4 results below; zero API calls.', main[columns]),
        ('2. Why common-period spatial analysis?', BRIDGE_WARNING, t['vs_1981_spatial_comparison']),
        ('3. Station and grid networks', 'Coordinates and station IDs remain distinct. Grid coordinates are inferred native centres, never averages of station coordinates. Full daily series including NaNs rechecked; within-grid derived NASA slopes must agree.', grids),
        ('4. Weight policy', 'Main directed K4; sensitivity directed K3/K5/K6, symmetric K4, full row IDW p2, connected-cutoff row IDW p1/p2, connected distance-band. Each representation recomputes the connected MST cutoff. No raw IDW or full row p1. Numerical suitability is not scientific validity.', t['spatial_weight_network_summary']),
        ('5. KMA TAVG/TMAX/TMIN spatial pattern', 'Sen slopes in °C/decade; raw Global permutation p, not FDR discoveries.', main.loc[main.variable.isin(['kma_tavg_sen_slope', 'kma_tmax_sen_slope', 'kma_tmin_sen_slope']), columns]),
        ('6. Weight robustness and old/new continuity', 'Stage13 rule unchanged: sign reversal first; ≥75% positive-significant ROBUST_POSITIVE; ≥75% nonsignificant ROBUST_NON_SIGNIFICANT; else WEIGHT_SENSITIVE. Same operational rule, different 13 versus 9 weight sets; not an academic standard.', t['spatial_robustness_summary']),
        ('7. Period/composition bridge', comparison_text, bridge),
        ('8. Local Moran and Inje continuity', local_text, t['stable_local_patterns']),
        ('9. NASA duplication sensitivity', GRID_WARNING+' Main impact counts: '+str(dup.duplication_class.value_counts().to_dict()), dup),
        ('10. NASA representation comparison', 'UNIQUE_GRID−STATION_LINKED defines ΔI. Sign change HIGH; otherwise p-class change or |ΔI|>.1 MODERATE, else LOW. Fixed project thresholds, not field standards. Significance changes are classified moderate unless accompanied by a sign change.', main.loc[main.source.eq('NASA'), columns]),
        ('11. TMAX/TMIN contrast and DTR', f'Contrast median={contrast.median():.6f} °C/decade, TMIN faster={(contrast>1e-12).sum()}, TMAX faster={(contrast < -1e-12).sum()}, range={contrast.min():.6f} to {contrast.max():.6f}. DTR is refitted from annual Tmax−Tmin: median={dtr.median():.6f}, increasing={(dtr>0).sum()}, decreasing={(dtr<0).sum()}. Difference of two Sen slopes is not DTR Sen.', main.loc[main.variable.isin(['tmin_minus_tmax', 'dtr_slope']), columns]),
        ('12. Seasonal spatial patterns', 'KMA TAVG DJF/MAM/JJA/SON; DJF1992–2025 complete boundary rule inherited. Dominant season is a category, not an input to Moran.', t['seasonal_spatial_analysis']),
        ('13. Threshold proxies', 'TMAX≥33°C and TMIN≥25°C, days/decade. Stage16 valid-pair-day proxy slopes retained; zero Sen may reflect sparse events. Never official event counts.', main.loc[main.variable.str.contains('33|25', regex=True), columns]),
        ('14. Bias/RMSE station-specific validation', 'Bias=NASA−KMA (°C), RMSE °C. Never aggregate station validation into grid-level accuracy. Shared/single grid groups are descriptive, not independent-station proof.', main.loc[main.source.eq('NASA-KMA'), columns]),
        ('15. Coast-distance associations', 'Pearson/Spearman are exploratory unadjusted tests; correlation is not attribution. Coastline distances are reused without changing the official geometry.', t['coastal_distance_associations']),
        ('16. Coastal threshold sensitivity', 'Main 30 km fixed before tests; also 20/50 km. Tie-corrected two-sided asymptotic MWU, rank-biserial positive=Coastal higher, BH over nine metrics separately at each cutoff. Significant metrics: '+str(significant), coastal),
        ('17. Regions and elevation', 'Unweighted station medians/IQR; small regions n<3 flagged. Elevation bands <50/50–200/200–500/≥500 m unchanged. Additional elevation/coordinate/coast-old-new CSVs linked below.', t['spatial_regional_summary']),
        ('18. Limitations', LIMITS, t['data_quality'][['station_id', 'source', 'missing_dates', 'tavg_missing', 'tmax_missing', 'tmin_missing']]),
        ('19. Next step', 'Stage18 detailed period sensitivity requires a separate request. This stage performs only the specified bridge, not causal decomposition or model-based attribution.', None)]


def write_reports(tables: dict, root: Path = PROJECT_ROOT) -> list[str]:
    """Generate deterministic HTML/Markdown from saved table values, with complete CSV links."""
    title = f'{len(tables["spatial_station_master"])}-Station Common-Period Spatial Reanalysis | 1991–2025'
    md, html = [f'# {title}\n'], [f'<h1>{escape(title)}</h1>']
    for heading, narrative, frame in report_sections(tables):
        md.append(f'\n## {heading}\n\n{narrative}\n'); html.append(f'<h2>{escape(heading)}</h2><p>{escape(narrative)}</p>')
        if frame is not None:
            notice = f'Showing {min(len(frame), 80)} of {len(frame)} rows; complete CSV linked below.'
            md.extend([notice, markdown_table(frame.head(80))])
            html.extend([f'<p>{notice}</p>', '<div class="table">'+frame.head(80).to_html(index=False, float_format=lambda x: f'{x:.6g}')+'</div>'])
    md.append('\n## Complete results\n'); html.append('<h2>Complete results</h2>')
    for name in sorted(tables):
        url = f'../../tables/common_period_spatial/{PREFIX}{name}.csv'
        md.append(f'- [{name}]({url})'); html.append(f'<p><a href="{url}">{name}</a></p>')
    for name in [*MAPS, *[f'kma_tavg_{s}_map' for s in ('djf', 'mam', 'jja', 'son')]]:
        url = f'../../charts/common_period_spatial/{name}.html'
        md.append(f'\n[{name}]({url})'); html.append(f'<p><a href="{url}">{name}</a></p>')
    for name in PNGS:
        url = f'../../charts/common_period_spatial/{name}.png'
        md.append(f'\n![{name}]({url})'); html.append(f'<img src="{url}" alt="{name}">')
    directory = root/REPORT_DIR; directory.mkdir(parents=True, exist_ok=True)
    paths = [directory/'common_period_51station_spatial_reanalysis_report.html', directory/'common_period_51station_spatial_reanalysis_report.md']
    paths[0].write_text('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>'+escape(title)+
        '</title><style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:16px;color:#193449}'
        '.table{overflow:auto}table{border-collapse:collapse;font-size:12px}td,th{padding:5px;border:1px solid #ccd}'
        'h2{margin-top:40px}p{line-height:1.7}img{max-width:100%}</style></head><body>'+'\n'.join(html)+'</body></html>\n', encoding='utf-8')
    paths[1].write_text('\n'.join(md)+'\n', encoding='utf-8')
    return [p.relative_to(root).as_posix() for p in paths]


def report_from_saved(root: Path = PROJECT_ROOT) -> list[str]:
    """Report-only entry point: validate saved table hashes without recalculating statistics."""
    return write_reports(load_tables(root), root)
