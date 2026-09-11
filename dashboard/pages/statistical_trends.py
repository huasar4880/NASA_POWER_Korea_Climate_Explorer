"""Focused exploration of stage-5 statistical trend results."""

from __future__ import annotations

import streamlit as st

from dashboard.charts import (
    create_heatmap,
    create_sen_slope_ci_chart,
    create_slope_comparison_scatter,
    create_trend_bar_chart,
)
from dashboard.components import data_table, download_table, page_header, plotly_chart, safely_load
from dashboard.data_loader import load_statistical_trends
from dashboard.filters import filter_statistical_trends
from dashboard.formatting import CITY_LABELS, METRICS, city_display_name, metric_label


DISPLAY_COLUMNS = [
    "city",
    "metric",
    "unit",
    "n_years",
    "valid_start_year",
    "valid_end_year",
    "linear_slope_per_decade",
    "linear_r_squared",
    "linear_p_value",
    "mk_trend",
    "mk_tau",
    "mk_p_value",
    "lag1_autocorrelation",
    "modified_mk_method",
    "modified_mk_p_value",
    "sen_slope_per_decade",
    "sen_ci_lower",
    "sen_ci_upper",
    "fdr_q_value",
    "significant_fdr",
]


def render() -> None:
    """Render statistical trend filters, charts, and values."""

    page_header("통계적 추세", "Mann-Kendall, Modified MK, Sen's slope, 선형회귀와 FDR 결과를 함께 탐색합니다.")
    trends = safely_load(load_statistical_trends)
    if trends is None:
        return

    cities = st.sidebar.multiselect(
        "도시",
        list(CITY_LABELS),
        default=list(CITY_LABELS),
        format_func=city_display_name,
        key="stats_cities",
    )
    metric_options = sorted(trends["metric"].dropna().unique(), key=metric_label)
    default_index = metric_options.index("temperature") if "temperature" in metric_options else 0
    metric = st.sidebar.selectbox(
        "Metric",
        metric_options,
        index=default_index,
        format_func=metric_label,
        key="stats_metric",
    )
    fdr = st.sidebar.radio("FDR 유의성", ["전체", "유의", "비유의"], horizontal=True, key="stats_fdr")
    directions = ["전체"] + sorted(trends["mk_trend"].dropna().unique().tolist())
    direction = st.sidebar.selectbox("Trend direction", directions, key="stats_direction")
    if not cities:
        st.warning("한 개 이상의 도시를 선택하세요.")
        return

    filtered = filter_statistical_trends(trends, cities, metric, fdr, direction)
    if filtered.empty:
        st.warning("현재 필터에 해당하는 통계 결과가 없습니다.")
        return
    unit = str(filtered.iloc[0]["unit"])

    with st.expander("통계값 짧은 설명", expanded=True):
        st.markdown(
            "- **Sen's slope**: 이상값의 영향을 상대적으로 덜 받는 강건한 장기 추세 추정치\n"
            "- **Mann-Kendall**: 시계열의 단조 증가·감소 추세를 평가하는 비모수 검정\n"
            "- **Modified Mann-Kendall**: lag-1 자기상관 flag가 있는 경우 적용한 sensitivity 분석\n"
            "- **FDR q-value**: 여러 검정에서 발생할 수 있는 false discovery를 Benjamini-Hochberg 방식으로 조정한 값\n"
            "- **R²**: 선형회귀가 관측 변동을 설명하는 비율이며 인과관계를 뜻하지 않음"
        )

    col1, col2 = st.columns(2)
    with col1:
        plotly_chart(
            create_sen_slope_ci_chart(filtered, title=f"{metric_label(metric)} Sen's slope와 95% CI", unit=unit),
            key="stats_sen_ci",
        )
    with col2:
        plotly_chart(
            create_trend_bar_chart(
                filtered,
                value_column="mk_tau",
                title=f"{metric_label(metric)} Mann-Kendall tau",
                y_title="Kendall tau",
            ),
            key="stats_tau",
        )

    significance = filtered.loc[:, ["city", "metric", "significant_fdr"]].copy()
    significance["metric_label"] = significance["metric"].map(metric_label)
    significance["FDR_significant"] = significance["significant_fdr"].astype(str).str.lower().eq("true").astype(int)
    col3, col4 = st.columns(2)
    with col3:
        plotly_chart(
            create_heatmap(
                significance,
                row_column="city",
                column_column="metric_label",
                value_column="FDR_significant",
                title="FDR significance heatmap",
                colorbar_title="유의",
                colorscale="Blues",
                zmid=None,
            ),
            key="stats_fdr_heatmap",
        )
    with col4:
        plotly_chart(
            create_slope_comparison_scatter(filtered, title="Linear slope vs Sen's slope"),
            key="stats_slope_scatter",
        )

    st.subheader("통계 분석값")
    available = [column for column in DISPLAY_COLUMNS if column in filtered.columns]
    table = filtered.loc[:, available].copy()
    data_table(table, height=430)
    download_table(
        table,
        filename=f"dashboard_statistical_trends_{metric}.csv",
        key="stats_download",
    )

