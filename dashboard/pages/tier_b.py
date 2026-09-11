"""Read-only independent Tier B page; no raw processing or network access."""
from __future__ import annotations

import streamlit as st
from src.tier_b.artifacts import load_tables, CHARTS
from src.tier_b.data import WARNING, CHART_DIR
from src.config import PROJECT_ROOT


def render() -> None:
    """Display saved cohort outputs with explicit period-comparison warning."""
    st.title('Tier B 1991–2025')
    st.warning(WARNING)
    try:
        tables = load_tables()
    except (FileNotFoundError, ValueError):
        st.info('먼저 python main.py --analyze-tier-b를 완료하세요. 이 페이지는 API를 호출하지 않습니다.')
        return
    stations = tables['tier_b_analysis_stations']
    st.metric('Final Tier B stations', len(stations))
    st.dataframe(stations, hide_index=True)
    selection = st.selectbox('분석 표', [
        'tier_b_temperature_trends', 'tier_b_temperature_anomalies_1991_2025',
        'tier_b_seasonal_temperature_trends', 'tier_b_threshold_trends',
        'tier_b_nasa_kma_temperature_validation', 'tier_b_data_quality',
        'tier_b_annual_completeness', 'tier_b_nasa_kma_trend_consistency',
        'tier_b_station_temperature_summary', 'tier_b_temperature_rankings',
        'tier_b_station_coastal_distance'])
    st.dataframe(tables[selection], hide_index=True)
    st.caption('Sen: °C/10년, threshold: 일/10년 · proxy는 공식 폭염/열대야 통계가 아닙니다. Tier B 내부 비교만 제공합니다.')
    for label, names in [('기온 추세', CHARTS[:2]), ('Anomaly·계절', CHARTS[2:4]),
                         ('Threshold proxy', CHARTS[4:6]), ('NASA–KMA 일별 검증', CHARTS[6:])]:
        with st.expander(label, expanded=label == '기온 추세'):
            for name in names:
                path = PROJECT_ROOT/CHART_DIR/f'{name}.png'
                if path.exists():
                    st.image(str(path))
