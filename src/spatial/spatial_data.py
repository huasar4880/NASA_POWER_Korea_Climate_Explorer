"""저장된 Stage-11 결과를 검증하고 공간분석 master table로 결합한다."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT


SPATIAL_CONFIG_PATH = PROJECT_ROOT / "config" / "spatial_analysis.json"
STATION_PATH = PROJECT_ROOT / "output" / "tables" / "nationwide_tier_a_analysis_stations.csv"
NATIONWIDE_TABLE_DIR = PROJECT_ROOT / "output" / "tables" / "nationwide"
INPUT_PATHS = {
    "summary": NATIONWIDE_TABLE_DIR / "nationwide_station_temperature_summary.csv",
    "trends": NATIONWIDE_TABLE_DIR / "nationwide_station_temperature_trends.csv",
    "anomalies": NATIONWIDE_TABLE_DIR / "nationwide_temperature_anomalies_1981_2025.csv",
    "validation": NATIONWIDE_TABLE_DIR / "nationwide_nasa_kma_temperature_validation.csv",
    "thresholds": NATIONWIDE_TABLE_DIR / "nationwide_temperature_threshold_comparison.csv",
    "regional": NATIONWIDE_TABLE_DIR / "nationwide_regional_temperature_summary.csv",
    "associations": NATIONWIDE_TABLE_DIR / "nationwide_validation_spatial_associations.csv",
    "annual": NATIONWIDE_TABLE_DIR / "nationwide_annual_temperature_1981_2025.csv",
    "seasonal": NATIONWIDE_TABLE_DIR / "nationwide_seasonal_temperature_trends.csv",
}


@dataclass(frozen=True)
class SpatialInputs:
    """공간분석이 읽기 전용으로 사용하는 Stage-11 결과표 모음."""

    stations: pd.DataFrame
    summary: pd.DataFrame
    trends: pd.DataFrame
    anomalies: pd.DataFrame
    validation: pd.DataFrame
    thresholds: pd.DataFrame
    regional: pd.DataFrame
    associations: pd.DataFrame
    annual: pd.DataFrame
    seasonal: pd.DataFrame


def load_spatial_config(path: Path = SPATIAL_CONFIG_PATH) -> dict[str, Any]:
    """공간분석 JSON 설정을 읽고 핵심 파라미터 범위를 검증한다."""

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"공간분석 설정을 읽을 수 없습니다: {path}") from exc
    required = {
        "distance_metric", "spatial_weights_method", "knn_k",
        "sensitivity_knn_k", "moran_permutations", "local_moran_permutations",
        "random_seed", "coastal_distance_threshold_km", "fdr_alpha",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"공간분석 설정 누락: {sorted(missing)}")
    if config["distance_metric"] != "haversine":
        raise ValueError("이번 분석에서 지원하는 distance_metric은 haversine입니다.")
    if config["spatial_weights_method"] != "knn":
        raise ValueError("이번 분석에서 지원하는 spatial_weights_method는 knn입니다.")
    if int(config["knn_k"]) < 1 or int(config["moran_permutations"]) < 1:
        raise ValueError("knn_k와 moran_permutations는 1 이상이어야 합니다.")
    if not 0 < float(config["fdr_alpha"]) < 1:
        raise ValueError("fdr_alpha는 0과 1 사이여야 합니다.")
    return config


def _read_csv(path: Path, required: set[str]) -> pd.DataFrame:
    """입력 CSV를 읽고 비어 있거나 필수 컬럼이 없는 경우 중단한다."""

    if not path.exists():
        raise FileNotFoundError(f"Stage-11 입력표가 없습니다: {path}")
    data = pd.read_csv(path)
    if data.empty:
        raise ValueError(f"Stage-11 입력표가 비어 있습니다: {path.name}")
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"{path.name} 필수 컬럼 누락: {sorted(missing)}")
    return data


def _normalize_station_ids(dataframe: pd.DataFrame) -> pd.DataFrame:
    """조인 키인 station_id를 문자열로 정규화한 복사본을 반환한다."""

    result = dataframe.copy()
    if "station_id" in result:
        result["station_id"] = result["station_id"].astype(str)
    return result


def validate_tier_a_station_set(stations: pd.DataFrame) -> None:
    """Final Tier-A station의 키·좌표·기간·manual-review 제외 조건을 검사한다."""

    if stations.empty or stations["station_id"].duplicated().any():
        raise ValueError("Final Tier A station이 비어 있거나 station_id가 중복됩니다.")
    coordinate_columns = ["latitude", "longitude", "elevation_m"]
    if stations[coordinate_columns].isna().any().any():
        raise ValueError("Final Tier A station 좌표 또는 고도가 누락되었습니다.")
    if not stations["actual_data_start_date"].astype(str).eq("1981-01-01").all():
        raise ValueError("Final Tier A에 1981-01-01 이후 시작 station이 포함되었습니다.")
    if not stations["actual_data_end_date"].astype(str).eq("2025-12-31").all():
        raise ValueError("Final Tier A에 2025-12-31 이전 종료 station이 포함되었습니다.")
    for column in ("manual_review_required", "continuity_unresolved"):
        if column in stations and stations[column].astype(str).str.casefold().isin(
            {"true", "1", "yes"}
        ).any():
            raise ValueError(f"Final Tier A에 제외 대상 {column} station이 포함되었습니다.")


def load_spatial_inputs(
    station_path: Path = STATION_PATH,
    input_paths: dict[str, Path] = INPUT_PATHS,
) -> SpatialInputs:
    """API 호출 없이 Final Tier-A 목록과 Stage-11 CSV를 source of truth로 읽는다."""

    stations = _normalize_station_ids(_read_csv(station_path, {
        "station_id", "station_name", "region_level1", "region_level2",
        "latitude", "longitude", "elevation_m", "actual_data_start_date",
        "actual_data_end_date", "temperature_missing_rate", "annual_completeness",
        "continuity_risk",
    }))
    validate_tier_a_station_set(stations)
    requirements = {
        "summary": {"station_id", "kma_tavg_sen_slope_decade"},
        "trends": {
            "station_id", "metric", "kma_sen_slope_per_decade", "kma_fdr_q",
            "kma_significant_fdr", "nasa_sen_slope_per_decade",
        },
        "anomalies": {"station_id", "source", "metric", "year", "anomaly"},
        "validation": {"station_id", "metric", "bias", "mae", "rmse", "pearson_r"},
        "thresholds": {"station_id", "threshold", "kma_sen_slope_per_decade", "nasa_sen_slope_per_decade"},
        "regional": {"region", "station_count"},
        "associations": {"spatial_variable", "validation_metric", "spearman_rho"},
        "annual": {"station_id", "source", "metric", "year", "annual_mean"},
        "seasonal": {"station_id", "source", "metric", "season", "sen_slope_per_decade"},
    }
    loaded = {
        name: _normalize_station_ids(_read_csv(input_paths[name], required))
        for name, required in requirements.items()
    }
    expected = set(stations["station_id"])
    for name in ("summary", "trends", "anomalies", "validation", "thresholds", "annual", "seasonal"):
        observed = set(loaded[name]["station_id"])
        if observed != expected:
            raise ValueError(
                f"{name} station set이 Final Tier A와 다릅니다: "
                f"missing={sorted(expected-observed)}, extra={sorted(observed-expected)}"
            )
    return SpatialInputs(stations=stations, **loaded)


def _metric_rows(data: pd.DataFrame, metric: str) -> pd.DataFrame:
    """station당 한 행인 metric trend subset을 검증해 반환한다."""

    selected = data.loc[data["metric"].eq(metric)].copy()
    if selected["station_id"].duplicated().any():
        raise ValueError(f"중복 trend: {metric}")
    return selected


def build_spatial_station_master(inputs: SpatialInputs) -> pd.DataFrame:
    """Stage-11 위치·추세·validation·threshold 결과를 station당 한 행으로 결합한다."""

    base_columns = [
        "station_id", "station_name", "region_level1", "region_level2", "latitude",
        "longitude", "elevation_m", "temperature_missing_rate",
        "annual_completeness", "continuity_risk",
    ]
    master = inputs.stations.loc[:, base_columns].copy()
    for metric, output in (
        ("TAVG", "kma_tavg_sen_slope"), ("TMAX", "kma_tmax_sen_slope"),
        ("TMIN", "kma_tmin_sen_slope"),
    ):
        selected = _metric_rows(inputs.trends, metric)
        columns = ["station_id", "kma_sen_slope_per_decade"]
        rename = {"kma_sen_slope_per_decade": output}
        if metric == "TAVG":
            columns += ["kma_fdr_q", "kma_significant_fdr", "nasa_sen_slope_per_decade"]
            rename.update({
                "kma_fdr_q": "tavg_fdr_q", "kma_significant_fdr": "tavg_fdr_significant",
                "nasa_sen_slope_per_decade": "nasa_tavg_sen_slope",
            })
        master = master.merge(
            selected.loc[:, columns].rename(columns=rename), on="station_id",
            how="left", validate="one_to_one",
        )
    for metric, prefix in (("TAVG", "tavg"), ("TMAX", "tmax"), ("TMIN", "tmin")):
        selected = inputs.validation.loc[inputs.validation["metric"].eq(metric)].copy()
        metrics = ["bias", "rmse"] if metric != "TAVG" else ["bias", "mae", "rmse", "pearson_r"]
        renamed = {column: f"{prefix}_{'pearson' if column == 'pearson_r' else column}" for column in metrics}
        master = master.merge(
            selected.loc[:, ["station_id", *metrics]].rename(columns=renamed),
            on="station_id", how="left", validate="one_to_one",
        )
    threshold_specs = {
        "TMAX_GE_33": ("days_tmax_ge_33_kma_slope", "days_tmax_ge_33_nasa_slope"),
        "TMIN_GE_25": ("days_tmin_ge_25_kma_slope", "days_tmin_ge_25_nasa_slope"),
    }
    for threshold, (kma_column, nasa_column) in threshold_specs.items():
        selected = inputs.thresholds.loc[inputs.thresholds["threshold"].eq(threshold)]
        master = master.merge(
            selected.loc[:, ["station_id", "kma_sen_slope_per_decade", "nasa_sen_slope_per_decade"]].rename(
                columns={"kma_sen_slope_per_decade": kma_column, "nasa_sen_slope_per_decade": nasa_column}
            ), on="station_id", how="left", validate="one_to_one",
        )
    if len(master) != len(inputs.stations) or master["station_id"].duplicated().any():
        raise ValueError("공간 master의 station 정합성이 깨졌습니다.")
    required_values = [
        "latitude", "longitude", "kma_tavg_sen_slope", "kma_tmax_sen_slope",
        "kma_tmin_sen_slope", "nasa_tavg_sen_slope", "tavg_bias", "tavg_rmse",
    ]
    if master[required_values].isna().any().any():
        raise ValueError("공간 master 핵심 값에 결측이 있습니다.")
    return master.sort_values("station_id", key=lambda s: pd.to_numeric(s, errors="coerce")).reset_index(drop=True)
