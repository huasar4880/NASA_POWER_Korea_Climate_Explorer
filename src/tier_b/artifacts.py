"""Deterministic Tier B figures and saved-table-only reports."""
from __future__ import annotations

from html import escape
from pathlib import Path
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.tier_b.data import TABLE_DIR, CHART_DIR, REPORT_DIR, WARNING, MANIFEST
from src.spatial.robustness_audit import sha256

TABLES = ('tier_b_analysis_stations', 'tier_b_data_quality', 'tier_b_annual_completeness',
          'tier_b_annual_temperature_1991_2025', 'tier_b_temperature_trends',
          'tier_b_temperature_normals_1991_2020', 'tier_b_temperature_anomalies_1991_2025',
          'tier_b_seasonal_temperature_trends', 'tier_b_threshold_annual', 'tier_b_threshold_trends',
          'tier_b_nasa_kma_temperature_validation', 'tier_b_nasa_kma_trend_consistency',
          'tier_b_station_temperature_summary', 'tier_b_temperature_rankings',
          'tier_b_station_coastal_distance')
CHARTS = ('tier_b_tavg_trends', 'tier_b_tmax_tmin_trends', 'tier_b_anomaly_heatmap',
          'tier_b_seasonal_trends', 'tier_b_threshold_33c', 'tier_b_threshold_25c',
          'tier_b_validation_bias', 'tier_b_validation_rmse')


def load_tables(root: Path = PROJECT_ROOT, *, verify: bool = True) -> dict[str, pd.DataFrame]:
    """Read only the explicit Tier B output allowlist; never trigger downloads or fits."""
    manifest_path = root/MANIFEST
    if verify and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('status') != 'completed':
            raise ValueError('Tier B run incomplete; saved tables may be stale')
        for name in TABLES:
            path = root/TABLE_DIR/f'{name}.csv'
            expected = manifest.get('output_hashes', {}).get(path.relative_to(root).as_posix())
            if not expected or sha256(path) != expected:
                raise ValueError(f'Tier B table checksum mismatch: {name}')
    return {name: pd.read_csv(root/TABLE_DIR/f'{name}.csv', dtype={'station_id': str}) for name in TABLES}


def _bars(ax: plt.Axes, frame: pd.DataFrame, value: str, group: str, title: str, unit: str) -> None:
    """Small grouped station bars with explicit units and zero reference."""
    pivot = frame.pivot(index='station_id', columns=group, values=value).sort_index(key=lambda x: x.astype(int))
    pivot.plot.bar(ax=ax, width=.78, rot=0, color=['#0072B2', '#D55E00', '#009E73', '#CC79A7'])
    ax.set(title=title, xlabel='Station ID (Tier B only)', ylabel=unit)
    ax.axhline(0, color='#555555', linewidth=.6)
    ax.grid(axis='y', alpha=.2)


def save_charts(tables: dict[str, pd.DataFrame], root: Path = PROJECT_ROOT) -> list[str]:
    """Generate eight scientific PNGs, keeping station IDs font-portable."""
    directory = root/CHART_DIR
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    trends = tables['tier_b_temperature_trends']
    for name in CHARTS:
        fig, ax = plt.subplots(figsize=(10, 5), layout='constrained')
        if name == 'tier_b_tavg_trends':
            _bars(ax, trends.loc[trends.metric.eq('TAVG')], 'sen_slope_per_decade', 'source',
                  'TAVG Sen trend | 1991–2025', '°C / decade')
        elif name == 'tier_b_tmax_tmin_trends':
            selected = trends.loc[trends.metric.isin(['TMAX', 'TMIN'])].copy()
            selected['series'] = selected.source + ' ' + selected.metric
            _bars(ax, selected, 'sen_slope_per_decade', 'series', 'TMAX / TMIN Sen trends | 1991–2025', '°C / decade')
        elif name == 'tier_b_anomaly_heatmap':
            anomaly = tables['tier_b_temperature_anomalies_1991_2025']
            matrix = anomaly.loc[anomaly.source.eq('KMA') & anomaly.metric.eq('TAVG')].pivot(
                index='station_id', columns='year', values='anomaly').sort_index(key=lambda x: x.astype(int))
            limit = max(abs(matrix.to_numpy()).max(), .01)
            im = ax.imshow(matrix, aspect='auto', cmap='RdBu_r', vmin=-limit, vmax=limit)
            ax.set_yticks(range(len(matrix)), matrix.index)
            ax.set_xticks(range(0, len(matrix.columns), 4), matrix.columns[::4], rotation=45)
            ax.set(title='KMA TAVG anomaly | normal 1991–2020', xlabel='Year', ylabel='Station ID')
            fig.colorbar(im, ax=ax, label='°C relative to 1991–2020 normal')
        elif name == 'tier_b_seasonal_trends':
            seasonal = tables['tier_b_seasonal_temperature_trends']
            _bars(ax, seasonal.loc[seasonal.source.eq('KMA') & seasonal.metric.eq('TAVG')],
                  'sen_slope_per_decade', 'season', 'KMA seasonal TAVG Sen trends', '°C / decade')
        elif name in ('tier_b_threshold_33c', 'tier_b_threshold_25c'):
            threshold = 'TMAX_GE_33' if name.endswith('33c') else 'TMIN_GE_25'
            frame = tables['tier_b_threshold_trends']
            _bars(ax, frame.loc[frame.threshold.eq(threshold)], 'sen_slope_per_decade', 'source',
                  f'{threshold} trend | paired-day analysis proxy, not official KMA statistic', 'days / decade')
        else:
            value = 'bias' if name.endswith('bias') else 'rmse'
            frame = tables['tier_b_nasa_kma_temperature_validation']
            _bars(ax, frame, value, 'metric', f'Daily NASA − KMA | {value.upper()}', '°C')
        path = directory/f'{name}.png'
        fig.savefig(path, dpi=160, metadata={'Software': 'NASA POWER Korea Climate Explorer'})
        plt.close(fig)
        paths.append(path.relative_to(root).as_posix())
    return paths


def report_sections(tables: dict[str, pd.DataFrame]) -> list[tuple[str, str, pd.DataFrame | None]]:
    """Provide the same thirteen evidence-backed sections to Markdown and HTML."""
    trends = tables['tier_b_temperature_trends']
    columns = ['station_id', 'station_name', 'source', 'sen_slope_per_decade', 'sen_ci_lower', 'sen_ci_upper', 'fdr_q_value']
    return [
        ('1. Cohort', WARNING, tables['tier_b_analysis_stations']),
        ('2. Selection', 'Final B shortlist + master eligible_1991_2025, no manual review; low/medium continuity only. '
         'No Tier A rows or hardcoded station IDs. Invalid selection stops the run.', None),
        ('3. Data quality', '12784 calendar days; missing observations remain NaN. Screening failure withholds all cohort statistics. '
         'Per-variable missing ≤5%, longest core gap <90 days, ≥90% of years with ≥90% core completeness.', tables['tier_b_data_quality']),
        ('4. TAVG', 'Sen and CI: °C/decade. Linear/MK/lag-1 Hamed–Rao sensitivity reuse existing methods. '
         'BH FDR independently within source × metric, Tier B only, α=.05.', trends.loc[trends.metric.eq('TAVG'), columns]),
        ('5. TMAX', 'Daily maxima annual means; not annual extreme maximum.', trends.loc[trends.metric.eq('TMAX'), columns]),
        ('6. TMIN', 'Daily minima annual means; not annual extreme minimum.', trends.loc[trends.metric.eq('TMIN'), columns]),
        ('7. Normal and anomalies', 'Equal-weight mean of 30 annual means, 1991–2020. Annual anomaly = annual mean − normal (°C). '
         'First/last comparisons: 1991–2000 versus 2016–2025, in station summary.', tables['tier_b_temperature_anomalies_1991_2025'].loc[
             lambda d: d.year.eq(2025), ['station_id', 'source', 'metric', 'annual_mean', 'normal_mean', 'anomaly']]),
        ('8. Seasons', 'December belongs to following DJF; incomplete boundary seasons excluded, ≥95% valid daily values. '
         'DJF 1992–2025; other seasons 1991–2025. FDR within source × metric × season.',
         tables['tier_b_seasonal_temperature_trends'][['station_id', 'source', 'metric', 'season', 'sen_slope_per_decade', 'fdr_q_value']]),
        ('9. Threshold proxies', 'TMAX≥30/33°C, TMIN≥25°C; count only metric-matched valid days for NASA/KMA. '
         'Not official KMA heat-wave/tropical-night statistics; missing days are not zero or scaled. Sen units days/decade.',
         tables['tier_b_threshold_trends'][['station_id', 'source', 'threshold', 'mean_annual_count', 'sen_slope_per_decade', 'fdr_q_value']]),
        ('10. Daily validation', 'Bias = NASA − KMA. MAE/RMSE in °C; Pearson/Spearman dimensionless. Each metric uses its own valid pairs.',
         tables['tier_b_nasa_kma_temperature_validation'][['station_id', 'metric', 'n_pairs', 'bias', 'mae', 'rmse', 'pearson_r', 'spearman_rho']]),
        ('11. Trend consistency', 'Direction agreement is not absolute agreement or equal trend magnitude.', tables['tier_b_nasa_kma_trend_consistency']),
        ('12. Limits and coastal distance', 'Small, non-area-weighted cohort; period differences prohibit direct Tier A magnitude comparison. '
         'Grid versus point, station history, autocorrelation, multiple testing and proxy missingness remain limitations. '
         'Official cached coastline distance is descriptive only: no Coastal/Inland tests, Moran, SAR or SEM. '
         'Stage14.5 numerical weight policy is retained, not fitted here.', tables['tier_b_station_coastal_distance']),
        ('13. Stage16 preparation', 'Next stage may combine verified A+B on a common 1991–2025 period after a separate authorization. '
         'No combined rankings, reanalysis or spatial models were executed in Stage15.', None),
    ]


def write_reports(tables: dict[str, pd.DataFrame], root: Path = PROJECT_ROOT) -> list[str]:
    """Write deterministic saved-result reports without reading raw or calling APIs."""
    from src.spatial.robustness_reporting import markdown_table
    title = 'Tier B 1991–2025 Independent Cohort Analysis'
    md, html = [f'# {title}\n'], [f'<h1>{title}</h1>']
    for heading, text, frame in report_sections(tables):
        md.append(f'\n## {heading}\n\n{text}\n')
        html.append(f'<section><h2>{escape(heading)}</h2><p>{escape(text)}</p>')
        if frame is not None:
            md.append(markdown_table(frame))
            html.append('<div class="table">'+frame.to_html(index=False, escape=True, float_format=lambda x: f'{x:.6g}')+'</div>')
        html.append('</section>')
    for name in CHARTS:
        link = f'../../charts/tier_b/{name}.png'
        md.append(f'\n![{name}]({link})\n')
        html.append(f'<figure><img src="{link}" alt="{name}"></figure>')
    directory = root/REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory/'tier_b_temperature_analysis_report.md'
    webpage = directory/'tier_b_temperature_analysis_report.html'
    markdown.write_text('\n'.join(md)+'\n', encoding='utf-8')
    webpage.write_text('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>'+title+
                       '</title><style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:16px;color:#182b3a}'
                       '.table{overflow:auto}table{border-collapse:collapse;font-size:13px}td,th{padding:6px;border:1px solid #ccd}'
                       'h2{margin-top:40px;color:#17517a}img{max-width:100%}p{line-height:1.7}</style></head><body>'+
                       '\n'.join(html)+'</body></html>\n', encoding='utf-8')
    return [p.relative_to(root).as_posix() for p in (webpage, markdown)]


def report_from_saved(root: Path = PROJECT_ROOT) -> list[str]:
    """Public report-only entry point."""
    return write_reports(load_tables(root), root)
