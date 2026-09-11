"""다변수 연간 기후통계와 threshold 기반 분석용 proxy 계산."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pandas as pd

from src.analysis import fit_linear_trend
from src.config import CLIMATE_PARAMETERS


ANNUAL_TREND_METRICS: dict[str, tuple[str, str]] = {
    "temperature": ("T2M_mean_C", "C"),
    "temperature_max_mean": ("T2M_MAX_mean_C", "C"),
    "temperature_min_mean": ("T2M_MIN_mean_C", "C"),
    "precipitation": ("precipitation_total_mm", "mm/year"),
    "humidity": ("RH2M_mean_pct", "%"),
    "wind": ("WS10M_mean_m_s", "m/s"),
    "solar": ("solar_mean_kWh_m2_day", "kW-hr/m^2/day"),
    "hot_day_30": ("days_tmax_ge_30", "days/year"),
    "hot_day_33": ("days_tmax_ge_33", "days/year"),
    "warm_night_25": ("days_tmin_ge_25", "days/year"),
    "heavy_precip_30": ("days_precip_ge_30", "days/year"),
    "heavy_precip_50": ("days_precip_ge_50", "days/year"),
    "dry_day_lt_1": ("days_precip_lt_1", "days/year"),
}


PAST_RECENT_METRICS: dict[str, tuple[str, str, str, bool]] = {
    "T2M": ("T2M_mean_C", "C", "annual mean", False),
    "T2M_MAX": ("T2M_MAX_mean_C", "C", "annual mean", False),
    "T2M_MIN": ("T2M_MIN_mean_C", "C", "annual mean", False),
    "PRECTOTCORR": (
        "precipitation_total_mm",
        "mm/year",
        "annual total",
        True,
    ),
    "RH2M": ("RH2M_mean_pct", "%", "annual mean", False),
    "WS10M": ("WS10M_mean_m_s", "m/s", "annual mean", True),
    "ALLSKY_SFC_SW_DWN": (
        "solar_mean_kWh_m2_day",
        "kW-hr/m^2/day",
        "annual mean daily irradiation",
        True,
    ),
    "days_tmax_ge_30": ("days_tmax_ge_30", "days/year", "annual count", True),
    "days_tmax_ge_33": ("days_tmax_ge_33", "days/year", "annual count", True),
    "days_tmin_ge_25": ("days_tmin_ge_25", "days/year", "annual count", True),
    "days_precip_ge_30": ("days_precip_ge_30", "days/year", "annual count", True),
    "days_precip_ge_50": ("days_precip_ge_50", "days/year", "annual count", True),
    "days_precip_lt_1": ("days_precip_lt_1", "days/year", "annual count", True),
}


def _require_climate_columns(daily_data: pd.DataFrame) -> None:
    """다변수 분석에 필요한 날짜·연도·7개 변수 컬럼을 검증한다."""

    required = {"DATE", "YEAR", *CLIMATE_PARAMETERS}
    missing = required.difference(daily_data.columns)
    if missing:
        raise ValueError(f"기후통계에 필요한 컬럼이 없습니다: {sorted(missing)}")
    if daily_data.empty:
        raise ValueError("기후통계를 계산할 일별 데이터가 없습니다.")


def _threshold_count(
    series: pd.Series,
    predicate: Callable[[pd.Series], pd.Series],
) -> float:
    """결측치를 제외한 threshold 충족 일수를 계산한다."""

    valid = series.dropna()
    if valid.empty:
        return float("nan")
    return float(predicate(valid).sum())


def _maximum_consecutive_days(
    dates: pd.Series,
    values: pd.Series,
    predicate: Callable[[pd.Series], pd.Series],
) -> float:
    """결측·날짜 공백에서 끊어지는 최대 연속 threshold 충족 일수를 계산한다."""

    if values.notna().sum() == 0:
        return float("nan")
    maximum = 0
    current = 0
    previous_date: pd.Timestamp | None = None
    conditions = predicate(values)
    for date_value, value, meets_threshold in zip(
        pd.to_datetime(dates), values, conditions, strict=True
    ):
        is_next_day = (
            previous_date is not None
            and date_value - previous_date == pd.Timedelta(days=1)
        )
        if pd.notna(value) and bool(meets_threshold):
            current = current + 1 if is_next_day else 1
            maximum = max(maximum, current)
        else:
            current = 0
        previous_date = date_value
    return float(maximum)


def calculate_consecutive_climate_indices(daily_data: pd.DataFrame) -> pd.DataFrame:
    """연도 경계에서 sequence를 끊고 4개 최대 연속일수 proxy를 계산한다."""

    required = {"DATE", "YEAR", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"}
    missing = required.difference(daily_data.columns)
    if missing:
        raise ValueError(f"연속일수 계산 컬럼이 없습니다: {sorted(missing)}")
    working = daily_data.copy()
    working["DATE"] = pd.to_datetime(working["DATE"], errors="raise")
    working = working.sort_values("DATE").reset_index(drop=True)
    rows: list[dict[str, float | int]] = []
    specs: dict[str, tuple[str, Callable[[pd.Series], pd.Series]]] = {
        "max_consecutive_tmax_ge_30": ("T2M_MAX", lambda values: values >= 30.0),
        "max_consecutive_tmax_ge_33": ("T2M_MAX", lambda values: values >= 33.0),
        "max_consecutive_tmin_ge_25": ("T2M_MIN", lambda values: values >= 25.0),
        "max_consecutive_precip_lt_1": ("PRECTOTCORR", lambda values: values < 1.0),
    }
    for year, group in working.groupby("YEAR", sort=True):
        row: dict[str, float | int] = {"YEAR": int(year)}
        for output_column, (source_column, predicate) in specs.items():
            row[output_column] = _maximum_consecutive_days(
                group["DATE"], group[source_column], predicate
            )
        rows.append(row)
    if not rows:
        raise ValueError("연속일수 지표를 계산할 데이터가 없습니다.")
    return pd.DataFrame(rows)


def calculate_annual_climate_statistics(daily_data: pd.DataFrame) -> pd.DataFrame:
    """연간 기본 기후통계와 threshold proxy를 계산한다.

    PRECTOTCORR는 일 강수 깊이를 합산하고, 나머지 연속 변수는 평균한다.
    """

    _require_climate_columns(daily_data)
    working = daily_data.copy()
    working["DATE"] = pd.to_datetime(working["DATE"], errors="raise")
    grouped = working.groupby("YEAR", sort=True)

    annual = grouped.agg(
        T2M_mean_C=("T2M", "mean"),
        T2M_MAX_mean_C=("T2M_MAX", "mean"),
        T2M_MAX_annual_max_C=("T2M_MAX", "max"),
        T2M_MIN_mean_C=("T2M_MIN", "mean"),
        T2M_MIN_annual_min_C=("T2M_MIN", "min"),
        precipitation_total_mm=("PRECTOTCORR", lambda values: values.sum(min_count=1)),
        precipitation_max_daily_mm=("PRECTOTCORR", "max"),
        RH2M_mean_pct=("RH2M", "mean"),
        WS10M_mean_m_s=("WS10M", "mean"),
        solar_mean_kWh_m2_day=("ALLSKY_SFC_SW_DWN", "mean"),
    ).reset_index()

    annual["T2M_MA5_C"] = annual["T2M_mean_C"].rolling(5, min_periods=5).mean()
    annual["T2M_MA10_C"] = annual["T2M_mean_C"].rolling(10, min_periods=10).mean()

    threshold_specs: dict[str, tuple[str, Callable[[pd.Series], pd.Series]]] = {
        "days_tmax_ge_30": ("T2M_MAX", lambda values: values >= 30.0),
        "days_tmax_ge_33": ("T2M_MAX", lambda values: values >= 33.0),
        "days_tmin_ge_25": ("T2M_MIN", lambda values: values >= 25.0),
        "days_precip_ge_30": ("PRECTOTCORR", lambda values: values >= 30.0),
        "days_precip_ge_50": ("PRECTOTCORR", lambda values: values >= 50.0),
        "days_precip_lt_1": ("PRECTOTCORR", lambda values: values < 1.0),
    }
    for output_column, (source_column, predicate) in threshold_specs.items():
        counts = grouped[source_column].apply(
            lambda values, rule=predicate: _threshold_count(values, rule)
        )
        annual[output_column] = annual["YEAR"].map(counts)

    return annual.sort_values("YEAR").reset_index(drop=True)


def calculate_monthly_climate_climatology(daily_data: pd.DataFrame) -> pd.DataFrame:
    """전체기간의 월별 기온·강수·습도·풍속·일사 climatology를 계산한다."""

    _require_climate_columns(daily_data)
    working = daily_data.copy()
    working["DATE"] = pd.to_datetime(working["DATE"], errors="raise")
    working["YEAR"] = working["DATE"].dt.year
    working["MONTH"] = working["DATE"].dt.month

    daily_means = (
        working.groupby("MONTH", sort=True)
        .agg(
            T2M_mean_C=("T2M", "mean"),
            precipitation_daily_mean_mm=("PRECTOTCORR", "mean"),
            RH2M_mean_pct=("RH2M", "mean"),
            WS10M_mean_m_s=("WS10M", "mean"),
            solar_mean_kWh_m2_day=("ALLSKY_SFC_SW_DWN", "mean"),
        )
        .reset_index()
    )
    monthly_totals = (
        working.groupby(["YEAR", "MONTH"], sort=True)["PRECTOTCORR"]
        .sum(min_count=1)
        .groupby("MONTH")
        .mean()
        .rename("precipitation_monthly_total_mean_mm")
        .reset_index()
    )
    return daily_means.merge(monthly_totals, on="MONTH", validate="one_to_one")


def calculate_annual_metric_trends(
    annual_data: pd.DataFrame,
    metrics: Mapping[str, tuple[str, str]] = ANNUAL_TREND_METRICS,
) -> pd.DataFrame:
    """연간 기후변수와 proxy 지표에 동일한 선형추세 계산을 적용한다."""

    if "YEAR" not in annual_data.columns:
        raise ValueError("기후추세 계산에 YEAR 컬럼이 필요합니다.")
    rows: list[dict[str, float | int | str]] = []
    for metric, (column, unit) in metrics.items():
        if column not in annual_data.columns:
            raise ValueError(f"기후추세 계산 컬럼이 없습니다: {column}")
        trend = fit_linear_trend(annual_data["YEAR"], annual_data[column])
        rows.append(
            {
                "metric": metric,
                "source_column": column,
                "unit": unit,
                "n_years": trend.n_observations,
                "slope_per_year": trend.slope_per_unit,
                "trend_per_decade": trend.trend_per_decade,
                "r_squared": trend.r_squared,
                "p_value": trend.p_value,
            }
        )
    return pd.DataFrame(rows)


def calculate_past_vs_recent(
    annual_data: pd.DataFrame,
    past_period: tuple[int, int] = (1981, 1990),
    recent_period: tuple[int, int] = (2016, 2025),
    metrics: Mapping[str, tuple[str, str, str, bool]] = PAST_RECENT_METRICS,
) -> pd.DataFrame:
    """과거·최근 10년의 기후변수 및 proxy 평균 차이를 long format으로 계산한다."""

    past = annual_data.loc[annual_data["YEAR"].between(*past_period)]
    recent = annual_data.loc[annual_data["YEAR"].between(*recent_period)]
    if len(past) != 10 or len(recent) != 10:
        raise ValueError("과거 또는 최근 10년 연간 자료가 완전하지 않습니다.")

    rows: list[dict[str, float | str]] = []
    for variable, (column, unit, aggregation, allow_percent) in metrics.items():
        past_mean = float(past[column].mean())
        recent_mean = float(recent[column].mean())
        difference = recent_mean - past_mean
        percent_difference = (
            difference / past_mean * 100.0
            if allow_percent and past_mean != 0
            else float("nan")
        )
        rows.append(
            {
                "variable": variable,
                "unit": unit,
                "aggregation": aggregation,
                "past_period": f"{past_period[0]}-{past_period[1]}",
                "recent_period": f"{recent_period[0]}-{recent_period[1]}",
                "past_mean": past_mean,
                "recent_mean": recent_mean,
                "absolute_difference": difference,
                "percent_difference": percent_difference,
            }
        )
    return pd.DataFrame(rows)
