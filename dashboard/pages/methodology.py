"""Data source, variables, methods, quality, and interpretation page."""

from __future__ import annotations

import streamlit as st

from dashboard.components import data_table, download_table, page_header, safely_load, show_proxy_notice, show_solar_notice
from dashboard.data_loader import load_data_quality, load_locations, load_parameter_metadata


def render() -> None:
    """Render project data and methodology documentation."""

    page_header("데이터·방법론", "대시보드 값의 출처, 단위, 계산 기준과 해석 한계를 확인합니다.")
    metadata = safely_load(load_parameter_metadata)
    quality = safely_load(load_data_quality)
    locations = safely_load(load_locations)
    if metadata is None or quality is None or locations is None:
        return

    cards = st.columns(4)
    cards[0].metric("Data Source", "NASA POWER")
    cards[1].metric("분석기간", "1981~2025")
    cards[2].metric("분석 도시", f"{len(locations)}개")
    cards[3].metric("Climate Normal", "1991~2020")

    st.header("A–D. Data Source와 사용 변수")
    st.markdown(
        "NASA POWER Daily Point API의 LST(Local Solar Time) 일자료를 사용합니다. "
        "도시별 좌표 한 점의 위성관측·모델 기반 격자자료이며 특정 관측소 실측값과 같지 않을 수 있습니다."
    )
    data_table(metadata)

    st.header("E–F. Statistical Methods와 Climate Normal")
    st.markdown(
        "- **Linear Regression**: 연간 값과 연도의 최소제곱 직선 기울기, R²와 p-value\n"
        "- **Mann-Kendall**: 단조 추세를 평가하는 비모수 검정\n"
        "- **Modified Mann-Kendall**: lag-1 자기상관 flag가 있을 때 Hamed-Rao 방식 sensitivity 적용\n"
        "- **Sen's slope**: 모든 연도 쌍 기울기의 중앙값과 95% confidence interval\n"
        "- **Benjamini-Hochberg FDR**: original MK p-value의 검정 family별 다중검정 보정\n"
        "- **Climate Normal**: 1991–2020의 30년 평균\n"
        "- **Climate Anomaly**: 연간 값 − 1991–2020 normal"
    )

    st.header("G. 데이터 품질")
    data_table(quality, height=410)
    download_table(
        quality,
        filename="data_quality_summary.csv",
        label="데이터 품질표 CSV 다운로드",
        key="method_quality_download",
    )

    st.header("H. Solar Missing Data")
    show_solar_notice()

    st.header("I. 연구 해석 주의사항")
    show_proxy_notice()
    st.markdown(
        "- NASA POWER는 위성관측 및 모델 기반 격자형 자료이며 특정 기상관측소의 실제 관측값과 동일하지 않을 수 있습니다.\n"
        "- 통계적 유의성은 기후변화 원인이나 인과관계를 증명하지 않습니다.\n"
        "- 도시별 순위는 특정 지표의 변화량 비교이며 종합적인 기후위험도 순위가 아닙니다.\n"
        "- 필터로 바꾼 기간은 탐색용 표시 범위이며 공식 1981–2025 통계를 재정의하지 않습니다.\n"
        "- 결측값은 임의로 보간하거나 0으로 채우지 않습니다."
    )
