"""Read-only nationwide ASOS inventory and eligibility screening page."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components import data_table, download_table, page_header, plotly_chart, safely_load
from dashboard.data_loader import load_nationwide_station_master


TIER_COLORS = {"A": "#1b9e77", "B": "#377eb8", "C/D": "#999999", "Manual Review": "#e41a1c"}


def _to_bool(series: pd.Series) -> pd.Series:
    """Normalize persisted booleans without treating non-empty strings as true."""

    return series.astype(str).str.casefold().eq("true")


def render() -> None:
    """Render metadata/eligibility only; no nationwide trend analysis is performed."""

    page_header(
        "전국 ASOS 확장",
        "v1.1 experimental · 공식 station metadata와 일자료 completeness screening 결과",
    )
    master = safely_load(load_nationwide_station_master)
    if master is None:
        st.info("먼저 `python main.py --screen-nationwide-asos`를 실행하세요.")
        return
    master = master.copy()
    master["station_id"] = master["station_id"].astype(str)
    master["active_flag"] = _to_bool(master["is_active"])
    master["start_year"] = pd.to_datetime(master["metadata_start_date"], errors="coerce").dt.year
    master["elevation_m"] = pd.to_numeric(master["elevation_m"], errors="coerce")

    metrics = st.columns(5)
    metrics[0].metric("전체 ASOS", f"{len(master):,}")
    metrics[1].metric("Tier A", f"{int(master['eligibility_tier'].eq('A').sum()):,}")
    metrics[2].metric("Tier B", f"{int(master['eligibility_tier'].eq('B').sum()):,}")
    metrics[3].metric("Manual Review", f"{int(_to_bool(master['manual_review_required']).sum()):,}")
    metrics[4].metric("Excluded", f"{int((~master['eligibility_tier'].isin(['A', 'B'])).sum()):,}")

    region_options = sorted(master["region_level1"].dropna().astype(str).unique())
    tier_options = sorted(master["eligibility_tier"].dropna().astype(str).unique())
    risk_options = sorted(master["continuity_risk"].dropna().astype(str).unique())
    with st.expander("필터", expanded=True):
        first, second, third = st.columns(3)
        regions = first.multiselect("시도", region_options, default=region_options)
        tiers = second.multiselect("Eligibility tier", tier_options, default=tier_options)
        active_choice = third.selectbox("운영 상태", ["전체", "Active", "Historical / inactive"])
        fourth, fifth, sixth = st.columns(3)
        min_year = int(master["start_year"].dropna().min()) if master["start_year"].notna().any() else 1900
        max_year = int(master["start_year"].dropna().max()) if master["start_year"].notna().any() else 2025
        start_year = fourth.slider("관측 시작연도 상한", min_year, max_year, max_year)
        elevation_values = master["elevation_m"].dropna()
        elevation_limit = float(elevation_values.max()) if not elevation_values.empty else 1000.0
        elevation_range = fifth.slider("고도 범위 (m)", float(min(0, elevation_values.min() if not elevation_values.empty else 0)), elevation_limit, (float(min(0, elevation_values.min() if not elevation_values.empty else 0)), elevation_limit))
        risks = sixth.multiselect("Continuity risk", risk_options, default=risk_options)

    filtered = master.loc[
        master["eligibility_tier"].isin(tiers)
        & master["continuity_risk"].isin(risks)
        & master["start_year"].le(start_year)
        & master["elevation_m"].between(*elevation_range)
    ].copy()
    if regions:
        filtered = filtered.loc[filtered["region_level1"].astype(str).isin(regions)]
    if active_choice == "Active":
        filtered = filtered.loc[filtered["active_flag"]]
    elif active_choice == "Historical / inactive":
        filtered = filtered.loc[~filtered["active_flag"]]

    map_data = filtered.dropna(subset=["latitude", "longitude"])
    if not map_data.empty:
        map_data = map_data.copy()
        map_data["map_category"] = map_data["eligibility_tier"].where(
            map_data["eligibility_tier"].isin(["A", "B"]), "C/D"
        )
        map_data.loc[_to_bool(map_data["manual_review_required"]), "map_category"] = "Manual Review"
        figure = px.scatter_map(
            map_data,
            lat="latitude",
            lon="longitude",
            color="map_category",
            color_discrete_map=TIER_COLORS,
            hover_name="station_name",
            hover_data=["station_id", "metadata_start_date", "metadata_end_date", "elevation_m", "eligibility_tier", "continuity_risk"],
            zoom=5.4,
            center={"lat": 36.2, "lon": 127.8},
            title="ASOS station inventory · climate trend 값이 아님",
        )
        figure.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=50, b=0))
        plotly_chart(figure, key="nationwide_asos_map")
    st.caption("Tier는 이 프로젝트의 screening rule이며 KMA 공식 품질등급이 아닙니다. 가까운 station도 자동 연결하지 않습니다.")
    shown = filtered.loc[:, [
        "station_id", "station_name", "region_level1", "region_level2", "metadata_start_date",
        "metadata_end_date", "is_active", "elevation_m", "eligibility_tier", "continuity_risk",
        "core_temperature_missing_rate", "annual_completeness_median", "eligibility_reason",
    ]]
    data_table(shown)
    download_table(shown, filename="nationwide_asos_filtered_inventory.csv", key="nationwide_asos_download")
