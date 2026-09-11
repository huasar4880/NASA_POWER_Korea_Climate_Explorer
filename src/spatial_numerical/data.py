"""Read-only Stage-14 source validation and full previous-stage protection."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.config import PROJECT_ROOT
from src.spatial_models.data import load_inputs as stage14_inputs
from src.spatial.robustness_audit import sha256
from src.spatial_numerical.weights import canonical

OLD_TABLES=['spatial_modeling_master','spatial_model_summary','spatial_model_weight_sensitivity',
            'spatial_model_failures','spatial_model_coefficient_stability','spatial_model_outcome_comparison',
            'spatial_ols_diagnostics']


def snapshot(root: Path=PROJECT_ROOT) -> dict:
    """Protect all previous data/results including the entire Stage-14 namespace."""
    paths=[root/'VERSION']+[p for folder in ('data','output') for p in (root/folder).rglob('*') if p.is_file()]
    return {p.relative_to(root).as_posix():{'sha256':sha256(p),'mtime_ns':p.stat().st_mtime_ns}
            for p in sorted(paths) if 'spatial_models_numerical' not in p.relative_to(root).parts
            and p.name!='spatial_model_numerical_review_manifest.json'}


def load_inputs(root: Path=PROJECT_ROOT) -> tuple[pd.DataFrame,dict,dict,dict]:
    """Validate against Final A and Stage-14 manifest; consume saved modeling master."""
    expected,config,hashes,_=stage14_inputs(root)
    manifest_path=root/'output/manifests/spatial_modeling_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    frames={}
    for key in OLD_TABLES:
        path=root/f'output/tables/spatial_models/{key}.csv'
        name=path.relative_to(root).as_posix()
        digest=sha256(path)
        if manifest['output_hashes'].get(name)!=digest:
            raise ValueError(f'Stage14 checksum mismatch: {key}')
        frames[key]=pd.read_csv(path,dtype={'station_id':str})
        hashes[name]=digest
    master=canonical(frames['spatial_modeling_master']); expected=canonical(expected)
    if list(master.station_id)!=list(expected.station_id):
        raise ValueError('Stage14 station membership mismatch')
    numeric=expected.select_dtypes(include='number').columns
    if not np.allclose(master[numeric],expected[numeric],equal_nan=True):
        raise ValueError('Stage14 values differ from original source of truth')
    hashes[manifest_path.relative_to(root).as_posix()]=sha256(manifest_path)
    return master,config,hashes,frames
