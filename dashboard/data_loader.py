"""Cached, read-only loaders for dashboard CSV and location data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from src.config import (
    LOCATIONS_PATH,
    PROCESSED_DIR,
    TABLES_DIR,
    VALIDATION_ANNUAL_BIAS_PATH,
    VALIDATION_METRICS_PATH,
    VALIDATION_MONTHLY_BIAS_PATH,
    VALIDATION_SEASONAL_BIAS_PATH,
    VALIDATION_THRESHOLD_PATH,
    validation_matched_path,
)


class DashboardDataError(RuntimeError):
    """Raised when an existing dashboard input is unavailable or invalid."""


DATA_GUIDANCE = "먼저 `python main.py --all`을 실행하여 분석 데이터를 생성하세요."


@st.cache_data(show_spinner=False)
def load_csv(
    path: str | Path,
    required_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Load one trusted project CSV and validate its basic schema."""

    csv_path = Path(path)
    if not csv_path.exists():
        raise DashboardDataError(f"데이터 파일이 없습니다: {csv_path.name}. {DATA_GUIDANCE}")
    try:
        dataframe = pd.read_csv(csv_path)
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise DashboardDataError(f"CSV를 읽을 수 없습니다: {csv_path.name} ({exc})") from exc
    if dataframe.empty:
        raise DashboardDataError(f"CSV가 비어 있습니다: {csv_path.name}. {DATA_GUIDANCE}")
    missing = sorted(set(required_columns) - set(dataframe.columns))
    if missing:
        raise DashboardDataError(
            f"{csv_path.name}에 필요한 컬럼이 없습니다: {', '.join(missing)}. {DATA_GUIDANCE}"
        )
    return dataframe


@st.cache_data(show_spinner=False)
def load_locations(path: str | Path = LOCATIONS_PATH) -> pd.DataFrame:
    """Load city names and coordinates from locations.json."""

    location_path = Path(path)
    if not location_path.exists():
        raise DashboardDataError(f"위치 설정 파일이 없습니다: {location_path}")
    try:
        payload = json.loads(location_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardDataError(f"위치 설정을 읽을 수 없습니다: {exc}") from exc

    rows = []
    for key, item in payload.items():
        try:
            rows.append(
                {
                    "key": key,
                    "city": str(item["name"]),
                    "latitude": float(item["latitude"]),
                    "longitude": float(item["longitude"]),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DashboardDataError(f"도시 좌표 설정이 올바르지 않습니다: {key}") from exc
    if not rows:
        raise DashboardDataError("locations.json에 도시가 없습니다.")
    return pd.DataFrame(rows)


def _table(filename: str, required_columns: Iterable[str]) -> pd.DataFrame:
    """Load a named output table with required columns."""

    return load_csv(TABLES_DIR / filename, tuple(required_columns))


def load_annual_climate_data() -> pd.DataFrame:
    """Load the combined annual climate table."""

    return _table(
        "city_climate_annual_1981_2025.csv",
        ("city", "YEAR", "T2M_mean_C", "precipitation_total_mm"),
    )


def load_climate_summary() -> pd.DataFrame:
    """Load city-level long-term climate summaries."""

    return _table(
        "city_climate_summary_1981_2025.csv",
        ("city", "temperature_mean", "temperature_trend_per_decade"),
    )


def load_monthly_climatology() -> pd.DataFrame:
    """Load 1981-2025 monthly climatology."""

    return _table("city_monthly_climatology_1981_2025.csv", ("city", "MONTH"))


def load_past_vs_recent() -> pd.DataFrame:
    """Load official 1981-1990 versus 2016-2025 comparisons."""

    return _table(
        "city_climate_past_vs_recent.csv",
        ("city", "variable", "past_mean", "recent_mean", "absolute_difference"),
    )


def load_statistical_trends() -> pd.DataFrame:
    """Load stage-5 trend-test results."""

    return _table(
        "city_climate_statistical_trends.csv",
        ("city", "metric", "sen_slope_per_decade", "fdr_q_value", "significant_fdr"),
    )


def load_climate_normals() -> pd.DataFrame:
    """Load 1991-2020 annual and monthly climate normals."""

    return _table(
        "city_climate_normals_1991_2020.csv",
        ("city", "period_type", "baseline_start_year", "baseline_end_year"),
    )


def load_anomalies() -> pd.DataFrame:
    """Load annual anomalies relative to the 1991-2020 normal."""

    return _table(
        "city_climate_anomalies_1981_2025.csv",
        ("city", "YEAR", "T2M_anomaly"),
    )


def load_seasonal_trends() -> pd.DataFrame:
    """Load stage-5 seasonal trend results."""

    return _table(
        "city_seasonal_climate_trends_1981_2025.csv",
        ("city", "season", "metric", "sen_slope_per_decade"),
    )


def load_consecutive_indices() -> pd.DataFrame:
    """Load annual maximum consecutive-event proxies."""

    return _table(
        "city_consecutive_climate_indices_1981_2025.csv",
        ("city", "YEAR", "max_consecutive_tmax_ge_30", "max_consecutive_precip_lt_1"),
    )


def load_change_rankings() -> pd.DataFrame:
    """Load per-metric city rankings."""

    return _table(
        "city_climate_change_rankings.csv",
        ("ranking", "rank", "city", "metric", "sen_slope_per_decade"),
    )


def load_data_quality() -> pd.DataFrame:
    """Load per-city data quality checks."""

    return _table(
        "data_quality_summary.csv",
        ("city", "start_date", "end_date", "row_count", "duplicate_dates"),
    )


def load_parameter_metadata() -> pd.DataFrame:
    """Load NASA POWER parameter descriptions and units."""

    return _table(
        "nasa_power_climate_parameter_metadata.csv",
        ("short_name", "long_name", "unit", "temporal_resolution"),
    )


def load_nationwide_station_master() -> pd.DataFrame:
    """Load the experimental nationwide ASOS eligibility master table."""

    return _table(
        "nationwide_asos_station_master.csv",
        (
            "station_id",
            "station_name",
            "latitude",
            "longitude",
            "elevation_m",
            "is_active",
            "eligibility_tier",
            "continuity_risk",
        ),
    )


def _nationwide_analysis_table(filename: str, required_columns: Iterable[str]) -> pd.DataFrame:
    """Load a Stage-11 table from the isolated nationwide namespace."""

    return load_csv(TABLES_DIR / "nationwide" / filename, tuple(required_columns))


def load_nationwide_temperature_summary() -> pd.DataFrame:
    """Load one-row-per-station Tier-A trend and validation summary."""

    return _nationwide_analysis_table(
        "nationwide_station_temperature_summary.csv",
        ("station_id", "station_name", "region", "latitude", "longitude", "elevation_m",
         "kma_tavg_sen_slope_decade", "nasa_tavg_sen_slope_decade", "tavg_bias", "tavg_rmse"),
    )


def load_nationwide_annual_temperature() -> pd.DataFrame:
    """Load station×source×metric annual temperature and moving averages."""

    return _nationwide_analysis_table(
        "nationwide_annual_temperature_1981_2025.csv",
        ("station_id", "station_name", "source", "metric", "year", "annual_mean"),
    )


def load_nationwide_temperature_anomalies() -> pd.DataFrame:
    """Load station annual anomalies relative to 1991–2020 normals."""

    return _nationwide_analysis_table(
        "nationwide_temperature_anomalies_1981_2025.csv",
        ("station_id", "station_name", "source", "metric", "year", "anomaly"),
    )


def load_nationwide_regional_summary() -> pd.DataFrame:
    """Load the non-area-weighted regional station-sample summary."""

    return _nationwide_analysis_table(
        "nationwide_regional_temperature_summary.csv",
        ("region", "station_count", "median_kma_tavg_sen_slope"),
    )


def load_nationwide_threshold_comparison() -> pd.DataFrame:
    """Load station threshold proxy mean counts and trends."""

    return _nationwide_analysis_table(
        "nationwide_temperature_threshold_comparison.csv",
        ("station_id", "threshold", "kma_mean_annual_count", "nasa_mean_annual_count"),
    )


def _spatial_table(filename: str, required_columns: Iterable[str]) -> pd.DataFrame:
    """Load a Stage-12 table from the isolated spatial namespace."""

    return load_csv(TABLES_DIR / "spatial" / filename, tuple(required_columns))


def load_spatial_station_master() -> pd.DataFrame:
    """Load one-row-per-Final-Tier-A station spatial master data."""

    return _spatial_table(
        "nationwide_spatial_station_master.csv",
        (
            "station_id", "station_name", "region_level1", "latitude", "longitude",
            "elevation_m", "kma_tavg_sen_slope", "tavg_bias", "tavg_rmse",
        ),
    )


def load_global_morans() -> pd.DataFrame:
    """Load Global Moran's I and permutation inference results."""

    return _spatial_table(
        "nationwide_global_morans_i.csv",
        ("variable", "n_stations", "weights_method", "k", "moran_i", "permutation_p"),
    )


def load_local_morans() -> pd.DataFrame:
    """Load station-level Local Moran results with BH-FDR categories."""

    return _spatial_table(
        "nationwide_local_moran_results.csv",
        (
            "station_id", "station_name", "variable", "local_i", "local_p",
            "local_fdr_q", "cluster_type_fdr", "latitude", "longitude",
        ),
    )


def load_spatial_association(kind: str) -> pd.DataFrame:
    """Load latitude, longitude, or elevation exploratory association table."""

    if kind not in {"latitude", "longitude", "elevation"}:
        raise DashboardDataError(f"지원하지 않는 공간 연관표입니다: {kind}")
    return _spatial_table(
        f"nationwide_{kind}_associations.csv",
        ("spatial_variable", "climate_metric", "pearson_r", "spearman_rho"),
    )


def load_spatial_contrast() -> pd.DataFrame:
    """Load station TMIN-minus-TMAX warming contrast."""

    return _spatial_table(
        "nationwide_tmax_tmin_warming_contrast.csv",
        ("station_id", "station_name", "tmax_slope", "tmin_slope", "tmin_minus_tmax"),
    )


def load_spatial_seasonal_summary() -> pd.DataFrame:
    """Load station×season KMA TAVG spatial summary."""

    return _spatial_table(
        "nationwide_seasonal_spatial_summary.csv",
        ("station_id", "station_name", "season", "sen_slope_per_decade"),
    )


def load_processed_city_data(city_key: str) -> pd.DataFrame:
    """Load one city's processed seven-variable daily CSV without modifying it."""

    return load_csv(
        PROCESSED_DIR / f"{city_key.lower()}_climate_daily_1981_2025.csv",
        ("DATE", "YEAR", "T2M", "T2M_MAX", "T2M_MIN"),
    )


@st.cache_data(show_spinner=False)
def load_dashboard_annual_data() -> pd.DataFrame:
    """Merge annual climate values with consecutive indices for exploration."""

    annual = load_annual_climate_data()
    consecutive = load_consecutive_indices()
    try:
        return annual.merge(consecutive, on=["city", "YEAR"], how="left", validate="one_to_one")
    except pd.errors.MergeError as exc:
        raise DashboardDataError(f"연간 자료의 도시·연도 키가 중복되었습니다: {exc}") from exc


def load_validation_metrics() -> pd.DataFrame:
    """Load overall NASA-KMA agreement metrics."""

    return load_csv(
        VALIDATION_METRICS_PATH,
        ("city", "metric", "n_pairs", "bias", "mae", "rmse", "pearson_r", "spearman_rho"),
    )


def load_monthly_validation() -> pd.DataFrame:
    """Load monthly NASA-KMA validation metrics."""

    return load_csv(
        VALIDATION_MONTHLY_BIAS_PATH,
        ("city", "month", "metric", "n_pairs", "bias", "rmse"),
    )


def load_seasonal_validation() -> pd.DataFrame:
    """Load seasonal NASA-KMA validation metrics."""

    return load_csv(
        VALIDATION_SEASONAL_BIAS_PATH,
        ("city", "season", "metric", "n_pairs", "bias", "rmse"),
    )


def load_annual_validation_bias() -> pd.DataFrame:
    """Load annual NASA-KMA bias series."""

    return load_csv(
        VALIDATION_ANNUAL_BIAS_PATH,
        ("city", "year", "metric", "n_pairs", "bias"),
    )


def load_threshold_validation() -> pd.DataFrame:
    """Load annual same-threshold NASA and KMA day counts."""

    return load_csv(
        VALIDATION_THRESHOLD_PATH,
        ("city", "year", "threshold", "nasa_count", "kma_count", "difference"),
    )


def load_validation_matched(city_key: str) -> pd.DataFrame:
    """Load one city's date-matched NASA-KMA daily pairs."""

    return load_csv(
        validation_matched_path(city_key),
        ("date", "city", "nasa_T2M", "kma_T2M", "season"),
    )
