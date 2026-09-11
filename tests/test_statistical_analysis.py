"""5단계 추세검정·강건 기울기·FDR 단위 테스트."""

import math

import numpy as np
import pandas as pd
import pytest

from src.statistical_analysis import (
    analyze_trend_series,
    apply_fdr_correction,
    mann_kendall_test,
    sen_slope,
)


def test_mann_kendall_increasing_series() -> None:
    """명확한 증가 series는 increasing으로 판정한다."""

    result = mann_kendall_test(range(1, 21))
    assert result.trend == "increasing"
    assert result.tau == pytest.approx(1.0)
    assert result.p_value < 0.05
    assert result.significant


def test_mann_kendall_decreasing_series() -> None:
    """명확한 감소 series는 decreasing으로 판정한다."""

    result = mann_kendall_test(range(20, 0, -1))
    assert result.trend == "decreasing"
    assert result.tau == pytest.approx(-1.0)
    assert result.p_value < 0.05
    assert result.significant


def test_mann_kendall_no_trend_series() -> None:
    """상수 series는 유의한 단조추세가 없다."""

    result = mann_kendall_test([5.0] * 20)
    assert result.trend == "no trend"
    assert result.tau == pytest.approx(0.0)
    assert result.p_value == pytest.approx(1.0)
    assert not result.significant


def test_sen_slope_and_confidence_interval() -> None:
    """정확한 선형 series의 Sen slope와 95% CI가 알려진 값과 같다."""

    years = list(range(2000, 2020))
    values = [2.0 * year + 1.0 for year in years]
    result = sen_slope(years, values)
    assert result.slope_per_year == pytest.approx(2.0)
    assert result.slope_per_decade == pytest.approx(20.0)
    assert result.ci_lower_per_year == pytest.approx(2.0)
    assert result.ci_upper_per_year == pytest.approx(2.0)


def test_benjamini_hochberg_fdr_correction() -> None:
    """BH 보정은 raw p-value 유의 3개 중 앞의 2개만 유지한다."""

    source = pd.DataFrame({"mk_p_value": [0.001, 0.01, 0.04, 0.2]})
    corrected = apply_fdr_correction(source)
    assert corrected["significant_raw"].tolist() == [True, True, True, False]
    assert corrected["significant_fdr"].tolist() == [True, True, False, False]
    assert corrected["fdr_q_value"].tolist() == pytest.approx(
        [0.004, 0.02, 0.0533333333, 0.2]
    )


def test_nan_values_do_not_contaminate_trend_results() -> None:
    """선행·내부 NaN은 제외되고 유효 연도만 통계에 사용된다."""

    years = range(2000, 2012)
    values = [math.nan, 1, 2, math.nan, 4, 5, 6, 7, 8, 9, 10, 11]
    result = analyze_trend_series(years, values)
    assert result["n_years"] == 10
    assert result["valid_start_year"] == 2001
    assert result["valid_end_year"] == 2011
    assert result["mk_trend"] == "increasing"
    assert math.isfinite(float(result["sen_slope_per_decade"]))


def test_modified_mk_is_reported_separately_for_autocorrelated_series() -> None:
    """lag-1 자기상관이 유의하면 original 결과를 유지한 채 Hamed-Rao를 추가한다."""

    random = np.random.default_rng(42)
    values: list[float] = []
    for index in range(60):
        previous = 0.85 * values[-1] if values else 0.0
        values.append(previous + float(random.normal(scale=0.3)) + 0.05 * index)
    result = analyze_trend_series(range(1960, 2020), values)
    assert result["autocorrelation_flag"] is True
    assert result["modified_mk_method"] == "Hamed-Rao modified MK (lag 1)"
    assert math.isfinite(float(result["modified_mk_p_value"]))
    assert result["mk_p_value"] is not None
