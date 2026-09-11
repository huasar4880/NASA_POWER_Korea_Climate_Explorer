"""11단계 Final Tier-A 전국 기온분석의 API-free 회귀 테스트."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.nasa_power import DownloadResult
from src.nationwide.tier_a_analysis import (
    build_elevation_summary,
    build_nationwide_products,
    build_rankings,
    build_regional_summary,
    build_spatial_associations,
    build_station_summary,
    build_trend_consistency,
    calculate_normals_and_anomalies,
    calculate_station_annual_temperature,
    calculate_station_trends,
    calculate_temperature_validation,
    calculate_threshold_annual,
)
from src.nationwide.tier_a_pipeline import (
    ANALYSIS_END,
    ANALYSIS_START,
    EXPECTED_DAYS,
    PreparedStation,
    build_download_plan,
    download_nasa_station,
    kma_processed_path,
    load_analysis_manifest,
    load_tier_a_stations,
    match_station_temperature,
    nasa_query_coordinates,
    nasa_raw_path,
    prepare_station,
    preprocess_kma_temperature,
)
from src.nationwide.tier_a_visualization import nationwide_map_dataframe


def _stations() -> pd.DataFrame:
    return pd.DataFrame([{
        "station_id": "999", "station_name": "Test", "region_level1": "Region",
        "region_level2": "County", "latitude": 36.0, "longitude": 128.0,
        "elevation_m": 100.0, "actual_data_start_date": "1981-01-01",
        "actual_data_end_date": "2025-12-31", "temperature_missing_rate": 0.0,
        "annual_completeness": 1.0, "continuity_risk": "low",
        "nasa_query_latitude": 36.0, "nasa_query_longitude": 128.0,
    }])


@pytest.fixture(scope="module")
def synthetic_prepared() -> tuple[pd.DataFrame, PreparedStation]:
    stations = _stations()
    dates = pd.date_range(ANALYSIS_START, ANALYSIS_END, freq="D")
    years = dates.year.to_numpy()
    seasonal = 12 * np.sin(2 * np.pi * (dates.dayofyear.to_numpy() - 80) / 365.25)
    annual_noise = np.random.default_rng(7).normal(0.0, 0.4, 45)
    trend = 0.03 * (years - 1981) + annual_noise[years - 1981]
    kma_avg = 12.0 + seasonal + trend
    nasa_avg = kma_avg + 0.5
    nasa = pd.DataFrame({
        "date": dates, "station_id": "999", "station_name": "Test",
        "T2M": nasa_avg, "T2M_MAX": nasa_avg + 6.0, "T2M_MIN": nasa_avg - 6.0,
    })
    kma = pd.DataFrame({
        "date": dates, "station_id": "999", "station_name": "Test",
        "avg_temperature": kma_avg, "max_temperature": kma_avg + 6.0,
        "min_temperature": kma_avg - 6.0,
    })
    matched = match_station_temperature(nasa, kma, stations.iloc[0])
    prepared = PreparedStation(
        "999", "Test", "cache", Path("raw.csv"), Path("nasa.csv"),
        Path("kma.csv"), Path("matched.csv"), nasa, kma, matched,
    )
    return stations, prepared


@pytest.fixture(scope="module")
def products(synthetic_prepared):
    stations, prepared = synthetic_prepared
    return build_nationwide_products([prepared], stations)


def _selection_files(tmp_path: Path, manual: bool = False) -> tuple[Path, Path]:
    shortlist = pd.DataFrame([
        {"station_id": "1", "station_name": "A", "region": "R C", "latitude": 36,
         "longitude": 128, "elevation_m": 10, "analysis_start": "1981-01-01",
         "analysis_end": "2025-12-31", "eligibility_tier": "A",
         "temperature_missing_rate": 0, "annual_completeness": 1,
         "continuity_risk": "low", "recommended_analysis_period": "1981~2025",
         "nasa_query_latitude": 36, "nasa_query_longitude": 128, "notes": ""},
        {"station_id": "2", "station_name": "B", "region": "R C", "latitude": 35,
         "longitude": 127, "elevation_m": 20, "analysis_start": "1991-01-01",
         "analysis_end": "2025-12-31", "eligibility_tier": "B",
         "temperature_missing_rate": 0, "annual_completeness": 1,
         "continuity_risk": "low", "recommended_analysis_period": "1991~2025",
         "nasa_query_latitude": 35, "nasa_query_longitude": 127, "notes": ""},
    ])
    master = pd.DataFrame([
        {"station_id": "1", "region_level1": "R", "region_level2": "C",
         "actual_data_start_date": "1981-01-01", "actual_data_end_date": "2025-12-31",
         "core_temperature_missing_rate": 0.0, "annual_completeness_median": 1.0,
         "eligible_1981_2025": True, "manual_review_required": manual},
        {"station_id": "2", "region_level1": "R", "region_level2": "C",
         "actual_data_start_date": "1991-01-01", "actual_data_end_date": "2025-12-31",
         "core_temperature_missing_rate": 0.0, "annual_completeness_median": 1.0,
         "eligible_1981_2025": False, "manual_review_required": False},
    ])
    shortlist_path, master_path = tmp_path / "short.csv", tmp_path / "master.csv"
    shortlist.to_csv(shortlist_path, index=False)
    master.to_csv(master_path, index=False)
    return shortlist_path, master_path


def test_tier_a_station_selection(tmp_path):
    shortlist, master = _selection_files(tmp_path)
    selected = load_tier_a_stations(shortlist, master)
    assert selected["station_id"].tolist() == ["1"]


def test_manual_review_is_excluded(tmp_path):
    shortlist, master = _selection_files(tmp_path, manual=True)
    with pytest.raises(ValueError, match="Tier A"):
        load_tier_a_stations(shortlist, master)


def test_nationwide_nasa_cache_path_contains_station_id():
    assert nasa_raw_path("108").name.startswith("108_")
    assert "1981_2025" in nasa_raw_path("108").name


def test_station_coordinate_query():
    assert nasa_query_coordinates(_stations().iloc[0]) == (36.0, 128.0)


def test_kma_processed_path_is_separate():
    path = kma_processed_path("108")
    assert path.parent.name == "nationwide_kma_processed"
    assert path.name.startswith("108_")


def test_kma_processed_station_data(synthetic_prepared):
    stations, prepared = synthetic_prepared
    raw = pd.DataFrame({
        "tm": prepared.kma["date"].dt.strftime("%Y-%m-%d"), "stnId": "999",
        "avgTa": prepared.kma["avg_temperature"], "maxTa": prepared.kma["max_temperature"],
        "minTa": prepared.kma["min_temperature"],
    })
    result = preprocess_kma_temperature(raw, stations.iloc[0])
    assert len(result) == EXPECTED_DAYS
    assert result[["avg_temperature", "max_temperature", "min_temperature"]].notna().all().all()


def test_kma_missing_observation_date_is_nan_not_invented(synthetic_prepared):
    stations, prepared = synthetic_prepared
    raw = pd.DataFrame({
        "tm": prepared.kma["date"].dt.strftime("%Y-%m-%d"), "stnId": "999",
        "avgTa": prepared.kma["avg_temperature"], "maxTa": prepared.kma["max_temperature"],
        "minTa": prepared.kma["min_temperature"],
    }).iloc[1:]
    result = preprocess_kma_temperature(raw, stations.iloc[0])
    first = result.iloc[0]
    assert first["date"].date() == ANALYSIS_START
    assert first[["avg_temperature", "max_temperature", "min_temperature"]].isna().all()


def test_daily_matching(synthetic_prepared):
    _, prepared = synthetic_prepared
    assert len(prepared.matched) == EXPECTED_DAYS
    assert not prepared.matched["date"].duplicated().any()


def test_annual_kma_tavg(synthetic_prepared):
    stations, prepared = synthetic_prepared
    annual = calculate_station_annual_temperature([prepared], stations)
    assert len(annual.query("source == 'KMA' and metric == 'TAVG'")) == 45


def test_annual_nasa_t2m(synthetic_prepared):
    stations, prepared = synthetic_prepared
    annual = calculate_station_annual_temperature([prepared], stations)
    assert len(annual.query("source == 'NASA' and metric == 'TAVG'")) == 45


def test_five_and_ten_year_moving_average(synthetic_prepared):
    stations, prepared = synthetic_prepared
    annual = calculate_station_annual_temperature([prepared], stations).query(
        "source == 'KMA' and metric == 'TAVG'"
    )
    assert annual["moving_average_5yr"].notna().sum() == 41
    assert annual["moving_average_10yr"].notna().sum() == 36


def test_sen_slope_station_result(synthetic_prepared):
    stations, prepared = synthetic_prepared
    annual = calculate_station_annual_temperature([prepared], stations)
    trends = calculate_station_trends(annual, stations)
    row = trends.query("source == 'KMA' and metric == 'TAVG'").iloc[0]
    assert row["sen_slope_per_decade"] > 0
    assert row["sen_ci_lower"] <= row["sen_slope_per_decade"] <= row["sen_ci_upper"]


def test_fdr_metric_family(products):
    assert products.trends["kma_fdr_q"].between(0, 1).all()
    assert products.trends["nasa_fdr_q"].between(0, 1).all()


def test_climate_normal(products):
    assert products.normals["n_years"].eq(30).all()
    assert len(products.normals) == 6


def test_anomaly_definition(products):
    row = products.anomalies.iloc[0]
    assert row["anomaly"] == pytest.approx(row["annual_mean"] - row["normal_mean"])


def test_seasonal_aggregation(products):
    assert set(products.seasonal["season"]) == {"DJF", "MAM", "JJA", "SON"}
    assert set(products.seasonal["metric"]) == {"TAVG", "TMAX", "TMIN"}


def test_threshold_tmax_ge_33(products):
    data = products.thresholds_annual.query("threshold == 'TMAX_GE_33'")
    assert len(data) == 45
    assert (data[["nasa_count", "kma_count"]].to_numpy() >= 0).all()


def test_threshold_tmin_ge_25(products):
    data = products.thresholds_annual.query("threshold == 'TMIN_GE_25'")
    assert len(data) == 45
    assert data["valid_pair_days"].gt(0).all()


def test_validation_bias(products):
    row = products.validation.query("metric == 'TAVG'").iloc[0]
    assert row["bias"] == pytest.approx(0.5)


def test_validation_mae(products):
    row = products.validation.query("metric == 'TAVG'").iloc[0]
    assert row["mae"] == pytest.approx(0.5)


def test_validation_rmse(products):
    row = products.validation.query("metric == 'TAVG'").iloc[0]
    assert row["rmse"] == pytest.approx(0.5)
    assert row["rmse"] >= row["mae"]


def test_validation_correlation(products):
    row = products.validation.query("metric == 'TAVG'").iloc[0]
    assert row["pearson_r"] == pytest.approx(1.0)
    assert row["spearman_rho"] == pytest.approx(1.0)


def test_station_summary(products):
    assert len(products.summary) == 1
    assert {"kma_tavg_sen_slope_decade", "tavg_bias", "days_tmax_ge_33_kma_mean"}.issubset(products.summary)


def test_regional_summary(products):
    assert products.regional.iloc[0]["station_count"] == 1
    assert products.regional.iloc[0]["region"] == "Region"
    assert "not regional climate truth" in products.regional.iloc[0]["interpretation_scope"]


def test_elevation_band_summary(products):
    band = products.elevation.query("elevation_band == '50-200m'").iloc[0]
    assert band["station_count"] == 1


def test_trend_ranking(products):
    assert products.rankings["ranking"].nunique() == 8
    assert products.rankings["rank"].eq(1).all()


def test_trend_consistency(products):
    assert products.trend_consistency["direction_consistency"].eq("both increasing").all()
    assert products.trend_consistency["interpretation_note"].str.contains("absolute").all()


def test_quality_metadata_join(products):
    assert products.trends["temperature_missing_rate"].eq(0).all()
    assert products.trends["continuity_risk"].eq("low").all()


def test_nationwide_map_dataframe(products):
    mapped = nationwide_map_dataframe(products.summary, "kma_tavg_sen_slope_decade")
    assert len(mapped) == 1
    assert {"latitude", "longitude", "tavg_bias", "tavg_rmse"}.issubset(mapped)


def test_manifest_resume(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": 1, "stations": {"108": {"status": "completed"}}}))
    loaded = load_analysis_manifest(path)
    assert loaded["stations"]["108"]["status"] == "completed"


def test_dry_run_plan_does_not_call_api(monkeypatch, tmp_path):
    monkeypatch.setattr("src.nationwide.tier_a_pipeline.nasa_raw_path", lambda station_id: tmp_path / f"{station_id}.csv")
    plan = build_download_plan(_stations())
    assert plan.station_count == 1
    assert plan.estimated_api_requests == 1


def test_api_key_missing_behavior_when_kma_cache_unavailable(monkeypatch, synthetic_prepared, tmp_path):
    stations, prepared = synthetic_prepared
    monkeypatch.setattr(
        "src.nationwide.tier_a_pipeline.download_nasa_station",
        lambda *args, **kwargs: (pd.DataFrame(), "cache", 0),
    )
    monkeypatch.setattr("src.nationwide.tier_a_pipeline.kma_raw_path", lambda station_id: tmp_path / "missing.csv")
    with pytest.raises(FileNotFoundError, match="KMA_API_KEY"):
        prepare_station(stations.iloc[0])


def test_no_api_call_when_valid_cache_exists(monkeypatch, tmp_path):
    path = tmp_path / "999.csv"
    pd.DataFrame({"DATE": ["19810101"], "T2M": [1], "T2M_MAX": [2], "T2M_MIN": [0]}).to_csv(path, index=False)
    monkeypatch.setattr("src.nationwide.tier_a_pipeline.nasa_raw_path", lambda station_id: path)
    monkeypatch.setattr("src.nationwide.tier_a_pipeline.validate_nasa_cache", lambda path: True)
    monkeypatch.setattr("src.nationwide.tier_a_pipeline._record_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.nationwide.tier_a_pipeline.fetch_daily_data", lambda *args, **kwargs: pytest.fail("API called"))
    data, source, calls = download_nasa_station(_stations().iloc[0])
    assert source == "cache" and calls == 0 and len(data) == 1


def test_existing_v1_data_unchanged_by_plan():
    path = Path("data/processed/seoul_temperature_daily_1981_2025.csv")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    build_download_plan(_stations())
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert after == before


def test_spatial_association_bounds(products):
    result = build_spatial_associations(products.summary)
    assert len(result) == 6
    assert result["spearman_rho"].dropna().between(-1, 1).all()
