"""재현 가능한 Global/Local Moran's I와 weight sensitivity 분석."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.spatial.weights import (
    SpatialWeights,
    align_values,
    build_knn_weights,
    subset_spatial_weights,
)
from src.statistical_analysis import apply_fdr_correction


GLOBAL_VARIABLES = {
    "kma_tavg_sen_slope": "KMA TAVG Sen slope",
    "kma_tmax_sen_slope": "KMA TMAX Sen slope",
    "kma_tmin_sen_slope": "KMA TMIN Sen slope",
    "nasa_tavg_sen_slope": "NASA TAVG Sen slope",
    "tavg_bias": "NASA-KMA TAVG Bias",
    "tavg_rmse": "NASA-KMA TAVG RMSE",
    "days_tmax_ge_33_kma_slope": "KMA TMAX >=33C proxy slope",
    "days_tmin_ge_25_kma_slope": "KMA TMIN >=25C proxy slope",
}

LOCAL_VARIABLES = {
    key: value for key, value in GLOBAL_VARIABLES.items()
    if key in {"kma_tavg_sen_slope", "kma_tmax_sen_slope", "kma_tmin_sen_slope", "tavg_bias", "tavg_rmse"}
}


@dataclass(frozen=True)
class GlobalMoranResult:
    """Global Moran 통계와 permutation inference 결과."""

    moran_i: float
    expected_i: float
    z_score: float
    permutation_p: float
    permutations: int


def _standardize(values: np.ndarray) -> np.ndarray:
    """유한한 1차원 값을 population standard deviation으로 표준화한다."""

    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) < 3 or not np.isfinite(array).all():
        raise ValueError("Moran 값은 3개 이상의 유한한 1차원 배열이어야 합니다.")
    deviation = float(array.std(ddof=0))
    if deviation == 0:
        raise ValueError("상수 계열에는 Moran's I를 계산할 수 없습니다.")
    return (array - array.mean()) / deviation


def moran_i(values: np.ndarray, weight_matrix: np.ndarray) -> float:
    """일반 가중치 행렬에 대한 Global Moran's I를 계산한다."""

    z = _standardize(values)
    weights = np.asarray(weight_matrix, dtype=float)
    if weights.shape != (len(z), len(z)):
        raise ValueError("Moran 값과 가중치 행렬 크기가 다릅니다.")
    s0 = float(weights.sum())
    denominator = float(z @ z)
    if s0 <= 0 or denominator <= 0:
        raise ValueError("Moran 계산에 유효한 가중치 또는 분산이 없습니다.")
    return float((len(z) / s0) * ((z @ weights @ z) / denominator))


def global_moran_permutation(
    values: np.ndarray,
    weight_matrix: np.ndarray,
    permutations: int,
    seed: int,
) -> GlobalMoranResult:
    """고정 seed의 two-sided permutation Global Moran 검정을 수행한다."""

    if int(permutations) < 1:
        raise ValueError("Moran permutation 수는 1 이상이어야 합니다.")
    observed = moran_i(values, weight_matrix)
    expected = -1.0 / (len(values) - 1)
    rng = np.random.default_rng(int(seed))
    simulated = np.array([
        moran_i(rng.permutation(values), weight_matrix) for _ in range(int(permutations))
    ])
    extreme = np.count_nonzero(np.abs(simulated - expected) >= abs(observed - expected))
    p_value = float((extreme + 1) / (int(permutations) + 1))
    standard_error = float(simulated.std(ddof=1)) if len(simulated) > 1 else float("nan")
    z_score = float((observed - simulated.mean()) / standard_error) if standard_error > 0 else 0.0
    return GlobalMoranResult(observed, expected, z_score, p_value, int(permutations))


def build_global_morans(
    master: pd.DataFrame,
    weights: SpatialWeights,
    permutations: int,
    seed: int,
) -> pd.DataFrame:
    """요청된 8개 station metric의 Global Moran 결과표를 만든다."""

    rows: list[dict[str, object]] = []
    for offset, (column, label) in enumerate(GLOBAL_VARIABLES.items()):
        subset = master.loc[master[column].notna(), ["station_id", column]].copy()
        metric_weights = subset_spatial_weights(weights, subset["station_id"].astype(str).tolist())
        values = align_values(subset, column, metric_weights)
        result = global_moran_permutation(
            values, metric_weights.matrix, permutations, seed + offset
        )
        rows.append({
            "variable": column, "label": label, "n_stations": len(values),
            "n_stations_used": len(values),
            "weights_method": metric_weights.method, "k": metric_weights.k,
            "moran_i": result.moran_i, "expected_i": result.expected_i,
            "z_score": result.z_score, "permutation_p": result.permutation_p,
            "permutations": result.permutations, "random_seed": seed + offset,
        })
    return pd.DataFrame(rows)


def build_weight_sensitivity(
    master: pd.DataFrame,
    distance_matrix: pd.DataFrame,
    k_values: list[int],
    permutations: int,
    seed: int,
) -> pd.DataFrame:
    """모든 Global metric에 대해 여러 KNN k의 Moran 결과를 비교한다."""

    rows: list[pd.DataFrame] = []
    for k in k_values:
        weights = build_knn_weights(distance_matrix, int(k))
        result = build_global_morans(master, weights, permutations, seed)
        result["sensitivity_setting"] = f"knn_k_{int(k)}"
        rows.append(result)
    return pd.concat(rows, ignore_index=True)


def local_moran_permutation(
    values: np.ndarray,
    weights: SpatialWeights,
    permutations: int,
    seed: int,
    alpha: float,
) -> pd.DataFrame:
    """전체값 permutation으로 Local Moran, quadrant와 BH-FDR을 계산한다."""

    z = _standardize(values)
    lag = weights.matrix @ z
    observed = z * lag
    rng = np.random.default_rng(int(seed))
    exceedances = np.zeros(len(z), dtype=int)
    indices = np.arange(len(z))
    for index in indices:
        others = indices[indices != index]
        other_values = z[others]
        other_weights = weights.matrix[index, others]
        simulated = np.array([
            z[index] * float(other_weights @ rng.permutation(other_values))
            for _ in range(int(permutations))
        ])
        exceedances[index] = int(
            np.count_nonzero(np.abs(simulated) >= abs(observed[index]))
        )
    p_values = (exceedances + 1) / (int(permutations) + 1)
    quadrants = np.select(
        [(z >= 0) & (lag >= 0), (z < 0) & (lag < 0), (z >= 0) & (lag < 0), (z < 0) & (lag >= 0)],
        ["High-High", "Low-Low", "High-Low", "Low-High"],
        default="Not Significant",
    )
    raw = pd.DataFrame({
        "station_id": weights.station_ids,
        "local_i": observed,
        "local_p": p_values,
        "cluster_quadrant": quadrants,
        "cluster_type": np.where(p_values <= alpha, quadrants, "Not Significant"),
        "significant": p_values <= alpha,
        "neighbor_count": np.count_nonzero(weights.matrix, axis=1),
    })
    corrected = apply_fdr_correction(raw, "local_p", alpha).rename(
        columns={"fdr_q_value": "local_fdr_q", "significant_fdr": "local_significant_fdr"}
    )
    corrected["cluster_type_fdr"] = np.where(
        corrected["local_significant_fdr"], corrected["cluster_quadrant"], "Not Significant"
    )
    corrected["permutations"] = int(permutations)
    corrected["random_seed"] = int(seed)
    return corrected


def build_local_morans(
    master: pd.DataFrame,
    weights: SpatialWeights,
    permutations: int,
    seed: int,
    alpha: float,
) -> pd.DataFrame:
    """TAVG/TMAX/TMIN/Bias/RMSE의 Local Moran과 metric별 FDR 표를 만든다."""

    frames: list[pd.DataFrame] = []
    metadata = master.set_index("station_id")[["station_name", "region_level1", "latitude", "longitude"]]
    for offset, (column, label) in enumerate(LOCAL_VARIABLES.items()):
        subset = master.loc[master[column].notna()].copy()
        metric_weights = subset_spatial_weights(
            weights, subset["station_id"].astype(str).tolist()
        )
        values = align_values(subset, column, metric_weights)
        local = local_moran_permutation(
            values, metric_weights, permutations, seed + offset, alpha
        )
        local["variable"] = column
        local["label"] = label
        local = local.join(metadata, on="station_id")
        frames.append(local)
    return pd.concat(frames, ignore_index=True)


def validate_moran_outputs(global_results: pd.DataFrame, local_results: pd.DataFrame) -> None:
    """Moran 결과의 유한성·확률범위·station 수를 검사한다."""

    if global_results.empty or not np.isfinite(global_results["moran_i"]).all():
        raise ValueError("Global Moran 결과가 비어 있거나 유한하지 않습니다.")
    if not global_results["permutation_p"].between(0, 1).all():
        raise ValueError("Global Moran permutation p가 0~1 범위를 벗어납니다.")
    if local_results.empty or not local_results["local_i"].map(np.isfinite).all():
        raise ValueError("Local Moran 결과가 비어 있거나 유한하지 않습니다.")
    if not local_results["local_p"].between(0, 1).all() or not local_results["local_fdr_q"].between(0, 1).all():
        raise ValueError("Local Moran p/q가 0~1 범위를 벗어납니다.")
