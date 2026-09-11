"""5단계 climate normal, anomaly와 계절 처리 테스트."""

import math

import pandas as pd
import pytest

from src.climatology import (
    calculate_annual_climate_normals,
    calculate_climate_anomalies,
    calculate_monthly_climate_normals,
    calculate_seasonal_climate_aggregates,
)


def _annual_sample(constant_t2m: bool = False) -> pd.DataFrame:
    rows = []
    for year in range(1991, 2021):
        value = 10.0 if constant_t2m else float(year - 1990)
        rows.append(
            {
                "city": "Sample",
                "YEAR": year,
                "T2M_mean_C": value,
                "T2M_MAX_mean_C": value + 5.0,
                "T2M_MIN_mean_C": value - 5.0,
                "precipitation_total_mm": value * 100.0,
                "RH2M_mean_pct": 60.0 + value / 10.0,
                "WS10M_mean_m_s": 2.0 + value / 100.0,
                "solar_mean_kWh_m2_day": 4.0 + value / 100.0,
            }
        )
    return pd.DataFrame(rows)


def test_climate_normal_and_anomalies_1991_2020() -> None:
    """30년 평균과 absolute/standardized anomaly를 정확히 계산한다."""

    annual = _annual_sample()
    normals = calculate_annual_climate_normals(annual)
    assert normals.loc[0, "n_years"] == 30
    assert normals.loc[0, "T2M_normal_C"] == pytest.approx(15.5)
    anomalies = calculate_climate_anomalies(annual, normals)
    first = anomalies.loc[anomalies["YEAR"] == 1991].iloc[0]
    assert first["T2M_anomaly"] == pytest.approx(1.0 - 15.5)
    expected_standardized = (1.0 - 15.5) / annual["T2M_mean_C"].std(ddof=1)
    assert first["T2M_standardized_anomaly"] == pytest.approx(expected_standardized)


def test_standardized_anomaly_handles_zero_baseline_std() -> None:
    """baseline 표준편차가 0이면 standardized anomaly를 NaN으로 둔다."""

    annual = _annual_sample(constant_t2m=True)
    normals = calculate_annual_climate_normals(annual)
    anomalies = calculate_climate_anomalies(annual, normals)
    assert anomalies["T2M_anomaly"].eq(0.0).all()
    assert anomalies["T2M_standardized_anomaly"].isna().all()


def test_monthly_climate_normal_uses_monthly_precipitation_totals() -> None:
    """월 normal은 연도·월 강수합계를 먼저 계산한 뒤 30년 평균한다."""

    dates = pd.date_range("1991-01-01", "2020-12-31")
    daily = pd.DataFrame(
        {
            "DATE": dates,
            "T2M": dates.month.astype(float),
            "T2M_MAX": dates.month.astype(float) + 5.0,
            "T2M_MIN": dates.month.astype(float) - 5.0,
            "PRECTOTCORR": 1.0,
            "RH2M": 70.0,
            "WS10M": 3.0,
            "ALLSKY_SFC_SW_DWN": 4.0,
        }
    )
    normals = calculate_monthly_climate_normals(daily, "Sample")
    january = normals.loc[normals["month"] == 1].iloc[0]
    assert len(normals) == 12
    assert january["T2M_normal_C"] == pytest.approx(1.0)
    assert january["precipitation_normal_mm"] == pytest.approx(31.0)
    assert january["solar_normal_kWh_m2_day"] == pytest.approx(4.0)


def test_djf_december_is_assigned_to_following_winter_year() -> None:
    """December 2019와 Jan-Feb 2020은 DJF season year 2020으로 묶인다."""

    dates = pd.date_range("2019-12-01", "2020-02-29")
    daily = pd.DataFrame(
        {
            "DATE": dates,
            "T2M": 1.0,
            "PRECTOTCORR": 1.0,
            "RH2M": 70.0,
            "WS10M": 3.0,
            "ALLSKY_SFC_SW_DWN": 4.0,
        }
    )
    seasonal = calculate_seasonal_climate_aggregates(daily, "Sample")
    assert len(seasonal) == 1
    assert seasonal.loc[0, "SEASON"] == "DJF"
    assert seasonal.loc[0, "SEASON_YEAR"] == 2020
    assert seasonal.loc[0, "n_days"] == 91
    assert seasonal.loc[0, "precipitation_total_mm"] == pytest.approx(91.0)


def test_missing_solar_makes_partial_season_nan_without_affecting_other_metrics() -> None:
    """일사 결측이 있는 완전한 날짜 계절은 일사만 NaN이고 다른 집계는 유지된다."""

    dates = pd.date_range("1983-12-01", "1985-02-28")
    solar = pd.Series(4.0, index=range(len(dates)))
    solar.loc[dates.year == 1983] = math.nan
    daily = pd.DataFrame(
        {
            "DATE": dates,
            "T2M": 2.0,
            "PRECTOTCORR": 1.0,
            "RH2M": 70.0,
            "WS10M": 3.0,
            "ALLSKY_SFC_SW_DWN": solar,
        }
    )
    seasonal = calculate_seasonal_climate_aggregates(daily, "Sample")
    djf_1984 = seasonal.loc[
        (seasonal["SEASON"] == "DJF") & (seasonal["SEASON_YEAR"] == 1984)
    ].iloc[0]
    djf_1985 = seasonal.loc[
        (seasonal["SEASON"] == "DJF") & (seasonal["SEASON_YEAR"] == 1985)
    ].iloc[0]
    assert math.isnan(djf_1984["solar_mean_kWh_m2_day"])
    assert djf_1984["T2M_mean_C"] == pytest.approx(2.0)
    assert djf_1985["solar_mean_kWh_m2_day"] == pytest.approx(4.0)
