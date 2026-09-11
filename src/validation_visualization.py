"""NASA POWER × KMA ASOS validation 정적 그래프 생성."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _save(figure: plt.Figure, path: Path) -> Path:
    """그래프를 PNG로 저장하고 matplotlib 자원을 해제한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return path


def plot_temperature_scatter(matched: pd.DataFrame, path: Path) -> Path:
    """도시별 T2M 산점도와 1:1 기준선을 그린다."""

    clean = matched.dropna(subset=["kma_T2M", "nasa_T2M"])
    if clean.empty:
        raise ValueError("T2M scatter에 사용할 pair가 없습니다.")
    if len(clean) > 40_000:
        clean = clean.iloc[np.linspace(0, len(clean) - 1, 40_000, dtype=int)]
    figure, axis = plt.subplots(figsize=(8, 7))
    for city, group in clean.groupby("city", sort=False):
        axis.scatter(group["kma_T2M"], group["nasa_T2M"], s=5, alpha=0.18, label=city)
    lower = float(min(clean["kma_T2M"].min(), clean["nasa_T2M"].min()))
    upper = float(max(clean["kma_T2M"].max(), clean["nasa_T2M"].max()))
    axis.plot([lower, upper], [lower, upper], linestyle="--", color="black", linewidth=1)
    axis.set(title="NASA POWER vs KMA ASOS Daily Mean Temperature", xlabel="KMA ASOS (deg C)", ylabel="NASA POWER (deg C)")
    axis.legend(ncol=2, fontsize=8)
    axis.grid(alpha=0.2)
    return _save(figure, path)


def plot_metric_by_city(
    metrics: pd.DataFrame,
    value_column: str,
    path: Path,
    title: str,
    ylabel: str,
) -> Path:
    """도시별 T2M validation 지표 막대그래프를 그린다."""

    clean = metrics.loc[metrics["metric"].eq("temperature")].dropna(subset=[value_column])
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.bar(clean["city"], clean[value_column], color="#2463a2")
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set(title=title, ylabel=ylabel)
    axis.tick_params(axis="x", rotation=30)
    axis.grid(axis="y", alpha=0.2)
    return _save(figure, path)


def plot_precipitation_validation(metrics: pd.DataFrame, path: Path) -> Path:
    """도시별 강수 MAE와 RMSE를 나란히 표시한다."""

    clean = metrics.loc[metrics["metric"].eq("precipitation")].dropna(subset=["mae", "rmse"])
    positions = np.arange(len(clean))
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.bar(positions - 0.18, clean["mae"], width=0.36, label="MAE")
    axis.bar(positions + 0.18, clean["rmse"], width=0.36, label="RMSE")
    axis.set_xticks(positions, clean["city"], rotation=30)
    axis.set(title="Daily Precipitation Agreement Metrics", ylabel="mm/day")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    return _save(figure, path)


def plot_metric_heatmap(
    metrics: pd.DataFrame,
    value_column: str,
    path: Path,
    title: str,
    colorbar_label: str,
    *,
    cmap: str,
) -> Path:
    """도시×변수 상관 또는 정규화 RMSE heatmap을 그린다."""

    pivot = metrics.pivot(index="city", columns="metric", values=value_column)
    figure, axis = plt.subplots(figsize=(11, 5.5))
    image = axis.imshow(pivot.to_numpy(dtype=float), aspect="auto", cmap=cmap)
    axis.set_xticks(range(len(pivot.columns)), pivot.columns, rotation=30, ha="right")
    axis.set_yticks(range(len(pivot.index)), pivot.index)
    axis.set_title(title)
    figure.colorbar(image, ax=axis, label=colorbar_label)
    return _save(figure, path)


def plot_city_annual_temperature(matched: pd.DataFrame, path: Path, city: str) -> Path:
    """한 도시의 NASA·KMA 연평균 T2M 시계열을 비교한다."""

    clean = matched.dropna(subset=["nasa_T2M", "kma_T2M"]).copy()
    clean["year"] = pd.to_datetime(clean["date"]).dt.year
    annual = clean.groupby("year")[["nasa_T2M", "kma_T2M"]].mean()
    figure, axis = plt.subplots(figsize=(10, 5))
    axis.plot(annual.index, annual["nasa_T2M"], label="NASA POWER", linewidth=2)
    axis.plot(annual.index, annual["kma_T2M"], label="KMA ASOS", linewidth=2)
    axis.set(title=f"{city}: Annual Mean T2M", xlabel="Year", ylabel="deg C")
    axis.legend()
    axis.grid(alpha=0.2)
    return _save(figure, path)


def plot_bland_altman_temperature(matched: pd.DataFrame, path: Path) -> Path:
    """T2M Bland–Altman plot에 평균 bias와 ±1.96 SD를 표시한다."""

    clean = matched.dropna(subset=["nasa_T2M", "kma_T2M"])
    if clean.empty:
        raise ValueError("Bland-Altman 분석에 사용할 T2M pair가 없습니다.")
    averages = (clean["nasa_T2M"] + clean["kma_T2M"]) / 2
    differences = clean["nasa_T2M"] - clean["kma_T2M"]
    mean_bias = float(differences.mean())
    sd = float(differences.std(ddof=1))
    figure, axis = plt.subplots(figsize=(9, 6))
    axis.scatter(averages, differences, s=5, alpha=0.15)
    axis.axhline(mean_bias, color="#d55e00", label=f"Bias {mean_bias:.2f}")
    axis.axhline(mean_bias + 1.96 * sd, color="#555", linestyle="--", label="Bias ± 1.96 SD")
    axis.axhline(mean_bias - 1.96 * sd, color="#555", linestyle="--")
    axis.set(title="T2M Bland-Altman Agreement", xlabel="Mean of NASA and KMA (deg C)", ylabel="NASA - KMA (deg C)")
    axis.legend()
    axis.grid(alpha=0.2)
    return _save(figure, path)


def create_validation_charts(
    matched: pd.DataFrame,
    metrics: pd.DataFrame,
    output_dir: Path,
) -> list[Path]:
    """요청된 핵심 validation 그래프와 도시별 연평균 비교를 생성한다."""

    paths = [
        plot_temperature_scatter(matched, output_dir / "nasa_kma_temperature_scatter.png"),
        plot_metric_by_city(
            metrics,
            "bias",
            output_dir / "nasa_kma_temperature_bias_by_city.png",
            "T2M Mean Bias by City (NASA - KMA)",
            "Bias (deg C)",
        ),
        plot_metric_by_city(
            metrics,
            "rmse",
            output_dir / "nasa_kma_temperature_rmse_by_city.png",
            "T2M RMSE by City",
            "RMSE (deg C)",
        ),
        plot_precipitation_validation(
            metrics, output_dir / "nasa_kma_precipitation_validation.png"
        ),
        plot_metric_heatmap(
            metrics,
            "pearson_r",
            output_dir / "nasa_kma_correlation_heatmap.png",
            "NASA-KMA Pearson Correlation",
            "Pearson r",
            cmap="RdBu_r",
        ),
        plot_metric_heatmap(
            metrics,
            "normalized_rmse",
            output_dir / "nasa_kma_rmse_heatmap.png",
            "Normalized RMSE (RMSE / |KMA mean|)",
            "Normalized RMSE",
            cmap="YlOrRd",
        ),
        plot_bland_altman_temperature(
            matched, output_dir / "nasa_kma_t2m_bland_altman.png"
        ),
    ]
    for city, group in matched.groupby("city", sort=False):
        key = str(city).casefold().replace(" ", "_")
        paths.append(
            plot_city_annual_temperature(
                group,
                output_dir / f"{key}_nasa_kma_t2m_timeseries.png",
                str(city),
            )
        )
    return paths
