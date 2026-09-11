"""5단계 고급 기후통계 workflow의 표 생성과 검증 로직."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from src.climate_analysis import CityClimateResult, combine_city_climate_annual
from src.climate_indices import calculate_consecutive_climate_indices
from src.climatology import (
    calculate_annual_climate_normals,
    calculate_climate_anomalies,
    calculate_monthly_climate_normals,
    calculate_seasonal_climate_aggregates,
    combine_climate_normals,
)
from src.config import CLIMATE_VALID_RANGES, STATISTICAL_ALPHA
from src.statistical_analysis import analyze_trend_series, apply_fdr_correction


ANNUAL_STATISTICAL_METRICS: dict[str, tuple[str, str]] = {
    "temperature": ("T2M_mean_C", "C"),
    "temperature_max_mean": ("T2M_MAX_mean_C", "C"),
    "temperature_min_mean": ("T2M_MIN_mean_C", "C"),
    "precipitation": ("precipitation_total_mm", "mm/year"),
    "humidity": ("RH2M_mean_pct", "percentage points"),
    "wind": ("WS10M_mean_m_s", "m/s"),
    "solar": ("solar_mean_kWh_m2_day", "kW-hr/m^2/day"),
    "hot_day_30": ("days_tmax_ge_30", "days/year"),
    "hot_day_33": ("days_tmax_ge_33", "days/year"),
    "warm_night_25": ("days_tmin_ge_25", "days/year"),
    "heavy_precip_30": ("days_precip_ge_30", "days/year"),
    "heavy_precip_50": ("days_precip_ge_50", "days/year"),
    "dry_day_lt_1": ("days_precip_lt_1", "days/year"),
    "consecutive_hot_days_30": ("max_consecutive_tmax_ge_30", "days"),
    "consecutive_extreme_heat_33": ("max_consecutive_tmax_ge_33", "days"),
    "consecutive_warm_nights_25": ("max_consecutive_tmin_ge_25", "days"),
    "consecutive_dry_days": ("max_consecutive_precip_lt_1", "days"),
}

SEASONAL_STATISTICAL_METRICS: dict[str, tuple[str, str]] = {
    "temperature": ("T2M_mean_C", "C"),
    "precipitation": ("precipitation_total_mm", "mm/season"),
    "humidity": ("RH2M_mean_pct", "percentage points"),
    "wind": ("WS10M_mean_m_s", "m/s"),
    "solar": ("solar_mean_kWh_m2_day", "kW-hr/m^2/day"),
}

RANKING_METRICS = {
    "Temperature warming rank": "temperature",
    "T2M_MAX warming rank": "temperature_max_mean",
    "T2M_MIN warming rank": "temperature_min_mean",
    "33C threshold-day trend rank": "hot_day_33",
    "Warm-night proxy trend rank": "warm_night_25",
    "Precipitation trend rank": "precipitation",
    "Humidity trend rank": "humidity",
    "Wind trend rank": "wind",
    "Solar trend rank": "solar",
    "Consecutive dry-day trend rank": "consecutive_dry_days",
}


@dataclass(frozen=True)
class Stage5AnalysisResult:
    """5단계에서 저장·시각화할 모든 분석표."""

    consecutive_indices: pd.DataFrame
    statistical_trends: pd.DataFrame
    climate_normals: pd.DataFrame
    climate_anomalies: pd.DataFrame
    seasonal_trends: pd.DataFrame
    rankings: pd.DataFrame
    warm_night_validation: pd.DataFrame


def build_consecutive_indices(results: Iterable[CityClimateResult]) -> pd.DataFrame:
    """도시별 네 가지 연간 최대 연속일수 proxy를 결합한다."""

    frames: list[pd.DataFrame] = []
    for result in results:
        frame = calculate_consecutive_climate_indices(result.processed_data)
        frame.insert(0, "city", result.location.name)
        frames.append(frame)
    if not frames:
        raise ValueError("연속일수 지표를 만들 도시 결과가 없습니다.")
    return pd.concat(frames, ignore_index=True)


def build_statistical_trends(
    annual_data: pd.DataFrame,
    consecutive_indices: pd.DataFrame,
    alpha: float = STATISTICAL_ALPHA,
) -> pd.DataFrame:
    """8개 도시 × 17개 연간 metric의 통계 추세와 하나의 FDR family를 만든다."""

    extended = annual_data.merge(
        consecutive_indices,
        on=["city", "YEAR"],
        how="left",
        validate="one_to_one",
    )
    rows: list[dict[str, float | int | bool | str | None]] = []
    for city, city_data in extended.groupby("city", sort=False):
        for metric, (column, unit) in ANNUAL_STATISTICAL_METRICS.items():
            trend = analyze_trend_series(city_data["YEAR"], city_data[column], alpha)
            rows.append(
                {
                    "city": city,
                    "metric": metric,
                    "source_column": column,
                    "unit": unit,
                    "series_mean": float(city_data[column].mean()),
                    **trend,
                }
            )
    if not rows:
        raise ValueError("통계 추세를 계산할 연간 데이터가 없습니다.")
    trends = apply_fdr_correction(pd.DataFrame(rows), alpha=alpha)
    trends.insert(2, "fdr_family", "all annual metrics across 8 cities")
    return trends.sort_values(["metric", "city"]).reset_index(drop=True)


def build_seasonal_trends(
    results: Iterable[CityClimateResult],
    alpha: float = STATISTICAL_ALPHA,
) -> pd.DataFrame:
    """도시·계절·변수별 집계와 추세를 계산하고 변수별 32개 검정을 FDR 보정한다."""

    aggregate_frames = [
        calculate_seasonal_climate_aggregates(
            result.processed_data,
            result.location.name,
        )
        for result in results
    ]
    seasonal = pd.concat(aggregate_frames, ignore_index=True)
    rows: list[dict[str, float | int | bool | str | None]] = []
    for (city, season), group in seasonal.groupby(["city", "SEASON"], observed=True):
        for metric, (column, unit) in SEASONAL_STATISTICAL_METRICS.items():
            trend = analyze_trend_series(group["SEASON_YEAR"], group[column], alpha)
            rows.append(
                {
                    "city": city,
                    "season": str(season),
                    "metric": metric,
                    "source_column": column,
                    "unit": unit,
                    "seasonal_mean": float(group[column].mean()),
                    **trend,
                }
            )
    raw = pd.DataFrame(rows)
    corrected_frames: list[pd.DataFrame] = []
    for metric, metric_data in raw.groupby("metric", sort=False):
        corrected = apply_fdr_correction(metric_data, alpha=alpha)
        corrected.insert(3, "fdr_family", f"seasonal {metric}: 8 cities x 4 seasons")
        corrected_frames.append(corrected)
    return pd.concat(corrected_frames, ignore_index=True).sort_values(
        ["metric", "city", "season"]
    ).reset_index(drop=True)


def build_rankings(statistical_trends: pd.DataFrame) -> pd.DataFrame:
    """서로 다른 변수를 합치지 않고 10개 metric의 Sen 기울기 순위를 만든다."""

    frames: list[pd.DataFrame] = []
    keep_columns = [
        "city",
        "metric",
        "unit",
        "sen_slope_per_decade",
        "linear_slope_per_decade",
        "mk_trend",
        "mk_p_value",
        "fdr_q_value",
        "significant_fdr",
    ]
    for ranking_name, metric in RANKING_METRICS.items():
        selected = statistical_trends.loc[
            statistical_trends["metric"] == metric,
            keep_columns,
        ].copy()
        if len(selected) != 8:
            raise ValueError(f"{ranking_name}에 필요한 8개 도시 결과가 없습니다.")
        selected.insert(0, "ranking", ranking_name)
        selected.insert(
            1,
            "rank",
            selected["sen_slope_per_decade"]
            .rank(method="min", ascending=False)
            .astype(int),
        )
        frames.append(selected.sort_values(["rank", "city"]))
    return pd.concat(frames, ignore_index=True)


def build_warm_night_validation(
    results: Iterable[CityClimateResult],
    statistical_trends: pd.DataFrame,
) -> pd.DataFrame:
    """Busan·Jeju T2M_MIN 원자료, 연도별 count와 세 추세방법을 교차검증한다."""

    rows: list[dict[str, float | int | bool | str]] = []
    for result in results:
        if result.location.name not in {"Busan", "Jeju"}:
            continue
        raw = pd.read_csv(result.raw_path, dtype={"DATE": "string"})
        raw["DATE"] = pd.to_datetime(raw["DATE"], format="%Y%m%d", errors="raise")
        raw_tmin = pd.to_numeric(raw["T2M_MIN"], errors="coerce")
        fill_count = int((raw_tmin == -999.0).sum())
        minimum, maximum = CLIMATE_VALID_RANGES["T2M_MIN"]
        abnormal_count = int(
            (raw_tmin.notna() & (raw_tmin != -999.0) & ~raw_tmin.between(minimum, maximum)).sum()
        )

        daily = result.processed_data.copy()
        daily["DATE"] = pd.to_datetime(daily["DATE"], errors="raise")
        by_year = (
            daily.groupby("YEAR", as_index=False, sort=True)
            .agg(
                daily_observations=("DATE", "size"),
                valid_tmin_observations=("T2M_MIN", "count"),
                tmin_mean_C=("T2M_MIN", "mean"),
                tmin_min_C=("T2M_MIN", "min"),
                tmin_max_C=("T2M_MIN", "max"),
                recomputed_days_tmin_ge_25=("T2M_MIN", lambda x: int((x.dropna() >= 25.0).sum())),
            )
        )
        expected_counts = result.annual_data.loc[:, ["YEAR", "days_tmin_ge_25"]]
        by_year = by_year.merge(expected_counts, on="YEAR", validate="one_to_one")
        by_year["count_matches_stage4"] = (
            by_year["recomputed_days_tmin_ge_25"] == by_year["days_tmin_ge_25"]
        )
        by_year["year_complete"] = (
            by_year["daily_observations"] == by_year["valid_tmin_observations"]
        )
        by_year["year_over_year_count_change"] = by_year["days_tmin_ge_25"].diff()
        largest_index = by_year["year_over_year_count_change"].abs().idxmax()
        largest_change = float(by_year.loc[largest_index, "year_over_year_count_change"])
        largest_change_year = int(by_year.loc[largest_index, "YEAR"])

        trend = statistical_trends.loc[
            (statistical_trends["city"] == result.location.name)
            & (statistical_trends["metric"] == "warm_night_25")
        ].iloc[0]
        first_mean = float(by_year.loc[by_year["YEAR"].between(1981, 1990), "days_tmin_ge_25"].mean())
        last_mean = float(by_year.loc[by_year["YEAR"].between(2016, 2025), "days_tmin_ge_25"].mean())
        quality_ok = (
            fill_count == 0
            and abnormal_count == 0
            and bool(by_year["count_matches_stage4"].all())
            and bool(by_year["year_complete"].all())
        )
        status = (
            "no missing/fill/range/count inconsistency detected"
            if quality_ok
            else "daily completeness, fill, range, or count inconsistency detected"
        )
        for record in by_year.to_dict("records"):
            rows.append(
                {
                    "city": result.location.name,
                    "year": int(record["YEAR"]),
                    "daily_observations": int(record["daily_observations"]),
                    "valid_tmin_observations": int(record["valid_tmin_observations"]),
                    "tmin_mean_C": float(record["tmin_mean_C"]),
                    "tmin_min_C": float(record["tmin_min_C"]),
                    "tmin_max_C": float(record["tmin_max_C"]),
                    "days_tmin_ge_25": float(record["days_tmin_ge_25"]),
                    "recomputed_days_tmin_ge_25": int(record["recomputed_days_tmin_ge_25"]),
                    "count_matches_stage4": bool(record["count_matches_stage4"]),
                    "year_complete": bool(record["year_complete"]),
                    "raw_fill_value_count": fill_count,
                    "raw_out_of_range_count": abnormal_count,
                    "first_10yr_mean_days": first_mean,
                    "last_10yr_mean_days": last_mean,
                    "recent_minus_past_days": last_mean - first_mean,
                    "linear_slope_per_decade": float(trend["linear_slope_per_decade"]),
                    "mk_trend": str(trend["mk_trend"]),
                    "mk_tau": float(trend["mk_tau"]),
                    "mk_p_value": float(trend["mk_p_value"]),
                    "fdr_q_value": float(trend["fdr_q_value"]),
                    "significant_fdr": bool(trend["significant_fdr"]),
                    "sen_slope_per_decade": float(trend["sen_slope_per_decade"]),
                    "sen_ci_lower": float(trend["sen_ci_lower"]),
                    "sen_ci_upper": float(trend["sen_ci_upper"]),
                    "largest_year_over_year_count_change": largest_change,
                    "largest_change_year": largest_change_year,
                    "data_quality_discontinuity_check": status,
                }
            )
    if len(rows) != 90:
        raise ValueError(f"Busan·Jeju warm-night 검증 행 수가 다릅니다: {len(rows)}/90")
    return pd.DataFrame(rows)


def build_stage5_analysis(results: Iterable[CityClimateResult]) -> Stage5AnalysisResult:
    """기존 processed 결과만 사용해 5단계 전체 분석표를 구성한다."""

    city_results = list(results)
    if not city_results:
        raise ValueError("5단계 분석에 사용할 도시 결과가 없습니다.")
    annual = combine_city_climate_annual(city_results)
    consecutive = build_consecutive_indices(city_results)
    statistical = build_statistical_trends(annual, consecutive)
    annual_normals = calculate_annual_climate_normals(annual)
    monthly_normals = [
        calculate_monthly_climate_normals(
            result.processed_data,
            result.location.name,
        )
        for result in city_results
    ]
    normals = combine_climate_normals(annual_normals, monthly_normals)
    anomalies = calculate_climate_anomalies(annual, annual_normals)
    seasonal = build_seasonal_trends(city_results)
    rankings = build_rankings(statistical)
    validation = build_warm_night_validation(city_results, statistical)
    return Stage5AnalysisResult(
        consecutive_indices=consecutive,
        statistical_trends=statistical,
        climate_normals=normals,
        climate_anomalies=anomalies,
        seasonal_trends=seasonal,
        rankings=rankings,
        warm_night_validation=validation,
    )
