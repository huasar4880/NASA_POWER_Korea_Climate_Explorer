"""Extreme-event proxy and climate-anomaly exploration page."""

from __future__ import annotations

import streamlit as st

from dashboard.charts import create_anomaly_chart, create_heatmap, create_timeseries_chart
from dashboard.components import (
    data_table,
    download_table,
    page_header,
    plotly_chart,
    safely_load,
    show_proxy_notice,
)
from dashboard.data_loader import load_anomalies, load_dashboard_annual_data
from dashboard.filters import filter_cities, filter_years
from dashboard.formatting import CITY_LABELS, city_display_name


def render() -> None:
    """Render anomaly, threshold, and consecutive-event sections."""

    page_header("극한·Anomaly", "기후 평균보다 연도별 이상편차와 threshold·지속기간 proxy에 집중합니다.")
    annual_all = safely_load(load_dashboard_annual_data)
    anomalies_all = safely_load(load_anomalies)
    if annual_all is None or anomalies_all is None:
        return

    city = st.sidebar.selectbox(
        "도시", list(CITY_LABELS), format_func=city_display_name, key="extreme_city"
    )
    year_range = st.sidebar.slider(
        "연도",
        min_value=int(annual_all["YEAR"].min()),
        max_value=int(annual_all["YEAR"].max()),
        value=(int(annual_all["YEAR"].min()), int(annual_all["YEAR"].max())),
        key="extreme_years",
    )
    annual = filter_years(filter_cities(annual_all, [city]), *year_range)
    city_anomaly = filter_years(filter_cities(anomalies_all, [city]), *year_range)
    heatmap_anomaly = filter_years(anomalies_all, *year_range)
    if annual.empty:
        st.warning("선택 기간에 도시 분석자료가 없습니다.")
        return

    show_proxy_notice()

    st.header("A. Temperature Anomaly")
    plotly_chart(
        create_anomaly_chart(
            city_anomaly,
            "T2M_anomaly",
            title=f"{city} 연도별 T2M anomaly (1991–2020 normal 기준)",
            unit="°C",
        ),
        key="extreme_anomaly_bar",
    )
    plotly_chart(
        create_heatmap(
            heatmap_anomaly,
            row_column="city",
            column_column="YEAR",
            value_column="T2M_anomaly",
            title=f"도시 × 연도 T2M anomaly ({year_range[0]}–{year_range[1]})",
            colorbar_title="°C",
        ),
        key="extreme_anomaly_heatmap",
    )

    st.header("B. Heat proxy")
    plotly_chart(
        create_timeseries_chart(
            annual,
            "YEAR",
            ["days_tmax_ge_30", "days_tmax_ge_33"],
            title=f"{city} T2M_MAX threshold days",
            y_title="일수 (days/year)",
            labels={"days_tmax_ge_30": ">= 30°C", "days_tmax_ge_33": ">= 33°C"},
        ),
        key="extreme_heat",
    )

    st.header("C. Warm-night proxy")
    plotly_chart(
        create_timeseries_chart(
            annual,
            "YEAR",
            "days_tmin_ge_25",
            title=f"{city} T2M_MIN >= 25°C 일수",
            y_title="일수 (days/year)",
        ),
        key="extreme_warm_night",
    )

    st.header("D. Heavy precipitation")
    plotly_chart(
        create_timeseries_chart(
            annual,
            "YEAR",
            ["days_precip_ge_30", "days_precip_ge_50"],
            title=f"{city} PRECTOTCORR threshold days",
            y_title="일수 (days/year)",
            labels={"days_precip_ge_30": ">= 30 mm/day", "days_precip_ge_50": ">= 50 mm/day"},
        ),
        key="extreme_precipitation",
    )

    st.header("E. Dry-day proxy")
    plotly_chart(
        create_timeseries_chart(
            annual,
            "YEAR",
            "days_precip_lt_1",
            title=f"{city} PRECTOTCORR < 1 mm/day 일수",
            y_title="일수 (days/year)",
        ),
        key="extreme_dry",
    )

    st.header("F. Consecutive events")
    plotly_chart(
        create_timeseries_chart(
            annual,
            "YEAR",
            [
                "max_consecutive_tmax_ge_30",
                "max_consecutive_tmax_ge_33",
                "max_consecutive_tmin_ge_25",
                "max_consecutive_precip_lt_1",
            ],
            title=f"{city} 연도별 최대 연속 event proxy",
            y_title="최대 연속 일수 (days)",
        ),
        key="extreme_consecutive",
    )

    st.subheader("현재 필터의 극한지표 값")
    index_columns = [
        "city", "YEAR", "days_tmax_ge_30", "days_tmax_ge_33", "days_tmin_ge_25",
        "days_precip_ge_30", "days_precip_ge_50", "days_precip_lt_1",
        "max_consecutive_tmax_ge_30", "max_consecutive_tmax_ge_33",
        "max_consecutive_tmin_ge_25", "max_consecutive_precip_lt_1",
    ]
    table = annual.loc[:, index_columns]
    data_table(table)
    download_table(
        table,
        filename=f"{city.lower()}_extreme_indices_{year_range[0]}_{year_range[1]}.csv",
        key="extreme_indices_download",
    )
    download_table(
        city_anomaly,
        filename=f"{city.lower()}_temperature_anomaly_{year_range[0]}_{year_range[1]}.csv",
        label="현재 anomaly를 CSV로 다운로드",
        key="extreme_anomaly_download",
    )
