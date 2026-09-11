"""Seventeenth dashboard page; saved-table-only common-period spatial evidence."""
from __future__ import annotations

import streamlit as st
from src.common_period_spatial.artifacts import load_tables, point_map, display_master, LIMITS
from src.common_period_spatial.data import GRID_WARNING, BRIDGE_WARNING


def render() -> None:
    """Render fifteen sections without downloads, refits, or modifications to saved data."""
    st.title('51개 공간 재분석')
    try:
        tables = load_tables()
    except (OSError, ValueError, KeyError):
        st.info('먼저 python main.py --analyze-common-period-spatial를 완료하세요. 저장된 결과만 읽는 페이지입니다.')
        return
    master, grids = display_master(tables), tables['nasa_unique_grid_spatial_master']
    for col, name, value in zip(st.columns(3), ['Analysis period', 'ASOS stations N', 'NASA unique grids G'], ['1991–2025', len(master), len(grids)]):
        col.metric(name, value)
    st.subheader('1. Spatial overview')
    st.caption('ASOS 관측소 좌표와 추정 native NASA 격자 중심 좌표를 구분합니다. 격자 좌표는 API 반환 좌표가 아닙니다.')
    st.dataframe(tables['spatial_weight_network_summary'], hide_index=True)
    st.subheader('2. KMA metric map')
    metric = st.selectbox('KMA metric', ['kma_tavg_sen_slope', 'kma_tmax_sen_slope', 'kma_tmin_sen_slope', 'tavg_bias', 'tavg_rmse'], key='stage17_kma_metric')
    st.plotly_chart(point_map(master, metric, metric), key='stage17_kma_map')
    for title, key in [('3. Global Moran', 'global_morans_i'), ('4. Weight robustness', 'spatial_robustness_summary')]:
        with st.expander(title):
            st.dataframe(tables[key], hide_index=True)
    st.subheader('5. Period / station bridge'); st.warning(BRIDGE_WARNING)
    st.dataframe(tables['spatial_bridge_comparison'], hide_index=True)
    with st.expander('6. Local Moran'):
        st.caption('각 weight별 BH-FDR. 세 주요 weight 모두 같은 유의 quadrant일 때만 stable이며 자동 hotspot 판정이 아닙니다.')
        st.plotly_chart(point_map(master, 'cluster_type_fdr', 'KMA TAVG local Moran · FDR'), key='stage17_local')
        st.dataframe(tables['stable_local_patterns'], hide_index=True)
        st.dataframe(tables['inje_local_continuity'], hide_index=True)
    st.subheader('7. NASA station-linked vs unique-grid'); st.warning(GRID_WARNING)
    st.caption('아래 Representation 선택기는 NASA-only 결과에만 적용됩니다. 위 KMA/Bias/RMSE 결과는 station 단위를 유지합니다.')
    nasa_metric = st.selectbox('NASA-only metric', ['nasa_tavg_sen_slope', 'nasa_tmax_sen_slope', 'nasa_tmin_sen_slope', 'nasa_33c_sen_slope', 'nasa_25c_sen_slope'], key='stage17_nasa_metric')
    representation = st.selectbox('NASA-only Representation', ['Station-linked', 'Unique-grid'], key='stage17_representation')
    unique = representation == 'Unique-grid'
    st.plotly_chart(point_map(grids if unique else master, nasa_metric, f'NASA {representation}', unique_grid=unique,
                             color_range=(float(master[nasa_metric].min()), float(master[nasa_metric].max()))), key='stage17_nasa_map')
    mode = 'UNIQUE_GRID' if unique else 'STATION_LINKED'
    st.dataframe(tables['global_morans_i'].loc[lambda d: d.source.eq('NASA') & d.representation.eq(mode) & d.variable.eq(nasa_metric)], hide_index=True)
    for title, keys in [
        ('8. NASA grid duplication sensitivity', ['nasa_grid_duplication_spatial_sensitivity']),
        ('9. TMAX/TMIN contrast + DTR', ['tmax_tmin_warming_contrast', 'dtr_trends']),
        ('10. Seasonal', ['seasonal_spatial_analysis', 'dominant_season']),
    ]:
        with st.expander(title):
            for key in keys:
                st.dataframe(tables[key], hide_index=True)
    with st.expander('11. Threshold proxy'):
        st.caption('TMAX≥33°C / TMIN≥25°C, days/decade. 유효 pair일 기반 분석 proxy이며 공식 폭염·열대야 통계가 아닙니다.')
        st.dataframe(tables['global_morans_i'].loc[lambda d: d.variable.str.contains('33|25', regex=True)], hide_index=True)
    with st.expander('12. Bias/RMSE'):
        st.dataframe(tables['global_morans_i'].loc[lambda d: d.source.eq('NASA-KMA')], hide_index=True)
        st.dataframe(tables['bias_rmse_shared_grid_sensitivity'], hide_index=True)
    with st.expander('13. Coast distance and coordinate associations'):
        st.dataframe(tables['coastal_distance_associations'], hide_index=True)
        st.dataframe(tables['coordinate_associations'], hide_index=True)
    with st.expander('14. Coastal threshold sensitivity'):
        st.caption('주 분석 30 km를 유지하며 20/50 km를 함께 표시합니다. 각 threshold에서 9개 metric의 BH-FDR을 적용했습니다.')
        st.dataframe(tables['coastal_threshold_sensitivity'], hide_index=True)
        st.dataframe(tables['coastal_old_new_comparison'], hide_index=True)
    st.subheader('15. Limitations'); st.write(LIMITS)
    with st.expander('Regional / elevation summaries'):
        st.dataframe(tables['spatial_regional_summary'], hide_index=True)
        st.dataframe(tables['spatial_elevation_summary'], hide_index=True)
