"""Stage-12 Final Tier-A 전국 공간분석의 API-free 회귀 테스트."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dashboard.data_loader import load_spatial_station_master
from src.spatial.associations import (
    build_coordinate_associations,
    build_regional_spatial_summary,
    build_seasonal_morans,
    build_seasonal_spatial_summary,
    build_threshold_spatial_summary,
    build_tmax_tmin_contrast,
    build_validation_spatial_summary,
    calculate_association,
    calculate_dtr_trends,
    validate_associations,
)
from src.spatial.autocorrelation import (
    build_global_morans,
    build_local_morans,
    build_weight_sensitivity,
    global_moran_permutation,
    moran_i,
    validate_moran_outputs,
)
from src.spatial.coastal import assess_coastline_availability
from src.spatial.distances import (
    add_neighbor_distance_summary,
    calculate_distance_matrix,
    distance_matrix_to_long,
    haversine_distance_km,
    validate_distance_matrix,
)
from src.spatial.reporting import build_spatial_report_markdown, save_spatial_report
from src.spatial.spatial_data import (
    INPUT_PATHS,
    STATION_PATH,
    build_spatial_station_master,
    load_spatial_config,
    load_spatial_inputs,
    validate_tier_a_station_set,
)
from src.spatial.spatial_workflow import (
    MANIFEST_PATH,
    TABLE_PATHS,
    SpatialProducts,
    build_spatial_products,
    expected_spatial_outputs,
    run_spatial_analysis,
)
from src.spatial.visualization import create_spatial_value_map
from src.spatial.weights import align_values, build_knn_weights, validate_spatial_weights


@pytest.fixture(scope="module")
def real_inputs():
    """Load the persisted Stage-11 source-of-truth tables once."""

    return load_spatial_inputs()


@pytest.fixture(scope="module")
def real_products(real_inputs):
    """Build real Stage-12 calculations in memory with short test permutations."""

    config = load_spatial_config()
    config = {**config, "moran_permutations": 19, "local_moran_permutations": 19}
    return build_spatial_products(real_inputs, config)


@pytest.fixture()
def sample_master() -> pd.DataFrame:
    """Return six non-collinear stations with every core spatial metric."""

    return pd.DataFrame({
        "station_id": [str(index) for index in range(1, 7)],
        "station_name": [f"S{index}" for index in range(1, 7)],
        "region_level1": ["A", "A", "A", "B", "B", "C"],
        "region_level2": ["x"] * 6,
        "latitude": [33.5, 34.2, 35.0, 36.0, 37.0, 38.0],
        "longitude": [126.5, 127.0, 128.0, 127.5, 129.0, 128.5],
        "elevation_m": [10.0, 30.0, 60.0, 100.0, 150.0, 250.0],
        "temperature_missing_rate": [0.0] * 6,
        "annual_completeness": [1.0] * 6,
        "continuity_risk": ["low"] * 6,
        "kma_tavg_sen_slope": [0.20, 0.24, 0.31, 0.40, 0.48, 0.55],
        "kma_tmax_sen_slope": [0.15, 0.20, 0.28, 0.35, 0.42, 0.50],
        "kma_tmin_sen_slope": [0.25, 0.29, 0.35, 0.45, 0.52, 0.60],
        "nasa_tavg_sen_slope": [0.18, 0.22, 0.30, 0.39, 0.47, 0.53],
        "tavg_fdr_q": [0.01] * 6,
        "tavg_fdr_significant": [True] * 6,
        "tavg_bias": [-1.0, -0.8, -0.4, 0.1, 0.4, 0.7],
        "tavg_mae": [1.2, 1.1, 1.0, 1.1, 1.3, 1.5],
        "tavg_rmse": [1.5, 1.4, 1.3, 1.5, 1.7, 2.0],
        "tavg_pearson": [0.99] * 6,
        "tmax_bias": [-1.0] * 6,
        "tmax_rmse": [2.0] * 6,
        "tmin_bias": [0.5] * 6,
        "tmin_rmse": [1.8] * 6,
        "days_tmax_ge_33_kma_slope": [0.1, 0.3, 0.5, 0.9, 1.2, 1.6],
        "days_tmax_ge_33_nasa_slope": [0.0, 0.0, 0.1, 0.2, 0.3, 0.5],
        "days_tmin_ge_25_kma_slope": [0.0, 0.1, 0.2, 0.6, 1.0, 1.5],
        "days_tmin_ge_25_nasa_slope": [0.0, 0.1, 0.3, 0.7, 1.2, 1.8],
    })


@pytest.fixture()
def sample_weights(sample_master):
    matrix = calculate_distance_matrix(sample_master)
    return build_knn_weights(matrix, 2)


def test_spatial_config_parameters() -> None:
    config = load_spatial_config()
    assert config["distance_metric"] == "haversine"
    assert config["spatial_weights_method"] == "knn"
    assert {3, 4, 5}.issubset(set(config["sensitivity_knn_k"]))


def test_tier_a_only_selection(real_inputs) -> None:
    assert len(real_inputs.stations) == real_inputs.stations["station_id"].nunique()
    assert set(real_inputs.stations["continuity_risk"]) <= {"low", "medium"}


def test_manual_review_station_is_rejected(real_inputs) -> None:
    stations = real_inputs.stations.copy()
    stations["manual_review_required"] = False
    stations.loc[stations.index[0], "manual_review_required"] = True
    with pytest.raises(ValueError, match="manual_review_required"):
        validate_tier_a_station_set(stations)


def test_coordinate_completeness(real_inputs) -> None:
    assert real_inputs.stations[["latitude", "longitude", "elevation_m"]].notna().all().all()


def test_spatial_master_creation(real_inputs) -> None:
    master = build_spatial_station_master(real_inputs)
    assert len(master) == len(real_inputs.stations)
    assert master["station_id"].is_unique


def test_spatial_master_required_columns(real_inputs) -> None:
    master = build_spatial_station_master(real_inputs)
    assert {
        "kma_tavg_sen_slope", "kma_tmax_sen_slope", "kma_tmin_sen_slope",
        "nasa_tavg_sen_slope", "tavg_fdr_q", "tavg_bias", "tavg_rmse",
        "days_tmax_ge_33_kma_slope", "days_tmin_ge_25_kma_slope",
    }.issubset(master.columns)


def test_haversine_self_distance() -> None:
    assert haversine_distance_km(37.5, 127.0, 37.5, 127.0) == pytest.approx(0.0)


def test_haversine_one_degree_latitude() -> None:
    assert haversine_distance_km(36.0, 127.0, 37.0, 127.0) == pytest.approx(111.195, rel=0.002)


def test_distance_matrix_symmetry(sample_master) -> None:
    matrix = calculate_distance_matrix(sample_master)
    assert np.allclose(matrix.to_numpy(), matrix.to_numpy().T)
    validate_distance_matrix(matrix)


def test_distance_matrix_self_zero(sample_master) -> None:
    matrix = calculate_distance_matrix(sample_master)
    assert np.allclose(np.diag(matrix), 0.0)


def test_distance_long_format(sample_master) -> None:
    result = distance_matrix_to_long(calculate_distance_matrix(sample_master))
    assert len(result) == len(sample_master) ** 2
    assert {"station_id", "other_station_id", "distance_km"} == set(result)


def test_neighbor_distance_summary(sample_master) -> None:
    result = add_neighbor_distance_summary(sample_master, calculate_distance_matrix(sample_master))
    assert result["nearest_neighbor_distance_km"].gt(0).all()
    assert result["median_neighbor_distance_km"].ge(result["nearest_neighbor_distance_km"]).all()


def test_knn_neighbor_count(sample_weights) -> None:
    assert sample_weights.neighbors.groupby("station_id").size().eq(2).all()


def test_spatial_weight_row_normalization(sample_weights) -> None:
    assert np.allclose(sample_weights.matrix.sum(axis=1), 1.0)
    validate_spatial_weights(sample_weights)


def test_knn_has_no_isolated_station(sample_weights) -> None:
    assert (np.count_nonzero(sample_weights.matrix, axis=1) > 0).all()


def test_moran_input_alignment(sample_master, sample_weights) -> None:
    shuffled = sample_master.sample(frac=1, random_state=3)
    values = align_values(shuffled, "kma_tavg_sen_slope", sample_weights)
    assert values.tolist() == sample_master.set_index("station_id").loc[list(sample_weights.station_ids), "kma_tavg_sen_slope"].tolist()


def test_global_moran_finite(sample_master, sample_weights) -> None:
    values = align_values(sample_master, "kma_tavg_sen_slope", sample_weights)
    assert np.isfinite(moran_i(values, sample_weights.matrix))


def test_global_moran_reproducibility(sample_master, sample_weights) -> None:
    values = align_values(sample_master, "kma_tavg_sen_slope", sample_weights)
    first = global_moran_permutation(values, sample_weights.matrix, 39, 11)
    second = global_moran_permutation(values, sample_weights.matrix, 39, 11)
    assert first == second


def test_moran_permutation_seed_is_recorded(sample_master, sample_weights) -> None:
    result = build_global_morans(sample_master, sample_weights, 19, 701)
    assert result["random_seed"].tolist() == list(range(701, 709))


def test_weight_sensitivity_k_values(sample_master) -> None:
    matrix = calculate_distance_matrix(sample_master)
    result = build_weight_sensitivity(sample_master, matrix, [1, 2, 3], 9, 22)
    assert set(result["k"]) == {1, 2, 3}
    assert len(result) == 24


def test_missing_metric_excludes_only_that_moran(sample_master, sample_weights) -> None:
    data = sample_master.copy()
    data.loc[data.index[0], "tavg_rmse"] = np.nan
    result = build_global_morans(data, sample_weights, 9, 22)
    assert result.loc[result["variable"].eq("tavg_rmse"), "n_stations"].iloc[0] == 5
    assert result.loc[result["variable"].ne("tavg_rmse"), "n_stations"].eq(6).all()
    assert len(data) == 6


def test_local_moran_output(sample_master, sample_weights) -> None:
    result = build_local_morans(sample_master, sample_weights, 19, 31, 0.05)
    assert len(result) == len(sample_master) * 5
    assert result["neighbor_count"].eq(2).all()


def test_local_moran_fdr(sample_master, sample_weights) -> None:
    result = build_local_morans(sample_master, sample_weights, 19, 31, 0.05)
    assert result["local_fdr_q"].between(0, 1).all()
    validate_moran_outputs(build_global_morans(sample_master, sample_weights, 9, 31), result)


def test_local_moran_cluster_categories(sample_master, sample_weights) -> None:
    result = build_local_morans(sample_master, sample_weights, 19, 31, 0.05)
    expected = {"High-High", "Low-Low", "High-Low", "Low-High", "Not Significant"}
    assert set(result["cluster_type_fdr"]) <= expected


def test_latitude_association(sample_master) -> None:
    result = calculate_association(sample_master, "latitude", "kma_tavg_sen_slope")
    assert result["n_stations_used"] == 6
    assert -1 <= result["pearson_r"] <= 1


def test_elevation_association(sample_master) -> None:
    outputs = build_coordinate_associations(sample_master)
    assert len(outputs["elevation_m"]) == 5
    assert "tavg_rmse" in outputs["elevation_m"]["climate_metric"].tolist()


def test_association_sanity(sample_master) -> None:
    outputs = build_coordinate_associations(sample_master)
    combined = pd.concat(outputs.values(), ignore_index=True)
    validate_associations(combined)
    assert combined["regression_r_squared"].between(0, 1).all()


def test_tmin_tmax_contrast(sample_master) -> None:
    result = build_tmax_tmin_contrast(sample_master)
    assert np.allclose(result["tmin_minus_tmax"], result["tmin_slope"] - result["tmax_slope"])
    assert result["contrast_direction"].eq("TMIN warming faster").all()


def test_dtr_calculation(sample_master) -> None:
    rows = []
    for source in ("KMA", "NASA"):
        for year in range(1981, 1987):
            rows.extend([
                {"station_id": "1", "source": source, "metric": "TMAX", "year": year, "annual_mean": 20 + 0.2 * (year - 1981)},
                {"station_id": "1", "source": source, "metric": "TMIN", "year": year, "annual_mean": 10 + 0.1 * (year - 1981)},
            ])
    result = calculate_dtr_trends(pd.DataFrame(rows), sample_master.iloc[:1], 0.05)
    assert len(result) == 2
    assert result["sen_slope_per_decade"].to_numpy() == pytest.approx([1.0, 1.0])


def _seasonal_sample(sample_master) -> pd.DataFrame:
    rows = []
    for station in sample_master.itertuples(index=False):
        for offset, season in enumerate(["DJF", "MAM", "JJA", "SON"]):
            rows.append({
                "station_id": station.station_id, "station_name": station.station_name,
                "region_level1": station.region_level1, "latitude": station.latitude,
                "longitude": station.longitude, "elevation_m": station.elevation_m,
                "source": "KMA", "metric": "TAVG", "season": season,
                "sen_slope_per_decade": station.kma_tavg_sen_slope + offset * 0.01,
                "fdr_q_value": 0.01, "significant_fdr": True,
            })
    return pd.DataFrame(rows)


def test_seasonal_spatial_input(sample_master) -> None:
    summary, _ = build_seasonal_spatial_summary(_seasonal_sample(sample_master), sample_master)
    assert len(summary) == len(sample_master) * 4
    assert set(summary["season"]) == {"DJF", "MAM", "JJA", "SON"}


def test_dominant_season(sample_master) -> None:
    _, dominant = build_seasonal_spatial_summary(_seasonal_sample(sample_master), sample_master)
    assert dominant["dominant_warming_season"].eq("SON").all()
    assert dominant["tie_count"].eq(1).all()


def test_seasonal_moran(sample_master, sample_weights) -> None:
    summary, _ = build_seasonal_spatial_summary(_seasonal_sample(sample_master), sample_master)
    result = build_seasonal_morans(summary, sample_weights, 9, 40)
    assert len(result) == 4
    assert result["permutation_p"].between(0, 1).all()


def test_threshold_spatial_input(sample_master, sample_weights) -> None:
    result = build_threshold_spatial_summary(sample_master, sample_weights, 9, 50)
    assert len(result) == 4
    assert set(result["threshold"]) == {"TMAX_GE_33", "TMIN_GE_25"}
    assert result["proxy_notice"].str.contains("not an official").all()


def test_bias_rmse_spatial_input(sample_master, sample_weights) -> None:
    result = build_validation_spatial_summary(sample_master, sample_weights, 9, 60)
    assert set(result["validation_metric"]) == {"tavg_bias", "tavg_rmse"}
    assert result["permutation_p"].between(0, 1).all()


def test_regional_small_sample_flag(sample_master) -> None:
    result = build_regional_spatial_summary(sample_master)
    assert not bool(result.loc[result["region_level1"].eq("A"), "small_sample_region"].iloc[0])
    assert bool(result.loc[result["region_level1"].eq("C"), "small_sample_region"].iloc[0])


def test_coastal_analysis_is_safely_deferred() -> None:
    result = assess_coastline_availability()
    assert result.available is False
    assert "deferred" in result.reason


def test_dry_run_has_no_products_or_paths() -> None:
    result = run_spatial_analysis(dry_run=True)
    assert result.dry_run and result.products is None
    assert result.table_paths == {} and result.chart_paths == {}
    assert len(expected_spatial_outputs()) > len(TABLE_PATHS)


def test_dry_run_does_not_modify_spatial_outputs() -> None:
    before = {path: path.stat().st_mtime_ns for path in TABLE_PATHS.values() if path.exists()}
    run_spatial_analysis(dry_run=True)
    after = {path: path.stat().st_mtime_ns for path in before}
    assert before == after


def test_no_api_call(monkeypatch) -> None:
    import requests

    def fail(*args, **kwargs):
        raise AssertionError("spatial analysis must not call an API")

    monkeypatch.setattr(requests.sessions.Session, "request", fail)
    result = run_spatial_analysis(dry_run=True)
    assert result.station_count > 0


def test_stage11_input_unchanged_by_build(real_inputs) -> None:
    path = INPUT_PATHS["trends"]
    before = hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
    build_spatial_products(real_inputs, {**load_spatial_config(), "moran_permutations": 9, "local_moran_permutations": 9})
    after = hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
    assert before == after


def test_spatial_manifest() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["api_calls"] == 0
    assert payload["station_count"] > 0
    assert payload["random_seed"] == load_spatial_config()["random_seed"]
    assert payload["generated_tables"] and payload["generated_charts"]


def test_dashboard_spatial_loader() -> None:
    data = load_spatial_station_master()
    assert len(data) == pd.read_csv(STATION_PATH).shape[0]
    assert data[["latitude", "longitude"]].notna().all().all()


def test_spatial_report_rendering(real_products, tmp_path: Path) -> None:
    config = {**load_spatial_config(), "moran_permutations": 19, "local_moran_permutations": 19}
    markdown = build_spatial_report_markdown(
        real_products.master, real_products.global_morans, real_products.local_morans,
        real_products.latitude, real_products.elevation, real_products.contrast,
        real_products.dtr, real_products.seasonal, real_products.seasonal_morans,
        real_products.dominant, real_products.threshold, real_products.validation,
        real_products.regional, real_products.sensitivity, config,
        assess_coastline_availability().reason,
    )
    html_path, markdown_path = save_spatial_report(markdown, tmp_path)
    assert html_path.stat().st_size > 0 and markdown_path.stat().st_size > 0
    assert "## 16. Limitations" in markdown


def test_map_html_contains_station_label(sample_master, tmp_path: Path) -> None:
    figure = create_spatial_value_map(sample_master, "kma_tavg_sen_slope", "Test", "unit")
    path = tmp_path / "map.html"
    figure.write_html(path, include_plotlyjs=False)
    assert path.stat().st_size > 0
    assert "S1" in path.read_text(encoding="utf-8")
