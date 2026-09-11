"""Final Tier-A station의 전국 기온 통계, 검증과 요약표 계산."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats

from src.statistical_analysis import analyze_trend_series, apply_fdr_correction
from src.validation import calculate_pair_metrics
from src.nationwide.tier_a_pipeline import (
    ANALYSIS_END,
    ANALYSIS_START,
    EXPECTED_DAYS,
    NORMAL_END_YEAR,
    NORMAL_START_YEAR,
    PreparedStation,
)


METRICS = ("TAVG", "TMAX", "TMIN")
SOURCE_DAILY_COLUMNS = {
    "KMA": {"TAVG": "avg_temperature", "TMAX": "max_temperature", "TMIN": "min_temperature"},
    "NASA": {"TAVG": "T2M", "TMAX": "T2M_MAX", "TMIN": "T2M_MIN"},
}
MATCHED_COLUMNS = {
    "TAVG": ("nasa_T2M", "kma_T2M"),
    "TMAX": ("nasa_T2M_MAX", "kma_TMAX"),
    "TMIN": ("nasa_T2M_MIN", "kma_TMIN"),
}
THRESHOLDS = {
    "TMAX_GE_30": ("nasa_T2M_MAX", "kma_TMAX", 30.0),
    "TMAX_GE_33": ("nasa_T2M_MAX", "kma_TMAX", 33.0),
    "TMIN_GE_25": ("nasa_T2M_MIN", "kma_TMIN", 25.0),
}


@dataclass(frozen=True)
class NationwideAnalysisProducts:
    """전국 분석에서 저장할 모든 계산표."""

    annual: pd.DataFrame
    trends: pd.DataFrame
    normals: pd.DataFrame
    anomalies: pd.DataFrame
    seasonal: pd.DataFrame
    thresholds_annual: pd.DataFrame
    threshold_comparison: pd.DataFrame
    validation: pd.DataFrame
    summary: pd.DataFrame
    rankings: pd.DataFrame
    regional: pd.DataFrame
    elevation: pd.DataFrame
    spatial_associations: pd.DataFrame
    trend_consistency: pd.DataFrame


def _station_metadata(stations: pd.DataFrame) -> pd.DataFrame:
    """결과표에 반복 연결할 품질·위치 metadata를 표준화한다."""

    metadata = stations.copy()
    metadata["station_id"] = metadata["station_id"].astype(str)
    metadata["region"] = metadata["region_level1"].fillna("UNSPECIFIED").astype(str)
    return metadata.loc[:, [
        "station_id", "station_name", "region", "region_level1", "region_level2",
        "latitude", "longitude", "elevation_m", "temperature_missing_rate",
        "annual_completeness", "continuity_risk",
    ]]


def calculate_station_annual_temperature(
    prepared: Iterable[PreparedStation], stations: pd.DataFrame
) -> pd.DataFrame:
    """station·source·metric별 연평균과 5/10년 후행 이동평균을 계산한다."""

    metadata = _station_metadata(stations)
    rows: list[dict[str, object]] = []
    for item in prepared:
        for source, dataframe in (("KMA", item.kma), ("NASA", item.nasa)):
            daily = dataframe.copy()
            daily["date"] = pd.to_datetime(daily["date"], errors="raise")
            daily["year"] = daily["date"].dt.year
            for metric, column in SOURCE_DAILY_COLUMNS[source].items():
                grouped = daily.groupby("year", sort=True)[column]
                for year, values in grouped:
                    rows.append({
                        "station_id": item.station_id,
                        "source": source,
                        "metric": metric,
                        "year": int(year),
                        "annual_mean": float(values.mean()) if values.notna().any() else math.nan,
                        "valid_days": int(values.notna().sum()),
                    })
    annual = pd.DataFrame(rows)
    annual = annual.merge(metadata, on="station_id", how="left", validate="many_to_one")
    annual = annual.sort_values(["station_id", "source", "metric", "year"]).reset_index(drop=True)
    annual["moving_average_5yr"] = annual.groupby(
        ["station_id", "source", "metric"], sort=False
    )["annual_mean"].transform(lambda values: values.rolling(5, min_periods=5).mean())
    annual["moving_average_10yr"] = annual.groupby(
        ["station_id", "source", "metric"], sort=False
    )["annual_mean"].transform(lambda values: values.rolling(10, min_periods=10).mean())
    return annual


def calculate_station_trends(
    annual: pd.DataFrame, stations: pd.DataFrame, alpha: float = 0.05
) -> pd.DataFrame:
    """station×source×metric의 linear/MK/modified-MK/Sen 통계를 계산한다.

    Benjamini-Hochberg FDR family는 source×metric별 모든 Tier-A station이다.
    """

    rows: list[dict[str, object]] = []
    for (station_id, source, metric), group in annual.groupby(
        ["station_id", "source", "metric"], sort=False
    ):
        rows.append({
            "station_id": str(station_id),
            "source": source,
            "metric": metric,
            "series_mean": float(group["annual_mean"].mean()),
            **analyze_trend_series(group["year"], group["annual_mean"], alpha=alpha),
        })
    raw = pd.DataFrame(rows)
    corrected: list[pd.DataFrame] = []
    for (source, metric), family in raw.groupby(["source", "metric"], sort=False):
        frame = apply_fdr_correction(family, p_value_column="mk_p_value", alpha=alpha)
        frame["fdr_family"] = f"{source} {metric}: all selected Tier A stations"
        corrected.append(frame)
    result = pd.concat(corrected, ignore_index=True)
    return result.merge(
        _station_metadata(stations), on="station_id", how="left", validate="many_to_one"
    ).sort_values(["metric", "source", "station_id"]).reset_index(drop=True)


def calculate_normals_and_anomalies(
    annual: pd.DataFrame,
    baseline_start: int = NORMAL_START_YEAR,
    baseline_end: int = NORMAL_END_YEAR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """1991–2020 연평균 normal과 1981–2025 anomaly를 계산한다."""

    baseline = annual.loc[annual["year"].between(baseline_start, baseline_end)].copy()
    expected = baseline_end - baseline_start + 1
    normal_rows: list[dict[str, object]] = []
    keys = ["station_id", "station_name", "source", "metric"]
    for key, group in baseline.groupby(keys, sort=False):
        years = sorted(group["year"].astype(int).unique())
        if years != list(range(baseline_start, baseline_end + 1)):
            raise ValueError(f"station {key[0]} {key[2]} {key[3]} normal 기간이 불완전합니다.")
        values = group["annual_mean"].dropna()
        if len(values) != expected:
            raise ValueError(f"station {key[0]} {key[2]} {key[3]} normal에 결측 연도가 있습니다.")
        normal_rows.append({
            "station_id": key[0], "station_name": key[1], "source": key[2], "metric": key[3],
            "normal_start_year": baseline_start, "normal_end_year": baseline_end,
            "n_years": expected, "normal_mean": float(values.mean()),
            "normal_std": float(values.std(ddof=1)),
        })
    normals = pd.DataFrame(normal_rows)
    anomalies = annual.merge(
        normals[["station_id", "source", "metric", "normal_mean"]],
        on=["station_id", "source", "metric"], how="left", validate="many_to_one"
    )
    anomalies["anomaly"] = anomalies["annual_mean"] - anomalies["normal_mean"]
    return normals, anomalies


def _season_definition(dates: pd.Series) -> pd.DataFrame:
    """기존 규칙대로 12월을 다음 해 DJF에 배정한다."""

    month = dates.dt.month
    season = pd.Series(index=dates.index, dtype="string")
    season.loc[month.isin([12, 1, 2])] = "DJF"
    season.loc[month.isin([3, 4, 5])] = "MAM"
    season.loc[month.isin([6, 7, 8])] = "JJA"
    season.loc[month.isin([9, 10, 11])] = "SON"
    season_year = dates.dt.year + month.eq(12).astype(int)
    return pd.DataFrame({"season": season, "season_year": season_year})


def _expected_season_days(season: str, season_year: int) -> int:
    """해당 season-year에 포함되는 실제 달력 일수를 반환한다."""

    ranges = {
        "DJF": (pd.Timestamp(season_year - 1, 12, 1), pd.Timestamp(season_year, 2, 1) + pd.offsets.MonthEnd(0)),
        "MAM": (pd.Timestamp(season_year, 3, 1), pd.Timestamp(season_year, 5, 31)),
        "JJA": (pd.Timestamp(season_year, 6, 1), pd.Timestamp(season_year, 8, 31)),
        "SON": (pd.Timestamp(season_year, 9, 1), pd.Timestamp(season_year, 11, 30)),
    }
    start, end = ranges[season]
    return int((end - start).days + 1)


def calculate_seasonal_temperature(
    prepared: Iterable[PreparedStation], stations: pd.DataFrame, alpha: float = 0.05
) -> pd.DataFrame:
    """완전한 달력 season에서 기온 평균과 station별 추세·FDR을 계산한다."""

    aggregate_rows: list[dict[str, object]] = []
    for item in prepared:
        for source, dataframe in (("KMA", item.kma), ("NASA", item.nasa)):
            daily = dataframe.copy()
            daily["date"] = pd.to_datetime(daily["date"], errors="raise")
            daily[["season", "season_year"]] = _season_definition(daily["date"])
            for (season, season_year), group in daily.groupby(["season", "season_year"], sort=True):
                expected = _expected_season_days(str(season), int(season_year))
                if len(group) != expected:
                    continue
                for metric, column in SOURCE_DAILY_COLUMNS[source].items():
                    valid = int(group[column].notna().sum())
                    aggregate_rows.append({
                        "station_id": item.station_id, "source": source, "metric": metric,
                        "season": str(season), "season_year": int(season_year),
                        "seasonal_mean": float(group[column].mean()) if valid / expected >= 0.95 else math.nan,
                        "valid_days": valid, "expected_days": expected,
                    })
    aggregates = pd.DataFrame(aggregate_rows)
    trend_rows: list[dict[str, object]] = []
    for key, group in aggregates.groupby(["station_id", "source", "metric", "season"], sort=False):
        trend_rows.append({
            "station_id": key[0], "source": key[1], "metric": key[2], "season": key[3],
            "seasonal_mean": float(group["seasonal_mean"].mean()),
            **analyze_trend_series(group["season_year"], group["seasonal_mean"], alpha=alpha),
        })
    raw = pd.DataFrame(trend_rows)
    corrected: list[pd.DataFrame] = []
    for (source, metric, season), family in raw.groupby(["source", "metric", "season"], sort=False):
        frame = apply_fdr_correction(family, "mk_p_value", alpha)
        frame["fdr_family"] = f"{source} {metric} {season}: all selected Tier A stations"
        corrected.append(frame)
    trends = pd.concat(corrected, ignore_index=True)
    return trends.merge(
        _station_metadata(stations), on="station_id", how="left", validate="many_to_one"
    ).sort_values(["metric", "season", "source", "station_id"]).reset_index(drop=True)


def calculate_threshold_annual(prepared: Iterable[PreparedStation]) -> pd.DataFrame:
    """동일 날짜 pair에서 30/33°C Tmax와 25°C Tmin 연간 proxy 일수를 센다."""

    rows: list[dict[str, object]] = []
    for item in prepared:
        data = item.matched.copy()
        data["year"] = pd.to_datetime(data["date"], errors="raise").dt.year
        for year, group in data.groupby("year", sort=True):
            for threshold, (nasa_column, kma_column, value) in THRESHOLDS.items():
                pairs = group[[nasa_column, kma_column]].dropna()
                rows.append({
                    "station_id": item.station_id, "station_name": item.station_name,
                    "year": int(year), "threshold": threshold, "threshold_c": value,
                    "valid_pair_days": len(pairs),
                    "nasa_count": int((pairs[nasa_column] >= value).sum()),
                    "kma_count": int((pairs[kma_column] >= value).sum()),
                })
    result = pd.DataFrame(rows)
    result["difference"] = result["nasa_count"] - result["kma_count"]
    return result


def calculate_threshold_comparison(
    threshold_annual: pd.DataFrame, stations: pd.DataFrame
) -> pd.DataFrame:
    """station별 threshold proxy 평균과 KMA/NASA Sen 기울기를 비교한다."""

    rows: list[dict[str, object]] = []
    for (station_id, station_name, threshold), group in threshold_annual.groupby(
        ["station_id", "station_name", "threshold"], sort=False
    ):
        kma_trend = analyze_trend_series(group["year"], group["kma_count"])
        nasa_trend = analyze_trend_series(group["year"], group["nasa_count"])
        rows.append({
            "station_id": station_id, "station_name": station_name, "threshold": threshold,
            "threshold_c": float(group["threshold_c"].iloc[0]),
            "kma_mean_annual_count": float(group["kma_count"].mean()),
            "nasa_mean_annual_count": float(group["nasa_count"].mean()),
            "mean_count_difference_nasa_minus_kma": float(group["difference"].mean()),
            "kma_sen_slope_per_decade": kma_trend["sen_slope_per_decade"],
            "nasa_sen_slope_per_decade": nasa_trend["sen_slope_per_decade"],
            "kma_mk_p_value": kma_trend["mk_p_value"],
            "nasa_mk_p_value": nasa_trend["mk_p_value"],
            "proxy_notice": "analysis proxy; not an official KMA heat-wave/tropical-night statistic",
        })
    return pd.DataFrame(rows).merge(
        _station_metadata(stations), on=["station_id", "station_name"], how="left", validate="many_to_one"
    )


def calculate_temperature_validation(
    prepared: Iterable[PreparedStation], stations: pd.DataFrame
) -> pd.DataFrame:
    """station×기온 metric의 NASA-KMA 일별 agreement 통계를 계산한다."""

    rows: list[dict[str, object]] = []
    for item in prepared:
        for metric, (nasa_column, kma_column) in MATCHED_COLUMNS.items():
            rows.append({
                "station_id": item.station_id, "station_name": item.station_name,
                "metric": metric, "unit": "deg C", "bias_definition": "NASA minus KMA",
                **calculate_pair_metrics(item.matched, nasa_column, kma_column),
            })
    return pd.DataFrame(rows).merge(
        _station_metadata(stations), on=["station_id", "station_name"], how="left", validate="many_to_one"
    )


def build_station_trend_table(
    trends: pd.DataFrame, validation: pd.DataFrame
) -> pd.DataFrame:
    """KMA 중심 통계에 NASA 추세와 일별 validation을 결합한 long 핵심표를 만든다."""

    identity = [
        "station_id", "station_name", "region", "region_level1", "region_level2",
        "latitude", "longitude", "elevation_m", "temperature_missing_rate",
        "annual_completeness", "continuity_risk", "metric",
    ]
    kma = trends.loc[trends["source"].eq("KMA")].copy()
    nasa = trends.loc[trends["source"].eq("NASA")].copy()
    result = kma.loc[:, identity + [
        "series_mean", "linear_slope_per_decade", "linear_r_squared", "linear_p_value",
        "sen_slope_per_year", "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper",
        "mk_trend", "mk_tau", "mk_p_value", "modified_mk_method", "modified_mk_p_value",
        "fdr_q_value", "significant_fdr", "n_years",
    ]].rename(columns={
        "series_mean": "kma_mean", "linear_slope_per_decade": "kma_linear_slope_per_decade",
        "linear_r_squared": "kma_linear_r_squared", "linear_p_value": "kma_linear_p_value",
        "sen_slope_per_year": "kma_sen_slope_per_year",
        "sen_slope_per_decade": "kma_sen_slope_per_decade",
        "sen_ci_lower": "kma_sen_ci_lower", "sen_ci_upper": "kma_sen_ci_upper",
        "mk_trend": "kma_mk_trend", "mk_tau": "kma_mk_tau", "mk_p_value": "kma_mk_p",
        "modified_mk_method": "kma_modified_mk_method",
        "modified_mk_p_value": "kma_modified_mk_p", "fdr_q_value": "kma_fdr_q",
        "significant_fdr": "kma_significant_fdr",
    })
    nasa_keep = nasa.loc[:, [
        "station_id", "metric", "series_mean", "linear_slope_per_decade",
        "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper", "mk_p_value",
        "fdr_q_value", "significant_fdr",
    ]].rename(columns={
        "series_mean": "nasa_mean", "linear_slope_per_decade": "nasa_linear_slope_per_decade",
        "sen_slope_per_decade": "nasa_sen_slope_per_decade",
        "sen_ci_lower": "nasa_sen_ci_lower", "sen_ci_upper": "nasa_sen_ci_upper",
        "mk_p_value": "nasa_mk_p", "fdr_q_value": "nasa_fdr_q",
        "significant_fdr": "nasa_significant_fdr",
    })
    result = result.merge(nasa_keep, on=["station_id", "metric"], validate="one_to_one")
    validation_keep = validation.loc[:, [
        "station_id", "metric", "n_pairs", "bias", "mae", "rmse", "pearson_r", "spearman_rho"
    ]].rename(columns={
        "bias": "nasa_kma_bias", "mae": "nasa_kma_mae", "rmse": "nasa_kma_rmse",
        "pearson_r": "nasa_kma_pearson", "spearman_rho": "nasa_kma_spearman",
    })
    return result.merge(
        validation_keep, on=["station_id", "metric"], validate="one_to_one"
    ).sort_values(["metric", "station_id"]).reset_index(drop=True)


def build_station_summary(
    trend_table: pd.DataFrame, threshold_comparison: pd.DataFrame
) -> pd.DataFrame:
    """station당 한 행의 전국 wide summary를 만든다."""

    identity = ["station_id", "station_name", "region", "latitude", "longitude", "elevation_m",
                "temperature_missing_rate", "annual_completeness", "continuity_risk"]
    base = trend_table.loc[trend_table["metric"].eq("TAVG"), identity].drop_duplicates("station_id")
    result = base.copy()
    fields = {
        "TAVG": ["kma_mean", "kma_sen_slope_per_decade", "kma_significant_fdr",
                 "nasa_sen_slope_per_decade", "nasa_kma_bias", "nasa_kma_mae",
                 "nasa_kma_rmse", "nasa_kma_pearson"],
        "TMAX": ["kma_sen_slope_per_decade"],
        "TMIN": ["kma_sen_slope_per_decade"],
    }
    for metric, columns in fields.items():
        selected = trend_table.loc[trend_table["metric"].eq(metric), ["station_id", *columns]].copy()
        prefix = metric.casefold()
        selected = selected.rename(columns={column: f"{prefix}_{column}" for column in columns})
        result = result.merge(selected, on="station_id", validate="one_to_one")
    rename = {
        "tavg_kma_mean": "kma_tavg_mean",
        "tavg_kma_sen_slope_per_decade": "kma_tavg_sen_slope_decade",
        "tavg_kma_significant_fdr": "kma_tavg_fdr_significant",
        "tavg_nasa_sen_slope_per_decade": "nasa_tavg_sen_slope_decade",
        "tavg_nasa_kma_bias": "tavg_bias", "tavg_nasa_kma_mae": "tavg_mae",
        "tavg_nasa_kma_rmse": "tavg_rmse", "tavg_nasa_kma_pearson": "tavg_pearson",
        "tmax_kma_sen_slope_per_decade": "kma_tmax_sen_slope_decade",
        "tmin_kma_sen_slope_per_decade": "kma_tmin_sen_slope_decade",
    }
    result = result.rename(columns=rename)
    threshold_names = {"TMAX_GE_33": "days_tmax_ge_33", "TMIN_GE_25": "days_tmin_ge_25"}
    for threshold, prefix in threshold_names.items():
        selected = threshold_comparison.loc[
            threshold_comparison["threshold"].eq(threshold),
            ["station_id", "kma_mean_annual_count", "nasa_mean_annual_count",
             "kma_sen_slope_per_decade", "nasa_sen_slope_per_decade"],
        ].rename(columns={
            "kma_mean_annual_count": f"{prefix}_kma_mean",
            "nasa_mean_annual_count": f"{prefix}_nasa_mean",
            "kma_sen_slope_per_decade": f"{prefix}_kma_sen_slope_decade",
            "nasa_sen_slope_per_decade": f"{prefix}_nasa_sen_slope_decade",
        })
        result = result.merge(selected, on="station_id", validate="one_to_one")
    return result.sort_values("station_id", key=lambda values: values.astype(int)).reset_index(drop=True)


def build_rankings(summary: pd.DataFrame) -> pd.DataFrame:
    """서로 다른 추세를 합치지 않고 독립 ranking family로 정렬한다."""

    definitions = {
        "KMA TAVG Sen slope": "kma_tavg_sen_slope_decade",
        "KMA TMAX Sen slope": "kma_tmax_sen_slope_decade",
        "KMA TMIN Sen slope": "kma_tmin_sen_slope_decade",
        "NASA TAVG Sen slope": "nasa_tavg_sen_slope_decade",
        "KMA TMAX >=33C proxy Sen slope": "days_tmax_ge_33_kma_sen_slope_decade",
        "NASA TMAX >=33C proxy Sen slope": "days_tmax_ge_33_nasa_sen_slope_decade",
        "KMA TMIN >=25C proxy Sen slope": "days_tmin_ge_25_kma_sen_slope_decade",
        "NASA TMIN >=25C proxy Sen slope": "days_tmin_ge_25_nasa_sen_slope_decade",
    }
    frames: list[pd.DataFrame] = []
    for ranking, value_column in definitions.items():
        frame = summary.loc[:, ["station_id", "station_name", "region", value_column]].copy()
        frame["ranking"] = ranking
        frame["rank"] = frame[value_column].rank(method="min", ascending=False).astype(int)
        frame = frame.rename(columns={value_column: "sen_slope_per_decade"})
        frame["is_climate_risk_ranking"] = False
        frames.append(frame.sort_values(["rank", "station_id"]))
    return pd.concat(frames, ignore_index=True)


def build_regional_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """region별 KMA TAVG Sen 추세 분포를 station 수준에서 요약한다."""

    grouped = summary.groupby("region", dropna=False)["kma_tavg_sen_slope_decade"]
    result = grouped.agg(
        station_count="count", median_kma_tavg_sen_slope="median",
        mean_kma_tavg_sen_slope="mean", min_kma_tavg_sen_slope="min",
        max_kma_tavg_sen_slope="max",
    ).reset_index()
    significant = summary.groupby("region")["kma_tavg_fdr_significant"].sum().rename(
        "fdr_significant_station_count"
    )
    result = result.merge(significant, on="region", validate="one_to_one")
    result["interpretation_scope"] = "station sample summary; not regional climate truth"
    return result.sort_values("region").reset_index(drop=True)


def assign_elevation_band(elevation: pd.Series) -> pd.Series:
    """10단계와 동일한 좌폐우개 고도대 label을 반환한다."""

    return pd.cut(
        pd.to_numeric(elevation, errors="coerce"),
        [-math.inf, 50, 200, 500, math.inf], right=False,
        labels=["<50m", "50-200m", "200-500m", ">=500m"],
    )


def build_elevation_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """고도대별 KMA TAVG Sen 추세의 탐색적 분포를 계산한다."""

    working = summary.copy()
    working["elevation_band"] = assign_elevation_band(working["elevation_m"])
    result = working.groupby("elevation_band", observed=False)["kma_tavg_sen_slope_decade"].agg(
        station_count="count", median_kma_tavg_sen_slope="median", mean_kma_tavg_sen_slope="mean",
        min_kma_tavg_sen_slope="min", max_kma_tavg_sen_slope="max",
    ).reset_index()
    result["interpretation_scope"] = "exploratory station comparison; no causal attribution"
    return result


def build_spatial_associations(summary: pd.DataFrame) -> pd.DataFrame:
    """위도·경도·고도와 TAVG Bias/RMSE의 탐색적 Spearman 연관을 계산한다."""

    rows: list[dict[str, object]] = []
    for spatial in ("latitude", "longitude", "elevation_m"):
        for validation in ("tavg_bias", "tavg_rmse"):
            pairs = summary[[spatial, validation]].apply(pd.to_numeric, errors="coerce").dropna()
            result = stats.spearmanr(pairs[spatial], pairs[validation]) if len(pairs) >= 3 else None
            rows.append({
                "spatial_variable": spatial, "validation_metric": validation,
                "spearman_rho": float(result.statistic) if result is not None else math.nan,
                "p_value": float(result.pvalue) if result is not None else math.nan,
                "n_stations": len(pairs),
                "interpretation_scope": "exploratory association; not causality",
            })
    return pd.DataFrame(rows)


def build_trend_consistency(trend_table: pd.DataFrame) -> pd.DataFrame:
    """NASA와 KMA의 station별 추세 방향·FDR 유의성 패턴을 비교한다."""

    result = trend_table.loc[:, [
        "station_id", "station_name", "metric", "kma_sen_slope_per_decade",
        "nasa_sen_slope_per_decade", "kma_significant_fdr", "nasa_significant_fdr",
    ]].copy()

    def direction(row: pd.Series) -> str:
        kma = float(row["kma_sen_slope_per_decade"])
        nasa = float(row["nasa_sen_slope_per_decade"])
        if kma > 0 and nasa > 0:
            return "both increasing"
        if kma < 0 and nasa < 0:
            return "both decreasing"
        if kma == 0 or nasa == 0:
            return "one flat"
        return "opposite"

    def significance(row: pd.Series) -> str:
        kma, nasa = bool(row["kma_significant_fdr"]), bool(row["nasa_significant_fdr"])
        if kma and nasa:
            return "both significant"
        if kma:
            return "KMA significant only"
        if nasa:
            return "NASA significant only"
        return "neither significant"

    result["direction_consistency"] = result.apply(direction, axis=1)
    result["significance_pattern"] = result.apply(significance, axis=1)
    result["interpretation_note"] = "direction agreement does not imply absolute agreement"
    return result


def validate_nationwide_products(
    products: NationwideAnalysisProducts, stations: pd.DataFrame
) -> None:
    """station 수, 통계 범위, 기간, manual exclusion을 종합 검사한다."""

    expected_ids = set(stations["station_id"].astype(str))
    if not expected_ids or products.summary["station_id"].astype(str).nunique() != len(expected_ids):
        raise ValueError("전국 summary station 수가 선택 Tier A 수와 다릅니다.")
    if set(products.summary["station_id"].astype(str)) != expected_ids:
        raise ValueError("전국 summary station ID 집합이 Tier A 선택과 다릅니다.")
    if set(products.annual["year"].unique()) != set(range(ANALYSIS_START.year, ANALYSIS_END.year + 1)):
        raise ValueError("전국 연간표의 분석기간이 1981~2025와 다릅니다.")
    for column in ("kma_fdr_q", "nasa_fdr_q"):
        if not products.trends[column].dropna().between(0, 1).all():
            raise ValueError(f"{column}가 0~1 범위를 벗어났습니다.")
    validation = products.validation
    if (validation["n_pairs"] <= 0).any():
        raise ValueError("NASA-KMA validation에 pair가 없는 station이 있습니다.")
    if (validation["rmse"] + 1e-12 < validation["mae"]).any():
        raise ValueError("NASA-KMA validation에서 RMSE < MAE가 발견되었습니다.")
    for column in ("pearson_r", "spearman_rho"):
        if not validation[column].dropna().between(-1, 1).all():
            raise ValueError(f"{column}이 -1~1 범위를 벗어났습니다.")
    trend = products.trends
    for prefix in ("kma", "nasa"):
        if not (
            (trend[f"{prefix}_sen_ci_lower"] <= trend[f"{prefix}_sen_slope_per_decade"])
            & (trend[f"{prefix}_sen_slope_per_decade"] <= trend[f"{prefix}_sen_ci_upper"])
        ).all():
            raise ValueError(f"{prefix.upper()} Sen slope가 95% CI 밖에 있습니다.")
    if not products.normals["n_years"].eq(NORMAL_END_YEAR - NORMAL_START_YEAR + 1).all():
        raise ValueError("1991~2020 normal 기간이 불완전합니다.")


def build_nationwide_products(
    prepared: Iterable[PreparedStation], stations: pd.DataFrame
) -> NationwideAnalysisProducts:
    """준비된 모든 Tier A station에서 전국 분석 산출물을 계산한다."""

    prepared_items = list(prepared)
    annual = calculate_station_annual_temperature(prepared_items, stations)
    raw_trends = calculate_station_trends(annual, stations)
    normals, anomalies = calculate_normals_and_anomalies(annual)
    seasonal = calculate_seasonal_temperature(prepared_items, stations)
    threshold_annual = calculate_threshold_annual(prepared_items)
    threshold_comparison = calculate_threshold_comparison(threshold_annual, stations)
    validation = calculate_temperature_validation(prepared_items, stations)
    trends = build_station_trend_table(raw_trends, validation)
    summary = build_station_summary(trends, threshold_comparison)
    rankings = build_rankings(summary)
    regional = build_regional_summary(summary)
    elevation = build_elevation_summary(summary)
    spatial = build_spatial_associations(summary)
    consistency = build_trend_consistency(trends)
    products = NationwideAnalysisProducts(
        annual, trends, normals, anomalies, seasonal, threshold_annual,
        threshold_comparison, validation, summary, rankings, regional,
        elevation, spatial, consistency,
    )
    validate_nationwide_products(products, stations)
    return products
