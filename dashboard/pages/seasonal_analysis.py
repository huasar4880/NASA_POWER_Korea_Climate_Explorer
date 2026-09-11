"""Seasonal climate-trend exploration page."""

from __future__ import annotations

import streamlit as st

from dashboard.charts import (
    create_heatmap,
    create_seasonal_chart,
    create_sen_slope_ci_chart,
    create_trend_bar_chart,
)
from dashboard.components import (
    data_table,
    download_table,
    page_header,
    plotly_chart,
    safely_load,
    show_solar_notice,
)
from dashboard.data_loader import load_seasonal_trends
from dashboard.filters import filter_seasonal
from dashboard.formatting import CITY_LABELS, SEASONAL_METRICS, SEASON_LABELS, city_display_name


def render() -> None:
    """Render the DJF/MAM/JJA/SON trend page."""

    page_header("계절 분석", "DJF·MAM·JJA·SON별 Sen's slope와 FDR 결과를 비교합니다.")
    seasonal = safely_load(load_seasonal_trends)
    if seasonal is None:
        return

    city = st.sidebar.selectbox(
        "도시", list(CITY_LABELS), format_func=city_display_name, key="season_city"
    )
    metric = st.sidebar.selectbox(
        "변수",
        list(SEASONAL_METRICS),
        format_func=lambda key: SEASONAL_METRICS[key].label,
        key="season_metric",
    )
    season = st.sidebar.selectbox(
        "계절", list(SEASON_LABELS), format_func=lambda key: SEASON_LABELS[key], key="season_name"
    )
    spec = SEASONAL_METRICS[metric]
    if metric == "solar":
        show_solar_notice()

    temperature = filter_seasonal(seasonal, metrics="temperature", seasons=season)
    plotly_chart(
        create_seasonal_chart(
            temperature,
            title=f"{SEASON_LABELS[season]} 도시별 T2M trend",
            unit="°C",
        ),
        key="season_temperature",
    )

    metric_all = filter_seasonal(seasonal, metrics=metric)
    plotly_chart(
        create_heatmap(
            metric_all,
            row_column="city",
            column_column="season",
            value_column="sen_slope_per_decade",
            title=f"도시 × 계절 {spec.label} Sen's slope",
            colorbar_title=f"{spec.unit}/10년",
        ),
        key="season_heatmap",
    )

    city_four = filter_seasonal(seasonal, cities=[city], metrics=metric)
    selected = filter_seasonal(seasonal, metrics=metric, seasons=season)
    col1, col2 = st.columns(2)
    with col1:
        plotly_chart(
            create_trend_bar_chart(
                city_four,
                category_column="season",
                value_column="sen_slope_per_decade",
                title=f"{city} 4계절 변화 비교: {spec.label}",
                y_title=f"{spec.unit}/10년",
            ),
            key="season_city_four",
        )
    with col2:
        plotly_chart(
            create_sen_slope_ci_chart(
                selected,
                title=f"{SEASON_LABELS[season]} 도시별 seasonal Sen's slope",
                unit=spec.unit,
            ),
            key="season_selected_ci",
        )

    exact = filter_seasonal(seasonal, cities=[city], metrics=metric, seasons=season)
    st.subheader("현재 필터의 계절 통계값")
    data_table(exact)
    download_table(
        exact,
        filename=f"dashboard_seasonal_{city.lower()}_{metric}_{season}.csv",
        key="season_download",
    )
    st.info(
        "DJF season year 기준: December 2020 + January 2021 + February 2021 = DJF 2021. "
        "첫·마지막의 불완전한 DJF는 제외하며, 원자료에 결측일이 있는 변수의 부분계절 값은 만들지 않습니다."
    )

