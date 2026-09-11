"""Fourteenth, entirely read-only exploratory spatial modeling page."""
from __future__ import annotations
import streamlit as st
import streamlit.components.v1 as components
from dashboard.spatial_model_loader import load_manifest, load_table
from src.config import PROJECT_ROOT
from src.spatial_models.data import OUTCOMES, PREDICTORS, BASE_WEIGHT
from src.spatial_models.visualization import LABELS, PREFIXES, baseline_rows
from src.spatial_models.reporting import LIMITATIONS, narrative


def render() -> None:
    """Render saved models and diagnostics without analysis or external data requests."""
    st.title('공간보정 모델')
    st.caption('Experimental Stage 14 · Spatial Dependence–Adjusted Modeling · 저장 결과 전용')
    manifest = load_manifest()
    if not manifest:
        st.info('먼저 python main.py --analyze-spatial-models를 실행하세요.')
        return
    st.warning(LIMITATIONS)
    c1,c2,c3 = st.columns(3)
    c1.metric('Final Tier A', manifest['station_count'])
    c2.metric('주요 가중치', len(manifest['weight_configurations']))
    c3.metric('실패/불안정 모형', manifest['failed_models'])
    st.write('Spatial Lag: 인접 station outcome의 통계적 의존성을 포함합니다. Spatial Error: 잔차에 남는 공간구조를 반영합니다. 인과효과 분석이 아닙니다.')
    outcome = st.selectbox('Outcome', OUTCOMES, format_func=lambda y: LABELS[y])
    from dashboard.numerical_review_loader import render_review
    render_review(outcome)
    summary = load_table('spatial_model_summary')
    if summary.empty:
        st.error('저장된 model summary를 읽을 수 없습니다.')
        return
    base = baseline_rows(summary)
    base = base[base.outcome.eq(outcome)]
    st.info(narrative(base))
    display = ['model_type','coefficient','std_error','p_value','fdr_q','ci_lower','ci_upper','rho','lambda','AIC','BIC','residual_moran_I','residual_moran_p','converged']
    for title, models in [('OLS baseline / HC3',['OLS','OLS-HC3']), ('Spatial Lag (SAR)',['SAR']), ('Spatial Error (SEM)',['SEM'])]:
        st.subheader(title)
        st.dataframe(base[base.model_type.isin(models)][display], hide_index=True)
    st.subheader('OLS diagnostics / VIF / Influence / LM')
    for name in ('spatial_ols_diagnostics','spatial_model_vif','spatial_model_influence_diagnostics','spatial_lm_diagnostics'):
        with st.expander(name):
            frame = load_table(name)
            st.dataframe(frame[frame.outcome.eq(outcome)], hide_index=True)
    st.subheader('Coefficient comparison / Residual Moran / Fit')
    folder = PROJECT_ROOT/'output/charts/spatial_models'
    for name in (f'{PREFIXES[outcome]}_coast_coefficient_comparison.png','residual_moran_comparison.png','model_aic_comparison.png'):
        if (folder/name).is_file():
            st.image(str(folder/name))
    st.caption('SEM Moran은 filtered innovation 기준. Structural residual Moran도 summary 원표에서 확인할 수 있습니다. R²와 pseudo-R²는 직접 비교하지 않습니다.')
    st.subheader('Weight sensitivity / Standardized / Longitude sensitivity')
    for name in ('spatial_model_coefficient_stability','spatial_model_weight_sensitivity'):
        frame = load_table(name)
        frame = frame[frame.outcome.eq(outcome)]
        if name == 'spatial_model_weight_sensitivity':
            frame = frame[['model_type','weight_type','coefficient','p_value','rho','lambda',
                           'AIC','residual_moran_I','residual_moran_p','converged','numerical_issue']]
        st.dataframe(frame, hide_index=True)
    st.caption('ROBUST_SIGNIFICANT는 OLS classical/SAR/SEM의 12셀 운영분류입니다. HC3 강건성 보장은 아닙니다. INCOMPLETE_MODELS는 실패 조합 때문에 전체 강건성을 확정할 수 없다는 뜻입니다.')
    with st.expander('표준화 및 경도 추가 결과'):
        st.dataframe(summary[summary.outcome.eq(outcome) & summary.weight_type.eq(BASE_WEIGHT)
                            & summary.predictor.isin([*PREDICTORS,'longitude'])], hide_index=True)
    st.subheader('LOO sensitivity')
    frame = load_table('spatial_model_loo_summary')
    st.dataframe(frame[frame.outcome.eq(outcome)], hide_index=True)
    if (folder/f'{PREFIXES[outcome]}_loo_sensitivity.png').is_file():
        st.image(str(folder/f'{PREFIXES[outcome]}_loo_sensitivity.png'))
    st.subheader('Residual maps · station points only')
    family = st.radio('Residual model', ['OLS','SAR','SEM'], horizontal=True)
    path = folder/f'{family.lower()}_residual_maps.html'
    if path.is_file():
        if hasattr(st, 'iframe'):
            st.iframe(path, height=690)
        else:
            components.html(path.read_text(), height=690, scrolling=True)
    st.caption('세 outcome 지도는 baseline directed KNN k=4. 공간보간 없음. Plotly CDN 표시에는 인터넷이 필요합니다.')
    with st.expander('Manifest / reproducibility'):
        st.json(manifest)
    for relative in manifest.get('generated_reports', []):
        path = PROJECT_ROOT/relative
        if path.is_file():
            st.download_button(path.name, path.read_bytes(), file_name=path.name)
