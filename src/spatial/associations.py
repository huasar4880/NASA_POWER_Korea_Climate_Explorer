"""공간 좌표 연관, Tmax/Tmin contrast, DTR·계절·지역 탐색 요약."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

from src.spatial.autocorrelation import global_moran_permutation
from src.spatial.weights import SpatialWeights, align_values, subset_spatial_weights
from src.statistical_analysis import analyze_trend_series, apply_fdr_correction


ASSOCIATION_TARGETS = {
    "latitude": [
        "kma_tavg_sen_slope", "kma_tmax_sen_slope", "kma_tmin_sen_slope",
    ],
    "longitude": [
        "kma_tavg_sen_slope", "kma_tmax_sen_slope", "kma_tmin_sen_slope",
    ],
    "elevation_m": [
        "kma_tavg_sen_slope", "kma_tmax_sen_slope", "kma_tmin_sen_slope",
        "tavg_bias", "tavg_rmse",
    ],
}


def calculate_association(
    dataframe: pd.DataFrame,
    x_column: str,
    y_column: str,
) -> dict[str, object]:
    """Pearson·Spearman·단순선형회귀의 탐색적 연관 통계를 계산한다."""

    clean = dataframe.loc[:, [x_column, y_column]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(clean) < 3 or clean[x_column].nunique() < 2 or clean[y_column].nunique() < 2:
        return {
            "spatial_variable": x_column, "climate_metric": y_column, "n_stations_used": len(clean),
            "pearson_r": math.nan, "pearson_p": math.nan, "spearman_rho": math.nan,
            "spearman_p": math.nan, "regression_slope": math.nan,
            "regression_intercept": math.nan, "regression_r_squared": math.nan,
            "regression_p": math.nan, "interpretation_scope": "exploratory association; not causality",
        }
    pearson = stats.pearsonr(clean[x_column], clean[y_column])
    spearman = stats.spearmanr(clean[x_column], clean[y_column])
    regression = stats.linregress(clean[x_column], clean[y_column])
    return {
        "spatial_variable": x_column, "climate_metric": y_column,
        "n_stations_used": len(clean), "pearson_r": float(pearson.statistic),
        "pearson_p": float(pearson.pvalue), "spearman_rho": float(spearman.statistic),
        "spearman_p": float(spearman.pvalue), "regression_slope": float(regression.slope),
        "regression_intercept": float(regression.intercept),
        "regression_r_squared": float(regression.rvalue ** 2),
        "regression_p": float(regression.pvalue),
        "interpretation_scope": "exploratory association; not causality",
    }


def build_coordinate_associations(master: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """위도·경도·고도별 요청 metric 연관표를 각각 생성한다."""

    outputs: dict[str, pd.DataFrame] = {}
    for spatial_variable, metrics in ASSOCIATION_TARGETS.items():
        outputs[spatial_variable] = pd.DataFrame([
            calculate_association(master, spatial_variable, metric) for metric in metrics
        ])
    validate_associations(pd.concat(outputs.values(), ignore_index=True))
    return outputs


def validate_associations(results: pd.DataFrame) -> None:
    """연관계수·p-value·R²의 범위와 inf 부재를 검사한다."""

    for column in ("pearson_r", "spearman_rho"):
        valid = results[column].dropna()
        if not valid.between(-1, 1).all():
            raise ValueError(f"{column}이 -1~1 범위를 벗어납니다.")
    for column in ("pearson_p", "spearman_p", "regression_p", "regression_r_squared"):
        valid = results[column].dropna()
        if not valid.between(0, 1).all():
            raise ValueError(f"{column}이 0~1 범위를 벗어납니다.")
    numeric = results.select_dtypes(include=[np.number])
    if np.isinf(numeric.to_numpy()).any():
        raise ValueError("연관 분석 결과에 inf가 있습니다.")


def build_tmax_tmin_contrast(master: pd.DataFrame, tolerance: float = 1e-12) -> pd.DataFrame:
    """station별 TMIN Sen slope와 TMAX Sen slope 차이 및 방향을 계산한다."""

    columns = [
        "station_id", "station_name", "region_level1", "latitude", "longitude",
        "elevation_m", "kma_tmax_sen_slope", "kma_tmin_sen_slope",
    ]
    result = master.loc[:, columns].rename(columns={
        "kma_tmax_sen_slope": "tmax_slope", "kma_tmin_sen_slope": "tmin_slope",
    })
    result["tmin_minus_tmax"] = result["tmin_slope"] - result["tmax_slope"]
    result["contrast_direction"] = np.select(
        [result["tmin_minus_tmax"] > tolerance, result["tmin_minus_tmax"] < -tolerance],
        ["TMIN warming faster", "TMAX warming faster"], default="Equal within tolerance",
    )
    return result


def calculate_dtr_trends(annual: pd.DataFrame, master: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """연평균 DTR(TMAX−TMIN)을 source별로 만든 뒤 1981–2025 추세를 계산한다."""

    selected = annual.loc[annual["metric"].isin(["TMAX", "TMIN"])].copy()
    pivot = selected.pivot_table(
        index=["station_id", "source", "year"], columns="metric",
        values="annual_mean", aggfunc="first",
    ).reset_index()
    pivot["dtr"] = pivot["TMAX"] - pivot["TMIN"]
    rows: list[dict[str, object]] = []
    for (station_id, source), group in pivot.groupby(["station_id", "source"], sort=False):
        rows.append({
            "station_id": str(station_id), "source": source,
            "mean_dtr": float(group["dtr"].mean()),
            **analyze_trend_series(group["year"], group["dtr"], alpha=alpha),
        })
    raw = pd.DataFrame(rows)
    corrected = []
    for source, family in raw.groupby("source", sort=False):
        frame = apply_fdr_correction(family, "mk_p_value", alpha).rename(
            columns={"fdr_q_value": "dtr_fdr_q", "significant_fdr": "dtr_significant_fdr"}
        )
        frame["fdr_family"] = f"{source} DTR: all Final Tier A stations"
        corrected.append(frame)
    result = pd.concat(corrected, ignore_index=True)
    metadata = master[[
        "station_id", "station_name", "region_level1", "latitude", "longitude",
        "elevation_m", "continuity_risk", "annual_completeness",
    ]]
    return result.merge(metadata, on="station_id", how="left", validate="many_to_one").sort_values(
        ["source", "station_id"]
    ).reset_index(drop=True)


def build_seasonal_spatial_summary(
    seasonal: pd.DataFrame,
    master: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """KMA TAVG 계절 Sen slope 분포와 station별 dominant season을 계산한다."""

    season_order = ["DJF", "MAM", "JJA", "SON"]
    selected = seasonal.loc[
        seasonal["source"].eq("KMA") & seasonal["metric"].eq("TAVG")
    ].copy()
    selected["station_id"] = selected["station_id"].astype(str)
    if selected.duplicated(["station_id", "season"]).any():
        raise ValueError("KMA TAVG seasonal station×season이 중복됩니다.")
    expected = {(sid, season) for sid in master["station_id"] for season in season_order}
    observed = set(zip(selected["station_id"], selected["season"]))
    if observed != expected:
        raise ValueError("KMA TAVG seasonal station×season 구성이 불완전합니다.")
    aggregate = selected.groupby("season", sort=False)["sen_slope_per_decade"].agg(
        station_count="count", national_median_slope="median", national_min_slope="min",
        national_max_slope="max",
    ).reset_index()
    output = selected[[
        "station_id", "station_name", "region_level1", "latitude", "longitude",
        "elevation_m", "season", "sen_slope_per_decade", "fdr_q_value", "significant_fdr",
    ]].merge(aggregate, on="season", how="left", validate="many_to_one")
    wide = selected.pivot(index="station_id", columns="season", values="sen_slope_per_decade")
    wide = wide.reindex(columns=season_order)
    maximum = wide.max(axis=1)
    ties = wide.eq(maximum, axis=0)
    dominant = pd.DataFrame({
        "station_id": wide.index.astype(str),
        "dominant_warming_season": [
            next(season for season in season_order if ties.loc[station_id, season])
            for station_id in wide.index
        ],
        "dominant_sen_slope_per_decade": maximum.to_numpy(dtype=float),
        "tie_count": ties.sum(axis=1).to_numpy(dtype=int),
        "tie_rule": "exact tie resolved by fixed order DJF,MAM,JJA,SON",
    })
    dominant = dominant.merge(
        master[["station_id", "station_name", "region_level1", "latitude", "longitude", "elevation_m"]],
        on="station_id", how="left", validate="one_to_one",
    )
    return output.sort_values(["station_id", "season"]).reset_index(drop=True), dominant


def build_seasonal_morans(
    seasonal_summary: pd.DataFrame,
    weights: SpatialWeights,
    permutations: int,
    seed: int,
) -> pd.DataFrame:
    """DJF/MAM/JJA/SON KMA TAVG Sen slope의 Global Moran 결과를 만든다."""

    rows = []
    for offset, season in enumerate(["DJF", "MAM", "JJA", "SON"]):
        data = seasonal_summary.loc[seasonal_summary["season"].eq(season)]
        values = align_values(data, "sen_slope_per_decade", weights)
        result = global_moran_permutation(values, weights.matrix, permutations, seed + offset)
        rows.append({
            "season": season, "variable": "kma_tavg_sen_slope", "n_stations_used": len(values),
            "weights_method": weights.method, "k": weights.k, "moran_i": result.moran_i,
            "expected_i": result.expected_i, "z_score": result.z_score,
            "permutation_p": result.permutation_p, "permutations": permutations,
            "random_seed": seed + offset,
        })
    return pd.DataFrame(rows)


def build_threshold_spatial_summary(
    master: pd.DataFrame,
    weights: SpatialWeights,
    permutations: int,
    seed: int,
) -> pd.DataFrame:
    """33°C/25°C proxy의 source별 분포·Moran·위도/고도 연관을 요약한다."""

    specifications = [
        ("TMAX_GE_33", "KMA", "days_tmax_ge_33_kma_slope", 6),
        ("TMAX_GE_33", "NASA", "days_tmax_ge_33_nasa_slope", 200),
        ("TMIN_GE_25", "KMA", "days_tmin_ge_25_kma_slope", 7),
        ("TMIN_GE_25", "NASA", "days_tmin_ge_25_nasa_slope", 201),
    ]
    rows = []
    for threshold, source, column, seed_offset in specifications:
        subset = master.loc[master[column].notna()].copy()
        metric_weights = subset_spatial_weights(
            weights, subset["station_id"].astype(str).tolist()
        )
        values = align_values(subset, column, metric_weights)
        moran = global_moran_permutation(
            values, metric_weights.matrix, permutations, seed + seed_offset
        )
        latitude = calculate_association(master, "latitude", column)
        elevation = calculate_association(master, "elevation_m", column)
        rows.append({
            "threshold": threshold, "source": source, "metric_column": column,
            "n_stations_used": len(values), "median_slope_per_decade": float(np.median(values)),
            "min_slope_per_decade": float(np.min(values)), "max_slope_per_decade": float(np.max(values)),
            "moran_i": moran.moran_i, "permutation_p": moran.permutation_p,
            "weights_method": metric_weights.method, "k": metric_weights.k,
            "latitude_pearson_r": latitude["pearson_r"], "latitude_spearman_rho": latitude["spearman_rho"],
            "elevation_pearson_r": elevation["pearson_r"], "elevation_spearman_rho": elevation["spearman_rho"],
            "proxy_notice": "analysis proxy; not an official heat-wave/tropical-night statistic",
        })
    return pd.DataFrame(rows)


def build_validation_spatial_summary(
    master: pd.DataFrame,
    weights: SpatialWeights,
    permutations: int,
    seed: int,
) -> pd.DataFrame:
    """NASA−KMA TAVG Bias와 RMSE의 분포·Moran·좌표 연관을 요약한다."""

    rows = []
    for metric, seed_offset in (("tavg_bias", 4), ("tavg_rmse", 5)):
        subset = master.loc[master[metric].notna()].copy()
        metric_weights = subset_spatial_weights(
            weights, subset["station_id"].astype(str).tolist()
        )
        values = align_values(subset, metric, metric_weights)
        moran = global_moran_permutation(
            values, metric_weights.matrix, permutations, seed + seed_offset
        )
        associations = {
            spatial: calculate_association(master, spatial, metric)
            for spatial in ("latitude", "longitude", "elevation_m")
        }
        rows.append({
            "validation_metric": metric, "n_stations_used": len(values),
            "median": float(np.median(values)), "minimum": float(np.min(values)),
            "maximum": float(np.max(values)), "moran_i": moran.moran_i,
            "permutation_p": moran.permutation_p, "weights_method": metric_weights.method, "k": metric_weights.k,
            **{
                f"{spatial}_{coefficient}": associations[spatial][coefficient]
                for spatial in associations for coefficient in ("pearson_r", "spearman_rho")
            },
            "bias_definition": "NASA minus KMA" if metric == "tavg_bias" else "not applicable",
            "interpretation_scope": "exploratory spatial association; not attribution",
        })
    return pd.DataFrame(rows)


def build_regional_spatial_summary(master: pd.DataFrame) -> pd.DataFrame:
    """region_level1 station 표본의 TAVG/TMAX/TMIN 분포와 소표본 flag를 만든다."""

    rows = []
    for region, group in master.groupby("region_level1", sort=True):
        row: dict[str, object] = {
            "region_level1": region, "station_count": len(group),
            "small_sample_region": len(group) < 3,
            "tavg_fdr_significant_count": int(group["tavg_fdr_significant"].astype(bool).sum()),
            "interpretation_scope": "station sample; not area-weighted regional climate",
        }
        for short, column in (
            ("tavg", "kma_tavg_sen_slope"), ("tmax", "kma_tmax_sen_slope"),
            ("tmin", "kma_tmin_sen_slope"),
        ):
            row.update({
                f"{short}_median": float(group[column].median()),
                f"{short}_iqr": float(group[column].quantile(0.75) - group[column].quantile(0.25)),
                f"{short}_min": float(group[column].min()),
                f"{short}_max": float(group[column].max()),
            })
        rows.append(row)
    return pd.DataFrame(rows)
