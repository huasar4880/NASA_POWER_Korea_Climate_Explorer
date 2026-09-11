"""Offline Stage-14 orchestration, integrity audit and reproducible saved reporting."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.config import PROJECT_ROOT
from src.spatial.robustness_audit import sha256, check_snapshot
from src.spatial_models.data import load_inputs, protected_snapshot, OUTCOMES, PREDICTORS
from src.spatial_models.analysis import selected_weights, calculate
from src.spatial_models.models import ordering_hash
from src.spatial_models.visualization import CHART_NAMES, create_charts
from src.spatial_models.reporting import write_reports

MANIFEST = 'output/manifests/spatial_modeling_manifest.json'
TABLE_NAMES = ['spatial_modeling_master','spatial_ols_results','spatial_ols_diagnostics','spatial_model_vif',
               'spatial_lm_diagnostics','spatial_model_summary','spatial_model_outcome_comparison',
               'spatial_model_coefficient_stability','spatial_model_weight_sensitivity',
               'spatial_model_leave_one_out_sensitivity','spatial_model_loo_summary',
               'spatial_model_influence_diagnostics','spatial_model_residuals','spatial_model_failures',
               'tavg_spatial_model_comparison','bias_spatial_model_comparison','rmse_spatial_model_comparison',
               'spatial_model_scaling','spatial_model_prior_robustness','spatial_model_stage13_ols_reproduction']
REPORTS = [f'output/reports/spatial_models/spatial_dependence_adjusted_modeling_report.{ext}' for ext in ('html','md')]


def execution_plan(master: pd.DataFrame, config: dict, hashes: dict) -> dict:
    """Describe bounded fits and expected files without fitting or writing."""
    settings, weights = selected_weights(master, config)
    return {'station_count': len(master), 'outcomes': OUTCOMES, 'predictors': PREDICTORS,
            'model_families': ['OLS','SAR','SEM'], 'weight_configurations': settings,
            'main_model_weight_cells': 36, 'main_unique_fits': 27, 'longitude_sensitivity_fits': 9,
            'standardized_additional_fits': 0, 'loo_fits': len(master)*len(OUTCOMES),
            'expected_model_count': 36 + len(master)*len(OUTCOMES),
            'scaling_method': 'exact affine reparameterization of all main and longitude fits; predictors only, ddof=0',
            'expected_output_files': [*[f'output/tables/spatial_models/{key}.csv' for key in TABLE_NAMES],
                                      *[f'output/charts/spatial_models/{name}' for name in CHART_NAMES], *REPORTS, MANIFEST],
            'input_hashes': hashes, 'ordering_hash': ordering_hash(tuple(master.station_id)),
            'weight_matrix_hashes': {key: __import__('hashlib').sha256(w.matrix.astype('<f8').tobytes()).hexdigest() for key,w in weights.items()},
            'random_seed': config['random_seed'], 'diagnostic_settings': {'permutations': config['moran_permutations'],
                'outcome_seed_offsets': {'kma_tavg_sen_slope':0,'tavg_bias':4,'tavg_rmse':5},
                'alpha': .05, 'VIF_flag':5, 'Cook_threshold':'4/n', 'BP':'Koenker studentized',
                'moran':'Stage13 two-sided permutation centered at -1/(n-1); exploratory residual exchangeability assumption',
                'spatial_optimizer_bounds':[-1,1], 'spatial_optimizer_audit':'independent scipy profile ML, success + parameter and likelihood agreement',
                'AIC_BIC':'full Gaussian ML; all parameters including variance; native IC separately retained',
                'FDR':'baseline original coast across three outcomes, separately for OLS, OLS-HC3, SAR, SEM'},
            'NASA_API_calls':0, 'KMA_API_calls':0, 'coastline_downloads':0}


def validate_outputs(tables: dict, n: int) -> None:
    """Sanity checks on successful fits; failed fits remain explicitly incomplete."""
    summary = tables['spatial_model_summary']
    success = summary[summary.converged]
    required = ['coefficient','std_error','p_value','AIC','BIC','log_likelihood','residual_moran_I','residual_moran_p']
    if not np.isfinite(success[required].to_numpy(float)).all() or not summary.n.eq(n).all():
        raise ValueError('Model summary numeric/station sanity check failed')
    if not success.p_value.between(0,1).all() or not success.residual_moran_p.between(0,1).all():
        raise ValueError('Invalid probabilities')
    if not np.isfinite(tables['spatial_model_vif'].VIF).all():
        raise ValueError('Nonfinite VIF')
    loo = tables['spatial_model_leave_one_out_sensitivity']
    if not loo.groupby('outcome').size().eq(n).all() or not loo.n.eq(n-1).all():
        raise ValueError('LOO iteration/sample mismatch')
    if success.ordering_hash.nunique() != 1:
        raise ValueError('Inconsistent station ordering')


def run_modeling(dry_run: bool = False, root: Path = PROJECT_ROOT) -> dict:
    """Read existing observations; write only new Stage-14 namespaces."""
    master, config, hashes, frames = load_inputs(root)
    plan = execution_plan(master, config, hashes)
    plan['dry_run'] = dry_run
    if dry_run:
        return plan
    before = protected_snapshot(root)
    tables = calculate(master, config)
    tables['spatial_model_scaling'] = pd.DataFrame([{'predictor': p, 'mean': master[p].mean(),
        'population_sd': master[p].std(ddof=0), 'original_unit': 'km' if p == PREDICTORS[0] else 'm' if p == 'elevation_m' else 'degree'}
        for p in [*PREDICTORS, 'longitude']])
    tables['spatial_model_prior_robustness'] = frames['robustness'][frames['robustness'].variable.isin(OUTCOMES)].copy()
    old = frames['old_ols']
    old = old[old.variable.isin(OUTCOMES)].rename(columns={'variable':'outcome','term':'predictor','coefficient':'stage13_coefficient'})
    new = tables['spatial_model_summary'].query("model_type == 'OLS' and scale == 'original' and specification == 'main' and weight_type == 'directed_knn_k4'")
    reproduction = old[['outcome','predictor','stage13_coefficient']].merge(new[['outcome','predictor','coefficient']], on=['outcome','predictor'], validate='one_to_one')
    reproduction['absolute_difference'] = (reproduction.coefficient-reproduction.stage13_coefficient).abs()
    reproduction['reproduced'] = np.isclose(reproduction.coefficient, reproduction.stage13_coefficient, atol=1e-10)
    if reproduction.empty or not reproduction.reproduced.all():
        raise ValueError('Stage-13 OLS reproduction failed')
    tables['spatial_model_stage13_ols_reproduction'] = reproduction
    validate_outputs(tables, len(master))
    paths = {}
    for name, frame in tables.items():
        path = root / f'output/tables/spatial_models/{name}.csv'
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        paths[name] = path.relative_to(root).as_posix()
    # Both first report and saved-report regeneration use the exact same CSV parser.
    saved = {name: pd.read_csv(root/path, dtype={'station_id':str, 'excluded_station_id':str}) for name,path in paths.items()}
    charts = create_charts(saved, root)
    plan.update(generated_tables=paths, generated_charts=charts,
                software_versions={name: importlib.metadata.version(name) for name in ['numpy','pandas','scipy','statsmodels','spreg','libpysal','matplotlib','plotly','streamlit']},
                failed_models=len(tables['spatial_model_failures']))
    reports = write_reports(saved, plan, root)
    plan['generated_reports'] = reports
    changed = check_snapshot(root, before)
    plan.update(protected_files_count=len(before), protected_files_changed=changed)
    if changed:
        raise RuntimeError(f'Protected files changed: {changed}')
    plan['output_hashes'] = {name: sha256(root/name) for name in [*paths.values(), *charts, *reports]}
    path = root / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return plan


def report_from_saved(root: Path = PROJECT_ROOT) -> list[str]:
    """Regenerate only new reports after verifying table/chart checksums; never refit."""
    manifest = json.loads((root/MANIFEST).read_text())
    for name, digest in manifest['output_hashes'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('Invalid manifest path')
        if name not in manifest['generated_reports'] and sha256(path) != digest:
            raise ValueError(f'Stored artifact checksum mismatch: {name}')
    tables = {key: pd.read_csv(root/name, dtype={'station_id':str, 'excluded_station_id':str}) for key,name in manifest['generated_tables'].items()}
    return write_reports(tables, manifest, root)
