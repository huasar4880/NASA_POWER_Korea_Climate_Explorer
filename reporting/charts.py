"""Static report graphics from facts; never download or refit statistical models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd

from reporting.data_provider import ComparisonFacts, ReportFacts
from src.validation_visualization import plot_city_annual_temperature, plot_temperature_scatter


@dataclass(frozen=True)
class Chart:
    """A rendered figure and source-table/operation provenance."""

    key: str
    title: str
    path: Path
    source_files: tuple[str, ...]
    operation: str = "저장된 결과값을 그대로 시각화; 통계 재추정 없음"


def font_settings() -> dict[str, object]:
    """Detect a portable Korean font; English plot labels also work with DejaVu Sans."""

    available = {font.name for font in font_manager.fontManager.ttflist}
    family = next((name for name in ("Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR") if name in available), "DejaVu Sans")
    return {"font.family": family, "axes.unicode_minus": False, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False}


def _save(fig: plt.Figure, path: Path) -> None:
    """Write a report-owned PNG and release figure resources."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _line(ax: plt.Axes, frame: pd.DataFrame, x: str, columns: list[str], labels: list[str], unit: str) -> None:
    """Draw stored series with gaps intact and no interpolation."""

    for col, label in zip(columns, labels):
        ax.plot(frame[x], pd.to_numeric(frame[col], errors="coerce"), label=label, linewidth=1.6)
    ax.set_ylabel(unit)
    ax.grid(alpha=0.18)
    ax.legend(fontsize=8, ncol=min(3, len(columns)))


def city_charts(facts: ReportFacts, directory: Path) -> list[Chart]:
    """Create the eight required figures and a precipitation time series."""

    directory.mkdir(parents=True, exist_ok=True)
    charts: list[Chart] = []

    def add(key: str, title: str, fig: plt.Figure, *tables: str, operation: str = "저장된 결과값을 그대로 표시") -> None:
        """Save a figure with explicit input source paths."""

        path = directory / f"{key}.png"
        _save(fig, path)
        charts.append(Chart(key, title, path, tuple(facts.tables[t].source_file for t in tables),
            operation))

    annual = pd.DataFrame(facts.tables["annual"].rows).sort_values("YEAR")
    anomaly = pd.DataFrame(facts.tables["anomalies"].rows).sort_values("YEAR")
    with plt.rc_context(font_settings()):
        fig, ax = plt.subplots(figsize=(10, 4))
        _line(ax, annual, "YEAR", ["T2M_mean_C", "T2M_MAX_mean_C", "T2M_MIN_mean_C", "T2M_MA5_C", "T2M_MA10_C"], ["T2M", "T2M_MAX", "T2M_MIN", "T2M MA5", "T2M MA10"], "°C")
        ax.set(title=f"{facts.city}: annual temperature", xlabel="Year")
        add("temperature_longterm", "연평균기온과 5·10년 이동평균", fig, "annual")
        fig, ax = plt.subplots(figsize=(10, 3.6))
        ax.bar(anomaly.YEAR, anomaly.T2M_anomaly, color=["#b85042" if v >= 0 else "#3b7297" for v in anomaly.T2M_anomaly])
        ax.axhline(0, color="#333", linewidth=0.7)
        ax.set(title=f"{facts.city}: T2M anomaly vs stored climate normal", ylabel="°C", xlabel="Year")
        add("temperature_anomaly", "T2M anomaly", fig, "anomalies")
        monthly = pd.DataFrame(facts.tables["monthly"].rows).sort_values("MONTH")
        fig, axes = plt.subplots(2, 3, figsize=(11, 6), layout="constrained")
        for ax, col, title, unit in zip(axes.flat, ["T2M_mean_C", "precipitation_monthly_total_mean_mm", "RH2M_mean_pct", "WS10M_mean_m_s", "solar_mean_kWh_m2_day"], ["T2M", "Precipitation", "Humidity", "Wind", "Solar"], ["°C", "mm/month", "%", "m/s", "kWh/m²/day"]):
            _line(ax, monthly, "MONTH", [col], [title], unit)
            ax.set_xticks([1, 3, 6, 9, 12])
            ax.set_title(title)
        axes.flat[-1].set_visible(False)
        add("monthly_climatology", "기후변수 월별 climatology", fig, "monthly")
        fig, axes = plt.subplots(2, 1, figsize=(10, 6), layout="constrained")
        _line(axes[0], annual, "YEAR", ["days_tmax_ge_30", "days_tmax_ge_33", "days_tmin_ge_25"], ["Tmax >=30°C", "Tmax >=33°C", "Tmin >=25°C"], "days/year")
        _line(axes[1], annual, "YEAR", ["days_precip_ge_30", "days_precip_ge_50", "days_precip_lt_1"], ["P >=30mm", "P >=50mm", "P <1mm"], "days/year")
        add("extreme_proxies", "분석용 threshold proxy의 연간 변화", fig, "annual")
        seasonal = pd.DataFrame(facts.tables["seasonal"].rows)
        seasonal = seasonal.loc[seasonal.metric.eq("temperature")].set_index("season").reindex(["DJF", "MAM", "JJA", "SON"])
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.scatter(seasonal.index, seasonal.sen_slope_per_decade, color="#246881")
        ax.vlines(range(len(seasonal)), seasonal.sen_ci_lower, seasonal.sen_ci_upper, color="#246881", linewidth=2)
        ax.axhline(0, color="#555", linewidth=0.7)
        ax.set(title="Seasonal T2M Sen slope and 95% CI", ylabel="°C / decade")
        add("seasonal_trend", "계절별 T2M Sen 기울기와 95% CI", fig, "seasonal")
        matched = pd.DataFrame(facts.tables["matched"].rows)
        for key, title, function in [
            ("t2m_scatter", "NASA vs KMA 일평균 T2M 산점도", plot_temperature_scatter),
            ("t2m_annual_validation", "NASA vs KMA 연평균 T2M", plot_city_annual_temperature),
        ]:
            path = directory / f"{key}.png"
            if key == "t2m_scatter":
                function(matched, path)
            else:
                function(matched, path, facts.city)
            charts.append(Chart(key, title, path, (facts.tables["matched"].source_file,),
                "기존 7단계 시각화 함수 재사용; 연평균은 T2M 유효 daily pair의 연도별 산술평균, 새 통계모형 없음"))
        validation = pd.DataFrame(facts.tables["validation"].rows)
        fig, ax = plt.subplots(figsize=(10, 3.8))
        ax.barh(validation.metric, validation.pearson_r, color="#427c91")
        ax.set(xlim=(-1, 1), xlabel="Pearson r (not accuracy %)", title="Agreement by variable; see table for Bias / MAE / RMSE")
        add("validation_summary", "변수별 상관 요약 — 절대오차·단위는 표 참조", fig, "validation")
        fig, ax = plt.subplots(figsize=(10, 3.5))
        _line(ax, annual, "YEAR", ["precipitation_total_mm"], ["NASA annual precipitation"], "mm/year")
        add("precipitation", "NASA 연간 강수량", fig, "annual")
    return charts


def comparison_charts(facts: ComparisonFacts, directory: Path) -> list[Chart]:
    """Create the required comparison graphics plus a coordinate-location schematic."""

    directory.mkdir(parents=True, exist_ok=True)
    charts: list[Chart] = []
    cities = facts.cities

    def save(key: str, title: str, fig: plt.Figure, table: str, operation: str = "저장된 결과값을 그대로 시각화") -> None:
        """Attach shared table sources to comparison figures."""

        path = directory / f"{key}.png"
        _save(fig, path)
        sources = tuple(sorted({f.tables[table].source_file for f in cities}))
        charts.append(Chart(key, title, path, sources, operation))

    with plt.rc_context(font_settings()):
        for key, title, metric, unit, table in [
            ("sen_temperature", "T2M Sen 기울기", "temperature_sen_slope", "°C / decade", "trends"),
            ("hot_day_33", "33°C 분석용 proxy 변화", "days_tmax_ge_33_sen_slope", "days/year / decade", "trends"),
            ("warm_night_25", "Tmin 25°C 분석용 proxy 변화", "days_tmin_ge_25_sen_slope", "days/year / decade", "trends"),
            ("t2m_bias", "도시별 T2M Bias", "kma_t2m_bias", "NASA - KMA (°C)", "validation"),
            ("t2m_rmse", "도시별 T2M RMSE", "kma_t2m_rmse", "°C", "validation"),
        ]:
            fig, ax = plt.subplots(figsize=(10, 4))
            values = [f.value(metric) if f.value(metric) is not None else np.nan for f in cities]
            ax.bar([f.city for f in cities], values, color="#3b758b")
            if key == "sen_temperature":
                ax.vlines(range(len(cities)), [f.value("temperature_sen_ci_lower") for f in cities], [f.value("temperature_sen_ci_upper") for f in cities], color="#222")
            ax.axhline(0, color="#555", linewidth=0.7)
            ax.set_ylabel(unit)
            ax.grid(axis="y", alpha=0.15)
            save(key, title, fig, table)
        for key, title, table, column, x, unit in [
            ("anomaly_heatmap", "T2M anomaly 도시·연도 비교", "anomalies", "T2M_anomaly", "YEAR", "°C"),
            ("seasonal_heatmap", "계절별 T2M Sen 기울기", "seasonal", "sen_slope_per_decade", "season", "°C / decade"),
        ]:
            rows = [r for f in cities for r in f.tables[table].rows if table != "seasonal" or r["metric"] == "temperature"]
            pivot = pd.DataFrame(rows).pivot(index="city", columns=x, values=column).reindex([f.city for f in cities])
            if x == "season":
                pivot = pivot.reindex(columns=["DJF", "MAM", "JJA", "SON"])
            fig, ax = plt.subplots(figsize=(11, 4.5))
            values = pivot.to_numpy(dtype=float)
            limit = np.nanmax(np.abs(values)) if np.isfinite(values).any() else 1
            limit = max(limit, 0.01)
            im = ax.imshow(np.ma.masked_invalid(values), aspect="auto", cmap="RdBu_r", vmin=-limit, vmax=limit)
            step = 5 if x == "YEAR" else 1
            ax.set_xticks(range(0, len(pivot.columns), step), pivot.columns[::step])
            ax.set_yticks(range(len(pivot.index)), pivot.index)
            fig.colorbar(im, ax=ax, label=unit)
            save(key, title, fig, table)
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
        for ax, label, table, col in [(axes[0], "KMA precipitation: numeric blank/NaN count", "kma_quality", "missing_precipitation"), (axes[1], "NASA solar: missing value count", "nasa_quality", "missing_ALLSKY_SFC_SW_DWN")]:
            ax.barh([f.city for f in cities], [f.tables[table].rows[0][col] for f in cities], color="#899b9f")
            ax.set(title=label, xlabel="Days (not confirmed observation outages)")
        path = directory / "data_quality.png"
        _save(fig, path)
        charts.append(Chart("data_quality", "변수별 수치 결측", path, tuple(sorted({f.tables[t].source_file for f in cities for t in ("kma_quality", "nasa_quality")}))))
        fig, ax = plt.subplots(figsize=(7, 6))
        for f in cities:
            ax.scatter(f.value("longitude"), f.value("latitude"), s=45, color="#245d79")
            ax.annotate(f.city, (f.value("longitude"), f.value("latitude")), xytext=(5, 5), textcoords="offset points")
        ax.set(xlabel="Longitude (°E)", ylabel="Latitude (°N)", title="City locations (coordinate schematic; no administrative boundaries)")
        ax.margins(0.18)
        ax.grid(alpha=0.2)
        ax.set_aspect(1 / np.cos(np.deg2rad(36)))
        save("city_locations", "분석도시 위치 — 위·경도 개략도", fig, "summary")
    return charts
