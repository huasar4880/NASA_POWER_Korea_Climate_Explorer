"""5단계 비모수 추세검정, 강건 기울기, 자기상관과 FDR 보정."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import pymannkendall as mk
from scipy.stats import theilslopes
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.multitest import multipletests

from src.analysis import fit_linear_trend
from src.config import STATISTICAL_ALPHA


@dataclass(frozen=True)
class MannKendallResult:
    """원 Mann-Kendall 검정의 핵심 결과."""

    trend: str
    p_value: float
    tau: float
    significant: bool


@dataclass(frozen=True)
class AutocorrelationResult:
    """lag-1 상관계수와 Ljung-Box 유의성 점검 결과."""

    lag1_autocorrelation: float
    ljung_box_p_value: float
    significant: bool


@dataclass(frozen=True)
class ModifiedMannKendallResult:
    """Hamed-Rao modified Mann-Kendall sensitivity 결과."""

    method: str
    status: str
    trend: str | None
    p_value: float
    significant: bool | None


@dataclass(frozen=True)
class SenSlopeResult:
    """Theil-Sen 기울기와 95% 신뢰구간."""

    slope_per_year: float
    slope_per_decade: float
    ci_lower_per_year: float
    ci_upper_per_year: float
    ci_lower_per_decade: float
    ci_upper_per_decade: float


def _clean_xy(
    years: Iterable[float],
    values: Iterable[float],
) -> pd.DataFrame:
    """연도·값을 숫자로 바꾸고 결측과 중복 연도를 제거한다."""

    dataframe = pd.DataFrame({"year": list(years), "value": list(values)})
    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce")
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = dataframe.dropna().sort_values("year").reset_index(drop=True)
    if dataframe["year"].duplicated().any():
        raise ValueError("추세분석 시계열에 중복 연도가 있습니다.")
    if len(dataframe) < 3:
        raise ValueError("통계적 추세분석에는 최소 3개 유효 연도가 필요합니다.")
    return dataframe


def mann_kendall_test(
    values: Iterable[float],
    alpha: float = STATISTICAL_ALPHA,
) -> MannKendallResult:
    """결측치를 제외하고 original Mann-Kendall 단조추세 검정을 수행한다."""

    series = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna()
    if len(series) < 3:
        raise ValueError("Mann-Kendall 검정에는 최소 3개 유효값이 필요합니다.")
    result = mk.original_test(series.to_numpy(dtype=float), alpha=alpha)
    return MannKendallResult(
        trend=str(result.trend),
        p_value=float(result.p),
        tau=float(result.Tau),
        significant=bool(result.h),
    )


def lag1_autocorrelation_test(
    values: Iterable[float],
    alpha: float = STATISTICAL_ALPHA,
) -> AutocorrelationResult:
    """lag-1 자기상관과 lag 1 Ljung-Box p-value를 계산한다."""

    series = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna()
    if len(series) < 4 or math.isclose(float(series.std(ddof=0)), 0.0, abs_tol=1e-15):
        return AutocorrelationResult(math.nan, math.nan, False)

    lag1 = float(series.autocorr(lag=1))
    ljung_box = acorr_ljungbox(series.to_numpy(dtype=float), lags=[1], return_df=True)
    p_value = float(ljung_box["lb_pvalue"].iloc[0])
    return AutocorrelationResult(
        lag1_autocorrelation=lag1,
        ljung_box_p_value=p_value,
        significant=bool(np.isfinite(p_value) and p_value < alpha),
    )


def modified_mann_kendall_test(
    values: Iterable[float],
    apply: bool,
    alpha: float = STATISTICAL_ALPHA,
) -> ModifiedMannKendallResult:
    """필요할 때만 lag 1 Hamed-Rao modified MK를 sensitivity로 계산한다."""

    if not apply:
        return ModifiedMannKendallResult(
            method="not applied",
            status="lag-1 autocorrelation not significant",
            trend=None,
            p_value=math.nan,
            significant=None,
        )

    series = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna()
    if len(series) < 4:
        return ModifiedMannKendallResult(
            method="not applied",
            status="fewer than 4 valid observations",
            trend=None,
            p_value=math.nan,
            significant=None,
        )

    result = mk.hamed_rao_modification_test(
        series.to_numpy(dtype=float),
        alpha=alpha,
        lag=1,
    )
    p_value = float(result.p)
    if not np.isfinite(p_value):
        return ModifiedMannKendallResult(
            method="Hamed-Rao modified MK (lag 1)",
            status="calculation returned non-finite p-value",
            trend=str(result.trend),
            p_value=math.nan,
            significant=None,
        )
    return ModifiedMannKendallResult(
        method="Hamed-Rao modified MK (lag 1)",
        status="applied because lag-1 Ljung-Box p-value < alpha",
        trend=str(result.trend),
        p_value=p_value,
        significant=bool(result.h),
    )


def sen_slope(
    years: Iterable[float],
    values: Iterable[float],
    confidence: float = 0.95,
) -> SenSlopeResult:
    """SciPy Theil-Sen으로 연간 기울기와 신뢰구간을 계산한다."""

    valid = _clean_xy(years, values)
    result = theilslopes(
        valid["value"].to_numpy(dtype=float),
        valid["year"].to_numpy(dtype=float),
        alpha=confidence,
        method="separate",
    )
    return SenSlopeResult(
        slope_per_year=float(result.slope),
        slope_per_decade=float(result.slope) * 10.0,
        ci_lower_per_year=float(result.low_slope),
        ci_upper_per_year=float(result.high_slope),
        ci_lower_per_decade=float(result.low_slope) * 10.0,
        ci_upper_per_decade=float(result.high_slope) * 10.0,
    )


def analyze_trend_series(
    years: Iterable[float],
    values: Iterable[float],
    alpha: float = STATISTICAL_ALPHA,
) -> dict[str, float | int | bool | str | None]:
    """한 연간 시계열의 선형·MK·자기상관·modified MK·Sen 결과를 결합한다."""

    valid = _clean_xy(years, values)
    linear = fit_linear_trend(valid["year"], valid["value"])
    mann_kendall = mann_kendall_test(valid["value"], alpha)
    autocorrelation = lag1_autocorrelation_test(valid["value"], alpha)
    modified = modified_mann_kendall_test(
        valid["value"],
        apply=autocorrelation.significant,
        alpha=alpha,
    )
    robust = sen_slope(valid["year"], valid["value"])
    return {
        "n_years": len(valid),
        "valid_start_year": int(valid["year"].min()),
        "valid_end_year": int(valid["year"].max()),
        "linear_slope_per_year": linear.slope_per_unit,
        "linear_slope_per_decade": linear.trend_per_decade,
        "linear_r_squared": linear.r_squared,
        "linear_p_value": linear.p_value,
        "mk_trend": mann_kendall.trend,
        "mk_tau": mann_kendall.tau,
        "mk_p_value": mann_kendall.p_value,
        "mk_significant": mann_kendall.significant,
        "lag1_autocorrelation": autocorrelation.lag1_autocorrelation,
        "lag1_ljung_box_p_value": autocorrelation.ljung_box_p_value,
        "autocorrelation_flag": autocorrelation.significant,
        "modified_mk_method": modified.method,
        "modified_mk_status": modified.status,
        "modified_mk_trend": modified.trend,
        "modified_mk_p_value": modified.p_value,
        "modified_mk_significant": modified.significant,
        "sen_slope_per_year": robust.slope_per_year,
        "sen_slope_per_decade": robust.slope_per_decade,
        "sen_ci_lower_per_year": robust.ci_lower_per_year,
        "sen_ci_upper_per_year": robust.ci_upper_per_year,
        "sen_ci_lower": robust.ci_lower_per_decade,
        "sen_ci_upper": robust.ci_upper_per_decade,
    }


def apply_fdr_correction(
    dataframe: pd.DataFrame,
    p_value_column: str = "mk_p_value",
    alpha: float = STATISTICAL_ALPHA,
) -> pd.DataFrame:
    """하나의 검정 family에 Benjamini-Hochberg FDR 보정을 적용한다."""

    if p_value_column not in dataframe.columns:
        raise ValueError(f"FDR 보정 p-value 컬럼이 없습니다: {p_value_column}")
    result = dataframe.copy()
    p_values = pd.to_numeric(result[p_value_column], errors="coerce")
    valid = p_values.notna()
    result["raw_p_value"] = p_values
    result["significant_raw"] = valid & (p_values < alpha)
    result["fdr_q_value"] = math.nan
    result["significant_fdr"] = False
    if valid.any():
        rejected, corrected, _, _ = multipletests(
            p_values.loc[valid].to_numpy(dtype=float),
            alpha=alpha,
            method="fdr_bh",
        )
        result.loc[valid, "fdr_q_value"] = corrected
        result.loc[valid, "significant_fdr"] = rejected
    return result
