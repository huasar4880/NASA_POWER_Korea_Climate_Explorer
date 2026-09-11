"""Stage-12 station point maps와 공간관계 정적 charts."""

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
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=KOREAN_FONT_PATH).get_name()
    plt.rcParams["axes.unicode_minus"] = False


MAP_SPECS = {
    "kma_tavg_spatial_pattern.html": ("kma_tavg_sen_slope", "KMA TAVG Sen slope", "°C/10년"),
    "kma_tmax_spatial_pattern.html": ("kma_tmax_sen_slope", "KMA TMAX Sen slope", "°C/10년"),
    "kma_tmin_spatial_pattern.html": ("kma_tmin_sen_slope", "KMA TMIN Sen slope", "°C/10년"),
    "tmax_tmin_warming_contrast.html": ("tmin_minus_tmax", "TMIN - TMAX warming contrast", "°C/10년"),
    "days_tmax_ge_33_proxy.html": ("days_tmax_ge_33_kma_slope", "KMA TMAX ≥33°C proxy slope", "일/년/10년"),
    "days_tmin_ge_25_proxy.html": ("days_tmin_ge_25_kma_slope", "KMA TMIN ≥25°C proxy slope", "일/년/10년"),
    "nasa_kma_tavg_bias.html": ("tavg_bias", "NASA-KMA TAVG Bias", "°C"),
    "nasa_kma_tavg_rmse.html": ("tavg_rmse", "NASA-KMA TAVG RMSE", "°C"),
}


def _map_data(master: pd.DataFrame, value_column: str) -> pd.DataFrame:
    """공간 point map의 필수 station/metric 값을 검증한다."""

    required = {
        "station_id", "station_name", "region_level1", "latitude", "longitude",
        "elevation_m", "tavg_fdr_q", "continuity_risk", "annual_completeness", value_column,
    }
    missing = required - set(master)
    if missing:
        raise ValueError(f"공간 지도 필수 컬럼 누락: {sorted(missing)}")
    data = master.dropna(subset=["latitude", "longitude", value_column]).copy()
    if data[["latitude", "longitude"]].isna().any().any():
        raise ValueError("공간 지도 좌표가 누락되었습니다.")
    return data


def create_spatial_value_map(
    master: pd.DataFrame,
    value_column: str,
    title: str,
    unit: str,
) -> go.Figure:
    """보간하지 않은 station-level Plotly Scattergeo 지도를 만든다."""

    data = _map_data(master, value_column)
    values = pd.to_numeric(data[value_column], errors="coerce")
    maximum = max(float(np.nanmax(np.abs(values))), 1e-9)
    minimum = -maximum if float(values.min()) < 0 else float(values.min())
    hover = np.column_stack([
        data["station_id"].astype(str), data["station_name"].astype(str),
        data["region_level1"].astype(str), data["elevation_m"], values,
        data["tavg_fdr_q"], data["continuity_risk"].astype(str), data["annual_completeness"],
    ])
    figure = go.Figure(go.Scattergeo(
        lon=data["longitude"], lat=data["latitude"], mode="markers",
        text=data["station_id"].astype(str) + " " + data["station_name"].astype(str),
        customdata=hover,
        marker={
            "size": 11, "color": values, "colorscale": "RdBu_r", "cmin": minimum,
            "cmax": maximum, "colorbar": {"title": unit}, "line": {"color": "#222", "width": 0.5},
        },
        hovertemplate=(
            "ID: %{customdata[0]}<br>Station: %{customdata[1]}<br>Region: %{customdata[2]}"
            "<br>Elevation: %{customdata[3]:.1f} m<br>Metric: %{customdata[4]:+.4f}"
            "<br>TAVG FDR q: %{customdata[5]:.4g}<br>Continuity: %{customdata[6]}"
            "<br>Annual completeness: %{customdata[7]:.3f}<extra></extra>"
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
            "text": "Final Tier A station points; no interpolation and not area-weighted.",
            "x": 0.01, "y": 0.01, "xref": "paper", "yref": "paper", "showarrow": False,
        }],
    )
    return figure


def create_category_map(
    data: pd.DataFrame,
    category_column: str,
    title: str,
    categories: list[str],
) -> go.Figure:
    """dominant season 또는 Local Moran category station point map을 만든다."""

    required = {"station_id", "station_name", "latitude", "longitude", category_column}
    missing = required - set(data)
    if missing:
        raise ValueError(f"category map 필수 컬럼 누락: {sorted(missing)}")
    palette = ["#d73027", "#4575b4", "#fdae61", "#74add1", "#8c8c8c"]
    figure = go.Figure()
    for category, color in zip(categories, palette):
        subset = data.loc[data[category_column].eq(category)]
        if subset.empty:
            continue
        figure.add_trace(go.Scattergeo(
            lon=subset["longitude"], lat=subset["latitude"], mode="markers", name=category,
            text=subset["station_id"].astype(str) + " " + subset["station_name"].astype(str),
            marker={"size": 11, "color": color, "line": {"color": "#222", "width": 0.5}},
            hovertemplate="%{text}<br>" + category_column + f": {category}<extra></extra>",
        ))
    figure.update_geos(
        projection_type="mercator", lonaxis_range=[124.0, 132.0], lataxis_range=[32.0, 39.5],
        showcountries=True, showcoastlines=True, showland=True, landcolor="#f3f4f6",
    )
    figure.update_layout(
        title={"text": title, "x": 0.02}, template="plotly_white", height=700,
        margin={"l": 5, "r": 5, "b": 5, "t": 65},
        annotations=[{
            "text": "Station-level categories; no interpolated surface.",
            "x": 0.01, "y": 0.01, "xref": "paper", "yref": "paper", "showarrow": False,
        }],
    )
    return figure


def save_interactive_spatial_maps(
    master: pd.DataFrame,
    contrast: pd.DataFrame,
    dominant: pd.DataFrame,
    local: pd.DataFrame,
    seasonal: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    """요청된 핵심·계절 interactive station map HTML을 저장한다."""

    output_dir.mkdir(parents=True, exist_ok=True)
    map_master = master.merge(
        contrast[["station_id", "tmin_minus_tmax"]], on="station_id", how="left", validate="one_to_one"
    )
    paths: dict[str, Path] = {}
    for filename, (column, title, unit) in MAP_SPECS.items():
        path = output_dir / filename
        create_spatial_value_map(map_master, column, title, unit).write_html(
            path, include_plotlyjs="cdn", full_html=True
        )
        paths[filename] = path
    dominant_path = output_dir / "dominant_warming_season.html"
    create_category_map(
        dominant, "dominant_warming_season", "Dominant KMA TAVG warming season",
        ["DJF", "MAM", "JJA", "SON"],
    ).write_html(dominant_path, include_plotlyjs="cdn", full_html=True)
    paths[dominant_path.name] = dominant_path
    local_tavg = local.loc[local["variable"].eq("kma_tavg_sen_slope")].copy()
    local_path = output_dir / "local_moran_tavg.html"
    create_category_map(
        local_tavg, "cluster_type_fdr", "Local Moran KMA TAVG · BH-FDR",
        ["High-High", "Low-Low", "High-Low", "Low-High", "Not Significant"],
    ).write_html(local_path, include_plotlyjs="cdn", full_html=True)
    paths[local_path.name] = local_path
    for season in ["DJF", "MAM", "JJA", "SON"]:
        season_values = seasonal.loc[seasonal["season"].eq(season), [
            "station_id", "sen_slope_per_decade",
        ]].rename(columns={"sen_slope_per_decade": "seasonal_slope"})
        season_master = master.merge(
            season_values, on="station_id", how="left", validate="one_to_one"
        )
        season_path = output_dir / f"seasonal_{season.lower()}_tavg_spatial_pattern.html"
        create_spatial_value_map(
            season_master, "seasonal_slope", f"{season} KMA TAVG Sen slope", "°C/10년"
        ).write_html(season_path, include_plotlyjs="cdn", full_html=True)
        paths[season_path.name] = season_path
    return paths


def _static_point_map(
    data: pd.DataFrame,
    value_column: str,
    path: Path,
    title: str,
    colorbar_label: str,
) -> Path:
    """보간 없는 lon/lat point map PNG를 저장한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    clean = data.dropna(subset=["latitude", "longitude", value_column])
    values = pd.to_numeric(clean[value_column], errors="coerce")
    maximum = max(float(np.nanmax(np.abs(values))), 1e-9)
    vmin = -maximum if float(values.min()) < 0 else float(values.min())
    figure, axis = plt.subplots(figsize=(8.3, 9.0))
    scatter = axis.scatter(
        clean["longitude"], clean["latitude"], c=values, cmap="RdBu_r", vmin=vmin,
        vmax=maximum, s=68, edgecolor="#222", linewidth=0.5,
    )
    axis.set(xlim=(124.5, 131.5), ylim=(32.8, 39.0), xlabel="Longitude (°E)", ylabel="Latitude (°N)", title=title)
    axis.grid(alpha=0.2)
    figure.colorbar(scatter, ax=axis, label=colorbar_label)
    figure.text(0.5, 0.01, "Final Tier A station points; no interpolation.", ha="center", fontsize=9)
    figure.tight_layout(rect=[0, 0.03, 1, 1])
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _scatter_with_regression(
    data: pd.DataFrame,
    x: str,
    y: str,
    path: Path,
    title: str,
    x_label: str,
    y_label: str,
) -> Path:
    """탐색적 least-squares line을 포함한 station scatter PNG를 저장한다."""

    clean = data[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    figure, axis = plt.subplots(figsize=(8.2, 5.4))
    axis.scatter(clean[x], clean[y], color="#2369a1", edgecolor="#222", alpha=0.85)
    if len(clean) >= 3 and clean[x].nunique() > 1:
        slope, intercept = np.polyfit(clean[x], clean[y], 1)
        grid = np.linspace(clean[x].min(), clean[x].max(), 100)
        axis.plot(grid, slope * grid + intercept, color="#d55e00", linewidth=2)
    axis.set(title=title, xlabel=x_label, ylabel=y_label)
    axis.grid(alpha=0.2)
    figure.text(0.5, 0.01, "Exploratory association; not causality.", ha="center", fontsize=9)
    figure.tight_layout(rect=[0, 0.04, 1, 1])
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _seasonal_summary_chart(seasonal: pd.DataFrame, path: Path) -> Path:
    """계절별 station Sen slope를 보간 없는 2×2 point map으로 저장한다."""

    order = ["DJF", "MAM", "JJA", "SON"]
    all_values = pd.to_numeric(seasonal["sen_slope_per_decade"], errors="coerce")
    maximum = max(float(np.nanmax(np.abs(all_values))), 1e-9)
    minimum = -maximum if float(all_values.min()) < 0 else float(all_values.min())
    figure, axes = plt.subplots(2, 2, figsize=(11.0, 10.0), sharex=True, sharey=True)
    scatter = None
    for axis, season in zip(axes.flat, order):
        subset = seasonal.loc[seasonal["season"].eq(season)]
        scatter = axis.scatter(
            subset["longitude"], subset["latitude"], c=subset["sen_slope_per_decade"],
            cmap="RdBu_r", vmin=minimum, vmax=maximum, s=52,
            edgecolor="#222", linewidth=0.4,
        )
        axis.set(title=season, xlim=(124.5, 131.5), ylim=(32.8, 39.0))
        axis.grid(alpha=0.2)
    axes[1, 0].set_xlabel("Longitude (°E)")
    axes[1, 1].set_xlabel("Longitude (°E)")
    axes[0, 0].set_ylabel("Latitude (°N)")
    axes[1, 0].set_ylabel("Latitude (°N)")
    assert scatter is not None
    figure.colorbar(scatter, ax=axes.ravel().tolist(), label="°C / 10 years", shrink=0.85)
    figure.suptitle("Seasonal KMA TAVG Sen slope · station points")
    figure.text(0.5, 0.01, "No interpolation; station coverage is not uniform.", ha="center", fontsize=9)
    figure.subplots_adjust(left=0.08, right=0.88, bottom=0.06, top=0.93, wspace=0.12, hspace=0.14)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _local_category_png(local: pd.DataFrame, path: Path) -> Path:
    """TAVG Local Moran FDR category를 station point PNG로 저장한다."""

    categories = ["High-High", "Low-Low", "High-Low", "Low-High", "Not Significant"]
    colors = dict(zip(categories, ["#d73027", "#4575b4", "#fdae61", "#74add1", "#bdbdbd"]))
    figure, axis = plt.subplots(figsize=(8.3, 9.0))
    for category in categories:
        subset = local.loc[local["cluster_type_fdr"].eq(category)]
        axis.scatter(
            subset["longitude"], subset["latitude"], s=68, color=colors[category],
            edgecolor="#222", linewidth=0.5, label=category,
        )
    axis.set(xlim=(124.5, 131.5), ylim=(32.8, 39.0), xlabel="Longitude (°E)", ylabel="Latitude (°N)", title="Local Moran KMA TAVG · BH-FDR")
    axis.grid(alpha=0.2)
    axis.legend(loc="best")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def save_static_spatial_charts(
    master: pd.DataFrame,
    contrast: pd.DataFrame,
    seasonal: pd.DataFrame,
    local: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    """요청된 point maps와 5개 공간관계 scatter를 PNG로 저장한다."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "kma_tavg_spatial_pattern.png": _static_point_map(
            master, "kma_tavg_sen_slope", output_dir / "kma_tavg_spatial_pattern.png",
            "KMA TAVG Sen slope · Final Tier A", "°C / 10 years",
        ),
        "tmax_tmin_warming_contrast.png": _static_point_map(
            contrast, "tmin_minus_tmax", output_dir / "tmax_tmin_warming_contrast.png",
            "TMIN - TMAX warming contrast", "°C / 10 years",
        ),
        "seasonal_warming_spatial_summary.png": _seasonal_summary_chart(
            seasonal, output_dir / "seasonal_warming_spatial_summary.png"
        ),
        "latitude_vs_tavg_slope.png": _scatter_with_regression(
            master, "latitude", "kma_tavg_sen_slope", output_dir / "latitude_vs_tavg_slope.png",
            "Latitude vs KMA TAVG Sen slope", "Latitude (°N)", "°C / 10 years",
        ),
        "elevation_vs_tavg_slope.png": _scatter_with_regression(
            master, "elevation_m", "kma_tavg_sen_slope", output_dir / "elevation_vs_tavg_slope.png",
            "Elevation vs KMA TAVG Sen slope", "Elevation (m)", "°C / 10 years",
        ),
        "elevation_vs_bias.png": _scatter_with_regression(
            master, "elevation_m", "tavg_bias", output_dir / "elevation_vs_bias.png",
            "Elevation vs NASA-KMA TAVG Bias", "Elevation (m)", "Bias (°C)",
        ),
        "elevation_vs_rmse.png": _scatter_with_regression(
            master, "elevation_m", "tavg_rmse", output_dir / "elevation_vs_rmse.png",
            "Elevation vs NASA-KMA TAVG RMSE", "Elevation (m)", "RMSE (°C)",
        ),
        "tmax_vs_tmin_slope.png": _scatter_with_regression(
            master, "kma_tmax_sen_slope", "kma_tmin_sen_slope", output_dir / "tmax_vs_tmin_slope.png",
            "KMA TMAX vs TMIN Sen slope", "TMAX °C / 10 years", "TMIN °C / 10 years",
        ),
    }
    local_tavg = local.loc[local["variable"].eq("kma_tavg_sen_slope")]
    paths["local_moran_tavg.png"] = _local_category_png(local_tavg, output_dir / "local_moran_tavg.png")
    return paths
