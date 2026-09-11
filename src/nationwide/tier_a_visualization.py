"""Tier-A 전국 기온분석의 Plotly 지도와 보고서용 정적 PNG."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
import plotly.graph_objects as go


KOREAN_FONT_PATH = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
if KOREAN_FONT_PATH.exists():
    font_manager.fontManager.addfont(KOREAN_FONT_PATH)
    plt.rcParams["font.family"] = font_manager.FontProperties(
        fname=KOREAN_FONT_PATH
    ).get_name()
    plt.rcParams["axes.unicode_minus"] = False


def nationwide_map_dataframe(summary: pd.DataFrame, value_column: str) -> pd.DataFrame:
    """지도 hover와 색상에 필요한 station metadata를 검증해 반환한다."""

    required = {
        "station_id", "station_name", "region", "latitude", "longitude", "elevation_m",
        "kma_tavg_sen_slope_decade", "kma_tavg_fdr_significant", "tavg_bias", "tavg_rmse",
        value_column,
    }
    missing = required - set(summary.columns)
    if missing:
        raise ValueError(f"전국 지도 필수 컬럼 누락: {sorted(missing)}")
    return summary.loc[:, list(dict.fromkeys(required))].dropna(
        subset=["latitude", "longitude", value_column]
    ).copy()


def create_station_value_map(
    summary: pd.DataFrame, value_column: str, title: str, colorbar_title: str
) -> go.Figure:
    """외부 token 없이 대한민국 station 값의 interactive Scattergeo 지도를 만든다."""

    data = nationwide_map_dataframe(summary, value_column)
    labels = data["station_id"].astype(str) + " " + data["station_name"].astype(str)
    hover = np.column_stack([
        data["station_id"].astype(str), data["station_name"].astype(str), data["region"].astype(str),
        data["elevation_m"], data["kma_tavg_sen_slope_decade"],
        data["kma_tavg_fdr_significant"].astype(str), data["tavg_bias"], data["tavg_rmse"],
    ])
    values = pd.to_numeric(data[value_column], errors="coerce")
    maximum = float(np.nanmax(np.abs(values))) if len(values) else 1.0
    if maximum == 0:
        maximum = 1.0
    figure = go.Figure(go.Scattergeo(
        lon=data["longitude"], lat=data["latitude"], text=labels, customdata=hover,
        mode="markers", marker={
            "size": 10, "color": values, "colorscale": "RdBu_r",
            "cmin": -maximum if values.min() < 0 else float(values.min()),
            "cmax": maximum, "colorbar": {"title": colorbar_title},
            "line": {"color": "#333", "width": 0.4},
        },
        hovertemplate=(
            "ID: %{customdata[0]}<br>Station: %{customdata[1]}<br>Region: %{customdata[2]}"
            "<br>Elevation: %{customdata[3]:.1f} m<br>KMA TAVG Sen: %{customdata[4]:+.3f} °C/decade"
            "<br>FDR significant: %{customdata[5]}<br>Bias: %{customdata[6]:+.3f} °C"
            "<br>RMSE: %{customdata[7]:.3f} °C<extra></extra>"
        ),
    ))
    figure.update_geos(
        projection_type="mercator", lonaxis_range=[124.0, 132.0], lataxis_range=[32.0, 39.5],
        showcountries=True, showcoastlines=True, showland=True, landcolor="#f3f4f6",
    )
    figure.update_layout(
        title={"text": title, "x": 0.02}, template="plotly_white", height=700,
        margin={"l": 5, "r": 5, "b": 5, "t": 65},
        annotations=[{
            "text": "Station-level comparison; spatial coverage is not uniform.",
            "x": 0.01, "y": 0.01, "xref": "paper", "yref": "paper", "showarrow": False,
        }],
    )
    return figure


def save_interactive_maps(summary: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    """요청된 7종 전국 Plotly map HTML을 저장한다."""

    output_dir.mkdir(parents=True, exist_ok=True)
    specs = {
        "nationwide_kma_tavg_sen_slope_map.html": (
            "kma_tavg_sen_slope_decade", "KMA TAVG Sen's Slope (1981–2025)", "°C/decade"
        ),
        "nationwide_kma_tmax_sen_slope_map.html": (
            "kma_tmax_sen_slope_decade", "KMA TMAX Sen's Slope (1981–2025)", "°C/decade"
        ),
        "nationwide_kma_tmin_sen_slope_map.html": (
            "kma_tmin_sen_slope_decade", "KMA TMIN Sen's Slope (1981–2025)", "°C/decade"
        ),
        "nationwide_nasa_tavg_sen_slope_map.html": (
            "nasa_tavg_sen_slope_decade", "NASA POWER TAVG Sen's Slope (1981–2025)", "°C/decade"
        ),
        "nationwide_tavg_bias_map.html": (
            "tavg_bias", "NASA–KMA TAVG Bias (NASA minus KMA)", "°C"
        ),
        "nationwide_tavg_rmse_map.html": (
            "tavg_rmse", "NASA–KMA TAVG RMSE", "°C"
        ),
        "nationwide_significance_map.html": (
            "kma_tavg_sen_slope_decade", "KMA TAVG Trend and FDR Significance", "°C/decade"
        ),
    }
    paths: dict[str, Path] = {}
    for filename, (column, title, unit) in specs.items():
        path = output_dir / filename
        figure = create_station_value_map(summary, column, title, unit)
        if filename == "nationwide_significance_map.html":
            significance = summary["kma_tavg_fdr_significant"].astype(bool)
            figure.data[0].marker.size = np.where(significance, 14, 7)
            figure.data[0].marker.symbol = np.where(significance, "diamond", "circle")
        figure.write_html(path, include_plotlyjs="cdn", full_html=True)
        paths[filename] = path
    return paths


def _static_station_map(
    summary: pd.DataFrame, value_column: str, path: Path, title: str, label: str
) -> Path:
    """보고서용 token-free station scatter PNG를 저장한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(8.3, 9.0))
    values = pd.to_numeric(summary[value_column], errors="coerce")
    maximum = max(float(np.nanmax(np.abs(values))), 1e-6)
    scatter = axis.scatter(
        summary["longitude"], summary["latitude"], c=values, cmap="RdBu_r",
        vmin=-maximum if values.min() < 0 else float(values.min()), vmax=maximum,
        s=60, edgecolor="#222", linewidth=0.4,
    )
    axis.set_xlim(124.5, 131.5)
    axis.set_ylim(32.8, 39.0)
    axis.set_xlabel("Longitude (°E)")
    axis.set_ylabel("Latitude (°N)")
    axis.set_title(title)
    axis.grid(alpha=0.2)
    figure.colorbar(scatter, ax=axis, label=label)
    figure.text(0.5, 0.01, "Station locations; not an area-weighted national surface.", ha="center", fontsize=9)
    figure.tight_layout(rect=[0, 0.03, 1, 1])
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def save_static_charts(
    summary: pd.DataFrame,
    anomalies: pd.DataFrame,
    regional: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    """요청된 4종 정적 PNG 지도/차트를 저장한다."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    paths["nationwide_kma_tavg_sen_slope.png"] = _static_station_map(
        summary, "kma_tavg_sen_slope_decade", output_dir / "nationwide_kma_tavg_sen_slope.png",
        "KMA TAVG Sen's Slope · Tier A Stations", "°C / decade",
    )
    paths["nationwide_tavg_validation_rmse.png"] = _static_station_map(
        summary, "tavg_rmse", output_dir / "nationwide_tavg_validation_rmse.png",
        "NASA–KMA TAVG RMSE · Tier A Stations", "°C",
    )

    heatmap_path = output_dir / "nationwide_temperature_anomaly_heatmap.png"
    selected = anomalies.loc[
        anomalies["source"].eq("KMA") & anomalies["metric"].eq("TAVG")
    ].copy()
    station_order = summary.sort_values("latitude", ascending=False)["station_id"].astype(str)
    label_map = (summary.set_index(summary["station_id"].astype(str))["station_name"].astype(str)).to_dict()
    selected["station_id"] = selected["station_id"].astype(str)
    pivot = selected.pivot(index="station_id", columns="year", values="anomaly").reindex(station_order)
    figure, axis = plt.subplots(figsize=(15, 12))
    maximum = max(float(np.nanmax(np.abs(pivot.to_numpy()))), 1e-6)
    image = axis.imshow(pivot.to_numpy(), aspect="auto", cmap="RdBu_r", vmin=-maximum, vmax=maximum)
    axis.set_xticks(np.arange(0, len(pivot.columns), 5), pivot.columns[::5])
    axis.set_yticks(np.arange(len(pivot.index)), [f"{sid} {label_map.get(sid, '')}" for sid in pivot.index])
    axis.set_xlabel("Year")
    axis.set_ylabel("Station (latitude descending)")
    axis.set_title("KMA TAVG Anomaly Relative to 1991–2020 Normal")
    figure.colorbar(image, ax=axis, label="°C")
    figure.tight_layout()
    figure.savefig(heatmap_path, dpi=180)
    plt.close(figure)
    paths[heatmap_path.name] = heatmap_path

    region_path = output_dir / "nationwide_regional_temperature_trend.png"
    ordered = regional.sort_values("median_kma_tavg_sen_slope")
    figure, axis = plt.subplots(figsize=(11, 7))
    axis.barh(ordered["region"], ordered["median_kma_tavg_sen_slope"], color="#d55e00")
    axis.axvline(0, color="#333", linewidth=0.8)
    axis.set_xlabel("Median KMA TAVG Sen slope (°C / decade)")
    axis.set_title("Regional Station-Sample Summary · Not Area-Weighted")
    figure.tight_layout()
    figure.savefig(region_path, dpi=180)
    plt.close(figure)
    paths[region_path.name] = region_path
    return paths
