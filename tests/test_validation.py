"""Known-answer NASA-KMA matching and validation metric tests."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.validation import (
    calculate_gangneung_continuity,
    calculate_monthly_validation,
    calculate_pair_metrics,
    calculate_precipitation_contingency,
    calculate_seasonal_validation,
    calculate_threshold_validation,
    match_daily_data,
)


def _nasa_sample() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "DATE": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-07-01", "2020-07-02"]),
            "T2M": [11.0, 12.0, 28.0, 29.0],
            "T2M_MAX": [31.0, 34.0, 35.0, 29.0],
            "T2M_MIN": [5.0, 6.0, 26.0, 24.0],
            "PRECTOTCORR": [2.0, 0.0, 2.0, 0.0],
            "RH2M": [60.0, 61.0, 70.0, 71.0],
            "WS10M": [2.0, 3.0, 4.0, 5.0],
            "ALLSKY_SFC_SW_DWN": [1.0, 2.0, 3.0, 4.0],
        }
    )


def _kma_sample() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-07-01", "2020-07-02"]),
            "avg_temperature": [10.0, 10.0, 27.0, 30.0],
            "max_temperature": [30.0, 33.0, 34.0, 30.0],
            "min_temperature": [4.0, 7.0, 25.0, 25.0],
            "precipitation": [2.0, 2.0, 0.0, 0.0],
            "relative_humidity": [59.0, 62.0, 69.0, 72.0],
            "wind_speed": [2.5, 2.5, 4.5, 4.5],
            "solar_radiation": [1.1, 1.9, 3.1, 3.9],
        }
    )


def test_daily_match_and_pair_counts() -> None:
    """Date inner join creates explicit variable pair counts and seasons."""

    kma = _kma_sample()
    kma.loc[1, "solar_radiation"] = None
    matched = match_daily_data(_nasa_sample(), kma, "Seoul")
    assert len(matched) == 4
    assert matched["season"].tolist() == ["DJF", "DJF", "JJA", "JJA"]
    assert matched["n_pairs_temperature"].iloc[0] == 4
    assert matched["n_pairs_solar_radiation"].iloc[0] == 3


def test_known_bias_mae_rmse_and_correlations() -> None:
    """Known vectors produce exact Bias, MAE, RMSE, Pearson and Spearman values."""

    values = pd.DataFrame({"nasa": [11.0, 12.0], "kma": [10.0, 10.0]})
    result = calculate_pair_metrics(values, "nasa", "kma")
    assert result["bias"] == pytest.approx(1.5)
    assert result["mae"] == pytest.approx(1.5)
    assert result["rmse"] == pytest.approx(math.sqrt(2.5))
    assert pd.isna(result["pearson_r"])

    monotonic = pd.DataFrame({"nasa": [1.0, 2.0, 4.0], "kma": [1.0, 2.0, 3.0]})
    correlated = calculate_pair_metrics(monotonic, "nasa", "kma")
    assert correlated["pearson_r"] == pytest.approx(0.9819805)
    assert correlated["spearman_rho"] == pytest.approx(1.0)


def test_monthly_and_seasonal_validation() -> None:
    """Validation aggregation returns all metrics for each present month and season."""

    matched = match_daily_data(_nasa_sample(), _kma_sample(), "Seoul")
    monthly = calculate_monthly_validation(matched)
    seasonal = calculate_seasonal_validation(matched)
    assert set(monthly["month"]) == {1, 7}
    assert set(seasonal["season"]) == {"DJF", "JJA"}
    assert len(monthly) == 2 * 7
    assert len(seasonal) == 2 * 7


def test_threshold_validation_known_counts() -> None:
    """Same-threshold yearly counts use only paired non-missing values."""

    matched = match_daily_data(_nasa_sample(), _kma_sample(), "Seoul")
    result = calculate_threshold_validation(matched)
    tmax33 = result.loc[result["threshold"].eq("tmax_ge_33")].iloc[0]
    assert tmax33["nasa_count"] == 2
    assert tmax33["kma_count"] == 2
    assert tmax33["difference"] == 0
    tmin25 = result.loc[result["threshold"].eq("tmin_ge_25")].iloc[0]
    assert tmin25["nasa_count"] == 1
    assert tmin25["kma_count"] == 2


def test_precipitation_contingency_pod_far_csi() -> None:
    """A one-of-each 2x2 table yields POD=.5, FAR=.5, and CSI=1/3."""

    matched = match_daily_data(_nasa_sample(), _kma_sample(), "Seoul")
    row = calculate_precipitation_contingency(matched).iloc[0]
    assert [row["hit"], row["miss"], row["false_alarm"], row["correct_negative"]] == [1, 1, 1, 1]
    assert row["pod"] == pytest.approx(0.5)
    assert row["far"] == pytest.approx(0.5)
    assert row["csi"] == pytest.approx(1 / 3)


def test_precipitation_wet_boundary_and_missing_pairs() -> None:
    """Wet includes exactly 1 mm; either-side NaN is excluded rather than treated as dry."""

    nasa = pd.concat([_nasa_sample(), _nasa_sample().iloc[:2]], ignore_index=True)
    kma = pd.concat([_kma_sample(), _kma_sample().iloc[:2]], ignore_index=True)
    dates = pd.date_range("2020-01-01", periods=6)
    nasa["DATE"] = dates
    kma["date"] = dates
    nasa["PRECTOTCORR"] = [1.0, 0.999, 1.0, 0.0, 1.0, None]
    kma["precipitation"] = [1.0, 1.0, 0.0, 0.999, None, 1.0]
    matched = match_daily_data(nasa, kma, "Seoul")
    row = calculate_precipitation_contingency(matched).iloc[0]
    assert row["n_pairs"] == 4
    assert row["threshold_mm"] == 1.0
    assert [row["hit"], row["miss"], row["false_alarm"], row["correct_negative"]] == [1, 1, 1, 1]
    assert row["pod"] == pytest.approx(0.5)
    assert row["far"] == pytest.approx(0.5)
    assert row["csi"] == pytest.approx(1 / 3)


def test_gangneung_overlap_continuity_metrics() -> None:
    """Numeric station IDs are compared over their real overlap without splicing series."""

    raw = pd.DataFrame(
        {
            "tm": ["2020-01-01", "2020-01-01", "2020-01-02", "2020-01-02"],
            "stnId": [104, 105, 104, 105],
            "avgTa": [11.0, 10.0, 13.0, 12.0],
        }
    )
    row = calculate_gangneung_continuity(raw).iloc[0]
    assert row["n_overlap_pairs"] == 2
    assert row["mean_difference_104_minus_105_c"] == pytest.approx(1.0)
    assert row["rmse_c"] == pytest.approx(1.0)
