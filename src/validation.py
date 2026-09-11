"""NASA POWER 격자자료와 KMA ASOS 지점관측의 agreement 통계."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from scipy import stats


METRIC_SPECS: dict[str, dict[str, str]] = {
    "temperature": {"nasa": "nasa_T2M", "kma": "kma_T2M", "unit": "deg C"},
    "maximum_temperature": {
        "nasa": "nasa_T2M_MAX",
        "kma": "kma_T2M_MAX",
        "unit": "deg C",
    },
    "minimum_temperature": {
        "nasa": "nasa_T2M_MIN",
        "kma": "kma_T2M_MIN",
        "unit": "deg C",
    },
    "precipitation": {
        "nasa": "nasa_precipitation",
        "kma": "kma_precipitation",
        "unit": "mm/day",
    },
    "relative_humidity": {
        "nasa": "nasa_RH2M",
        "kma": "kma_RH2M",
        "unit": "percentage points",
    },
    "wind_speed": {"nasa": "nasa_WS10M", "kma": "kma_WS10M", "unit": "m/s"},
    "solar_radiation": {
        "nasa": "nasa_solar",
        "kma": "kma_solar",
        "unit": "kWh/m^2/day",
    },
}

NASA_RENAME = {
    "T2M": "nasa_T2M",
    "T2M_MAX": "nasa_T2M_MAX",
    "T2M_MIN": "nasa_T2M_MIN",
    "PRECTOTCORR": "nasa_precipitation",
    "RH2M": "nasa_RH2M",
    "WS10M": "nasa_WS10M",
    "ALLSKY_SFC_SW_DWN": "nasa_solar",
}
KMA_RENAME = {
    "avg_temperature": "kma_T2M",
    "max_temperature": "kma_T2M_MAX",
    "min_temperature": "kma_T2M_MIN",
    "precipitation": "kma_precipitation",
    "relative_humidity": "kma_RH2M",
    "wind_speed": "kma_WS10M",
    "solar_radiation": "kma_solar",
}
SEASON_BY_MONTH = {
    12: "DJF",
    1: "DJF",
    2: "DJF",
    3: "MAM",
    4: "MAM",
    5: "MAM",
    6: "JJA",
    7: "JJA",
    8: "JJA",
    9: "SON",
    10: "SON",
    11: "SON",
}


def match_daily_data(
    nasa: pd.DataFrame,
    kma: pd.DataFrame,
    city: str,
) -> pd.DataFrame:
    """NASA와 KMA 일자료를 날짜 inner join하고 변수별 가용 pair 수를 기록한다."""

    nasa_date = "DATE" if "DATE" in nasa.columns else "date"
    required_nasa = {nasa_date, *NASA_RENAME}
    required_kma = {"date", *KMA_RENAME}
    missing_nasa = sorted(required_nasa - set(nasa.columns))
    missing_kma = sorted(required_kma - set(kma.columns))
    if missing_nasa or missing_kma:
        raise ValueError(
            f"일별 매칭 필수 컬럼 누락: NASA={missing_nasa}, KMA={missing_kma}"
        )
    nasa_part = nasa.loc[:, [nasa_date, *NASA_RENAME]].rename(
        columns={nasa_date: "date", **NASA_RENAME}
    )
    kma_extra = [column for column in ("station_id", "station_name") if column in kma]
    kma_part = kma.loc[:, ["date", *kma_extra, *KMA_RENAME]].rename(columns=KMA_RENAME)
    nasa_part["date"] = pd.to_datetime(nasa_part["date"], errors="raise")
    kma_part["date"] = pd.to_datetime(kma_part["date"], errors="raise")
    if nasa_part["date"].duplicated().any() or kma_part["date"].duplicated().any():
        raise ValueError("NASA 또는 KMA 일자료에 중복 날짜가 있어 one-to-one 매칭할 수 없습니다.")
    matched = nasa_part.merge(kma_part, on="date", how="inner", validate="one_to_one")
    matched.insert(1, "city", city)
    matched["year"] = matched["date"].dt.year
    matched["month"] = matched["date"].dt.month
    matched["season"] = matched["month"].map(SEASON_BY_MONTH)
    matched["season_year"] = matched["year"] + matched["month"].eq(12).astype(int)
    for metric, spec in METRIC_SPECS.items():
        matched[f"n_pairs_{metric}"] = int(
            matched[[spec["nasa"], spec["kma"]]].notna().all(axis=1).sum()
        )
    return matched.sort_values("date").reset_index(drop=True)


def _safe_correlations(nasa: np.ndarray, kma: np.ndarray) -> tuple[float, float, float, float]:
    """상수열 또는 짧은 표본에서 경고 없이 상관계수와 p-value를 반환한다."""

    if len(nasa) < 2 or np.ptp(nasa) == 0 or np.ptp(kma) == 0:
        return np.nan, np.nan, np.nan, np.nan
    pearson = stats.pearsonr(nasa, kma)
    spearman = stats.spearmanr(nasa, kma)
    return float(pearson.statistic), float(pearson.pvalue), float(spearman.statistic), float(
        spearman.pvalue
    )


def calculate_pair_metrics(
    dataframe: pd.DataFrame,
    nasa_column: str,
    kma_column: str,
) -> dict[str, float | int]:
    """한 변수 pair의 Bias(NASA-KMA), MAE, RMSE 및 상관을 계산한다."""

    pairs = dataframe.loc[:, [nasa_column, kma_column]].apply(pd.to_numeric, errors="coerce").dropna()
    n_pairs = len(pairs)
    if n_pairs == 0:
        return {
            "n_pairs": 0,
            "kma_mean": np.nan,
            "nasa_mean": np.nan,
            "bias": np.nan,
            "mae": np.nan,
            "rmse": np.nan,
            "normalized_rmse": np.nan,
            "pearson_r": np.nan,
            "pearson_p": np.nan,
            "spearman_rho": np.nan,
            "spearman_p": np.nan,
        }
    nasa_values = pairs[nasa_column].to_numpy(dtype=float)
    kma_values = pairs[kma_column].to_numpy(dtype=float)
    differences = nasa_values - kma_values
    kma_mean = float(kma_values.mean())
    rmse = float(np.sqrt(np.mean(np.square(differences))))
    pearson_r, pearson_p, spearman_rho, spearman_p = _safe_correlations(
        nasa_values, kma_values
    )
    return {
        "n_pairs": n_pairs,
        "kma_mean": kma_mean,
        "nasa_mean": float(nasa_values.mean()),
        "bias": float(differences.mean()),
        "mae": float(np.abs(differences).mean()),
        "rmse": rmse,
        "normalized_rmse": rmse / abs(kma_mean) if abs(kma_mean) > 1e-12 else np.nan,
        "pearson_r": pearson_r,
        "pearson_p": pearson_p,
        "spearman_rho": spearman_rho,
        "spearman_p": spearman_p,
    }


def calculate_validation_metrics(
    matched: pd.DataFrame,
    metrics: Iterable[str] | None = None,
) -> pd.DataFrame:
    """도시별·변수별 전체기간 validation 지표를 계산한다."""

    metrics = list(metrics or METRIC_SPECS)
    rows: list[dict[str, object]] = []
    for city, group in matched.groupby("city", sort=False):
        for metric in metrics:
            spec = METRIC_SPECS[metric]
            rows.append(
                {
                    "city": city,
                    "metric": metric,
                    "unit": spec["unit"],
                    **calculate_pair_metrics(group, spec["nasa"], spec["kma"]),
                }
            )
    result = pd.DataFrame(rows)
    validate_metric_sanity(result)
    return result


def _grouped_validation(
    matched: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    """월·계절처럼 지정한 키별로 모든 변수의 검증지표를 계산한다."""

    rows: list[dict[str, object]] = []
    grouper: str | list[str] = group_columns[0] if len(group_columns) == 1 else group_columns
    for key, group in matched.groupby(grouper, sort=False, dropna=False):
        keys = (key,) if len(group_columns) == 1 else key
        labels = dict(zip(group_columns, keys))
        for metric, spec in METRIC_SPECS.items():
            rows.append(
                {
                    **labels,
                    "metric": metric,
                    "unit": spec["unit"],
                    **calculate_pair_metrics(group, spec["nasa"], spec["kma"]),
                }
            )
    result = pd.DataFrame(rows)
    validate_metric_sanity(result)
    return result


def calculate_monthly_validation(matched: pd.DataFrame) -> pd.DataFrame:
    """도시×월×변수 validation 지표를 계산한다."""

    return _grouped_validation(matched, ["city", "month"])


def calculate_seasonal_validation(matched: pd.DataFrame) -> pd.DataFrame:
    """기존 정의(DJF/MAM/JJA/SON)와 일치하는 도시×계절 지표를 계산한다."""

    return _grouped_validation(matched, ["city", "season"])


def calculate_annual_bias(matched: pd.DataFrame) -> pd.DataFrame:
    """도시×연도별 기온 3종과 강수의 평균 NASA-KMA bias를 계산한다."""

    selected = ["temperature", "maximum_temperature", "minimum_temperature", "precipitation"]
    result = _grouped_validation(matched, ["city", "year"])
    return result.loc[
        result["metric"].isin(selected),
        ["city", "year", "metric", "unit", "n_pairs", "bias", "mae", "rmse"],
    ].reset_index(drop=True)


def calculate_threshold_validation(matched: pd.DataFrame) -> pd.DataFrame:
    """동일 임계값으로 NASA proxy와 ASOS 관측 기반 연간 일수를 비교한다."""

    rules = (
        ("tmax_ge_30", "nasa_T2M_MAX", "kma_T2M_MAX", 30.0),
        ("tmax_ge_33", "nasa_T2M_MAX", "kma_T2M_MAX", 33.0),
        ("tmin_ge_25", "nasa_T2M_MIN", "kma_T2M_MIN", 25.0),
    )
    rows = []
    for (city, year), group in matched.groupby(["city", "year"], sort=False):
        for threshold_name, nasa_column, kma_column, threshold in rules:
            pairs = group[[nasa_column, kma_column]].dropna()
            nasa_count = int((pairs[nasa_column] >= threshold).sum())
            kma_count = int((pairs[kma_column] >= threshold).sum())
            rows.append(
                {
                    "city": city,
                    "year": int(year),
                    "threshold": threshold_name,
                    "threshold_c": threshold,
                    "n_pairs": len(pairs),
                    "nasa_count": nasa_count,
                    "kma_count": kma_count,
                    "difference": nasa_count - kma_count,
                }
            )
    return pd.DataFrame(rows)


def _safe_ratio(numerator: int, denominator: int) -> float:
    """분모가 0인 categorical 지표를 NaN으로 반환한다."""

    return numerator / denominator if denominator else np.nan


def calculate_precipitation_contingency(
    matched: pd.DataFrame,
    threshold_mm: float = 1.0,
) -> pd.DataFrame:
    """도시별 wet-day hit/miss/false alarm과 POD/FAR/CSI를 계산한다."""

    rows = []
    for city, group in matched.groupby("city", sort=False):
        pairs = group[["nasa_precipitation", "kma_precipitation"]].dropna()
        nasa_wet = pairs["nasa_precipitation"] >= threshold_mm
        kma_wet = pairs["kma_precipitation"] >= threshold_mm
        hits = int((nasa_wet & kma_wet).sum())
        misses = int((~nasa_wet & kma_wet).sum())
        false_alarms = int((nasa_wet & ~kma_wet).sum())
        correct_negatives = int((~nasa_wet & ~kma_wet).sum())
        rows.append(
            {
                "city": city,
                "threshold_mm": threshold_mm,
                "n_pairs": len(pairs),
                "hit": hits,
                "miss": misses,
                "false_alarm": false_alarms,
                "correct_negative": correct_negatives,
                "pod": _safe_ratio(hits, hits + misses),
                "far": _safe_ratio(false_alarms, hits + false_alarms),
                "csi": _safe_ratio(hits, hits + misses + false_alarms),
            }
        )
    return pd.DataFrame(rows)


def calculate_gangneung_continuity(raw: pd.DataFrame) -> pd.DataFrame:
    """동일 날짜에 존재하는 강릉105·북강릉104 평균기온 차이를 요약한다."""

    required = {"tm", "stnId", "avgTa"}
    if not required.issubset(raw.columns):
        raise ValueError(f"강릉 continuity 필수 필드가 없습니다: {sorted(required - set(raw))}")
    subset = raw.loc[raw["stnId"].astype(str).isin(["104", "105"]), ["tm", "stnId", "avgTa"]].copy()
    subset["stnId"] = subset["stnId"].astype(str)
    subset["avgTa"] = pd.to_numeric(subset["avgTa"], errors="coerce")
    pivot = subset.pivot_table(index="tm", columns="stnId", values="avgTa", aggfunc="first")
    if not {"104", "105"}.issubset(pivot.columns):
        return pd.DataFrame(
            columns=[
                "comparison",
                "n_overlap_pairs",
                "overlap_start",
                "overlap_end",
                "mean_difference_104_minus_105_c",
                "mae_c",
                "rmse_c",
                "pearson_r",
            ]
        )
    pairs = pivot[["104", "105"]].dropna()
    metrics = calculate_pair_metrics(pairs, "104", "105")
    return pd.DataFrame(
        [
            {
                "comparison": "Bukgangneung(104) - Gangneung(105)",
                "n_overlap_pairs": metrics["n_pairs"],
                "overlap_start": pairs.index.min() if not pairs.empty else None,
                "overlap_end": pairs.index.max() if not pairs.empty else None,
                "mean_difference_104_minus_105_c": metrics["bias"],
                "mae_c": metrics["mae"],
                "rmse_c": metrics["rmse"],
                "pearson_r": metrics["pearson_r"],
            }
        ]
    )


def validate_metric_sanity(metrics: pd.DataFrame) -> None:
    """수치상 불가능한 validation 결과를 조기에 차단한다."""

    usable = metrics.loc[metrics["n_pairs"] > 0]
    if (usable[["mae", "rmse"]].to_numpy() < -1e-12).any():
        raise ValueError("MAE와 RMSE는 음수가 될 수 없습니다.")
    if (usable["rmse"] + 1e-12 < usable["mae"]).any():
        raise ValueError("RMSE는 MAE보다 작을 수 없습니다.")
    for column in ("pearson_r", "spearman_rho"):
        values = usable[column].dropna()
        if ((values < -1) | (values > 1)).any():
            raise ValueError(f"{column}은 -1~1 범위를 벗어날 수 없습니다.")
