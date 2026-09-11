"""정제된 NASA POWER 기온 데이터의 통계 및 장기추세 분석."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from scipy.stats import t as student_t

from src.config import SETTINGS


@dataclass(frozen=True)
class LinearTrendResult:
    """최소제곱 선형회귀의 재사용 가능한 핵심 결과."""

    n_observations: int
    start_x: float
    end_x: float
    slope_per_unit: float
    intercept: float
    trend_per_decade: float
    total_trend_change: float
    fitted_start: float
    fitted_end: float
    r_squared: float
    p_value: float


def fit_linear_trend(years: pd.Series, values: pd.Series) -> LinearTrendResult:
    """결측치를 제외하고 최소제곱 직선, R²와 양측 p-value를 계산한다."""

    valid = pd.DataFrame({"x": years, "y": values}).dropna().sort_values("x")
    if len(valid) < 2:
        raise ValueError("선형회귀에는 최소 2개 관측값이 필요합니다.")

    x = valid["x"].astype(float)
    y = valid["y"].astype(float)
    centered_x = x - x.mean()
    denominator = float((centered_x**2).sum())
    if denominator == 0:
        raise ValueError("선형회귀 설명변수의 분산이 0입니다.")

    slope = float((centered_x * (y - y.mean())).sum() / denominator)
    intercept = float(y.mean() - slope * x.mean())
    fitted = intercept + slope * x
    residual_sum_squares = float(((y - fitted) ** 2).sum())
    total_sum_squares = float(((y - y.mean()) ** 2).sum())
    r_squared = (
        1.0 - residual_sum_squares / total_sum_squares
        if total_sum_squares > 0
        else 1.0
    )

    degrees_of_freedom = len(valid) - 2
    if degrees_of_freedom <= 0:
        p_value = math.nan
    else:
        slope_standard_error = math.sqrt(
            (residual_sum_squares / degrees_of_freedom) / denominator
        )
        if slope_standard_error == 0:
            p_value = 0.0 if slope != 0 else 1.0
        else:
            statistic = slope / slope_standard_error
            p_value = float(2.0 * student_t.sf(abs(statistic), degrees_of_freedom))

    start_x = float(x.iloc[0])
    end_x = float(x.iloc[-1])
    return LinearTrendResult(
        n_observations=len(valid),
        start_x=start_x,
        end_x=end_x,
        slope_per_unit=slope,
        intercept=intercept,
        trend_per_decade=slope * 10.0,
        total_trend_change=slope * (end_x - start_x),
        fitted_start=intercept + slope * start_x,
        fitted_end=intercept + slope * end_x,
        r_squared=r_squared,
        p_value=p_value,
    )


def calculate_annual_means(
    daily_data: pd.DataFrame,
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> pd.DataFrame:
    """T2M, T2M_MAX, T2M_MIN의 연도별 산술평균을 계산한다."""

    required_columns = {"YEAR", *parameters}
    missing_columns = required_columns.difference(daily_data.columns)
    if missing_columns:
        raise ValueError(f"연간 집계에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if daily_data.empty:
        raise ValueError("연간 집계할 일별 데이터가 없습니다.")

    annual = (
        daily_data.groupby("YEAR", as_index=False, sort=True)[list(parameters)]
        .mean()
        .sort_values("YEAR")
        .reset_index(drop=True)
    )
    return annual


def save_annual_statistics(dataframe: pd.DataFrame, output_path: Path) -> None:
    """연도별 평균 기온 통계를 CSV로 저장한다."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_path, index=False, float_format="%.4f")


def add_moving_averages(
    annual_data: pd.DataFrame,
    windows: tuple[int, ...] = (5, 10),
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> pd.DataFrame:
    """연평균에 현재 연도를 포함하는 후행 이동평균 컬럼을 추가한다.

    각 창의 모든 연도가 있을 때만 값을 계산하므로 5년 이동평균의 첫 4개와
    10년 이동평균의 첫 9개 행은 결측치로 남는다.
    """

    required_columns = {"YEAR", *parameters}
    missing_columns = required_columns.difference(annual_data.columns)
    if missing_columns:
        raise ValueError(f"이동평균에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if annual_data.empty:
        raise ValueError("이동평균을 계산할 연간 데이터가 없습니다.")
    if any(not isinstance(window, int) or window < 1 for window in windows):
        raise ValueError("이동평균 창은 1 이상의 정수여야 합니다.")

    result = annual_data.sort_values("YEAR").reset_index(drop=True).copy()
    if result["YEAR"].duplicated().any():
        raise ValueError("연간 데이터에 중복 연도가 있습니다.")
    if len(result) > 1 and not result["YEAR"].diff().iloc[1:].eq(1).all():
        raise ValueError("이동평균 계산에는 누락 없는 연속 연도 자료가 필요합니다.")

    for parameter in parameters:
        for window in windows:
            result[f"{parameter}_MA{window}"] = result[parameter].rolling(
                window=window,
                min_periods=window,
            ).mean()
    return result


def calculate_linear_trends(
    annual_data: pd.DataFrame,
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> pd.DataFrame:
    """각 연평균 변수에 최소제곱 선형회귀를 적합해 추세 지표를 계산한다.

    기울기는 °C/년, 10년당 변화량과 전체 적합기간 변화량은 °C 단위다.
    """

    required_columns = {"YEAR", *parameters}
    missing_columns = required_columns.difference(annual_data.columns)
    if missing_columns:
        raise ValueError(f"선형추세에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")

    rows: list[dict[str, float | int | str]] = []
    for parameter in parameters:
        valid = annual_data.loc[:, ["YEAR", parameter]].dropna().sort_values("YEAR")
        if len(valid) < 2:
            raise ValueError(f"{parameter} 선형회귀에는 최소 2개 연도가 필요합니다.")
        trend = fit_linear_trend(valid["YEAR"], valid[parameter])
        values = valid[parameter].astype(float)
        start_year = int(trend.start_x)
        end_year = int(trend.end_x)

        rows.append(
            {
                "PARAMETER": parameter,
                "UNIT": "deg C",
                "START_YEAR": start_year,
                "END_YEAR": end_year,
                "N_YEARS": len(valid),
                "SLOPE_C_PER_YEAR": trend.slope_per_unit,
                "CHANGE_C_PER_DECADE": trend.trend_per_decade,
                "TOTAL_TREND_CHANGE_C": trend.total_trend_change,
                "FITTED_START_C": trend.fitted_start,
                "FITTED_END_C": trend.fitted_end,
                "OBSERVED_ENDPOINT_CHANGE_C": float(values.iloc[-1] - values.iloc[0]),
                "INTERCEPT_C": trend.intercept,
                "R_SQUARED": trend.r_squared,
                "P_VALUE": trend.p_value,
                "TREND_DIRECTION": (
                    "warming"
                    if trend.slope_per_unit > 0
                    else "cooling"
                    if trend.slope_per_unit < 0
                    else "flat"
                ),
            }
        )
    return pd.DataFrame(rows)


def build_annual_trend_table(
    annual_data: pd.DataFrame,
    windows: tuple[int, ...] = (5, 10),
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """연평균, 이동평균, 회귀 적합값과 회귀 요약표를 함께 만든다."""

    result = add_moving_averages(annual_data, windows, parameters)
    trend_summary = calculate_linear_trends(annual_data, parameters)
    for parameter in parameters:
        row = trend_summary.loc[trend_summary["PARAMETER"] == parameter].iloc[0]
        result[f"{parameter}_TREND"] = (
            float(row["INTERCEPT_C"]) + float(row["SLOPE_C_PER_YEAR"]) * result["YEAR"]
        )

    ordered_columns = ["YEAR"]
    for parameter in parameters:
        ordered_columns.extend(
            [parameter, *[f"{parameter}_MA{window}" for window in windows], f"{parameter}_TREND"]
        )
    return result.loc[:, ordered_columns], trend_summary


def _validated_daily_dates(daily_data: pd.DataFrame) -> pd.Series:
    """월 집계에 사용할 유효한 날짜 Series를 반환한다."""

    if "DATE" not in daily_data.columns:
        raise ValueError("월별 집계에 DATE 컬럼이 필요합니다.")
    dates = pd.to_datetime(daily_data["DATE"], errors="coerce")
    if dates.isna().any():
        raise ValueError("월별 집계 데이터에 유효하지 않은 날짜가 있습니다.")
    return dates


def calculate_monthly_climatology(
    daily_data: pd.DataFrame,
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> pd.DataFrame:
    """전체 기간 일별 값을 달력 월별로 묶어 월평균 climatology를 계산한다."""

    missing_columns = set(parameters).difference(daily_data.columns)
    if missing_columns:
        raise ValueError(f"월 climatology에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if daily_data.empty:
        raise ValueError("월 climatology를 계산할 일별 데이터가 없습니다.")

    working = daily_data.loc[:, ["DATE", *parameters]].copy()
    working["MONTH"] = _validated_daily_dates(working).dt.month
    return (
        working.groupby("MONTH", as_index=False, sort=True)[list(parameters)]
        .mean()
        .sort_values("MONTH")
        .reset_index(drop=True)
    )


def calculate_year_month_means(
    daily_data: pd.DataFrame,
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> pd.DataFrame:
    """heatmap 입력으로 사용할 연도별·월별 평균 기온을 계산한다."""

    missing_columns = set(parameters).difference(daily_data.columns)
    if missing_columns:
        raise ValueError(f"연도×월 집계에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")
    if daily_data.empty:
        raise ValueError("연도×월 평균을 계산할 일별 데이터가 없습니다.")

    working = daily_data.loc[:, ["DATE", *parameters]].copy()
    dates = _validated_daily_dates(working)
    working["YEAR"] = dates.dt.year
    working["MONTH"] = dates.dt.month
    return (
        working.groupby(["YEAR", "MONTH"], as_index=False, sort=True)[list(parameters)]
        .mean()
        .sort_values(["YEAR", "MONTH"])
        .reset_index(drop=True)
    )


def save_analysis_table(
    dataframe: pd.DataFrame,
    output_path: Path,
    float_format: str = "%.4f",
) -> None:
    """분석표를 지정한 부동소수점 형식의 CSV로 저장한다."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_path, index=False, float_format=float_format)


def save_trend_report(trend_summary: pd.DataFrame, output_path: Path) -> None:
    """회귀 추세의 핵심 결과와 계산 기준을 Markdown 보고서로 저장한다."""

    required_columns = {
        "PARAMETER",
        "START_YEAR",
        "END_YEAR",
        "SLOPE_C_PER_YEAR",
        "CHANGE_C_PER_DECADE",
        "TOTAL_TREND_CHANGE_C",
        "R_SQUARED",
    }
    missing_columns = required_columns.difference(trend_summary.columns)
    if missing_columns:
        raise ValueError(f"추세 보고서에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")

    start_year = int(trend_summary["START_YEAR"].min())
    end_year = int(trend_summary["END_YEAR"].max())
    lines = [
        f"# 서울 기온 장기추세 요약 ({start_year}-{end_year})",
        "",
        "NASA POWER 일별 자료에서 계산한 연평균 기온에 최소제곱 선형회귀를 적용했다.",
        "",
        "| 변수 | 기울기 (°C/년) | 10년당 변화 (°C/10년) | 전체기간 적합 변화 (°C) | R² |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, row in trend_summary.iterrows():
        lines.append(
            f"| {row['PARAMETER']} | {row['SLOPE_C_PER_YEAR']:+.4f} | "
            f"{row['CHANGE_C_PER_DECADE']:+.4f} | "
            f"{row['TOTAL_TREND_CHANGE_C']:+.4f} | {row['R_SQUARED']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 계산 기준",
            "",
            "- 10년당 변화량은 회귀 기울기(°C/년)에 10을 곱했다.",
            f"- 전체기간 적합 변화량은 회귀 기울기에 {end_year - start_year}년을 곱했다.",
            "- 이동평균은 현재 연도를 포함하는 후행 5년 및 10년 산술평균이다.",
            "- R²는 선형 시간추세가 연평균 변동을 설명하는 비율이다.",
            "- 이 결과는 기술적 추세이며 통계적 유의성이나 인과관계를 뜻하지 않는다.",
            "",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
