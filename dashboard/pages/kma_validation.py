"""Read-only NASA POWER × KMA ASOS agreement dashboard page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.charts import (
    create_heatmap,
    create_timeseries_chart,
    create_validation_annual_comparison,
    create_validation_scatter,
)
from dashboard.components import data_table, download_table, page_header, plotly_chart, safely_load
from dashboard.data_loader import (
    load_annual_validation_bias,
    load_monthly_validation,
    load_seasonal_validation,
    load_threshold_validation,
    load_validation_matched,
    load_validation_metrics,
)
from src.config import VALIDATION_METRICS_PATH
from src.validation import METRIC_SPECS


METRIC_LABELS = {
    "temperature": "평균기온",
    "maximum_temperature": "최고기온",
    "minimum_temperature": "최저기온",
    "precipitation": "강수량",
    "relative_humidity": "상대습도",
    "wind_speed": "풍속",
    "solar_radiation": "일사량",
}


def _metric_columns(metric: str) -> tuple[str, str, str]:
    """Return stored NASA/KMA columns and unit for a validation metric."""

    spec = METRIC_SPECS[metric]
    return spec["nasa"], spec["kma"], spec["unit"]


def render() -> None:
    """Render stored validation results without importing or calling a data API."""

    page_header(
        "NASA–KMA 검증",
        "격자형 NASA POWER와 지점 관측 KMA ASOS의 agreement와 systematic difference를 탐색합니다.",
    )
    st.info(
        "NASA POWER는 위성·모델 기반 격자자료이고 KMA ASOS는 특정 위치의 지상관측소 "
        "자료입니다. 공간대표성과 관측환경이 달라 완전히 동일할 것으로 기대하지 않으며, "
        "여기서는 정확도 판정이 아닌 agreement·bias를 함께 살펴봅니다."
    )
    if not VALIDATION_METRICS_PATH.exists():
        st.warning("KMA validation 데이터가 아직 생성되지 않았습니다.")
        st.code("python main.py --validate-kma --all")
        st.caption("Dashboard에서는 KMA API를 직접 호출하지 않습니다.")
        return

    metrics = safely_load(load_validation_metrics)
    monthly = safely_load(load_monthly_validation)
    seasonal = safely_load(load_seasonal_validation)
    annual_bias = safely_load(load_annual_validation_bias)
    thresholds = safely_load(load_threshold_validation)
    if any(value is None for value in (metrics, monthly, seasonal, annual_bias, thresholds)):
        return

    cities = metrics["city"].dropna().astype(str).unique().tolist()
    city = st.sidebar.selectbox("도시", cities, key="validation_city")
    metric_options = metrics.loc[metrics["city"].eq(city), "metric"].dropna().tolist()
    metric = st.sidebar.selectbox(
        "변수",
        metric_options,
        format_func=lambda value: METRIC_LABELS.get(value, value),
        key="validation_metric",
    )
    season = st.sidebar.selectbox(
        "계절",
        ["전체", "DJF", "MAM", "JJA", "SON"],
        key="validation_season",
    )
    matched = safely_load(lambda: load_validation_matched(city.casefold()))
    if matched is None:
        return
    matched["date"] = pd.to_datetime(matched["date"], errors="coerce")
    minimum_year = int(matched["date"].dt.year.min())
    maximum_year = int(matched["date"].dt.year.max())
    year_range = st.sidebar.slider(
        "기간",
        minimum_year,
        maximum_year,
        (minimum_year, maximum_year),
        key="validation_years",
    )
    matched = matched.loc[matched["date"].dt.year.between(*year_range)].copy()
    if season != "전체":
        matched = matched.loc[matched["season"].eq(season)].copy()

    summary = metrics.loc[metrics["city"].eq(city) & metrics["metric"].eq(metric)]
    if summary.empty:
        st.warning("선택한 도시·변수의 validation 지표가 없습니다.")
        return
    row = summary.iloc[0]
    columns = st.columns(6)
    for column, label, value, formatting in zip(
        columns,
        ["Bias", "MAE", "RMSE", "Pearson r", "Spearman ρ", "Pairs"],
        [row["bias"], row["mae"], row["rmse"], row["pearson_r"], row["spearman_rho"], row["n_pairs"]],
        ["{:.3f}", "{:.3f}", "{:.3f}", "{:.3f}", "{:.3f}", "{:,.0f}"],
    ):
        column.metric(label, formatting.format(value) if pd.notna(value) else "N/A")

    nasa_column, kma_column, unit = _metric_columns(metric)
    left, right = st.columns(2)
    with left:
        plotly_chart(
            create_validation_scatter(
                matched,
                nasa_column,
                kma_column,
                title=f"{city} {METRIC_LABELS.get(metric, metric)} daily agreement",
                unit=unit,
            ),
            key="validation_scatter",
        )
    with right:
        plotly_chart(
            create_validation_annual_comparison(
                matched,
                nasa_column,
                kma_column,
                title=f"{city} 연평균 비교",
                unit=unit,
            ),
            key="validation_annual",
        )

    monthly_filtered = monthly.loc[monthly["city"].eq(city) & monthly["metric"].eq(metric)]
    seasonal_filtered = seasonal.loc[seasonal["city"].eq(city) & seasonal["metric"].eq(metric)]
    chart_left, chart_right = st.columns(2)
    with chart_left:
        plotly_chart(
            create_timeseries_chart(
                monthly_filtered,
                "month",
                "bias",
                title="월별 Bias (NASA - KMA)",
                y_title=unit,
            ),
            key="validation_monthly_bias",
        )
    with chart_right:
        seasonal_chart = seasonal_filtered.copy()
        seasonal_chart["season_order"] = seasonal_chart["season"].map(
            {"DJF": 1, "MAM": 2, "JJA": 3, "SON": 4}
        )
        seasonal_chart = seasonal_chart.sort_values("season_order")
        plotly_chart(
            create_timeseries_chart(
                seasonal_chart,
                "season",
                "rmse",
                title="계절별 RMSE",
                y_title=unit,
            ),
            key="validation_seasonal_rmse",
        )

    correlation = metrics.loc[:, ["city", "metric", "pearson_r"]].copy()
    plotly_chart(
        create_heatmap(
            correlation,
            row_column="city",
            column_column="metric",
            value_column="pearson_r",
            title="도시×변수 Pearson correlation",
            colorbar_title="r",
        ),
        key="validation_correlation_heatmap",
    )

    st.subheader("필터 결과와 다운로드")
    data_table(summary)
    download_table(summary, filename=f"{city.lower()}_{metric}_validation_metrics.csv", key="validation_metrics_download")
    annual_filtered = annual_bias.loc[
        annual_bias["city"].eq(city)
        & annual_bias["metric"].eq(metric)
        & pd.to_numeric(annual_bias["year"], errors="coerce").between(*year_range)
    ]
    download_table(annual_filtered, filename=f"{city.lower()}_{metric}_annual_bias.csv", key="validation_annual_download")
    download_table(monthly_filtered, filename=f"{city.lower()}_{metric}_monthly_validation.csv", key="validation_monthly_download")
    download_table(seasonal_filtered, filename=f"{city.lower()}_{metric}_seasonal_validation.csv", key="validation_seasonal_download")
    threshold_filtered = thresholds.loc[
        thresholds["city"].eq(city)
        & pd.to_numeric(thresholds["year"], errors="coerce").between(*year_range)
    ]
    download_table(threshold_filtered, filename=f"{city.lower()}_threshold_validation.csv", key="validation_threshold_download")

