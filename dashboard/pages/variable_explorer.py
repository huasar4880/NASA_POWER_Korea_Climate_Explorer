"""Cross-city climate-variable comparison page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.charts import (
    create_anomaly_chart,
    create_sen_slope_ci_chart,
    create_timeseries_chart,
    create_trend_bar_chart,
)
from dashboard.components import (
    data_table,
    download_table,
    page_header,
    plotly_chart,
    safely_load,
    show_proxy_notice,
    show_solar_notice,
)
from dashboard.data_loader import load_anomalies, load_dashboard_annual_data, load_statistical_trends
from dashboard.filters import filter_cities, filter_metric, filter_years
from dashboard.formatting import CITY_LABELS, METRICS, city_display_name


def render() -> None:
    """Render the variable-comparison page."""

    page_header(
        "기후변수 비교",
        "선택 기간의 탐색용 시각화와 공식 1981–2025 통계결과를 구분해 도시 간 차이를 비교합니다.",
    )
    annual_all = safely_load(load_dashboard_annual_data)
    trends_all = safely_load(load_statistical_trends)
    anomalies_all = safely_load(load_anomalies)
    if any(item is None for item in (annual_all, trends_all, anomalies_all)):
        return
    assert annual_all is not None and trends_all is not None and anomalies_all is not None

    metric_key = st.sidebar.selectbox(
        "기후변수",
        list(METRICS),
        format_func=lambda key: METRICS[key].label,
        key="variable_metric",
    )
    cities = st.sidebar.multiselect(
        "도시",
        list(CITY_LABELS),
        default=list(CITY_LABELS),
        format_func=city_display_name,
        key="variable_cities",
    )
    year_range = st.sidebar.slider(
        "화면 표시 연도",
        min_value=int(annual_all["YEAR"].min()),
        max_value=int(annual_all["YEAR"].max()),
        value=(int(annual_all["YEAR"].min()), int(annual_all["YEAR"].max())),
        key="variable_years",
    )
    if not cities:
        st.warning("한 개 이상의 도시를 선택하세요.")
        return

    spec = METRICS[metric_key]
    filtered = filter_years(filter_cities(annual_all, cities), *year_range)
    st.info(
        f"{year_range[0]}–{year_range[1]} 범위는 화면 탐색에만 적용됩니다. "
        "Sen's slope와 FDR 결과는 기존 공식 분석기간 1981–2025를 그대로 사용합니다."
    )
    if metric_key == "solar":
        show_solar_notice()
    if metric_key not in {
        "temperature", "temperature_max_mean", "temperature_min_mean",
        "precipitation", "humidity", "wind", "solar",
    }:
        show_proxy_notice()

    plotly_chart(
        create_timeseries_chart(
            filtered,
            "YEAR",
            spec.annual_column,
            title=f"{spec.label}: 도시별 시계열 ({year_range[0]}–{year_range[1]})",
            y_title=spec.unit,
            color_column="city",
        ),
        key="variable_timeseries",
    )

    mean_table = (
        filtered.groupby("city", as_index=False)[spec.annual_column]
        .mean()
        .rename(columns={spec.annual_column: "display_period_mean"})
    )
    col1, col2 = st.columns(2)
    with col1:
        plotly_chart(
            create_trend_bar_chart(
                mean_table,
                value_column="display_period_mean",
                title=f"도시별 장기 평균 (탐색 범위 {year_range[0]}–{year_range[1]})",
                y_title=spec.unit,
            ),
            key="variable_mean",
        )
    official_trend = filter_metric(filter_cities(trends_all, cities), spec.stats_metric)
    with col2:
        plotly_chart(
            create_sen_slope_ci_chart(
                official_trend,
                title=f"도시별 공식 Sen's slope (1981–2025)",
                unit=spec.unit.replace("/year", ""),
            ),
            key="variable_sen",
        )

    if spec.anomaly_prefix:
        anomaly_column = f"{spec.anomaly_prefix}_anomaly"
        if anomaly_column in anomalies_all.columns:
            anomaly = filter_years(filter_cities(anomalies_all, cities), *year_range)
            plotly_chart(
                create_anomaly_chart(
                    anomaly,
                    anomaly_column,
                    title=f"{spec.label}: 1991–2020 normal 대비 anomaly",
                    unit=spec.unit.replace("/year", ""),
                ),
                key="variable_anomaly",
            )
        else:
            st.info("선택 변수의 anomaly 컬럼이 기존 결과 파일에 없습니다.")
    else:
        st.info("Threshold·연속일수 proxy에는 기존 5단계에서 climate-normal anomaly를 정의하지 않았습니다.")

    table = filtered.loc[:, ["city", "YEAR", spec.annual_column]].copy()
    st.subheader("현재 필터의 실제 분석값")
    data_table(table)
    download_table(
        table,
        filename=f"dashboard_{metric_key}_{year_range[0]}_{year_range[1]}.csv",
        key="variable_download",
    )
