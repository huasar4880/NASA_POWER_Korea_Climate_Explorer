"""Overview page for the eight-city climate explorer."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.charts import (
    create_heatmap,
    create_location_map,
    create_timeseries_chart,
    create_trend_bar_chart,
)
from dashboard.components import data_table, download_table, page_header, plotly_chart, safely_load
from dashboard.data_loader import (
    load_anomalies,
    load_dashboard_annual_data,
    load_locations,
    load_statistical_trends,
)
from dashboard.formatting import format_number, metric_label


def _leader(trends: pd.DataFrame, metric: str) -> pd.Series | None:
    """Return the row with the largest stored Sen slope for one metric."""

    subset = trends.loc[trends["metric"] == metric].dropna(subset=["sen_slope_per_decade"])
    return None if subset.empty else subset.loc[subset["sen_slope_per_decade"].idxmax()]


def _leader_city(row: pd.Series | None) -> str:
    """Return the metric leader's city without implying an overall risk ranking."""

    if row is None:
        return "자료 없음"
    return str(row["city"])


def render() -> None:
    """Show the final research landing and preserve the original eight-city overview."""
    from dashboard.final_home import render_final_home
    render_final_home()
    with st.expander("기존 8개 도시 종합현황", expanded=False):
        _render_city_overview()


def _render_city_overview() -> None:
    """Render the unchanged eight-city exploration content."""

    page_header(
        "NASA POWER Korea Climate Explorer",
        "1981–2025 NASA POWER 기반 대한민국 주요 도시 기후변화 탐색",
    )
    annual = safely_load(load_dashboard_annual_data)
    trends = safely_load(load_statistical_trends)
    anomalies = safely_load(load_anomalies)
    locations = safely_load(load_locations)
    if any(item is None for item in (annual, trends, anomalies, locations)):
        return
    assert annual is not None and trends is not None and anomalies is not None and locations is not None

    temperature_leader = _leader(trends, "temperature")
    hot_leader = _leader(trends, "hot_day_33")
    warm_leader = _leader(trends, "warm_night_25")
    metadata_cards = st.columns(2)
    metadata_cards[0].metric("분석 도시", f"{annual['city'].nunique()}개")
    metadata_cards[1].metric("분석 기간", f"{int(annual['YEAR'].min())}~{int(annual['YEAR'].max())}")
    leader_cards = st.columns(3)
    leader_cards[0].metric("가장 큰 T2M Sen slope 도시", _leader_city(temperature_leader))
    leader_cards[1].metric("가장 큰 33°C proxy 증가 도시", _leader_city(hot_leader))
    leader_cards[2].metric("가장 큰 warm-night proxy 증가 도시", _leader_city(warm_leader))
    st.caption("변화량이 가장 큰 도시를 지표별로 표시하며, 종합 기후위험도 순위가 아닙니다. Climate normal: 1991–2020.")

    left, right = st.columns([0.9, 1.5])
    with left:
        plotly_chart(create_location_map(locations, title="분석 대상 8개 도시"), key="overview_map")
    with right:
        plotly_chart(
            create_timeseries_chart(
                annual,
                "YEAR",
                "T2M_mean_C",
                title="8개 도시 연평균 기온 (T2M)",
                y_title="기온 (°C)",
                color_column="city",
            ),
            key="overview_t2m",
        )

    temp_trends = trends.loc[trends["metric"] == "temperature"].copy()
    latest_year = int(anomalies["YEAR"].max())
    recent = anomalies.loc[anomalies["YEAR"] == latest_year].copy()
    col1, col2 = st.columns(2)
    with col1:
        plotly_chart(
            create_trend_bar_chart(
                temp_trends,
                title="도시별 T2M Sen's slope",
                y_title="°C/10년",
            ),
            key="overview_sen",
        )
    with col2:
        plotly_chart(
            create_trend_bar_chart(
                recent,
                value_column="T2M_anomaly",
                title=f"{latest_year}년 T2M anomaly (1991–2020 기준)",
                y_title="Anomaly (°C)",
            ),
            key="overview_recent_anomaly",
        )

    significance = trends.loc[:, ["city", "metric", "significant_fdr"]].copy()
    significance["metric_label"] = significance["metric"].map(metric_label)
    significance["FDR_significant"] = (
        significance["significant_fdr"].astype(str).str.lower().eq("true").astype(int)
    )
    plotly_chart(
        create_heatmap(
            significance,
            row_column="city",
            column_column="metric_label",
            value_column="FDR_significant",
            title="도시 × 기후변수 FDR 유의성 (1=유의, 0=비유의)",
            colorbar_title="FDR 유의",
            colorscale="Blues",
            zmid=None,
        ),
        key="overview_significance",
    )

    with st.expander("핵심 값 표와 다운로드"):
        summary = temp_trends.loc[
            :, ["city", "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper", "fdr_q_value", "significant_fdr"]
        ].sort_values("sen_slope_per_decade", ascending=False)
        data_table(summary)
        download_table(
            summary,
            filename="overview_temperature_sen_slopes.csv",
            key="overview_download",
        )
