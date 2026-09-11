"""Daily ASOS availability, missingness, gap, and annual-completeness metrics."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.kma_preprocess import KMA_FIELD_MAP, solar_mj_to_kwh


CORE_TEMPERATURE_COLUMNS = ("avg_temperature", "max_temperature", "min_temperature")


def parse_daily_availability(raw: pd.DataFrame, station_id: str) -> pd.DataFrame:
    """Parse one station's ASOS rows while preserving blank precipitation as NaN."""

    if not {"tm", "stnId"}.issubset(raw.columns):
        raise ValueError("ASOS daily raw에는 tm과 stnId가 필요합니다.")
    selected = raw.copy(deep=True)
    selected["station_id"] = selected["stnId"].astype("string").str.strip()
    selected = selected.loc[selected["station_id"].eq(str(station_id))].copy()
    selected["date"] = pd.to_datetime(selected["tm"], format="%Y-%m-%d", errors="coerce")
    if selected["date"].isna().any():
        raise ValueError("ASOS daily 날짜 형식이 YYYY-MM-DD가 아닙니다.")
    output = pd.DataFrame({"date": selected["date"], "station_id": selected["station_id"]})
    for source, target in KMA_FIELD_MAP.items():
        output[target] = pd.to_numeric(selected[source], errors="coerce") if source in selected else np.nan
    output["solar_radiation"] = solar_mj_to_kwh(output.pop("solar_radiation_mj"))
    return output.sort_values("date").reset_index(drop=True)


def expected_day_count(start_date: date, end_date: date) -> int:
    """Count inclusive calendar dates, including leap days."""

    if start_date > end_date:
        raise ValueError("start_date는 end_date보다 늦을 수 없습니다.")
    return len(pd.date_range(start_date, end_date, freq="D"))


def _missing_runs(mask: pd.Series) -> list[int]:
    """Return lengths of consecutive True runs."""

    values = mask.fillna(False).astype(bool).to_numpy()
    runs: list[int] = []
    current = 0
    for value in values:
        if value:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def longest_missing_streak(values: pd.Series) -> int:
    """Return longest consecutive NaN run, or zero when there is none."""

    runs = _missing_runs(values.isna())
    return max(runs, default=0)


def count_missing_gaps(values: pd.Series, minimum_days: int) -> int:
    """Count distinct missing runs at least `minimum_days` long."""

    if minimum_days < 1:
        raise ValueError("minimum_days는 1 이상이어야 합니다.")
    return sum(run >= minimum_days for run in _missing_runs(values.isna()))


def _calendar_frame(daily: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    """Reindex unique daily observations to the expected calendar."""

    working = daily.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    deduplicated = working.drop_duplicates("date", keep="first").set_index("date")
    return deduplicated.reindex(pd.date_range(start_date, end_date, freq="D"))


def calculate_annual_completeness(
    daily: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Calculate annual completeness requiring all three core temperatures."""

    calendar = _calendar_frame(daily, start_date, end_date)
    valid_core = calendar.loc[:, CORE_TEMPERATURE_COLUMNS].notna().all(axis=1)
    frame = pd.DataFrame({"year": calendar.index.year, "core_valid": valid_core.astype(int)})
    result = frame.groupby("year", as_index=False).agg(
        expected_days=("core_valid", "size"), valid_days_T2M=("core_valid", "sum")
    )
    result["completeness_ratio"] = result["valid_days_T2M"] / result["expected_days"]
    return result


def calculate_daily_quality(
    daily: pd.DataFrame,
    station_id: str,
    start_date: date,
    end_date: date,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Summarize core/secondary missingness without changing observed values."""

    dates = pd.to_datetime(daily["date"], errors="coerce")
    in_period = daily.loc[dates.between(pd.Timestamp(start_date), pd.Timestamp(end_date))].copy()
    in_period["date"] = pd.to_datetime(in_period["date"])
    duplicate_dates = int(in_period["date"].duplicated(keep=False).sum())
    calendar = _calendar_frame(in_period, start_date, end_date)
    expected = len(calendar)
    actual_unique_dates = int(in_period["date"].nunique())
    missing = {column: int(calendar[column].isna().sum()) for column in CORE_TEMPERATURE_COLUMNS}
    core_missing_mask = calendar.loc[:, CORE_TEMPERATURE_COLUMNS].isna().any(axis=1)
    core_runs = _missing_runs(core_missing_mask)
    annual = calculate_annual_completeness(in_period, start_date, end_date)
    actual_dates = in_period["date"].dropna()
    record: dict[str, object] = {
        "station_id": str(station_id),
        "screening_start_date": start_date.isoformat(),
        "screening_end_date": end_date.isoformat(),
        "actual_data_start_date": actual_dates.min().date().isoformat() if not actual_dates.empty else pd.NA,
        "actual_data_end_date": actual_dates.max().date().isoformat() if not actual_dates.empty else pd.NA,
        "expected_dates": expected,
        "expected_days": expected,
        "actual_rows": len(in_period),
        "duplicate_dates": duplicate_dates,
        "missing_dates": expected - actual_unique_dates,
        "avg_temp_missing": missing["avg_temperature"],
        "max_temp_missing": missing["max_temperature"],
        "min_temp_missing": missing["min_temperature"],
        "humidity_missing": int(calendar["relative_humidity"].isna().sum()),
        "wind_missing": int(calendar["wind_speed"].isna().sum()),
        "precip_blank_or_nan": int(calendar["precipitation"].isna().sum()),
        "solar_missing": int(calendar["solar_radiation"].isna().sum()),
        "avg_temp_missing_rate": missing["avg_temperature"] / expected,
        "max_temp_missing_rate": missing["max_temperature"] / expected,
        "min_temp_missing_rate": missing["min_temperature"] / expected,
        # Explicitly the missing cells across the 3 × expected-days temperature matrix.
        "core_temperature_missing_rate": sum(missing.values()) / (3 * expected),
        "longest_missing_streak_avg_temp": longest_missing_streak(calendar["avg_temperature"]),
        "longest_missing_streak_max_temp": longest_missing_streak(calendar["max_temperature"]),
        "longest_missing_streak_min_temp": longest_missing_streak(calendar["min_temperature"]),
        "longest_temperature_gap_days": max(core_runs, default=0),
        "number_of_gaps_ge_7_days": sum(run >= 7 for run in core_runs),
        "number_of_gaps_ge_30_days": sum(run >= 30 for run in core_runs),
        "number_of_gaps_ge_90_days": sum(run >= 90 for run in core_runs),
        "annual_completeness_median": float(annual["completeness_ratio"].median()),
        "years_ge_95pct_complete": int((annual["completeness_ratio"] >= 0.95).sum()),
        "years_ge_90pct_complete": int((annual["completeness_ratio"] >= 0.90).sum()),
        "years_lt_80pct_complete": int((annual["completeness_ratio"] < 0.80).sum()),
        "solar_first_valid_date": (
            calendar["solar_radiation"].first_valid_index().date().isoformat()
            if calendar["solar_radiation"].first_valid_index() is not None
            else pd.NA
        ),
        "solar_last_valid_date": (
            calendar["solar_radiation"].last_valid_index().date().isoformat()
            if calendar["solar_radiation"].last_valid_index() is not None
            else pd.NA
        ),
        "solar_missing_rate": float(calendar["solar_radiation"].isna().mean()),
    }
    return record, annual
