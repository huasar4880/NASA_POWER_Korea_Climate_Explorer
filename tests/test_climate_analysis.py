"""4단계 다변수 기후통계와 proxy 지표 테스트."""

from __future__ import annotations

import pandas as pd
import pytest

from src.climate_indices import (
    calculate_annual_climate_statistics,
    calculate_annual_metric_trends,
    calculate_monthly_climate_climatology,
    calculate_past_vs_recent,
)
from src.config import CLIMATE_PARAMETERS
from src.nasa_power import response_to_dataframe


def _daily_fixture() -> pd.DataFrame:
    """threshold 경계와 두 연도를 포함하는 작은 일별 표본을 만든다."""

    return pd.DataFrame(
        {
            "DATE": pd.to_datetime(
                ["2020-01-01", "2020-01-02", "2021-02-01", "2021-02-02"]
            ),
            "YEAR": [2020, 2020, 2021, 2021],
            "T2M": [10.0, 12.0, 14.0, 16.0],
            "T2M_MAX": [29.9, 30.0, 33.0, 34.0],
            "T2M_MIN": [24.9, 25.0, 25.0, 24.0],
            "PRECTOTCORR": [0.5, 1.0, 30.0, 50.0],
            "RH2M": [40.0, 60.0, 70.0, 90.0],
            "WS10M": [1.0, 3.0, 5.0, 7.0],
            "ALLSKY_SFC_SW_DWN": [2.0, 4.0, 6.0, 8.0],
        }
    )


def test_response_parses_all_seven_climate_parameters() -> None:
    """NASA JSON의 신규 4개 변수를 포함한 7개 시계열을 모두 변환한다."""

    payload = {
        "properties": {
            "parameter": {
                parameter: {"20200101": float(index)}
                for index, parameter in enumerate(CLIMATE_PARAMETERS, start=1)
            }
        }
    }

    result = response_to_dataframe(payload, CLIMATE_PARAMETERS)

    assert result.columns.tolist() == ["DATE", *CLIMATE_PARAMETERS]
    assert result.loc[0, "PRECTOTCORR"] == pytest.approx(4.0)
    assert result.loc[0, "ALLSKY_SFC_SW_DWN"] == pytest.approx(7.0)


def test_precipitation_annual_sum_and_max_daily_value() -> None:
    """mm/day 강수는 연간 합계와 최대 일강수량으로 정확히 집계된다."""

    annual = calculate_annual_climate_statistics(_daily_fixture())

    assert annual["precipitation_total_mm"].tolist() == pytest.approx([1.5, 80.0])
    assert annual["precipitation_max_daily_mm"].tolist() == pytest.approx([1.0, 50.0])


def test_annual_humidity_wind_and_solar_use_mean() -> None:
    """RH2M, WS10M과 일사량의 연간 특성은 일값 평균으로 계산된다."""

    annual = calculate_annual_climate_statistics(_daily_fixture())

    assert annual["RH2M_mean_pct"].tolist() == pytest.approx([50.0, 80.0])
    assert annual["WS10M_mean_m_s"].tolist() == pytest.approx([2.0, 6.0])
    assert annual["solar_mean_kWh_m2_day"].tolist() == pytest.approx([3.0, 7.0])


def test_threshold_indices_include_exact_boundaries() -> None:
    """30·33·25·30·50 경계값이 각각의 연간 day count에 포함된다."""

    annual = calculate_annual_climate_statistics(_daily_fixture())
    year_2020 = annual.loc[annual["YEAR"] == 2020].iloc[0]
    year_2021 = annual.loc[annual["YEAR"] == 2021].iloc[0]

    assert year_2020["days_tmax_ge_30"] == 1
    assert year_2020["days_tmax_ge_33"] == 0
    assert year_2020["days_tmin_ge_25"] == 1
    assert year_2020["days_precip_lt_1"] == 1
    assert year_2021["days_tmax_ge_33"] == 2
    assert year_2021["days_precip_ge_30"] == 2
    assert year_2021["days_precip_ge_50"] == 1


def test_monthly_climatology_uses_daily_means_and_monthly_precipitation_totals() -> None:
    """월 climatology의 연속변수 평균과 월 강수합계 평균을 구분한다."""

    climatology = calculate_monthly_climate_climatology(_daily_fixture())
    january = climatology.loc[climatology["MONTH"] == 1].iloc[0]
    february = climatology.loc[climatology["MONTH"] == 2].iloc[0]

    assert january["T2M_mean_C"] == pytest.approx(11.0)
    assert january["precipitation_daily_mean_mm"] == pytest.approx(0.75)
    assert january["precipitation_monthly_total_mean_mm"] == pytest.approx(1.5)
    assert february["solar_mean_kWh_m2_day"] == pytest.approx(7.0)
    assert february["precipitation_monthly_total_mean_mm"] == pytest.approx(80.0)


def test_metric_trend_returns_decadal_slope_r_squared_and_p_value() -> None:
    """알려진 선형 연간값에서 10년당 추세와 통계량을 계산한다."""

    annual = pd.DataFrame(
        {"YEAR": range(2000, 2010), "T2M_mean_C": [float(value) for value in range(10)]}
    )

    result = calculate_annual_metric_trends(
        annual,
        metrics={"temperature": ("T2M_mean_C", "C")},
    ).iloc[0]

    assert result["slope_per_year"] == pytest.approx(1.0)
    assert result["trend_per_decade"] == pytest.approx(10.0)
    assert result["r_squared"] == pytest.approx(1.0)
    assert result["p_value"] == pytest.approx(0.0)


def test_past_vs_recent_calculates_absolute_and_selected_percent_differences() -> None:
    """1981-1990과 2016-2025의 평균 차이 및 적절한 percent change를 계산한다."""

    years = list(range(1981, 2026))
    annual = pd.DataFrame({"YEAR": years})
    for index, column in enumerate(
        [
            "T2M_mean_C",
            "T2M_MAX_mean_C",
            "T2M_MIN_mean_C",
            "precipitation_total_mm",
            "RH2M_mean_pct",
            "WS10M_mean_m_s",
            "solar_mean_kWh_m2_day",
            "days_tmax_ge_30",
            "days_tmax_ge_33",
            "days_tmin_ge_25",
            "days_precip_ge_30",
            "days_precip_ge_50",
            "days_precip_lt_1",
        ],
        start=1,
    ):
        annual[column] = [index + (year - 1981) for year in years]

    result = calculate_past_vs_recent(annual)
    temperature = result.loc[result["variable"] == "T2M"].iloc[0]
    precipitation = result.loc[result["variable"] == "PRECTOTCORR"].iloc[0]

    assert temperature["absolute_difference"] == pytest.approx(35.0)
    assert pd.isna(temperature["percent_difference"])
    assert precipitation["absolute_difference"] == pytest.approx(35.0)
    assert precipitation["percent_difference"] == pytest.approx(35.0 / 8.5 * 100.0)

