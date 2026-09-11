"""위경도 기반 Haversine station 거리 계산."""

from __future__ import annotations

import numpy as np
import pandas as pd


EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
    earth_radius_km: float = EARTH_RADIUS_KM,
) -> float:
    """두 위경도 좌표 사이의 대권거리를 km로 반환한다."""

    lat1, lon1, lat2, lon2 = np.radians(
        [latitude_1, longitude_1, latitude_2, longitude_2]
    )
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = np.sin(delta_lat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    return float(earth_radius_km * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))


def calculate_distance_matrix(
    stations: pd.DataFrame,
    earth_radius_km: float = EARTH_RADIUS_KM,
) -> pd.DataFrame:
    """station 순서가 보존된 대칭 Haversine 거리행렬을 반환한다."""

    required = {"station_id", "latitude", "longitude"}
    missing = required - set(stations)
    if missing:
        raise ValueError(f"거리 계산 필수 컬럼 누락: {sorted(missing)}")
    if stations["station_id"].duplicated().any() or stations[["latitude", "longitude"]].isna().any().any():
        raise ValueError("거리 계산 station ID가 중복되거나 좌표가 누락되었습니다.")
    lat = np.radians(stations["latitude"].to_numpy(dtype=float))
    lon = np.radians(stations["longitude"].to_numpy(dtype=float))
    delta_lat = lat[:, None] - lat[None, :]
    delta_lon = lon[:, None] - lon[None, :]
    a = np.sin(delta_lat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(delta_lon / 2) ** 2
    matrix = earth_radius_km * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.clip(1 - a, 0, 1)))
    np.fill_diagonal(matrix, 0.0)
    ids = stations["station_id"].astype(str).tolist()
    return pd.DataFrame(matrix, index=ids, columns=ids)


def distance_matrix_to_long(matrix: pd.DataFrame) -> pd.DataFrame:
    """square 거리행렬을 station ID 기반 long CSV 형태로 변환한다."""

    if matrix.shape[0] != matrix.shape[1] or list(matrix.index) != list(matrix.columns):
        raise ValueError("거리행렬은 동일 ID 순서의 정방행렬이어야 합니다.")
    result = matrix.rename_axis("station_id").reset_index().melt(
        id_vars="station_id", var_name="other_station_id", value_name="distance_km"
    )
    return result


def add_neighbor_distance_summary(master: pd.DataFrame, matrix: pd.DataFrame) -> pd.DataFrame:
    """station별 최근접 및 다른 station까지의 중앙거리를 master에 연결한다."""

    values = matrix.to_numpy(dtype=float).copy()
    np.fill_diagonal(values, np.nan)
    summary = pd.DataFrame({
        "station_id": matrix.index.astype(str),
        "nearest_neighbor_distance_km": np.nanmin(values, axis=1),
        "median_neighbor_distance_km": np.nanmedian(values, axis=1),
    })
    return master.merge(summary, on="station_id", how="left", validate="one_to_one")


def validate_distance_matrix(matrix: pd.DataFrame, tolerance: float = 1e-9) -> None:
    """거리행렬의 비음수·대칭·self-distance 0 조건을 검사한다."""

    values = matrix.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < -tolerance).any():
        raise ValueError("거리행렬에 음수 또는 유한하지 않은 값이 있습니다.")
    if not np.allclose(values, values.T, atol=tolerance):
        raise ValueError("거리행렬이 대칭이 아닙니다.")
    if not np.allclose(np.diag(values), 0.0, atol=tolerance):
        raise ValueError("거리행렬 self distance가 0이 아닙니다.")
