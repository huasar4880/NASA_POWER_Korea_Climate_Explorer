"""연평균 기온 결과를 시각화한다."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from src.config import SETTINGS


def plot_annual_mean_temperature(
    annual_data: pd.DataFrame,
    output_path: Path,
    location_name: str = "Seoul",
) -> None:
    """연평균 T2M 시계열을 PNG로 저장한다."""

    required_columns = {"YEAR", "T2M"}
    missing_columns = required_columns.difference(annual_data.columns)
    if missing_columns:
        raise ValueError(f"그래프에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if annual_data.empty:
        raise ValueError("그래프로 그릴 연간 데이터가 없습니다.")

    start_year = int(annual_data["YEAR"].min())
    end_year = int(annual_data["YEAR"].max())
    figure, axis = plt.subplots(figsize=(12, 6))
    axis.plot(
        annual_data["YEAR"],
        annual_data["T2M"],
        color="#c23b22",
        linewidth=1.8,
        marker="o",
        markersize=3.5,
        label="Annual mean T2M",
    )
    axis.set_title(f"{location_name} Annual Mean Temperature ({start_year}-{end_year})")
    axis.set_xlabel("Year")
    axis.set_ylabel("Annual mean temperature (deg C)")
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_long_term_trends(
    annual_trends: pd.DataFrame,
    output_path: Path,
    location_name: str = "Seoul",
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> None:
    """세 기온 변수의 연평균, 이동평균과 선형 추세선을 그린다."""

    required_columns = {"YEAR"}
    for parameter in parameters:
        required_columns.update(
            {parameter, f"{parameter}_MA5", f"{parameter}_MA10", f"{parameter}_TREND"}
        )
    missing_columns = required_columns.difference(annual_trends.columns)
    if missing_columns:
        raise ValueError(f"장기추세 그래프에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if annual_trends.empty:
        raise ValueError("장기추세 그래프로 그릴 데이터가 없습니다.")

    labels = {
        "T2M": "Annual mean T2M",
        "T2M_MAX": "Annual mean T2M_MAX",
        "T2M_MIN": "Annual mean T2M_MIN",
    }
    start_year = int(annual_trends["YEAR"].min())
    end_year = int(annual_trends["YEAR"].max())
    figure, axes = plt.subplots(len(parameters), 1, figsize=(13, 12), sharex=True)

    for axis, parameter in zip(axes, parameters, strict=True):
        axis.plot(
            annual_trends["YEAR"],
            annual_trends[parameter],
            color="#8c8c8c",
            linewidth=1.0,
            marker="o",
            markersize=2.8,
            alpha=0.75,
            label=labels.get(parameter, parameter),
        )
        axis.plot(
            annual_trends["YEAR"],
            annual_trends[f"{parameter}_MA5"],
            color="#e69f00",
            linewidth=2.0,
            label="5-year trailing mean",
        )
        axis.plot(
            annual_trends["YEAR"],
            annual_trends[f"{parameter}_MA10"],
            color="#0072b2",
            linewidth=2.2,
            label="10-year trailing mean",
        )
        axis.plot(
            annual_trends["YEAR"],
            annual_trends[f"{parameter}_TREND"],
            color="#d55e00",
            linewidth=2.0,
            linestyle="--",
            label="Linear trend",
        )
        axis.set_ylabel("Temperature (deg C)")
        axis.grid(True, alpha=0.25)
        axis.legend(loc="upper left", ncol=2, fontsize=8)

    axes[-1].set_xlabel("Year")
    figure.suptitle(
        f"{location_name} Long-Term Temperature Trends ({start_year}-{end_year})",
        fontsize=15,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_monthly_climatology(
    monthly_climatology: pd.DataFrame,
    output_path: Path,
    location_name: str = "Seoul",
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> None:
    """전체기간 월별 평균 기온 climatology를 PNG로 저장한다."""

    required_columns = {"MONTH", *parameters}
    missing_columns = required_columns.difference(monthly_climatology.columns)
    if missing_columns:
        raise ValueError(f"월 climatology 그래프에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if monthly_climatology.empty:
        raise ValueError("월 climatology 그래프로 그릴 데이터가 없습니다.")

    colors = {"T2M": "#222222", "T2M_MAX": "#d55e00", "T2M_MIN": "#0072b2"}
    figure, axis = plt.subplots(figsize=(11, 6))
    for parameter in parameters:
        axis.plot(
            monthly_climatology["MONTH"],
            monthly_climatology[parameter],
            color=colors.get(parameter),
            linewidth=2.0,
            marker="o",
            label=parameter,
        )
    axis.set_title(f"{location_name} Monthly Temperature Climatology (1981-2025)")
    axis.set_xlabel("Month")
    axis.set_ylabel("Mean temperature (deg C)")
    axis.set_xticks(range(1, 13), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_year_month_heatmap(
    year_month_data: pd.DataFrame,
    output_path: Path,
    location_name: str = "Seoul",
) -> None:
    """연도×월 T2M 평균을 heatmap PNG로 저장한다."""

    required_columns = {"YEAR", "MONTH", "T2M"}
    missing_columns = required_columns.difference(year_month_data.columns)
    if missing_columns:
        raise ValueError(f"heatmap에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if year_month_data.empty:
        raise ValueError("heatmap으로 그릴 데이터가 없습니다.")

    heatmap_data = (
        year_month_data.pivot(index="YEAR", columns="MONTH", values="T2M")
        .sort_index()
        .reindex(columns=range(1, 13))
    )
    years = heatmap_data.index.tolist()
    tick_positions = list(range(0, len(years), 4))
    if tick_positions[-1] != len(years) - 1:
        tick_positions.append(len(years) - 1)

    figure, axis = plt.subplots(figsize=(12, 11))
    image = axis.imshow(
        heatmap_data,
        aspect="auto",
        cmap="RdYlBu_r",
        interpolation="nearest",
    )
    axis.set_title(f"{location_name} Year-Month Mean Temperature (T2M, 1981-2025)")
    axis.set_xlabel("Month")
    axis.set_ylabel("Year")
    axis.set_xticks(range(12), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    axis.set_yticks(tick_positions, [str(years[position]) for position in tick_positions])
    colorbar = figure.colorbar(image, ax=axis, pad=0.02)
    colorbar.set_label("Monthly mean T2M (deg C)")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_annual_temperature_comparison(
    city_annual_data: pd.DataFrame,
    output_path: Path,
) -> None:
    """여러 도시의 연평균 T2M 시계열을 한 그래프에 비교한다."""

    required_columns = {"city", "YEAR", "T2M"}
    missing_columns = required_columns.difference(city_annual_data.columns)
    if missing_columns:
        raise ValueError(f"도시 연평균 그래프에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if city_annual_data.empty:
        raise ValueError("도시 연평균 그래프로 그릴 데이터가 없습니다.")

    cities = city_annual_data["city"].drop_duplicates().tolist()
    colors = matplotlib.colormaps["tab10"]
    figure, axis = plt.subplots(figsize=(14, 8))
    for index, city in enumerate(cities):
        city_data = city_annual_data.loc[city_annual_data["city"] == city].sort_values("YEAR")
        axis.plot(
            city_data["YEAR"],
            city_data["T2M"],
            linewidth=1.5,
            alpha=0.85,
            color=colors(index % 10),
            label=city,
        )
    axis.set_title("Korean Cities Annual Mean Temperature (1981-2025)")
    axis.set_xlabel("Year")
    axis.set_ylabel("Annual mean T2M (deg C)")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_trend_per_decade(
    comparison_data: pd.DataFrame,
    output_path: Path,
) -> None:
    """도시별 T2M 선형추세의 10년당 변화량을 막대그래프로 비교한다."""

    required_columns = {"city", "trend_per_decade"}
    missing_columns = required_columns.difference(comparison_data.columns)
    if missing_columns:
        raise ValueError(f"도시 추세 그래프에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if comparison_data.empty:
        raise ValueError("도시 추세 그래프로 그릴 데이터가 없습니다.")

    plot_data = comparison_data.sort_values("trend_per_decade", ascending=False)
    figure, axis = plt.subplots(figsize=(11, 6))
    bars = axis.bar(
        plot_data["city"],
        plot_data["trend_per_decade"],
        color="#d55e00",
        alpha=0.85,
    )
    axis.axhline(0, color="#333333", linewidth=0.8)
    axis.bar_label(bars, labels=[f"{value:+.3f}" for value in plot_data["trend_per_decade"]], padding=3)
    axis.set_title("Temperature Trend by City (1981-2025)")
    axis.set_xlabel("City")
    axis.set_ylabel("T2M trend (deg C / decade)")
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_recent_vs_past_temperature(
    comparison_data: pd.DataFrame,
    output_path: Path,
) -> None:
    """도시별 1981-1990과 2016-2025 평균 T2M을 비교한다."""

    required_columns = {"city", "first_10yr_mean", "last_10yr_mean"}
    missing_columns = required_columns.difference(comparison_data.columns)
    if missing_columns:
        raise ValueError(f"과거·최근 비교 그래프에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if comparison_data.empty:
        raise ValueError("과거·최근 비교 그래프로 그릴 데이터가 없습니다.")

    positions = list(range(len(comparison_data)))
    bar_width = 0.38
    figure, axis = plt.subplots(figsize=(13, 7))
    axis.bar(
        [position - bar_width / 2 for position in positions],
        comparison_data["first_10yr_mean"],
        width=bar_width,
        color="#0072b2",
        label="1981-1990 mean",
    )
    axis.bar(
        [position + bar_width / 2 for position in positions],
        comparison_data["last_10yr_mean"],
        width=bar_width,
        color="#d55e00",
        label="2016-2025 mean",
    )
    axis.set_xticks(positions, comparison_data["city"])
    axis.set_title("Past vs Recent Mean Temperature by City")
    axis.set_xlabel("City")
    axis.set_ylabel("Mean annual T2M (deg C)")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_temperature_heatmap(
    city_annual_data: pd.DataFrame,
    output_path: Path,
) -> None:
    """행은 도시, 열은 연도인 연평균 T2M heatmap을 생성한다."""

    required_columns = {"city", "YEAR", "T2M"}
    missing_columns = required_columns.difference(city_annual_data.columns)
    if missing_columns:
        raise ValueError(f"도시 heatmap에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if city_annual_data.empty:
        raise ValueError("도시 heatmap으로 그릴 데이터가 없습니다.")

    city_order = city_annual_data["city"].drop_duplicates().tolist()
    heatmap_data = (
        city_annual_data.pivot(index="city", columns="YEAR", values="T2M")
        .reindex(city_order)
        .sort_index(axis=1)
    )
    if heatmap_data.isna().any().any():
        raise ValueError("도시 heatmap 데이터에 누락된 도시·연도 조합이 있습니다.")

    years = heatmap_data.columns.astype(int).tolist()
    tick_positions = [index for index, year in enumerate(years) if year % 5 == 0]
    if 0 not in tick_positions:
        tick_positions.insert(0, 0)
    if len(years) - 1 not in tick_positions:
        tick_positions.append(len(years) - 1)

    figure, axis = plt.subplots(figsize=(15, 6))
    image = axis.imshow(
        heatmap_data,
        aspect="auto",
        cmap="RdYlBu_r",
        interpolation="nearest",
    )
    axis.set_title("Korean Cities Annual Mean Temperature Heatmap (1981-2025)")
    axis.set_xlabel("Year")
    axis.set_ylabel("City")
    axis.set_xticks(tick_positions, [str(years[index]) for index in tick_positions])
    axis.set_yticks(range(len(city_order)), city_order)
    colorbar = figure.colorbar(image, ax=axis, pad=0.02)
    colorbar.set_label("Annual mean T2M (deg C)")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_climate_metric(
    city_annual_data: pd.DataFrame,
    value_column: str,
    output_path: Path,
    title: str,
    y_label: str,
) -> None:
    """동일한 스타일로 8개 도시의 연간 기후변수 시계열을 그린다."""

    required_columns = {"city", "YEAR", value_column}
    missing_columns = required_columns.difference(city_annual_data.columns)
    if missing_columns:
        raise ValueError(f"도시 기후 그래프에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if city_annual_data.empty:
        raise ValueError("도시 기후 그래프로 그릴 데이터가 없습니다.")

    cities = city_annual_data["city"].drop_duplicates().tolist()
    colors = matplotlib.colormaps["tab10"]
    figure, axis = plt.subplots(figsize=(14, 8))
    for index, city in enumerate(cities):
        selected = city_annual_data.loc[city_annual_data["city"] == city].sort_values("YEAR")
        axis.plot(
            selected["YEAR"],
            selected[value_column],
            linewidth=1.5,
            alpha=0.85,
            color=colors(index % 10),
            label=city,
        )
    axis.set_title(title)
    axis.set_xlabel("Year")
    axis.set_ylabel(y_label)
    axis.grid(True, alpha=0.25)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_climate_trend_heatmap(
    climate_summary: pd.DataFrame,
    output_path: Path,
) -> None:
    """변수별 도시 간 z-score로 표준화한 장기추세 heatmap을 생성한다."""

    trend_columns = {
        "Temperature": "temperature_trend_per_decade",
        "Precipitation": "precipitation_trend_per_decade",
        "Humidity": "humidity_trend_per_decade",
        "Wind": "wind_speed_trend_per_decade",
        "Solar": "solar_trend_per_decade",
    }
    required_columns = {"city", *trend_columns.values()}
    missing_columns = required_columns.difference(climate_summary.columns)
    if missing_columns:
        raise ValueError(f"기후추세 heatmap 컬럼이 없습니다: {sorted(missing_columns)}")
    if climate_summary.empty:
        raise ValueError("기후추세 heatmap으로 그릴 데이터가 없습니다.")

    raw = climate_summary.loc[:, trend_columns.values()].astype(float).copy()
    standard_deviation = raw.std(axis=0, ddof=0).replace(0.0, float("nan"))
    standardized = ((raw - raw.mean(axis=0)) / standard_deviation).fillna(0.0)

    figure, axis = plt.subplots(figsize=(10, 7))
    image = axis.imshow(
        standardized,
        aspect="auto",
        cmap="RdBu_r",
        vmin=-2.0,
        vmax=2.0,
        interpolation="nearest",
    )
    axis.set_title("Standardized Climate Trends Across Cities (within-variable z-score)")
    axis.set_xlabel("Climate variable")
    axis.set_ylabel("City")
    axis.set_xticks(range(len(trend_columns)), list(trend_columns))
    axis.set_yticks(range(len(climate_summary)), climate_summary["city"])
    for row_index in range(len(climate_summary)):
        for column_index in range(len(trend_columns)):
            value = float(standardized.iloc[row_index, column_index])
            text_color = "white" if abs(value) >= 1.0 else "black"
            axis.text(
                column_index,
                row_index,
                f"{value:+.2f}",
                ha="center",
                va="center",
                color=text_color,
                fontsize=8,
            )
    colorbar = figure.colorbar(image, ax=axis, pad=0.02)
    colorbar.set_label("Trend z-score within each variable")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_temperature_anomalies(
    anomalies: pd.DataFrame,
    output_path: Path,
) -> None:
    """8개 도시의 1991-2020 normal 대비 연평균 T2M anomaly를 그린다."""

    required = {"city", "YEAR", "T2M_anomaly"}
    missing = required.difference(anomalies.columns)
    if missing:
        raise ValueError(f"기온 anomaly 그래프 컬럼이 없습니다: {sorted(missing)}")
    figure, axis = plt.subplots(figsize=(14, 8))
    colors = matplotlib.colormaps["tab10"]
    for index, (city, city_data) in enumerate(anomalies.groupby("city", sort=False)):
        axis.plot(
            city_data["YEAR"],
            city_data["T2M_anomaly"],
            label=city,
            color=colors(index % 10),
            linewidth=1.5,
            alpha=0.85,
        )
    axis.axhline(0.0, color="#222222", linewidth=1.0, linestyle="--")
    axis.set_title("Annual T2M Anomaly Relative to 1991-2020 Climate Normal")
    axis.set_xlabel("Year")
    axis.set_ylabel("T2M anomaly (deg C)")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_temperature_anomaly_heatmap(
    anomalies: pd.DataFrame,
    output_path: Path,
) -> None:
    """도시×연도 T2M anomaly heatmap을 생성한다."""

    required = {"city", "YEAR", "T2M_anomaly"}
    missing = required.difference(anomalies.columns)
    if missing:
        raise ValueError(f"기온 anomaly heatmap 컬럼이 없습니다: {sorted(missing)}")
    city_order = anomalies["city"].drop_duplicates().tolist()
    matrix = anomalies.pivot(index="city", columns="YEAR", values="T2M_anomaly").reindex(city_order)
    years = matrix.columns.astype(int).tolist()
    ticks = [index for index, year in enumerate(years) if year % 5 == 0]
    if 0 not in ticks:
        ticks.insert(0, 0)
    if len(years) - 1 not in ticks:
        ticks.append(len(years) - 1)
    limit = float(np.nanmax(np.abs(matrix.to_numpy(dtype=float))))
    figure, axis = plt.subplots(figsize=(15, 6))
    image = axis.imshow(
        matrix,
        aspect="auto",
        cmap="RdBu_r",
        vmin=-limit,
        vmax=limit,
        interpolation="nearest",
    )
    axis.set_title("Annual T2M Anomaly Heatmap (1991-2020 Normal)")
    axis.set_xlabel("Year")
    axis.set_ylabel("City")
    axis.set_xticks(ticks, [str(years[index]) for index in ticks])
    axis.set_yticks(range(len(city_order)), city_order)
    colorbar = figure.colorbar(image, ax=axis, pad=0.02)
    colorbar.set_label("T2M anomaly (deg C)")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_sen_slopes(
    statistical_trends: pd.DataFrame,
    metric: str,
    output_path: Path,
    title: str,
    y_label: str,
) -> None:
    """도시별 Sen slope와 95% slope 신뢰구간을 error-bar로 비교한다."""

    required = {"city", "metric", "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper"}
    missing = required.difference(statistical_trends.columns)
    if missing:
        raise ValueError(f"Sen slope 그래프 컬럼이 없습니다: {sorted(missing)}")
    selected = statistical_trends.loc[statistical_trends["metric"] == metric].copy()
    if selected.empty:
        raise ValueError(f"Sen slope 그래프 metric이 없습니다: {metric}")
    selected = selected.sort_values("sen_slope_per_decade", ascending=False)
    slope = selected["sen_slope_per_decade"].to_numpy(dtype=float)
    lower = selected["sen_ci_lower"].to_numpy(dtype=float)
    upper = selected["sen_ci_upper"].to_numpy(dtype=float)
    yerr = np.vstack([np.maximum(0.0, slope - lower), np.maximum(0.0, upper - slope)])
    colors = np.where(selected["significant_fdr"], "#d55e00", "#8c8c8c")
    figure, axis = plt.subplots(figsize=(12, 7))
    positions = np.arange(len(selected))
    axis.bar(positions, slope, color=colors, alpha=0.85)
    axis.errorbar(
        positions,
        slope,
        yerr=yerr,
        fmt="none",
        ecolor="#222222",
        capsize=5,
        linewidth=1.2,
    )
    axis.axhline(0.0, color="#222222", linewidth=0.8)
    axis.set_xticks(positions, selected["city"], rotation=20)
    axis.set_title(title)
    axis.set_xlabel("City")
    axis.set_ylabel(y_label)
    axis.grid(axis="y", alpha=0.25)
    axis.legend(
        handles=[
            Patch(color="#d55e00", label="FDR-significant original MK"),
            Patch(color="#8c8c8c", label="Not FDR-significant"),
        ],
        loc="best",
    )
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_seasonal_temperature_trends(
    seasonal_trends: pd.DataFrame,
    output_path: Path,
) -> None:
    """도시별 DJF/MAM/JJA/SON T2M Sen slope를 grouped bar로 표시한다."""

    selected = seasonal_trends.loc[seasonal_trends["metric"] == "temperature"].copy()
    required = {"city", "season", "sen_slope_per_decade"}
    missing = required.difference(selected.columns)
    if missing or selected.empty:
        raise ValueError(f"계절 기온 그래프 컬럼이 없습니다: {sorted(missing)}")
    city_order = selected["city"].drop_duplicates().tolist()
    seasons = ["DJF", "MAM", "JJA", "SON"]
    matrix = selected.pivot(index="city", columns="season", values="sen_slope_per_decade").reindex(
        index=city_order, columns=seasons
    )
    positions = np.arange(len(city_order))
    width = 0.2
    colors = ["#56b4e9", "#009e73", "#e69f00", "#cc79a7"]
    figure, axis = plt.subplots(figsize=(15, 8))
    for index, season in enumerate(seasons):
        offset = (index - 1.5) * width
        axis.bar(
            positions + offset,
            matrix[season],
            width=width,
            label=season,
            color=colors[index],
        )
    axis.axhline(0.0, color="#222222", linewidth=0.8)
    axis.set_xticks(positions, city_order)
    axis.set_title("Seasonal T2M Sen Slopes by City")
    axis.set_xlabel("City")
    axis.set_ylabel("T2M Sen slope (deg C / decade)")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(title="Season", ncol=4)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_seasonal_trend_heatmap(
    seasonal_trends: pd.DataFrame,
    output_path: Path,
) -> None:
    """도시×계절 T2M Sen slope의 실제 단위 heatmap을 생성한다."""

    selected = seasonal_trends.loc[seasonal_trends["metric"] == "temperature"].copy()
    city_order = selected["city"].drop_duplicates().tolist()
    seasons = ["DJF", "MAM", "JJA", "SON"]
    matrix = selected.pivot(index="city", columns="season", values="sen_slope_per_decade").reindex(
        index=city_order, columns=seasons
    )
    limit = float(np.nanmax(np.abs(matrix.to_numpy(dtype=float))))
    figure, axis = plt.subplots(figsize=(9, 7))
    image = axis.imshow(matrix, aspect="auto", cmap="RdBu_r", vmin=-limit, vmax=limit)
    axis.set_title("Seasonal T2M Sen Slope Heatmap")
    axis.set_xlabel("Season")
    axis.set_ylabel("City")
    axis.set_xticks(range(len(seasons)), seasons)
    axis.set_yticks(range(len(city_order)), city_order)
    for row in range(len(city_order)):
        for column in range(len(seasons)):
            value = float(matrix.iloc[row, column])
            axis.text(column, row, f"{value:+.2f}", ha="center", va="center", fontsize=8)
    colorbar = figure.colorbar(image, ax=axis, pad=0.02)
    colorbar.set_label("T2M Sen slope (deg C / decade)")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def plot_city_climate_significance_heatmap(
    statistical_trends: pd.DataFrame,
    output_path: Path,
) -> None:
    """주요 변수의 FDR 유의 증가·감소·비유의를 범주형 heatmap으로 표시한다."""

    metrics = {
        "T2M": "temperature",
        "T2M_MAX": "temperature_max_mean",
        "T2M_MIN": "temperature_min_mean",
        "Precip": "precipitation",
        "RH2M": "humidity",
        "WS10M": "wind",
        "Solar": "solar",
        "Hot33": "hot_day_33",
        "Warm25": "warm_night_25",
    }
    selected = statistical_trends.loc[statistical_trends["metric"].isin(metrics.values())].copy()
    selected["significance_code"] = 0
    selected.loc[
        selected["significant_fdr"] & selected["mk_trend"].eq("increasing"),
        "significance_code",
    ] = 1
    selected.loc[
        selected["significant_fdr"] & selected["mk_trend"].eq("decreasing"),
        "significance_code",
    ] = -1
    city_order = selected["city"].drop_duplicates().tolist()
    matrix = selected.pivot(index="city", columns="metric", values="significance_code").reindex(
        index=city_order, columns=list(metrics.values())
    )
    cmap = ListedColormap(["#0072b2", "#d9d9d9", "#d55e00"])
    figure, axis = plt.subplots(figsize=(12, 7))
    axis.imshow(matrix, aspect="auto", cmap=cmap, vmin=-1.5, vmax=1.5)
    axis.set_title("FDR-Corrected Mann-Kendall Significance (alpha=0.05)")
    axis.set_xlabel("Climate metric")
    axis.set_ylabel("City")
    axis.set_xticks(range(len(metrics)), list(metrics), rotation=25, ha="right")
    axis.set_yticks(range(len(city_order)), city_order)
    labels = {-1: "DEC", 0: "NS", 1: "INC"}
    for row in range(len(city_order)):
        for column in range(len(metrics)):
            code = int(matrix.iloc[row, column])
            axis.text(column, row, labels[code], ha="center", va="center", fontsize=8)
    axis.legend(
        handles=[
            Patch(color="#d55e00", label="FDR-significant increase"),
            Patch(color="#0072b2", label="FDR-significant decrease"),
            Patch(color="#d9d9d9", label="Not FDR-significant"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=3,
    )
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)
