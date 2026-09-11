"""KMA 다운로드, 정제, NASA 일별 매칭과 validation 결과 저장을 조정한다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.analysis import save_analysis_table
from src.config import (
    KMA_DATA_QUALITY_PATH,
    KMA_PROCESSED_DIR,
    KMA_STATION_METADATA_PATH,
    NASA_KMA_STATION_MAPPING_PATH,
    SETTINGS,
    VALIDATION_ANNUAL_BIAS_PATH,
    VALIDATION_CHARTS_DIR,
    VALIDATION_GANGNEUNG_CONTINUITY_PATH,
    VALIDATION_METRICS_PATH,
    VALIDATION_MONTHLY_BIAS_PATH,
    VALIDATION_PRECIP_CONTINGENCY_PATH,
    VALIDATION_SEASONAL_BIAS_PATH,
    VALIDATION_THRESHOLD_PATH,
    city_climate_processed_data_path,
    ensure_directories,
    kma_processed_data_path,
    validation_matched_path,
)
from src.kma_asos import KmaAsosClient, KmaDownloadResult, download_city_asos
from src.kma_preprocess import (
    KmaDataQuality,
    assess_kma_quality,
    preprocess_kma_data,
    quality_to_record,
    save_kma_processed,
)
from src.station_metadata import (
    CityStation,
    build_station_mapping_table,
    build_station_metadata_table,
    load_city_station,
    load_kma_stations,
)
from src.validation import (
    calculate_annual_bias,
    calculate_gangneung_continuity,
    calculate_monthly_validation,
    calculate_precipitation_contingency,
    calculate_seasonal_validation,
    calculate_threshold_validation,
    calculate_validation_metrics,
    match_daily_data,
)
from src.validation_visualization import create_validation_charts


@dataclass(frozen=True)
class KmaCityValidationResult:
    """한 도시의 KMA 처리·매칭·품질 결과."""

    station: CityStation
    download: KmaDownloadResult
    processed: pd.DataFrame
    matched: pd.DataFrame
    quality: KmaDataQuality


def save_station_reference_tables() -> tuple[Path, Path]:
    """공식 관측소 metadata와 NASA point 거리표를 저장한다."""

    save_analysis_table(build_station_metadata_table(), KMA_STATION_METADATA_PATH, "%.8g")
    save_analysis_table(build_station_mapping_table(), NASA_KMA_STATION_MAPPING_PATH, "%.8g")
    return KMA_STATION_METADATA_PATH, NASA_KMA_STATION_MAPPING_PATH


def download_kma_city(
    city_name: str,
    *,
    client: KmaAsosClient | None = None,
    force_download: bool = False,
    request_interval_seconds: float = 0.25,
) -> KmaDownloadResult:
    """한 도시 KMA raw만 다운로드하거나 캐시를 재사용한다."""

    station = load_city_station(city_name)
    return download_city_asos(
        station,
        client=client,
        force_download=force_download,
        request_interval_seconds=request_interval_seconds,
    )


def validate_kma_city(
    city_name: str,
    *,
    client: KmaAsosClient | None = None,
    force_download: bool = False,
    request_interval_seconds: float = 0.25,
) -> KmaCityValidationResult:
    """한 도시 ASOS를 정제하고 기존 NASA processed와 날짜별로 매칭한다."""

    station = load_city_station(city_name)
    download = download_city_asos(
        station,
        client=client,
        force_download=force_download,
        request_interval_seconds=request_interval_seconds,
    )
    processed = preprocess_kma_data(download.dataframe, station)
    quality = assess_kma_quality(
        processed,
        station,
        expected_start=SETTINGS.analysis_start,
        expected_end=SETTINGS.analysis_end,
    )
    save_kma_processed(processed, kma_processed_data_path(station.key))

    nasa_path = city_climate_processed_data_path(station.key)
    if not nasa_path.exists():
        raise FileNotFoundError(
            f"NASA processed 파일이 없습니다: {nasa_path}. 먼저 python main.py --all을 실행하세요."
        )
    nasa = pd.read_csv(nasa_path)
    matched = match_daily_data(nasa, processed, station.city)
    matched_path = validation_matched_path(station.key)
    matched_path.parent.mkdir(parents=True, exist_ok=True)
    matched.to_csv(matched_path, index=False, date_format="%Y-%m-%d")
    return KmaCityValidationResult(station, download, processed, matched, quality)


def _save_combined_validation(results: list[KmaCityValidationResult]) -> dict[str, Path]:
    """도시 결과를 합쳐 모든 validation 통계표와 그래프를 저장한다."""

    matched = pd.concat([result.matched for result in results], ignore_index=True)
    metrics = calculate_validation_metrics(matched)
    monthly = calculate_monthly_validation(matched)
    seasonal = calculate_seasonal_validation(matched)
    annual_bias = calculate_annual_bias(matched)
    thresholds = calculate_threshold_validation(matched)
    precipitation = calculate_precipitation_contingency(matched)
    quality = pd.DataFrame([quality_to_record(result.quality) for result in results])

    outputs = {
        "metrics": VALIDATION_METRICS_PATH,
        "monthly": VALIDATION_MONTHLY_BIAS_PATH,
        "seasonal": VALIDATION_SEASONAL_BIAS_PATH,
        "annual_bias": VALIDATION_ANNUAL_BIAS_PATH,
        "thresholds": VALIDATION_THRESHOLD_PATH,
        "precipitation": VALIDATION_PRECIP_CONTINGENCY_PATH,
        "quality": KMA_DATA_QUALITY_PATH,
    }
    for dataframe, path in (
        (metrics, outputs["metrics"]),
        (monthly, outputs["monthly"]),
        (seasonal, outputs["seasonal"]),
        (annual_bias, outputs["annual_bias"]),
        (thresholds, outputs["thresholds"]),
        (precipitation, outputs["precipitation"]),
        (quality, outputs["quality"]),
    ):
        save_analysis_table(dataframe, path, "%.8g")

    gangneung = next((result for result in results if result.station.key == "gangneung"), None)
    if gangneung is not None:
        continuity = calculate_gangneung_continuity(gangneung.download.dataframe)
        save_analysis_table(continuity, VALIDATION_GANGNEUNG_CONTINUITY_PATH, "%.8g")
        outputs["gangneung_continuity"] = VALIDATION_GANGNEUNG_CONTINUITY_PATH

    create_validation_charts(matched, metrics, VALIDATION_CHARTS_DIR)
    return outputs


def run_kma_downloads(
    city_names: list[str],
    *,
    client: KmaAsosClient | None = None,
    force_download: bool = False,
    request_interval_seconds: float = 0.25,
) -> list[KmaDownloadResult]:
    """선택 도시의 KMA raw를 독립적으로 저장하며 성공한 캐시를 보존한다."""

    ensure_directories()
    save_station_reference_tables()
    results: list[KmaDownloadResult] = []
    errors: list[str] = []
    for city_name in city_names:
        try:
            results.append(
                download_kma_city(
                    city_name,
                    client=client,
                    force_download=force_download,
                    request_interval_seconds=request_interval_seconds,
                )
            )
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            errors.append(f"{city_name}: {exc}")
    if errors:
        raise RuntimeError(
            "일부 KMA 다운로드에 실패했습니다. 성공한 도시 raw는 유지됩니다: "
            + "; ".join(errors)
        )
    return results


def run_kma_validation(
    city_names: list[str],
    *,
    client: KmaAsosClient | None = None,
    force_download: bool = False,
    request_interval_seconds: float = 0.25,
) -> tuple[list[KmaCityValidationResult], dict[str, Path]]:
    """선택 도시의 전체 NASA-KMA validation workflow를 실행한다."""

    ensure_directories()
    save_station_reference_tables()
    results: list[KmaCityValidationResult] = []
    errors: list[str] = []
    for city_name in city_names:
        try:
            results.append(
                validate_kma_city(
                    city_name,
                    client=client,
                    force_download=force_download,
                    request_interval_seconds=request_interval_seconds,
                )
            )
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            errors.append(f"{city_name}: {exc}")
    if errors:
        raise RuntimeError(
            "일부 KMA validation에 실패했습니다. 성공한 raw/processed/matched 파일은 "
            "유지됩니다: " + "; ".join(errors)
        )
    if not results:
        raise RuntimeError("KMA validation 대상 도시가 없습니다.")
    return results, _save_combined_validation(results)


def all_kma_city_names() -> list[str]:
    """KMA 관측소 config 선언 순서의 도시 이름을 반환한다."""

    return [station.city for station in load_kma_stations().values()]
