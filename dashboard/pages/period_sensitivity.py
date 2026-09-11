"""Eighteenth dashboard page: saved-result-only period sensitivity and A/B comparisons."""
from __future__ import annotations

import streamlit as st
from src.period_sensitivity.artifacts import load_tables,compare_windows,trajectory_figure,LIMITS
from src.period_sensitivity.data import WARNING


def render() -> None:
    """Display fifteen requested sections without refitting, downloading or modifying saved results."""
    st.title('기간 민감성')
    try:
        t=load_tables()
    except (OSError,ValueError,KeyError):
        st.info('먼저 python main.py --analyze-period-sensitivity를 완료하세요. 저장된 결과만 표시합니다.')
        return
    st.subheader('1. Overview')
    st.metric('Fixed Final Tier A stations',t['station_master'].station_id.nunique())
    st.caption('종료연도 2025 고정 · 시작연도 1981 / 1986 / 1991 / 1996 / 2001')
    st.warning(WARNING)
    st.subheader('2. Start-year / Window A–B')
    starts=sorted(t['windows'].start_year.tolist())
    a=st.selectbox('Window A start year',starts,key='stage18_window_a')
    b=st.selectbox('Window B start year',starts,index=len(starts)-1,key='stage18_window_b')
    metric=st.selectbox('Temperature metric',['TAVG','TMAX','TMIN'],key='stage18_metric')
    source=st.selectbox('Source',['KMA','NASA'],key='stage18_source')
    st.caption(f'A={a}–2025, B={b}–2025. 표시 차이 = B−A, 각 window BH-FDR 상태도 비교합니다.')
    compared=compare_windows(t,a,b)
    st.subheader('3. Temperature trends')
    st.dataframe(t['window_summary'].loc[lambda d:d.source.eq(source)&d.metric.eq(metric)],hide_index=True)
    st.dataframe(compared['temperature_trends'].loc[lambda d:d.source.eq(source)&d.metric.eq(metric)],hide_index=True)
    st.subheader('4. Station slope trajectories')
    st.plotly_chart(trajectory_figure(t['temperature_trends']),key='stage18_trajectory')
    for title,keys in [('5. Sign / significance stability',['national_stability_summary','trend_stability']),
        ('6. TMIN−TMAX contrast',['contrast_summary','contrast_stability']),
        ('7. Annual DTR',['dtr_summary','dtr_stability']),
        ('8. Seasonal TAVG',['seasonal_summary','dominant_season_stability']),
        ('9. Threshold proxies',['threshold_window_summary','threshold_stability']),
        ('10. NASA-KMA consistency',['trend_consistency_window_summary'])]:
        with st.expander(title):
            for key in keys:
                st.dataframe(t[key],hide_index=True)
    with st.expander('11. Bias / RMSE'):
        st.dataframe(t['validation_window_summary'],hide_index=True)
        st.dataframe(compared['nasa_kma_validation'].loc[lambda d:d.metric.eq(metric)],hide_index=True)
    with st.expander('12. Moran trajectories / A–B'):
        st.caption('主 directed K4; raw permutation p. Station-linked와 unique-grid를 구분합니다.')
        st.dataframe(t['spatial_robustness_summary'],hide_index=True)
        st.dataframe(compared['global_morans_i'],hide_index=True)
        st.dataframe(t['nasa_grid_spatial'],hide_index=True)
    with st.expander('13. Coast distance / Coastal–Inland'):
        st.dataframe(t['coastal_association_stability'],hide_index=True)
        st.dataframe(t['coastal_inland_comparison'],hide_index=True)
        st.dataframe(t['coastal_group_period_stability'],hide_index=True)
    with st.expander('14. Station-level sensitivity'):
        st.caption('절대 slope range 기준이며 위험도·품질 점수가 아닙니다.')
        st.dataframe(t['station_metric_summary'].loc[lambda d:d.source.eq(source)&d.metric.eq(metric)].sort_values('slope_range',ascending=False),hide_index=True)
    st.subheader('15. Limitations'); st.write(LIMITS)
