"""Deterministic coefficient/diagnostic charts and station-point residual maps."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.spatial_models.data import OUTCOMES, PREDICTORS, BASE_WEIGHT

PREFIXES = dict(zip(OUTCOMES, ['tavg', 'bias', 'rmse']))
LABELS = dict(zip(OUTCOMES, ['KMA TAVG trend', 'NASA-KMA Bias', 'NASA-KMA RMSE']))
CHART_NAMES = [f'{p}_coast_coefficient_comparison.png' for p in PREFIXES.values()] + [
    'residual_moran_comparison.png', 'model_aic_comparison.png'] + [f'{p}_loo_sensitivity.png' for p in PREFIXES.values()] + [
    f'{m}_residual_maps.html' for m in ('ols', 'sar', 'sem')]


def baseline_rows(summary: pd.DataFrame) -> pd.DataFrame:
    """Return baseline original-scale coast terms, including HC3 separately."""
    return summary[summary.weight_type.eq(BASE_WEIGHT) & summary.specification.eq('main')
                   & summary.scale.eq('original') & summary.predictor.eq(PREDICTORS[0])]


def create_charts(tables: dict, root: Path) -> list[str]:
    """Save eight PNGs and three maps; no interpolation or basemap downloads."""
    directory = root / 'output/charts/spatial_models'
    directory.mkdir(parents=True, exist_ok=True)
    baseline = baseline_rows(tables['spatial_model_summary'])
    paths = []

    def save(fig: plt.Figure, filename: str) -> None:
        """Finalize a labeled figure with deterministic Matplotlib metadata."""
        fig.tight_layout()
        path = directory / filename
        fig.savefig(path, dpi=160, facecolor='white')
        plt.close(fig)
        paths.append(path.relative_to(root).as_posix())

    for outcome, prefix in PREFIXES.items():
        sample = baseline[baseline.outcome.eq(outcome)].set_index('model_type').reindex(['OLS','OLS-HC3','SAR','SEM'])
        fig, ax = plt.subplots(figsize=(8, 4.2))
        for i, (label, row) in enumerate(sample.iterrows()):
            if row.converged:
                ax.errorbar(row.coefficient, i, xerr=[[row.coefficient-row.ci_lower], [row.ci_upper-row.coefficient]],
                            fmt='o', capsize=5, color=['#26758c','#7a5195','#d17a21','#33845a'][i])
            else:
                ax.text(.05, i, 'FAILED', transform=ax.get_yaxis_transform())
        ax.set_yticks(range(4), sample.index)
        ax.axvline(0, color='#888888', linewidth=1)
        ax.set_title(f'{LABELS[outcome]}: coast coefficient, 95% CI\nDirected KNN k=4; exploratory, not causal')
        ax.set_xlabel('Coefficient (°C/decade/km)' if prefix == 'tavg' else 'Coefficient (°C/km)')
        ax.grid(axis='x', alpha=.2)
        save(fig, f'{prefix}_coast_coefficient_comparison.png')
        loo = tables['spatial_model_leave_one_out_sensitivity']
        loo = loo[loo.outcome.eq(outcome)].sort_values('coefficient')
        fig, ax = plt.subplots(figsize=(9, 4.2))
        ax.plot(range(len(loo)), loo.coefficient, 'o', color='#26758c', markersize=4)
        ax.axhline(sample.loc['OLS','coefficient'], linestyle='--', color='#d17a21', label='Full-sample OLS')
        ax.axhline(0, color='#888888', linewidth=1)
        positions = np.unique(np.linspace(0, len(loo)-1, min(10,len(loo))).astype(int))
        ax.set_xticks(positions, loo.excluded_station_id.iloc[positions].astype(str), rotation=45)
        ax.set_xlabel('Excluded station ID (sorted by coefficient; all stations retained in main models)')
        ax.set_ylabel('Coast coefficient (' + ('°C/decade/km)' if prefix == 'tavg' else '°C/km)'))
        ax.set_title(f'{LABELS[outcome]}: leave-one-out sensitivity')
        ax.legend()
        save(fig, f'{prefix}_loo_sensitivity.png')
    for column, filename, label in [('residual_moran_I','residual_moran_comparison.png','Innovation Moran I'),
                                      ('AIC','model_aic_comparison.png','Gaussian AIC (including variance parameter)')]:
        fig, axes = plt.subplots(1, 3, figsize=(12,4.4))
        for ax, outcome in zip(axes, OUTCOMES):
            sample = baseline[baseline.outcome.eq(outcome) & baseline.model_type.isin(['OLS','SAR','SEM'])]
            ax.bar(sample.model_type, sample[column], color=['#26758c','#d17a21','#33845a'])
            ax.set_title(LABELS[outcome])
            ax.set_ylabel(label)
            ax.grid(axis='y', alpha=.2)
            if column == 'residual_moran_I':
                for i, row in enumerate(sample.itertuples()):
                    ax.text(i, row.residual_moran_I, f'p={row.residual_moran_p:.3f}', ha='center', va='bottom', fontsize=9)
        fig.suptitle('Baseline weight only; compare AIC within outcome, not between outcomes', fontsize=10)
        save(fig, filename)
    residuals = tables['spatial_model_residuals']
    residuals = residuals[residuals.specification.eq('main') & residuals.weight_type.eq(BASE_WEIGHT)]
    locations = tables['spatial_modeling_master'][['station_id','station_name','latitude','longitude']]
    for family in ('OLS','SAR','SEM'):
        fig = make_subplots(rows=1, cols=3, subplot_titles=[LABELS[y] for y in OUTCOMES], horizontal_spacing=.08)
        for j, outcome in enumerate(OUTCOMES, start=1):
            sample = residuals[residuals.model_type.eq(family) & residuals.outcome.eq(outcome)].merge(locations, on='station_id', validate='one_to_one')
            all_outcome = residuals[residuals.outcome.eq(outcome)]
            limit = float(all_outcome.residual.abs().max())
            if sample.empty:
                fig.add_annotation(text='MODEL FAILED', x=.5, y=.5, row=1, col=j, showarrow=False)
                continue
            fig.add_trace(go.Scatter(x=sample.longitude, y=sample.latitude, mode='markers',
                marker=dict(size=10, color=sample.residual, colorscale='RdBu_r', cmin=-limit, cmax=limit,
                            showscale=True, colorbar=dict(x=j/3-.025, len=.75, thickness=9, title='°C/decade' if j==1 else '°C')),
                text=sample.station_name, customdata=np.column_stack([sample.station_id, sample.residual]),
                hovertemplate='%{text} (%{customdata[0]})<br>innovation=%{customdata[1]:.5f}<extra></extra>',
                showlegend=False), row=1, col=j)
            fig.update_xaxes(title_text='Longitude (°E)', range=[125.5,130.1], row=1,col=j)
            fig.update_yaxes(title_text='Latitude (°N)', range=[33,39], row=1,col=j)
        fig.update_layout(title=f'{family} innovation residuals | directed KNN k=4 | station points only, no interpolation',
                          width=1320, height=640, template='plotly_white', margin=dict(t=110,r=60,l=55,b=65))
        path = directory / f'{family.lower()}_residual_maps.html'
        fig.write_html(path, include_plotlyjs='cdn', div_id=f'stage14-{family.lower()}-residuals')
        paths.append(path.relative_to(root).as_posix())
    return paths
