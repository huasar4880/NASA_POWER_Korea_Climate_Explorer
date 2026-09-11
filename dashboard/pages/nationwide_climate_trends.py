"""Read-only Stage-11 nationwide Tier-A climate trend dashboard page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.charts import create_heatmap, create_timeseries_chart
from dashboard.components import data_table, page_header, plotly_chart, safely_load, show_proxy_notice
from dashboard.data_loader import (
    load_nationwide_annual_temperature,
    load_nationwide_regional_summary,
    load_nationwide_temperature_anomalies,
    load_nationwide_temperature_summary,
    load_nationwide_threshold_comparison,
)
from src.nationwide.tier_a_analysis import assign_elevation_band
from src.nationwide.tier_a_visualization import create_station_value_map


def _bool_values(series: pd.Series) -> pd.Series:
    """Persisted bool/string values를 dashboard filter용 boolean으로 변환한다."""

    return series.astype(str).str.casefold().isin({"true", "1", "yes"})


def render() -> None:
    """Render saved nationwide results without any NASA or KMA API call."""

    page_header(
        "전국 기후추세",
        "Experimental nationwide analysis · Final Tier A station · 1981–2025 · Normal 1991–2020",
    )
    summary = safely_load(load_nationwide_temperature_summary)
    if summary is None:
        st.info("먼저 `python main.py --analyze-nationwide-tier-a`를 실행하세요.")
        return
    annual = safely_load(load_nationwide_annual_temperature)
    anomalies = safely_load(load_nationwide_temperature_anomalies)
    regional = safely_load(load_nationwide_regional_summary)
    thresholds = safely_load(load_nationwide_threshold_comparison)
    if any(value is None for value in (annual, anomalies, regional, thresholds)):
        return
    summary = summary.copy()
    summary["station_id"] = summary["station_id"].astype(str)
    summary["elevation_band"] = assign_elevation_band(summary["elevation_m"]).astype(str)
    summary["fdr_significant"] = _bool_values(summary["kma_tavg_fdr_significant"])

    kpis = st.columns(5)
    kpis[0].metric("Tier A station", f"{len(summary):,}")
    kpis[1].metric("공통기간", "1981–2025")
    kpis[2].metric("Climate Normal", "1991–2020")
    kpis[3].metric(
        "FDR 유의 TAVG 증가",
        f"{int((summary['fdr_significant'] & summary['kma_tavg_sen_slope_decade'].gt(0)).sum()):,}",
    )
    kpis[4].metric(
        "Median KMA TAVG Sen",
        f"{summary['kma_tavg_sen_slope_decade'].median():+.3f} °C/10년",
    )

    with st.expander("필터", expanded=True):
        first, second, third, fourth = st.columns(4)
        regions_all = sorted(summary["region"].dropna().astype(str).unique())
        regions = first.multiselect("Region", regions_all, default=regions_all)
        stations_all = summary.sort_values("station_id")["station_id"].tolist()
        station_ids = second.multiselect("Station ID", stations_all, default=stations_all)
        bands_all = ["<50m", "50-200m", "200-500m", ">=500m"]
        bands = third.multiselect("Elevation band", bands_all, default=bands_all)
        significance = fourth.selectbox("FDR significance", ["전체", "유의", "비유의"])
    filtered = summary.loc[
        summary["region"].isin(regions)
        & summary["station_id"].isin(station_ids)
        & summary["elevation_band"].isin(bands)
    ].copy()
    if significance == "유의":
        filtered = filtered.loc[filtered["fdr_significant"]]
    elif significance == "비유의":
        filtered = filtered.loc[~filtered["fdr_significant"]]

    map_tabs = st.tabs(["KMA TAVG", "NASA TAVG", "Bias", "RMSE"])
    map_specs = [
        ("kma_tavg_sen_slope_decade", "KMA TAVG Sen slope", "°C/decade"),
        ("nasa_tavg_sen_slope_decade", "NASA TAVG Sen slope", "°C/decade"),
        ("tavg_bias", "NASA–KMA TAVG Bias", "°C"),
        ("tavg_rmse", "NASA–KMA TAVG RMSE", "°C"),
    ]
    for tab, (column, title, unit) in zip(map_tabs, map_specs):
        with tab:
            plotly_chart(
                create_station_value_map(filtered, column, title, unit),
                key=f"nationwide_map_{column}",
            )

    anomaly = anomalies.loc[
        anomalies["station_id"].astype(str).isin(filtered["station_id"])
        & anomalies["source"].eq("KMA") & anomalies["metric"].eq("TAVG")
    ].copy()
    anomaly["station"] = anomaly["station_id"].astype(str) + " " + anomaly["station_name"].astype(str)
    plotly_chart(
        create_heatmap(
            anomaly, row_column="station", column_column="year", value_column="anomaly",
            title="KMA TAVG anomaly · 1991–2020 normal", colorbar_title="°C",
        ),
        key="nationwide_anomaly_heatmap",
    )

    region_figure = go.Figure(go.Bar(
        x=regional["region"], y=regional["median_kma_tavg_sen_slope"], marker_color="#d55e00",
        customdata=regional["station_count"],
        hovertemplate="%{x}<br>Median: %{y:+.3f} °C/decade<br>Stations: %{customdata}<extra></extra>",
    ))
    region_figure.update_layout(
        title="Regional station-sample median · not area-weighted", yaxis_title="°C / decade",
        template="plotly_white", height=480,
    )
    plotly_chart(region_figure, key="nationwide_regional_summary")

    st.subheader("Station 상세")
    selected_id = st.selectbox(
        "Station",
        filtered["station_id"].tolist() if not filtered.empty else summary["station_id"].tolist(),
        format_func=lambda sid: f"{sid} {summary.loc[summary['station_id'].eq(sid), 'station_name'].iloc[0]}",
    )
    station_summary = summary.loc[summary["station_id"].eq(selected_id)].iloc[0]
    details = st.columns(5)
    details[0].metric("KMA Sen", f"{station_summary['kma_tavg_sen_slope_decade']:+.3f} °C/10년")
    details[1].metric("Bias", f"{station_summary['tavg_bias']:+.3f} °C")
    details[2].metric("RMSE", f"{station_summary['tavg_rmse']:.3f} °C")
    details[3].metric("Pearson r", f"{station_summary['tavg_pearson']:.3f}")
    details[4].metric("Elevation", f"{station_summary['elevation_m']:.1f} m")
    station_annual = annual.loc[
        annual["station_id"].astype(str).eq(selected_id) & annual["metric"].eq("TAVG")
    ]
    plotly_chart(
        create_timeseries_chart(
            station_annual, "year", "annual_mean", color_column="source",
            title="KMA ASOS vs NASA POWER annual TAVG", y_title="°C",
        ),
        key="nationwide_station_timeseries",
    )
    station_thresholds = thresholds.loc[thresholds["station_id"].astype(str).eq(selected_id)].copy()
    show_proxy_notice()
    data_table(station_thresholds.loc[:, [
        "threshold", "kma_mean_annual_count", "nasa_mean_annual_count",
        "kma_sen_slope_per_decade", "nasa_sen_slope_per_decade",
    ]])
    st.caption(
        "Tier A station sample은 전국 공간을 균등 대표하지 않습니다. NASA 격자와 KMA station의 "
        "차이, correlation≠accuracy, significance≠causality를 함께 고려하세요."
    )
