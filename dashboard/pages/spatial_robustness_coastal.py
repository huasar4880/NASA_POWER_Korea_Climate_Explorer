"""Read-only thirteenth dashboard page; geometry failure never hides robustness."""
from __future__ import annotations
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
from src.config import PROJECT_ROOT
from dashboard.robustness_loader import load_robustness_manifest, load_robustness_table
from src.spatial.coastal_analysis import METRICS


def render() -> None:
    """Display saved robustness and optional coastal results without computing or downloading."""
    st.title('공간 강건성·해안성')
    st.caption('Experimental Stage 13 · Final Tier A · 읽기 전용 · 인과분석 아님')
    manifest=load_robustness_manifest()
    summary=load_robustness_table('summary')
    if summary.empty:
        st.info('저장된 Stage-13 결과가 없습니다. 분석 CLI를 먼저 실행하세요.')
        return
    st.subheader('Spatial Robustness Overview')
    st.dataframe(summary,hide_index=True)
    families={'전체':'all','Directed KNN':'directed_knn','Symmetric KNN':'symmetric_knn','Distance Band':'distance_band','Inverse Distance':'inverse_distance'}
    selected=st.selectbox('Weight Family',list(families))
    weights=load_robustness_table('weights')
    subset=weights if selected=='전체' else weights[weights.weight_family.eq(families[selected])]
    pivot=subset.pivot(index='variable',columns='weight_variant',values='moran_i')
    st.plotly_chart(px.imshow(pivot,color_continuous_scale='RdBu_r',color_continuous_midpoint=0,aspect='auto',title="Moran I robustness"),width='stretch')
    variable=st.selectbox('Variable',list(weights.variable.unique()))
    st.dataframe(subset[subset.variable.eq(variable)],hide_index=True)
    st.subheader('Local Moran robustness (TAVG, BH-FDR)')
    local=load_robustness_table('local')
    st.metric('Stable FDR-significant stations',local.loc[local.stable_local_pattern,'station_id'].nunique())
    st.dataframe(local,hide_index=True)
    coast=manifest.get('coastline',{})
    if not coast.get('available',False):
        st.warning('공식 coastline geometry가 검증되지 않아 Coastal/Inland 분석을 표시할 수 없습니다.')
        st.caption(coast.get('reason',''))
    else:
        st.subheader('Official coastline / Distance to coast')
        st.caption(f"{coast.get('source_name')} · {coast.get('analysis_crs')} · 표시만 250 m 단순화, 거리계산은 전체 해상도")
        map_path=PROJECT_ROOT/'output/charts/coastal/distance_to_coast_map.html'
        if map_path.exists():
            if hasattr(st, 'iframe'):
                st.iframe(map_path, height=750)
            else:
                components.html(map_path.read_text(),height=750,scrolling=True)
        distances=load_robustness_table('station_coastal_distance')
        st.dataframe(distances,hide_index=True)
        threshold=st.selectbox('Coastal threshold (km)',manifest['coastal_thresholds_km'],index=manifest['coastal_thresholds_km'].index(manifest['main_coastal_threshold_km']))
        classification=load_robustness_table('coastal_classification_sensitivity')
        chosen=classification[classification.threshold_km.eq(threshold)]
        st.plotly_chart(px.scatter(chosen,x='longitude',y='latitude',color='coastal_group',hover_name='station_name',title=f'Coastal / Inland: {threshold:g} km'),width='stretch')
        comparisons=load_robustness_table('coastal_threshold_sensitivity')
        st.dataframe(comparisons[comparisons.threshold_km.eq(threshold)],hide_index=True)
        st.subheader('Continuous coastal-distance associations')
        st.dataframe(load_robustness_table('coastal_continuous_associations'),hide_index=True)
        metric=st.selectbox('Coastal scatter metric',list(METRICS),format_func=METRICS.get)
        from src.spatial.robustness_workflow import load_inputs
        master,_,_=load_inputs()
        scatter=master.merge(distances[['station_id','distance_to_coast_km']],on='station_id',validate='one_to_one')
        st.plotly_chart(px.scatter(scatter,x='distance_to_coast_km',y=metric,hover_name='station_name',labels={'distance_to_coast_km':'Distance (km)',metric:METRICS[metric]}),width='stretch')
        st.subheader('Bias/RMSE coastal relation and exploratory model')
        st.dataframe(load_robustness_table('coastal_multivariable_models'),hide_index=True)
    st.subheader('Methodological limitations')
    st.warning('75% 강건성 분류와 20/30/50 km는 프로젝트 운영상 정의입니다. Global p는 다중검정 미보정, Local FDR은 설정별입니다. 집단 비교/OLS는 공간 의존성을 보정하지 않아 탐색적입니다. 해안거리 연관을 바다의 인과효과로 해석하지 마세요.')
