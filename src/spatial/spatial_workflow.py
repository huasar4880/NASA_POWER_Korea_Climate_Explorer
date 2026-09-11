"""Stage-12 API-free 전국 공간 기후패턴 분석 orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT
from src.spatial.associations import (
    build_coordinate_associations,
    build_regional_spatial_summary,
    build_seasonal_morans,
    build_seasonal_spatial_summary,
    build_threshold_spatial_summary,
    build_tmax_tmin_contrast,
    build_validation_spatial_summary,
    calculate_dtr_trends,
)
from src.spatial.autocorrelation import (
    build_global_morans,
    build_local_morans,
    build_weight_sensitivity,
    validate_moran_outputs,
)
from src.spatial.coastal import CoastalAvailability, assess_coastline_availability
from src.spatial.distances import (
    add_neighbor_distance_summary,
    calculate_distance_matrix,
    distance_matrix_to_long,
    validate_distance_matrix,
)
from src.spatial.spatial_data import (
    INPUT_PATHS,
    SPATIAL_CONFIG_PATH,
    STATION_PATH,
    SpatialInputs,
    build_spatial_station_master,
    load_spatial_config,
    load_spatial_inputs,
)
from src.spatial.weights import build_knn_weights


TABLE_DIR = PROJECT_ROOT / "output" / "tables" / "spatial"
CHART_DIR = PROJECT_ROOT / "output" / "charts" / "spatial"
REPORT_DIR = PROJECT_ROOT / "output" / "reports" / "spatial"
MANIFEST_PATH = PROJECT_ROOT / "output" / "manifests" / "spatial_analysis_manifest.json"
TABLE_PATHS = {
    "master": TABLE_DIR / "nationwide_spatial_station_master.csv",
    "distances": TABLE_DIR / "nationwide_station_distance_matrix.csv",
    "neighbors": TABLE_DIR / "nationwide_spatial_neighbors.csv",
    "sensitivity": TABLE_DIR / "nationwide_spatial_weight_sensitivity.csv",
    "global_morans": TABLE_DIR / "nationwide_global_morans_i.csv",
    "local_morans": TABLE_DIR / "nationwide_local_moran_results.csv",
    "latitude": TABLE_DIR / "nationwide_latitude_associations.csv",
    "longitude": TABLE_DIR / "nationwide_longitude_associations.csv",
    "elevation": TABLE_DIR / "nationwide_elevation_associations.csv",
    "contrast": TABLE_DIR / "nationwide_tmax_tmin_warming_contrast.csv",
    "dtr": TABLE_DIR / "nationwide_dtr_trends.csv",
    "seasonal": TABLE_DIR / "nationwide_seasonal_spatial_summary.csv",
    "seasonal_morans": TABLE_DIR / "nationwide_seasonal_morans_i.csv",
    "dominant": TABLE_DIR / "nationwide_station_dominant_warming_season.csv",
    "threshold": TABLE_DIR / "nationwide_spatial_threshold_summary.csv",
    "validation": TABLE_DIR / "nationwide_spatial_validation_summary.csv",
    "regional": TABLE_DIR / "nationwide_regional_spatial_summary.csv",
}


@dataclass(frozen=True)
class SpatialProducts:
    """Stage-12에서 별도 namespace에 저장하는 계산 결과표."""

    master: pd.DataFrame
    distances: pd.DataFrame
    neighbors: pd.DataFrame
    sensitivity: pd.DataFrame
    global_morans: pd.DataFrame
    local_morans: pd.DataFrame
    latitude: pd.DataFrame
    longitude: pd.DataFrame
    elevation: pd.DataFrame
    contrast: pd.DataFrame
    dtr: pd.DataFrame
    seasonal: pd.DataFrame
    seasonal_morans: pd.DataFrame
    dominant: pd.DataFrame
    threshold: pd.DataFrame
    validation: pd.DataFrame
    regional: pd.DataFrame


@dataclass(frozen=True)
class SpatialRunResult:
    """CLI 보고용 공간분석 실행 결과."""

    station_count: int
    config: dict[str, Any]
    coastline: CoastalAvailability
    products: SpatialProducts | None
    table_paths: dict[str, Path]
    chart_paths: dict[str, Path]
    report_paths: tuple[Path, Path] | None
    manifest_path: Path | None
    dry_run: bool


def expected_spatial_outputs() -> list[Path]:
    """dry-run에서 표시할 예상 output 파일 목록을 반환한다."""

    chart_names = [
        "kma_tavg_spatial_pattern.html", "kma_tmax_spatial_pattern.html",
        "kma_tmin_spatial_pattern.html", "tmax_tmin_warming_contrast.html",
        "dominant_warming_season.html", "days_tmax_ge_33_proxy.html",
        "days_tmin_ge_25_proxy.html", "nasa_kma_tavg_bias.html",
        "nasa_kma_tavg_rmse.html", "local_moran_tavg.html",
        "kma_tavg_spatial_pattern.png", "tmax_tmin_warming_contrast.png",
        "seasonal_warming_spatial_summary.png", "latitude_vs_tavg_slope.png",
        "elevation_vs_tavg_slope.png", "elevation_vs_bias.png", "elevation_vs_rmse.png",
        "tmax_vs_tmin_slope.png", "local_moran_tavg.png",
        "seasonal_djf_tavg_spatial_pattern.html", "seasonal_mam_tavg_spatial_pattern.html",
        "seasonal_jja_tavg_spatial_pattern.html", "seasonal_son_tavg_spatial_pattern.html",
    ]
    return [
        *TABLE_PATHS.values(), *(CHART_DIR / name for name in chart_names),
        REPORT_DIR / "nationwide_spatial_climate_analysis_report.html",
        REPORT_DIR / "nationwide_spatial_climate_analysis_report.md", MANIFEST_PATH,
    ]


def build_spatial_products(inputs: SpatialInputs, config: dict[str, Any]) -> SpatialProducts:
    """Stage-11 inputs에서 모든 Stage-12 표를 메모리 내 계산한다."""

    master = build_spatial_station_master(inputs)
    distance_matrix = calculate_distance_matrix(master, float(config.get("earth_radius_km", 6371.0088)))
    validate_distance_matrix(distance_matrix)
    master = add_neighbor_distance_summary(master, distance_matrix)
    k_values = [int(value) for value in config["sensitivity_knn_k"]]
    if int(config["knn_k"]) not in k_values:
        k_values.append(int(config["knn_k"]))
    if max(k_values) >= len(master):
        raise ValueError("KNN sensitivity k가 station 수 이상입니다.")
    sensitivity = build_weight_sensitivity(
        master, distance_matrix, sorted(set(k_values)), int(config["moran_permutations"]),
        int(config["random_seed"]),
    )
    weights = build_knn_weights(distance_matrix, int(config["knn_k"]))
    global_morans = build_global_morans(
        master, weights, int(config["moran_permutations"]), int(config["random_seed"])
    )
    local_morans = build_local_morans(
        master, weights, int(config["local_moran_permutations"]),
        int(config["random_seed"]), float(config["fdr_alpha"]),
    )
    validate_moran_outputs(global_morans, local_morans)
    associations = build_coordinate_associations(master)
    contrast = build_tmax_tmin_contrast(master)
    dtr = calculate_dtr_trends(inputs.annual, master, float(config["fdr_alpha"]))
    seasonal, dominant = build_seasonal_spatial_summary(inputs.seasonal, master)
    seasonal_morans = build_seasonal_morans(
        seasonal, weights, int(config["moran_permutations"]), int(config["random_seed"]) + 100
    )
    threshold = build_threshold_spatial_summary(
        master, weights, int(config["moran_permutations"]), int(config["random_seed"])
    )
    validation = build_validation_spatial_summary(
        master, weights, int(config["moran_permutations"]), int(config["random_seed"])
    )
    regional = build_regional_spatial_summary(master)
    return SpatialProducts(
        master=master, distances=distance_matrix_to_long(distance_matrix), neighbors=weights.neighbors,
        sensitivity=sensitivity, global_morans=global_morans, local_morans=local_morans,
        latitude=associations["latitude"], longitude=associations["longitude"],
        elevation=associations["elevation_m"], contrast=contrast, dtr=dtr,
        seasonal=seasonal, seasonal_morans=seasonal_morans, dominant=dominant,
        threshold=threshold, validation=validation, regional=regional,
    )


def _atomic_csv(dataframe: pd.DataFrame, path: Path) -> Path:
    """완성된 공간분석 CSV를 전용 namespace에서 원자적으로 교체한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    dataframe.to_csv(temporary, index=False)
    temporary.replace(path)
    return path


def save_spatial_products(products: SpatialProducts) -> dict[str, Path]:
    """모든 계산표를 output/tables/spatial에만 저장한다."""

    return {name: _atomic_csv(getattr(products, name), path) for name, path in TABLE_PATHS.items()}


def _relative(path: Path) -> str:
    """manifest에 개인 절대경로가 아닌 프로젝트 상대경로를 쓴다."""

    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def _sha256(path: Path) -> str:
    """입력 provenance용 SHA-256을 계산한다."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_spatial_manifest(
    station_count: int,
    config: dict[str, Any],
    table_paths: dict[str, Path],
    chart_paths: dict[str, Path],
    report_paths: tuple[Path, Path],
    coastline: CoastalAvailability,
) -> Path:
    """입력 hash·설정·seed·산출물 목록을 JSON manifest로 저장한다."""

    input_files = {"stations": STATION_PATH, **INPUT_PATHS, "config": SPATIAL_CONFIG_PATH}
    payload = {
        "version": 1,
        "analysis_stage": "12 experimental nationwide spatial analysis",
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        "station_count": int(station_count),
        "input_files": {
            name: {"path": _relative(path), "sha256": _sha256(path)}
            for name, path in input_files.items()
        },
        "spatial_config": config,
        "weight_method": config["spatial_weights_method"],
        "k": int(config["knn_k"]),
        "moran_permutations": int(config["moran_permutations"]),
        "local_moran_permutations": int(config["local_moran_permutations"]),
        "random_seed": int(config["random_seed"]),
        "coastline_analysis": {
            "available": coastline.available, "source": coastline.source,
            "license": coastline.license, "reason": coastline.reason,
        },
        "generated_tables": [_relative(path) for path in table_paths.values()],
        "generated_charts": [_relative(path) for path in chart_paths.values()],
        "generated_reports": [_relative(path) for path in report_paths],
        "api_calls": 0,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(MANIFEST_PATH)
    return MANIFEST_PATH


def _build_and_save_report(
    products: SpatialProducts,
    config: dict[str, Any],
    coastline: CoastalAvailability,
) -> tuple[Path, Path]:
    """계산표에서 deterministic 공간분석 보고서를 생성한다."""

    from src.spatial.reporting import build_spatial_report_markdown, save_spatial_report

    markdown = build_spatial_report_markdown(
        products.master, products.global_morans, products.local_morans,
        products.latitude, products.elevation, products.contrast, products.dtr,
        products.seasonal, products.seasonal_morans, products.dominant,
        products.threshold, products.validation, products.regional,
        products.sensitivity, config, coastline.reason,
    )
    return save_spatial_report(markdown, REPORT_DIR)


def generate_spatial_report_from_saved_tables(
    config_path: Path = SPATIAL_CONFIG_PATH,
) -> tuple[Path, Path]:
    """API 호출 없이 저장된 Stage-12 표만 읽어 보고서를 재생성한다."""

    missing = [str(path) for path in TABLE_PATHS.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("공간분석 보고서 입력표가 없습니다: " + ", ".join(missing))
    products = SpatialProducts(**{
        name: pd.read_csv(path, dtype={"station_id": str, "other_station_id": str})
        for name, path in TABLE_PATHS.items()
    })
    return _build_and_save_report(products, load_spatial_config(config_path), assess_coastline_availability())


def run_spatial_analysis(
    *,
    dry_run: bool = False,
    config_path: Path = SPATIAL_CONFIG_PATH,
    inputs: SpatialInputs | None = None,
) -> SpatialRunResult:
    """Final Tier-A Stage-11 결과만 읽어 Stage-12 공간분석을 실행한다."""

    config = load_spatial_config(config_path)
    selected_inputs = inputs if inputs is not None else load_spatial_inputs()
    coastline = assess_coastline_availability()
    station_count = len(selected_inputs.stations)
    if dry_run:
        return SpatialRunResult(station_count, config, coastline, None, {}, {}, None, None, True)
    products = build_spatial_products(selected_inputs, config)
    table_paths = save_spatial_products(products)
    from src.spatial.visualization import save_interactive_spatial_maps, save_static_spatial_charts

    chart_paths = save_interactive_spatial_maps(
        products.master, products.contrast, products.dominant, products.local_morans,
        products.seasonal, CHART_DIR
    )
    chart_paths.update(save_static_spatial_charts(
        products.master, products.contrast, products.seasonal, products.local_morans, CHART_DIR
    ))
    report_paths = _build_and_save_report(products, config, coastline)
    manifest_path = save_spatial_manifest(
        station_count, config, table_paths, chart_paths, report_paths, coastline
    )
    return SpatialRunResult(
        station_count, config, coastline, products, table_paths, chart_paths,
        report_paths, manifest_path, False,
    )
