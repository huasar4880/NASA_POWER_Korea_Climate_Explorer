"""Read-only Stage14.5 manifested numerical diagnostics with mtime cache keys."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from src.config import PROJECT_ROOT


def load_manifest(root: Path=PROJECT_ROOT) -> dict:
    """Return an empty state until a numerical review has been saved."""
    try:
        return json.loads((root/'output/manifests/spatial_model_numerical_review_manifest.json').read_text())
    except (OSError,ValueError):
        return {}


@st.cache_data(show_spinner=False)
def _read(path: str,mtime_ns: int) -> pd.DataFrame:
    """Cache only immutable reads; explicitly invalidate when the file changes."""
    return pd.read_csv(path,dtype={'station_id':str})


def load_table(key: str,root: Path=PROJECT_ROOT) -> pd.DataFrame:
    """Reject paths outside the numerical namespace and tolerate missing artifacts."""
    name=load_manifest(root).get('generated_tables',{}).get(key)
    if not name:
        return pd.DataFrame()
    path=(root/name).resolve()
    if not path.is_relative_to((root/'output/tables/spatial_models_numerical').resolve()) or not path.is_file():
        return pd.DataFrame()
    try:
        return _read(str(path),path.stat().st_mtime_ns)
    except (OSError,ValueError):
        return pd.DataFrame()


def render_review(outcome: str) -> None:
    """Render the new expander without modifying or recalculating Stage14 results."""
    with st.expander('수치 안정성 · Stage 14.5',expanded=False):
        manifest=load_manifest()
        if not manifest:
            st.info('수치 안정성 검토 결과가 아직 없습니다.')
            return
        st.warning('Primary non-spatial inference: OLS-HC3. Classical OLS p는 참고용입니다. Solver 경계 (-1,1)와 행렬의 비특이 구간은 다릅니다. 감사용 diagnostic_estimate를 정상 추정값으로 사용하지 마세요.')
        weights=load_table('inverse_distance_weight_diagnostics')
        st.dataframe(weights[['weight_type','row_standardized','density','spectral_radius',
            'lower_admissible_bound','upper_admissible_bound']],hide_index=True)
        boundary=load_table('spatial_boundary_diagnostics')
        st.dataframe(boundary[boundary.outcome.eq(outcome)][['weight_type','model_type','estimate','diagnostic_estimate',
            'relative_boundary_distance','solver_relative_boundary_distance','numerical_class']],hide_index=True)
        st.caption('Admissible 1% / solver 5% 근접은 별도 기준. Distance-band 근접 모형은 정상 추정으로 사용하지 않는 조건부 sensitivity입니다.')
        st.dataframe(load_table('spatial_model_final_specification_recommendation'),hide_index=True)
        interpretation=load_table('stage14_model_interpretation_status')
        st.dataframe(interpretation[interpretation.outcome.eq(outcome)],hide_index=True)
        folder=PROJECT_ROOT/'output/charts/spatial_models_numerical'
        for name in ['parameter_boundary_distance.png','inverse_distance_model_stability.png']:
            if (folder/name).is_file():
                st.image(str(folder/name))
        for name in manifest.get('generated_reports',[]):
            path=PROJECT_ROOT/name
            if path.is_file():
                st.download_button(path.name,path.read_bytes(),file_name=path.name,key='numerical-'+path.suffix)
