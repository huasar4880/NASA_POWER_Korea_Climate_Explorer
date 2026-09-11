"""Shared Streamlit presentation components and safe error handling."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.data_loader import DashboardDataError
from dashboard.filters import dataframe_to_csv_bytes


T = TypeVar("T")

PROXY_NOTICE = (
    "본 지표는 NASA POWER 격자자료를 이용한 분석용 threshold proxy이며, "
    "대한민국 기상청의 공식 폭염·열대야·극한기후 통계와 동일하지 않습니다."
)

SOLAR_NOTICE = (
    "일사량(ALLSKY_SFC_SW_DWN)은 1981–1983년 NASA fill value -999를 processed 단계에서 "
    "NaN으로 처리했습니다. 0으로 대체하지 않으며 유효 분석기간은 1984–2025년입니다."
)


def page_header(title: str, description: str) -> None:
    """Render a consistent page title and short description."""

    st.title(title)
    st.caption(description)


def safely_load(loader: Callable[[], T]) -> T | None:
    """Run a dashboard loader and show an actionable message on failure."""

    try:
        return loader()
    except (DashboardDataError, KeyError, ValueError) as exc:
        st.error(str(exc))
        return None


def plotly_chart(figure: go.Figure, *, key: str) -> None:
    """Render a Plotly figure with standard interactive controls."""

    st.plotly_chart(
        figure,
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True, "responsive": True},
        key=key,
    )


def data_table(dataframe: pd.DataFrame, *, height: int = 360) -> None:
    """Display analysis values without modifying their underlying precision."""

    st.dataframe(dataframe, width="stretch", height=height, hide_index=True)


def download_table(
    dataframe: pd.DataFrame,
    *,
    filename: str,
    label: str = "현재 표를 CSV로 다운로드",
    key: str,
) -> None:
    """Provide a CSV download that reflects the current filtered dataframe."""

    st.download_button(
        label,
        data=dataframe_to_csv_bytes(dataframe),
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def show_proxy_notice() -> None:
    """Render the required threshold-proxy interpretation warning."""

    st.warning(PROXY_NOTICE)


def show_solar_notice() -> None:
    """Render the required solar missing-data notice."""

    st.info(SOLAR_NOTICE)
