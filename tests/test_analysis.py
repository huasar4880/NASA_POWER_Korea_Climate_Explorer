"""2단계 장기추세 분석 함수 테스트."""

from __future__ import annotations

import pandas as pd
import pytest

from src.analysis import (
    add_moving_averages,
    build_annual_trend_table,
    calculate_linear_trends,
    calculate_monthly_climatology,
    calculate_year_month_means,
)


def _linear_annual_fixture() -> pd.DataFrame:
    """기울기를 정확히 아는 연간 테스트 데이터를 만든다."""

    return pd.DataFrame(
        {
            "YEAR": range(2000, 2010),
            "T2M": range(1, 11),
            "T2M_MAX": range(6, 16),
            "T2M_MIN": range(-4, 6),
        }
    )


def test_add_moving_averages_uses_complete_trailing_windows() -> None:
    """5년·10년 후행 이동평균은 창이 찬 시점부터 계산된다."""

    annual = _linear_annual_fixture()
    result = add_moving_averages(annual)

    assert pd.isna(result.loc[3, "T2M_MA5"])
    assert result.loc[4, "T2M_MA5"] == pytest.approx(3.0)
    assert pd.isna(result.loc[8, "T2M_MA10"])
    assert result.loc[9, "T2M_MA10"] == pytest.approx(5.5)
    assert "T2M_MA5" not in annual.columns


def test_calculate_linear_trends_returns_decadal_and_total_change() -> None:
    """알려진 선형 자료에서 연간·10년당·전체기간 기울기가 정확하다."""

    annual = _linear_annual_fixture()
    summary = calculate_linear_trends(annual)
    t2m = summary.loc[summary["PARAMETER"] == "T2M"].iloc[0]

    assert t2m["SLOPE_C_PER_YEAR"] == pytest.approx(1.0)
    assert t2m["CHANGE_C_PER_DECADE"] == pytest.approx(10.0)
    assert t2m["TOTAL_TREND_CHANGE_C"] == pytest.approx(9.0)
    assert t2m["R_SQUARED"] == pytest.approx(1.0)
    assert t2m["TREND_DIRECTION"] == "warming"


def test_build_annual_trend_table_adds_fitted_values() -> None:
    """연간 확장표에 이동평균과 회귀 적합값이 함께 포함된다."""

    annual = _linear_annual_fixture()
    result, summary = build_annual_trend_table(annual)

    assert len(summary) == 3
    assert result["T2M_TREND"].tolist() == pytest.approx(annual["T2M"].tolist())
    assert {"T2M_MA5", "T2M_MA10", "T2M_TREND"}.issubset(result.columns)


def test_monthly_climatology_and_year_month_means() -> None:
    """일별 자료가 월 climatology와 연도×월 평균으로 올바르게 집계된다."""

    daily = pd.DataFrame(
        {
            "DATE": pd.to_datetime(
                ["2020-01-01", "2020-01-02", "2020-02-01", "2021-01-01", "2021-02-01"]
            ),
            "T2M": [0.0, 2.0, 10.0, 4.0, 14.0],
            "T2M_MAX": [5.0, 7.0, 15.0, 9.0, 19.0],
            "T2M_MIN": [-5.0, -3.0, 5.0, -1.0, 9.0],
        }
    )

    climatology = calculate_monthly_climatology(daily)
    year_month = calculate_year_month_means(daily)

    assert climatology["MONTH"].tolist() == [1, 2]
    assert climatology["T2M"].tolist() == pytest.approx([2.0, 12.0])
    january_2020 = year_month.loc[
        (year_month["YEAR"] == 2020) & (year_month["MONTH"] == 1), "T2M"
    ].iloc[0]
    assert january_2020 == pytest.approx(1.0)
    assert len(year_month) == 4

