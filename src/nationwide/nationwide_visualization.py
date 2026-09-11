"""Inventory-only map for nationwide ASOS screening results."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px


TIER_COLORS = {
    "A": "#1b9e77",
    "B": "#377eb8",
    "C/D": "#999999",
    "Manual Review": "#e41a1c",
}


def create_station_inventory_map(master: pd.DataFrame, output_path: Path) -> Path:
    """Save an interactive station eligibility map without climate trend values."""

    required = {"station_id", "station_name", "latitude", "longitude", "eligibility_tier"}
    missing = sorted(required - set(master.columns))
    if missing:
        raise ValueError(f"station map 필수 컬럼 누락: {', '.join(missing)}")
    plotted = master.dropna(subset=["latitude", "longitude"]).copy()
    if plotted.empty:
        raise ValueError("지도에 표시할 유효한 station 좌표가 없습니다.")
    plotted["station_id"] = plotted["station_id"].astype(str)
    review = plotted["manual_review_required"].fillna(False).astype(bool)
    plotted["map_category"] = plotted["eligibility_tier"].where(
        plotted["eligibility_tier"].isin(["A", "B"]), "C/D"
    )
    plotted.loc[review, "map_category"] = "Manual Review"
    figure = px.scatter_map(
        plotted,
        lat="latitude",
        lon="longitude",
        color="map_category",
        color_discrete_map=TIER_COLORS,
        hover_name="station_name",
        hover_data={
            "station_id": True,
            "metadata_start_date": True,
            "metadata_end_date": True,
            "elevation_m": ":.1f",
            "eligibility_tier": True,
            "continuity_risk": True,
            "latitude": ":.4f",
            "longitude": ":.4f",
        },
        zoom=5.4,
        center={"lat": 36.2, "lon": 127.8},
        title="Nationwide KMA ASOS station inventory and eligibility screening",
    )
    figure.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=50, b=0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(output_path, include_plotlyjs="cdn", full_html=True)
    return output_path
