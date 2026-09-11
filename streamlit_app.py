"""Streamlit router for the NASA POWER Korea Climate Explorer dashboard."""

from __future__ import annotations

import streamlit as st

from public_app.mode import app_mode

if app_mode() == 'public':
    from public_app.app import run
    run()
    st.stop()

from dashboard.pages.city_explorer import render as render_city_explorer
from dashboard.pages.extremes_anomalies import render as render_extremes_anomalies
from dashboard.pages.methodology import render as render_methodology
from dashboard.pages.kma_validation import render as render_kma_validation
from dashboard.pages.overview import render as render_overview
from dashboard.pages.seasonal_analysis import render as render_seasonal_analysis
from dashboard.pages.statistical_trends import render as render_statistical_trends
from dashboard.pages.variable_explorer import render as render_variable_explorer
from dashboard.pages.reports import render as render_reports
from dashboard.pages.nationwide_asos import render as render_nationwide_asos
from dashboard.pages.nationwide_climate_trends import render as render_nationwide_climate_trends
from dashboard.pages.nationwide_spatial_patterns import render as render_nationwide_spatial_patterns
from dashboard.pages.spatial_robustness_coastal import render as render_spatial_robustness_coastal
from dashboard.pages.spatial_models import render as render_spatial_models
from dashboard.pages.tier_b import render as render_tier_b
from dashboard.pages.common_period import render as render_common_period
from dashboard.pages.common_period_spatial import render as render_common_period_spatial
from dashboard.pages.period_sensitivity import render as render_period_sensitivity


st.set_page_config(
    page_title="NASA POWER Korea Climate Explorer",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      h1, h2, h3 { word-break: keep-all; overflow-wrap: break-word; }
      [data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, 0.35);
        border-radius: 0.6rem;
        padding: 0.75rem;
        background: transparent;
      }
      [data-testid="stMetricLabel"] { font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

pages = {
    "HOME": [
        st.Page(render_overview, title="종합현황", icon="📊", url_path="", default=True),
    ],
    "CORE ANALYSIS": [
        st.Page(render_city_explorer, title="도시별 탐색", icon="🏙️", url_path="city-explorer"),
        st.Page(render_variable_explorer, title="기후변수 비교", icon="📈", url_path="variable-comparison"),
        st.Page(render_statistical_trends, title="통계적 추세", icon="🔬", url_path="statistical-trends"),
        st.Page(render_extremes_anomalies, title="극한·Anomaly", icon="🌡️", url_path="extremes-anomalies"),
        st.Page(render_seasonal_analysis, title="계절 분석", icon="🍂", url_path="seasonal-analysis"),
        st.Page(render_nationwide_asos, title="전국 ASOS 확장", icon="🗺️", url_path="nationwide-asos"),
        st.Page(render_nationwide_climate_trends, title="전국 기후추세", icon="🌡️", url_path="nationwide-climate-trends"),
        st.Page(render_tier_b, title="Tier B 1991–2025", icon="🌡️", url_path="tier-b"),
        st.Page(render_common_period, title="51개 공통기간 분석", icon="🗺️", url_path="common-period"),
    ],
    "VALIDATION": [
        st.Page(render_kma_validation, title="NASA–KMA 검증", icon="🧭", url_path="nasa-kma-validation"),
    ],
    "SPATIAL": [
        st.Page(render_nationwide_spatial_patterns, title="전국 공간패턴", icon="🧩", url_path="nationwide-spatial-patterns"),
        st.Page(render_common_period_spatial, title="51개 공간 재분석", icon="📍", url_path="common-period-spatial"),
    ],
    "ROBUSTNESS": [
        st.Page(render_spatial_robustness_coastal, title="공간 강건성·해안성", icon="🌊", url_path="spatial-robustness-coastal"),
        st.Page(render_spatial_models, title="공간보정 모델", icon="🔎", url_path="spatial-models"),
        st.Page(render_period_sensitivity, title="기간 민감성", icon="📆", url_path="period-sensitivity"),
    ],
    "METHODS / REPORTS": [
        st.Page(render_methodology, title="데이터·방법론", icon="📚", url_path="methodology"),
        st.Page(render_reports, title="보고서", icon="📄", url_path="reports"),
    ],
}

navigation = st.navigation(pages, expanded=True)
st.sidebar.caption("Read-only · NASA/KMA API 호출 없음 · 지점≠격자 · 상관≠정확도·인과성 · threshold는 proxy · 기간 의존 · 면적가중 전국 평균 아님")
navigation.run()
