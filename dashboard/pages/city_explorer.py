"""Single-city interactive climate exploration page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.charts import create_anomaly_chart, create_climatology_chart, create_timeseries_chart
from dashboard.components import (
    data_table,
    download_table,
    page_header,
    plotly_chart,
    safely_load,
    show_proxy_notice,
    show_solar_notice,
)
from dashboard.data_loader import (
    load_anomalies,
    load_climate_normals,
    load_climate_summary,
    load_dashboard_annual_data,
    load_monthly_climatology,
    load_statistical_trends,
)
from dashboard.filters import filter_cities, filter_metric
from dashboard.formatting import CITY_LABELS, METRICS, city_display_name, format_number


def _trend_note(trends: pd.DataFrame, metric: str) -> str:
    """Format stored long-term trend statistics for one city and metric."""

    row = filter_metric(trends, metric)
    if row.empty:
        return "통계 추세 자료가 없습니다."
    item = row.iloc[0]
    return (
        f"Linear slope: {float(item['linear_slope_per_decade']):+.3f}, "
        f"Sen's slope: {float(item['sen_slope_per_decade']):+.3f} {item['unit']}/10년, "
        f"FDR q={float(item['fdr_q_value']):.4g}, 유의={bool(item['significant_fdr'])}"
    )


def _standard_metric_tab(
    city: str,
    annual: pd.DataFrame,
    monthly: pd.DataFrame,
    trends: pd.DataFrame,
    metric_key: str,
    chart_key: str,
) -> None:
    """Render annual, monthly, and stored trend views for one standard variable."""

    spec = METRICS[metric_key]
    plotly_chart(
        create_timeseries_chart(
            annual,
            "YEAR",
            spec.annual_column,
            title=f"{city} {spec.label} 연도별 변화",
            y_title=spec.unit,
            labels={spec.annual_column: spec.label},
        ),
        key=f"city_{chart_key}_annual",
    )
    if spec.monthly_column:
        plotly_chart(
            create_climatology_chart(
                monthly,
                spec.monthly_column,
                title=f"{city} {spec.label} 월별 climatology (1981–2025)",
                y_title=spec.unit.replace("/year", ""),
            ),
            key=f"city_{chart_key}_monthly",
        )
    st.caption(_trend_note(trends, metric_key))


def render() -> None:
    """Render the city explorer page."""

    page_header("도시별 탐색", "한 도시의 장기 기후, climatology, anomaly와 극한 proxy를 살펴봅니다.")
    annual_all = safely_load(load_dashboard_annual_data)
    monthly_all = safely_load(load_monthly_climatology)
    summary_all = safely_load(load_climate_summary)
    trends_all = safely_load(load_statistical_trends)
    normals_all = safely_load(load_climate_normals)
    anomalies_all = safely_load(load_anomalies)
    if any(item is None for item in (annual_all, monthly_all, summary_all, trends_all, normals_all, anomalies_all)):
        return
    assert annual_all is not None and monthly_all is not None and summary_all is not None
    assert trends_all is not None and normals_all is not None and anomalies_all is not None

    cities = list(CITY_LABELS)
    city = st.sidebar.selectbox("도시", cities, format_func=city_display_name, key="city_explorer_city")
    annual = filter_cities(annual_all, [city]).sort_values("YEAR")
    monthly = filter_cities(monthly_all, [city]).sort_values("MONTH")
    summary = filter_cities(summary_all, [city])
    trends = filter_cities(trends_all, [city])
    normals = filter_cities(normals_all, [city])
    anomalies = filter_cities(anomalies_all, [city])
    if annual.empty or summary.empty:
        st.warning("선택한 도시의 분석 자료가 없습니다.")
        return

    summary_row = summary.iloc[0]
    temperature_trend = filter_metric(trends, "temperature")
    sen_value = temperature_trend.iloc[0]["sen_slope_per_decade"] if not temperature_trend.empty else float("nan")
    top = st.columns(4)
    top[0].metric("평균기온", format_number(annual["T2M_mean_C"].mean(), 2, " °C"))
    top[1].metric("평균 최고기온", format_number(annual["T2M_MAX_mean_C"].mean(), 2, " °C"))
    top[2].metric("평균 최저기온", format_number(annual["T2M_MIN_mean_C"].mean(), 2, " °C"))
    top[3].metric("T2M Sen slope", format_number(sen_value, 3, " °C/10년"))
    bottom = st.columns(4)
    bottom[0].metric("연평균 강수량", format_number(summary_row["precipitation_annual_mean"], 1, " mm"))
    bottom[1].metric("평균 상대습도", format_number(summary_row["humidity_mean"], 2, " %"))
    bottom[2].metric("평균 풍속", format_number(summary_row["wind_speed_mean"], 2, " m/s"))
    bottom[3].metric("평균 일사량", format_number(summary_row["solar_mean"], 2, " kW-hr/m²/day"))

    temp_tab, rain_tab, humidity_tab, wind_tab, solar_tab, extreme_tab = st.tabs(
        ["기온", "강수", "습도", "풍속", "일사", "극한지표"]
    )
    with temp_tab:
        chart_data = annual.copy()
        trend_row = temperature_trend.iloc[0] if not temperature_trend.empty else None
        if trend_row is not None and pd.notna(trend_row["linear_slope_per_decade"]):
            slope_year = float(trend_row["linear_slope_per_decade"]) / 10.0
            chart_data["T2M_linear_trend_C"] = (
                chart_data["T2M_mean_C"].mean()
                + slope_year * (chart_data["YEAR"] - chart_data["YEAR"].mean())
            )
        annual_normal = normals.loc[normals["period_type"] == "annual"]
        if not annual_normal.empty:
            chart_data["T2M_normal_C"] = float(annual_normal.iloc[0]["T2M_normal_C"])
        temperature_columns = [
            column
            for column in ("T2M_mean_C", "T2M_MA5_C", "T2M_MA10_C", "T2M_linear_trend_C", "T2M_normal_C")
            if column in chart_data.columns
        ]
        plotly_chart(
            create_timeseries_chart(
                chart_data,
                "YEAR",
                temperature_columns,
                title=f"{city} 연평균 T2M 장기추세",
                y_title="기온 (°C)",
                labels={
                    "T2M_mean_C": "연평균 T2M",
                    "T2M_MA5_C": "5년 이동평균",
                    "T2M_MA10_C": "10년 이동평균",
                    "T2M_linear_trend_C": "Linear trend",
                    "T2M_normal_C": "1991–2020 normal",
                },
            ),
            key="city_temperature_trend",
        )
        plotly_chart(
            create_timeseries_chart(
                annual,
                "YEAR",
                ["T2M_mean_C", "T2M_MAX_mean_C", "T2M_MIN_mean_C"],
                title=f"{city} T2M·T2M_MAX·T2M_MIN 연평균",
                y_title="기온 (°C)",
                labels={
                    "T2M_mean_C": "T2M",
                    "T2M_MAX_mean_C": "T2M_MAX",
                    "T2M_MIN_mean_C": "T2M_MIN",
                },
            ),
            key="city_temperature_three",
        )
        plotly_chart(
            create_anomaly_chart(
                anomalies,
                "T2M_anomaly",
                title=f"{city} T2M anomaly (1991–2020 normal 기준)",
                unit="°C",
            ),
            key="city_temperature_anomaly",
        )
        st.caption(_trend_note(trends, "temperature"))

    with rain_tab:
        _standard_metric_tab(city, annual, monthly, trends, "precipitation", "rain")
        plotly_chart(
            create_timeseries_chart(
                annual,
                "YEAR",
                ["days_precip_ge_30", "days_precip_ge_50"],
                title=f"{city} heavy precipitation threshold days",
                y_title="일수 (days/year)",
                labels={"days_precip_ge_30": ">= 30 mm/day", "days_precip_ge_50": ">= 50 mm/day"},
            ),
            key="city_rain_thresholds",
        )
        show_proxy_notice()
    with humidity_tab:
        _standard_metric_tab(city, annual, monthly, trends, "humidity", "humidity")
    with wind_tab:
        _standard_metric_tab(city, annual, monthly, trends, "wind", "wind")
    with solar_tab:
        show_solar_notice()
        _standard_metric_tab(city, annual, monthly, trends, "solar", "solar")
    with extreme_tab:
        show_proxy_notice()
        plotly_chart(
            create_timeseries_chart(
                annual,
                "YEAR",
                [
                    "days_tmax_ge_30", "days_tmax_ge_33", "days_tmin_ge_25",
                    "days_precip_ge_30", "days_precip_ge_50", "days_precip_lt_1",
                ],
                title=f"{city} 연도별 threshold climate indices",
                y_title="일수 (days/year)",
            ),
            key="city_extreme_thresholds",
        )
        plotly_chart(
            create_timeseries_chart(
                annual,
                "YEAR",
                [
                    "max_consecutive_tmax_ge_30", "max_consecutive_tmax_ge_33",
                    "max_consecutive_tmin_ge_25", "max_consecutive_precip_lt_1",
                ],
                title=f"{city} 최대 연속 event proxy",
                y_title="최대 연속 일수 (days)",
            ),
            key="city_extreme_consecutive",
        )

    st.subheader("선택 도시 연간 분석값")
    data_table(annual)
    download_table(
        annual,
        filename=f"{city.lower()}_dashboard_annual_1981_2025.csv",
        key="city_annual_download",
    )
