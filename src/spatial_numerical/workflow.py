"""Offline review orchestration and immutable previous-stage artifact checks."""
from __future__ import annotations
import importlib.metadata
import inspect
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.config import PROJECT_ROOT
from src.spatial.robustness_audit import check_snapshot,sha256
from src.spatial_numerical.data import load_inputs,snapshot
from src.spatial_numerical.weights import diagnose_weights
from src.spatial_numerical.review import calculate_review
from src.spatial_numerical.artifacts import create_charts,write_reports
from src.spatial_models.models import ordering_hash

MANIFEST='output/manifests/spatial_model_numerical_review_manifest.json'


def sanity_check(tables: dict,n: int) -> None:
    """Validate numerical diagnostics without requiring every model to succeed."""
    diag=tables['inverse_distance_weight_diagnostics']
    if not diag.n_stations.eq(n).all() or not diag.isolates.eq(0).all():
        raise ValueError('Station count/isolation sanity failure')
    if not np.isfinite(tables['spatial_weight_eigenvalues'][['real','imaginary']]).all().all():
        raise ValueError('Nonfinite spectrum')
    if not diag.spectral_radius.gt(0).all() or not (diag.lower_admissible_bound < diag.upper_admissible_bound).all():
        raise ValueError('Invalid spectral interval')
    runs=tables['spatial_model_numerical_stability']
    if runs.groupby('weight_type').size().ne(6).any():
        raise ValueError('Incomplete numerical comparison')
    if runs.loc[runs.numerical_class.ne('STABLE'),'estimate'].notna().any():
        raise ValueError('Unstable candidate adopted as normal estimate')
    repro=tables['spatial_model_ordering_reproducibility']
    bad=repro[~repro[['same_seed_repeat','ordering_invariant','canonical_weight_hash_equal']].all(axis=1)]
    if not bad.empty:
        flagged=bad.merge(runs,on=['weight_type','outcome','model_type'],validate='one_to_one')
        if not flagged.numerical_class.eq('NUMERICALLY_UNSTABLE').all():
            raise ValueError('Reproducibility failure must be classified as numerically unstable')


def run_review(dry_run: bool=False,root: Path=PROJECT_ROOT) -> dict:
    """Review fixed specifications; write only new numerical namespaces, never Stage14."""
    master,config,hashes,old=load_inputs(root)
    inventory,_=diagnose_weights(master)
    plan=dict(station_count=len(master),station_ordering_hash=ordering_hash(tuple(master.station_id)),
        input_hashes=hashes,weight_configs=[item['setting'] for item in inventory.values()],
        numerical_model_combinations=len(inventory)*6,repeat_and_ordering_runs_per_combination=3,
        spectral_settings={'real_eigenvalue_tolerance':'1e-9*max(1,radius)',
            'admissible_definition':'open zero-connected nonsingularity component',
            'near_admissible_relative':.01,'near_solver_relative':.05,'solver_boundary_absolute':1e-6,
            'density_denominator':'n*(n-1)','cutoff_rule':'single Stage13 connected distance-band radius'},
        model_configs={'families':['SAR','SEM'],'outcomes':['kma_tavg_sen_slope','tavg_bias','tavg_rmse'],
            'predictors':['distance_to_coast_km','latitude','elevation_m'],
            'method':'FULL','solver_bounds':[-1,1],'tolerance':'native defaults unchanged',
            'native_optimizer_observation':'transparent wrapper, no argument/return-value modifications',
            'profile_points_per_scope':81,'profile_extended_scope':'diagnostic evaluation only; no expanded-bound fit',
            'primary_ols_inference':'HC3 robust standard errors','classical_p_role':'descriptive/reference'},
        random_seed=config['random_seed'],moran_permutations=config['moran_permutations'],
        NASA_API_calls=0,KMA_API_calls=0,new_climate_metrics=False,dry_run=dry_run)
    if dry_run:
        return plan
    protected=snapshot(root)
    tables,inventory=calculate_review(master,config,old)
    sanity_check(tables,len(master))
    paths={}
    for key,frame in tables.items():
        path=root/f'output/tables/spatial_models_numerical/{key}.csv';path.parent.mkdir(parents=True,exist_ok=True)
        frame.to_csv(path,index=False);paths[key]=path.relative_to(root).as_posix()
    saved={key:pd.read_csv(root/path,dtype={'station_id':str}) for key,path in paths.items()}
    charts=create_charts(saved,inventory,root)
    plan.update(generated_tables=paths,generated_charts=charts,
        library_versions={key:importlib.metadata.version(key) for key in ['numpy','pandas','scipy','spreg','libpysal','statsmodels','matplotlib','streamlit']},
        numerical_class_counts=tables['spatial_model_numerical_stability'].numerical_class.value_counts().to_dict())
    # Record installed implementation fingerprints without personal filesystem paths.
    import spreg.ml_lag as lag
    import spreg.ml_error as error
    import spreg.utils as utils
    plan['installed_library_source_hashes']={module.__name__:sha256(Path(inspect.getfile(module))) for module in (lag,error,utils)}
    reports=write_reports(saved,plan,root);plan['generated_reports']=reports
    changed=check_snapshot(root,protected)
    plan.update(protected_files_count=len(protected),protected_files_changed=changed)
    if changed:
        raise RuntimeError(f'Previous-stage artifacts changed: {changed}')
    plan['output_hashes']={name:sha256(root/name) for name in [*paths.values(),*charts,*reports]}
    path=root/MANIFEST;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return plan


def report_from_saved(root: Path=PROJECT_ROOT) -> list[str]:
    """Rebuild ONLY Stage14.5 reports from checksum-verified saved files."""
    manifest=json.loads((root/MANIFEST).read_text())
    for name,digest in manifest['output_hashes'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('Unsafe manifest path')
        if name not in manifest['generated_reports'] and sha256(path)!=digest:
            raise ValueError(f'Review checksum mismatch: {name}')
    tables={key:pd.read_csv(root/name,dtype={'station_id':str}) for key,name in manifest['generated_tables'].items()}
    return write_reports(tables,manifest,root)
