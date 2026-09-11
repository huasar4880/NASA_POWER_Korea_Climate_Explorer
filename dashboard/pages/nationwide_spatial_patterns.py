"""Read-only Stage-12 nationwide spatial climate pattern dashboard page."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard.components import data_table, page_header, plotly_chart, safely_load, show_proxy_notice
from dashboard.data_loader import (
    load_global_morans,
    load_local_morans,
    load_spatial_association,
    load_spatial_contrast,
    load_spatial_seasonal_summary,
    load_spatial_station_master,
)
from src.spatial.visualization import create_category_map, create_spatial_value_map


METRICS = {
    "TAVG": ("kma_tavg_sen_slope", "KMA TAVG Sen slope", "°C/10년"),
    "TMAX": ("kma_tmax_sen_slope", "KMA TMAX Sen slope", "°C/10년"),
    "TMIN": ("kma_tmin_sen_slope", "KMA TMIN Sen slope", "°C/10년"),
    "Bias": ("tavg_bias", "NASA−KMA TAVG Bias", "°C"),
    "RMSE": ("tavg_rmse", "NASA−KMA TAVG RMSE", "°C"),
    "33°C proxy": ("days_tmax_ge_33_kma_slope", "KMA TMAX ≥33°C proxy", "일/년/10년"),
    "25°C proxy": ("days_tmin_ge_25_kma_slope", "KMA TMIN ≥25°C proxy", "일/년/10년"),
}


def _association_scatter(master, x_column: str, y_column: str, title: str) -> go.Figure:
    """Create an exploratory station scatter for a selected coordinate relationship."""

    figure = go.Figure(go.Scatter(
        x=master[x_column], y=master[y_column], mode="markers",
        text=master["station_id"].astype(str) + " " + master["station_name"].astype(str),
        marker={"size": 9, "color": "#2369a1"},
        hovertemplate="%{text}<br>x=%{x:.3f}<br>y=%{y:+.4f}<extra></extra>",
    ))
    figure.update_layout(title=title, xaxis_title=x_column, yaxis_title=y_column, template="plotly_white")
    return figure


def render() -> None:
    """Render saved Stage-12 outputs without any NASA or KMA API call."""

    page_header(
        "전국 공간패턴",
        "Experimental · Final Tier A station points · Haversine/KNN Moran · API 호출 없음",
    )
    master = safely_load(load_spatial_station_master)
    global_morans = safely_load(load_global_morans)
    local = safely_load(load_local_morans)
    contrast = safely_load(load_spatial_contrast)
    seasonal = safely_load(load_spatial_seasonal_summary)
    latitude = safely_load(lambda: load_spatial_association("latitude"))
    elevation = safely_load(lambda: load_spatial_association("elevation"))
    if any(value is None for value in (master, global_morans, local, contrast, seasonal, latitude, elevation)):
        st.info("먼저 `python main.py --analyze-spatial`을 실행하세요.")
        return
    master = master.copy()
    master["station_id"] = master["station_id"].astype(str)

    st.subheader("1. 공간분석 개요")
    first, second, third = st.columns(3)
    first.metric("Final Tier A station", f"{len(master):,}")
    second.metric("기본 K", str(int(global_morans["k"].iloc[0])))
    third.metric("공간보간", "사용 안 함")
    st.caption("Station point 표본은 전국 면적을 균등 대표하지 않으며 공간 연관은 인과관계가 아닙니다.")

    st.subheader("2–3. Metric 선택과 전국 station map")
    selected = st.selectbox("Metric", list(METRICS))
    column, title, unit = METRICS[selected]
    plotly_chart(create_spatial_value_map(master, column, title, unit), key="spatial_metric_map")

    st.subheader("4. Global Moran's I")
    st.caption("유사한 값이 인접 station에 모여 있는 정도를 평가합니다. I의 부호와 permutation p를 함께 봅니다.")
    data_table(global_morans[["label", "n_stations", "weights_method", "k", "moran_i", "permutation_p"]])

    st.subheader("5. Local Moran cluster map")
    st.caption("특정 station 주변의 상대적으로 높은/낮은 값 동반 여부이며 BH-FDR 유의 결과를 우선합니다.")
    local_tavg = local.loc[local["variable"].eq("kma_tavg_sen_slope")]
    plotly_chart(create_category_map(
        local_tavg, "cluster_type_fdr", "Local Moran TAVG · BH-FDR",
        ["High-High", "Low-Low", "High-Low", "Low-High", "Not Significant"],
    ), key="spatial_local_moran")

    st.subheader("6. 위도/고도 관계")
    left, right = st.columns(2)
    with left:
        plotly_chart(_association_scatter(master, "latitude", "kma_tavg_sen_slope", "Latitude vs TAVG Sen slope"), key="latitude_tavg")
        data_table(latitude)
    with right:
        plotly_chart(_association_scatter(master, "elevation_m", "kma_tavg_sen_slope", "Elevation vs TAVG Sen slope"), key="elevation_tavg")
        data_table(elevation)

    st.subheader("7. TMAX vs TMIN contrast")
    data_table(contrast[["station_id", "station_name", "tmax_slope", "tmin_slope", "tmin_minus_tmax", "contrast_direction"]])

    st.subheader("8. 계절 공간패턴")
    season = st.selectbox("Season", ["DJF", "MAM", "JJA", "SON"])
    season_data = seasonal.loc[seasonal["season"].eq(season)].copy()
    season_data["station_id"] = season_data["station_id"].astype(str)
    season_map = master.drop(columns=["kma_tavg_sen_slope"]).merge(
        season_data[["station_id", "sen_slope_per_decade"]].rename(columns={"sen_slope_per_decade": "kma_tavg_sen_slope"}),
        on="station_id", how="left", validate="one_to_one",
    )
    plotly_chart(create_spatial_value_map(season_map, "kma_tavg_sen_slope", f"{season} KMA TAVG Sen slope", "°C/10년"), key="season_map")

    st.subheader("9. 해안/내륙 분석")
    st.warning("해안/내륙 분석 보류 - 신뢰 가능한 coastline geometry의 해상도·provenance·재배포 라이선스 확인 필요")

    st.subheader("10. 분석 한계")
    show_proxy_notice()
    st.markdown(
        "Tier A station만 사용했고 공간분포가 불균등합니다. KNN 정의에 따라 Moran 결과가 달라질 수 "
        "있으며 Local Moran에는 multiple testing이 있습니다. NASA grid와 KMA station의 공간대표성이 "
        "다르고, latitude/elevation 연관은 confounding이 가능하며 causality를 뜻하지 않습니다."
    )
