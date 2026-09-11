"""K-nearest-neighbor 공간가중치 생성과 정렬 검증."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SpatialWeights:
    """station 순서와 row-standardized KNN 가중치 행렬."""

    station_ids: tuple[str, ...]
    matrix: np.ndarray
    neighbors: pd.DataFrame
    method: str
    k: int
    distance_matrix: np.ndarray | None = None


def build_knn_weights(distance_matrix: pd.DataFrame, k: int) -> SpatialWeights:
    """거리 tie를 station ID 순으로 해소하는 directed row-standardized KNN을 만든다."""

    n = len(distance_matrix)
    if n < 2 or not 1 <= int(k) < n:
        raise ValueError(f"KNN k는 1 이상 station 수({n}) 미만이어야 합니다.")
    if list(distance_matrix.index) != list(distance_matrix.columns):
        raise ValueError("KNN 입력 거리행렬의 행·열 ID 순서가 다릅니다.")
    ids = tuple(str(value) for value in distance_matrix.index)
    values = distance_matrix.to_numpy(dtype=float)
    weights = np.zeros((n, n), dtype=float)
    rows: list[dict[str, object]] = []
    for index, station_id in enumerate(ids):
        candidates = [j for j in range(n) if j != index]
        candidates.sort(key=lambda j: (values[index, j], ids[j]))
        selected = candidates[: int(k)]
        weights[index, selected] = 1.0 / int(k)
        for neighbor_index in selected:
            rows.append({
                "station_id": station_id,
                "neighbor_station_id": ids[neighbor_index],
                "distance_km": float(values[index, neighbor_index]),
                "weight": 1.0 / int(k),
                "weights_method": "knn_directed_row_standardized",
                "k": int(k),
            })
    result = SpatialWeights(
        station_ids=ids,
        matrix=weights,
        neighbors=pd.DataFrame(rows),
        method="knn_directed_row_standardized",
        k=int(k),
        distance_matrix=values.copy(),
    )
    validate_spatial_weights(result)
    return result


def validate_spatial_weights(weights: SpatialWeights, tolerance: float = 1e-12) -> None:
    """KNN 행렬의 정렬·유한성·고립 없음·row normalization을 검사한다."""

    matrix = np.asarray(weights.matrix, dtype=float)
    n = len(weights.station_ids)
    if matrix.shape != (n, n):
        raise ValueError("공간가중치 행렬 크기가 station 수와 다릅니다.")
    if not np.isfinite(matrix).all() or (matrix < 0).any():
        raise ValueError("공간가중치에 음수 또는 유한하지 않은 값이 있습니다.")
    if not np.allclose(np.diag(matrix), 0.0, atol=tolerance):
        raise ValueError("공간가중치 self weight는 0이어야 합니다.")
    if (np.count_nonzero(matrix, axis=1) == 0).any():
        raise ValueError("공간가중치에 고립 station이 있습니다.")
    if not np.allclose(matrix.sum(axis=1), 1.0, atol=tolerance):
        raise ValueError("공간가중치 행 합이 1이 아닙니다.")
    if not (np.count_nonzero(matrix, axis=1) == weights.k).all():
        raise ValueError("KNN station별 이웃 수가 k와 다릅니다.")


def subset_spatial_weights(
    weights: SpatialWeights,
    station_ids: list[str] | tuple[str, ...],
) -> SpatialWeights:
    """결측 metric에서 유효 station만 남겨 같은 거리 정의로 KNN을 재구성한다."""

    selected = tuple(str(value) for value in station_ids)
    if selected == weights.station_ids:
        return weights
    if weights.distance_matrix is None:
        raise ValueError("부분 station KNN 재구성에 원 거리행렬이 필요합니다.")
    if len(selected) < 2 or not set(selected).issubset(weights.station_ids):
        raise ValueError("부분 공간가중치 station 구성이 유효하지 않습니다.")
    positions = [weights.station_ids.index(station_id) for station_id in selected]
    distances = weights.distance_matrix[np.ix_(positions, positions)]
    frame = pd.DataFrame(distances, index=selected, columns=selected)
    return build_knn_weights(frame, min(weights.k, len(selected) - 1))


def align_values(
    dataframe: pd.DataFrame,
    value_column: str,
    weights: SpatialWeights,
) -> np.ndarray:
    """station_id에 따라 metric을 weight 순서로 정렬하고 결측·중복을 거부한다."""

    required = {"station_id", value_column}
    missing = required - set(dataframe)
    if missing:
        raise ValueError(f"Moran 입력 컬럼 누락: {sorted(missing)}")
    data = dataframe.loc[:, ["station_id", value_column]].copy()
    data["station_id"] = data["station_id"].astype(str)
    if data["station_id"].duplicated().any():
        raise ValueError("Moran 입력 station_id가 중복됩니다.")
    indexed = data.set_index("station_id").reindex(weights.station_ids)
    values = pd.to_numeric(indexed[value_column], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"Moran 입력 {value_column}에 결측 또는 무한값이 있습니다.")
    return values
