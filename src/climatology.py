"""1991-2020 climate normal, anomaly와 완전한 계절 집계."""

from __future__ import annotations

import math
from collections.abc import Iterable

import pandas as pd

from src.config import CLIMATE_NORMAL_END_YEAR, CLIMATE_NORMAL_START_YEAR


ANNUAL_NORMAL_SPECS: dict[str, tuple[str, str, str]] = {
    "T2M": ("T2M_mean_C", "T2M_normal_C", "T2M_std_C"),
    "T2M_MAX": ("T2M_MAX_mean_C", "T2M_MAX_normal_C", "T2M_MAX_std_C"),
    "T2M_MIN": ("T2M_MIN_mean_C", "T2M_MIN_normal_C", "T2M_MIN_std_C"),
    "PRECTOTCORR": (
        "precipitation_total_mm",
        "precipitation_normal_mm",
        "precipitation_std_mm",
    ),
    "RH2M": ("RH2M_mean_pct", "RH2M_normal_pct", "RH2M_std_pct"),
    "WS10M": ("WS10M_mean_m_s", "WS10M_normal_m_s", "WS10M_std_m_s"),
    "ALLSKY_SFC_SW_DWN": (
        "solar_mean_kWh_m2_day",
        "solar_normal_kWh_m2_day",
        "solar_std_kWh_m2_day",
    ),
}

SEASON_MONTHS = {
    "DJF": (12, 1, 2),
    "MAM": (3, 4, 5),
    "JJA": (6, 7, 8),
    "SON": (9, 10, 11),
}


def calculate_annual_climate_normals(
    annual_data: pd.DataFrame,
    baseline_start: int = CLIMATE_NORMAL_START_YEAR,
    baseline_end: int = CLIMATE_NORMAL_END_YEAR,
) -> pd.DataFrame:
    """도시별 1991-2020 연간 기후 normal과 표준편차를 계산한다."""

    required = {"city", "YEAR", *(spec[0] for spec in ANNUAL_NORMAL_SPECS.values())}
    missing = required.difference(annual_data.columns)
    if missing:
        raise ValueError(f"연간 climate normal 컬럼이 없습니다: {sorted(missing)}")
    baseline = annual_data.loc[annual_data["YEAR"].between(baseline_start, baseline_end)].copy()
    expected_years = baseline_end - baseline_start + 1
    rows: list[dict[str, float | int | str]] = []
    for city, city_data in baseline.groupby("city", sort=False):
        years = sorted(city_data["YEAR"].astype(int).unique())
        if years != list(range(baseline_start, baseline_end + 1)):
            raise ValueError(f"{city}의 climate normal 기준기간 연도가 완전하지 않습니다.")
        row: dict[str, float | int | str] = {
            "city": city,
            "period_type": "annual",
            "month": math.nan,
            "baseline_start_year": baseline_start,
            "baseline_end_year": baseline_end,
            "n_years": expected_years,
        }
        for _, (source, normal_column, std_column) in ANNUAL_NORMAL_SPECS.items():
            values = city_data[source].dropna()
            if len(values) != expected_years:
                raise ValueError(
                    f"{city}의 {source} 기준기간에 결측 연도가 있습니다: "
                    f"{len(values)}/{expected_years}"
                )
            row[normal_column] = float(values.mean())
            row[std_column] = float(values.std(ddof=1))
        rows.append(row)
    if not rows:
        raise ValueError("계산할 연간 climate normal 데이터가 없습니다.")
    return pd.DataFrame(rows)


def calculate_monthly_climate_normals(
    daily_data: pd.DataFrame,
    city: str,
    baseline_start: int = CLIMATE_NORMAL_START_YEAR,
    baseline_end: int = CLIMATE_NORMAL_END_YEAR,
) -> pd.DataFrame:
    """한 도시의 연도별 월 집계를 먼저 만든 뒤 1991-2020 월 normal을 계산한다."""

    required = {
        "DATE",
        "T2M",
        "T2M_MAX",
        "T2M_MIN",
        "PRECTOTCORR",
        "RH2M",
        "WS10M",
        "ALLSKY_SFC_SW_DWN",
    }
    missing = required.difference(daily_data.columns)
    if missing:
        raise ValueError(f"월 climate normal 컬럼이 없습니다: {sorted(missing)}")
    working = daily_data.copy()
    working["DATE"] = pd.to_datetime(working["DATE"], errors="raise")
    working["YEAR"] = working["DATE"].dt.year
    working["MONTH"] = working["DATE"].dt.month
    working = working.loc[working["YEAR"].between(baseline_start, baseline_end)]
    monthly_by_year = (
        working.groupby(["YEAR", "MONTH"], as_index=False, sort=True)
        .agg(
            T2M_mean_C=("T2M", "mean"),
            T2M_MAX_mean_C=("T2M_MAX", "mean"),
            T2M_MIN_mean_C=("T2M_MIN", "mean"),
            precipitation_total_mm=("PRECTOTCORR", lambda x: x.sum(min_count=1)),
            RH2M_mean_pct=("RH2M", "mean"),
            WS10M_mean_m_s=("WS10M", "mean"),
            solar_mean_kWh_m2_day=("ALLSKY_SFC_SW_DWN", "mean"),
        )
    )
    expected_years = baseline_end - baseline_start + 1
    rows: list[dict[str, float | int | str]] = []
    for month, month_data in monthly_by_year.groupby("MONTH", sort=True):
        if len(month_data) != expected_years:
            raise ValueError(f"{city}의 {month}월 기준기간 자료가 완전하지 않습니다.")
        row: dict[str, float | int | str] = {
            "city": city,
            "period_type": "monthly",
            "month": int(month),
            "baseline_start_year": baseline_start,
            "baseline_end_year": baseline_end,
            "n_years": expected_years,
        }
        for _, (source, normal_column, std_column) in ANNUAL_NORMAL_SPECS.items():
            values = month_data[source].dropna()
            if len(values) != expected_years:
                raise ValueError(f"{city} {month}월 {source} normal에 결측 연도가 있습니다.")
            row[normal_column] = float(values.mean())
            row[std_column] = float(values.std(ddof=1))
        rows.append(row)
    return pd.DataFrame(rows)


def combine_climate_normals(
    annual_normals: pd.DataFrame,
    monthly_normals: Iterable[pd.DataFrame],
) -> pd.DataFrame:
    """연간 및 월별 climate normal을 하나의 long-period 표로 결합한다."""

    frames = [annual_normals.copy(), *(frame.copy() for frame in monthly_normals)]
    return pd.concat(frames, ignore_index=True).sort_values(
        ["city", "period_type", "month"], na_position="first"
    ).reset_index(drop=True)


def calculate_climate_anomalies(
    annual_data: pd.DataFrame,
    annual_normals: pd.DataFrame,
    near_zero: float = 1e-12,
) -> pd.DataFrame:
    """연간 값에서 1991-2020 normal을 빼 absolute 및 standardized anomaly를 계산한다."""

    normals = annual_normals.loc[annual_normals["period_type"] == "annual"]
    if normals["city"].duplicated().any():
        raise ValueError("도시별 annual climate normal이 하나가 아닙니다.")
    merged = annual_data.merge(normals, on="city", how="left", validate="many_to_one")
    output = merged.loc[:, ["city", "YEAR"]].copy()
    for short_name, (source, normal_column, std_column) in ANNUAL_NORMAL_SPECS.items():
        if merged[normal_column].isna().any():
            raise ValueError(f"{short_name} anomaly 계산에 normal이 없습니다.")
        prefix = {
            "PRECTOTCORR": "precipitation",
            "ALLSKY_SFC_SW_DWN": "solar",
        }.get(short_name, short_name)
        output[f"{prefix}_value"] = merged[source]
        output[f"{prefix}_normal"] = merged[normal_column]
        output[f"{prefix}_anomaly"] = merged[source] - merged[normal_column]
        std = merged[std_column]
        safe_std = std.where(std.abs() > near_zero)
        output[f"{prefix}_standardized_anomaly"] = (
            output[f"{prefix}_anomaly"] / safe_std
        )
    return output.sort_values(["city", "YEAR"]).reset_index(drop=True)


def _season_and_year(date_value: pd.Timestamp) -> tuple[str, int]:
    """December를 다음 winter year의 DJF로 배정한다."""

    month = date_value.month
    if month in (12, 1, 2):
        return "DJF", date_value.year + (1 if month == 12 else 0)
    if month in (3, 4, 5):
        return "MAM", date_value.year
    if month in (6, 7, 8):
        return "JJA", date_value.year
    return "SON", date_value.year


def _expected_season_dates(season: str, season_year: int) -> pd.DatetimeIndex:
    """season year 정의에 따른 완전한 계절 날짜 범위를 반환한다."""

    if season == "DJF":
        february_end = pd.Timestamp(season_year, 3, 1) - pd.Timedelta(days=1)
        return pd.date_range(f"{season_year - 1}-12-01", february_end)
    bounds = {
        "MAM": (f"{season_year}-03-01", f"{season_year}-05-31"),
        "JJA": (f"{season_year}-06-01", f"{season_year}-08-31"),
        "SON": (f"{season_year}-09-01", f"{season_year}-11-30"),
    }
    start, end = bounds[season]
    return pd.date_range(start, end)


def calculate_seasonal_climate_aggregates(
    daily_data: pd.DataFrame,
    city: str,
) -> pd.DataFrame:
    """완전한 DJF/MAM/JJA/SON에 대해 물리적으로 적절한 계절 집계를 계산한다."""

    required = {"DATE", "T2M", "PRECTOTCORR", "RH2M", "WS10M", "ALLSKY_SFC_SW_DWN"}
    missing = required.difference(daily_data.columns)
    if missing:
        raise ValueError(f"계절 집계 컬럼이 없습니다: {sorted(missing)}")
    working = daily_data.copy()
    working["DATE"] = pd.to_datetime(working["DATE"], errors="raise")
    working = working.sort_values("DATE").reset_index(drop=True)
    if working["DATE"].duplicated().any():
        raise ValueError(f"{city} 계절 집계 데이터에 중복 날짜가 있습니다.")
    assigned = working["DATE"].map(_season_and_year)
    working["SEASON"] = assigned.map(lambda item: item[0])
    working["SEASON_YEAR"] = assigned.map(lambda item: item[1])

    rows: list[dict[str, float | int | str]] = []
    for (season, season_year), group in working.groupby(
        ["SEASON", "SEASON_YEAR"], sort=True
    ):
        expected_dates = _expected_season_dates(str(season), int(season_year))
        actual_dates = pd.DatetimeIndex(group["DATE"].sort_values())
        if not actual_dates.equals(expected_dates):
            continue
        expected_count = len(expected_dates)
        row: dict[str, float | int | str] = {
            "city": city,
            "SEASON": str(season),
            "SEASON_YEAR": int(season_year),
            "n_days": expected_count,
        }
        aggregations = {
            "T2M_mean_C": ("T2M", "mean"),
            "precipitation_total_mm": ("PRECTOTCORR", "sum"),
            "RH2M_mean_pct": ("RH2M", "mean"),
            "WS10M_mean_m_s": ("WS10M", "mean"),
            "solar_mean_kWh_m2_day": ("ALLSKY_SFC_SW_DWN", "mean"),
        }
        for output_column, (source_column, operation) in aggregations.items():
            values = group[source_column]
            if int(values.notna().sum()) != expected_count:
                row[output_column] = math.nan
            elif operation == "sum":
                row[output_column] = float(values.sum())
            else:
                row[output_column] = float(values.mean())
        rows.append(row)
    if not rows:
        raise ValueError(f"{city}에서 완전한 계절 자료를 만들 수 없습니다.")
    order = pd.CategoricalDtype(["DJF", "MAM", "JJA", "SON"], ordered=True)
    result = pd.DataFrame(rows)
    result["SEASON"] = result["SEASON"].astype(order)
    return result.sort_values(["SEASON", "SEASON_YEAR"]).reset_index(drop=True)
