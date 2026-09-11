"""프로젝트 경로와 NASA POWER 기본 설정을 관리한다."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = PROJECT_ROOT / "output"
CHARTS_DIR = OUTPUT_DIR / "charts"
TABLES_DIR = OUTPUT_DIR / "tables"
REPORTS_DIR = OUTPUT_DIR / "reports"
LOCATIONS_PATH = CONFIG_DIR / "locations.json"
KMA_STATIONS_PATH = CONFIG_DIR / "kma_stations.json"
KMA_RAW_DIR = DATA_DIR / "kma_raw"
KMA_PROCESSED_DIR = DATA_DIR / "kma_processed"
VALIDATION_DIR = OUTPUT_DIR / "validation"
VALIDATION_MATCHED_DIR = VALIDATION_DIR / "matched"
VALIDATION_CHARTS_DIR = CHARTS_DIR / "validation"
STATION_METADATA_DIR = DATA_DIR / "station_metadata"
STATION_METADATA_RAW_DIR = STATION_METADATA_DIR / "raw"
STATION_METADATA_PROCESSED_DIR = STATION_METADATA_DIR / "processed"
NATIONWIDE_ASOS_RAW_DIR = DATA_DIR / "nationwide_asos_raw"
NATIONWIDE_CHARTS_DIR = CHARTS_DIR / "nationwide"
NATIONWIDE_SCREENING_CONFIG_PATH = CONFIG_DIR / "nationwide_screening.json"

ANALYSIS_PERIOD_LABEL = f"{1981}_{2025}"
CLIMATE_NORMAL_START_YEAR = 1991
CLIMATE_NORMAL_END_YEAR = 2020
STATISTICAL_ALPHA = 0.05
CLIMATE_PARAMETERS = (
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "RH2M",
    "WS10M",
    "ALLSKY_SFC_SW_DWN",
)


def city_raw_data_path(city_key: str) -> Path:
    """도시 키에 대응하는 NASA POWER 원본 CSV 경로를 반환한다."""

    return RAW_DIR / f"{city_key.lower()}_power_daily_{ANALYSIS_PERIOD_LABEL}.csv"


def city_processed_data_path(city_key: str) -> Path:
    """도시 키에 대응하는 정제 일별 CSV 경로를 반환한다."""

    return PROCESSED_DIR / f"{city_key.lower()}_temperature_daily_{ANALYSIS_PERIOD_LABEL}.csv"


def city_climate_raw_data_path(city_key: str) -> Path:
    """도시별 7변수 NASA POWER 원본 CSV 경로를 반환한다."""

    return RAW_DIR / f"{city_key.lower()}_power_daily_climate_{ANALYSIS_PERIOD_LABEL}.csv"


def city_climate_processed_data_path(city_key: str) -> Path:
    """도시별 7변수 정제 일별 CSV 경로를 반환한다."""

    return PROCESSED_DIR / f"{city_key.lower()}_climate_daily_{ANALYSIS_PERIOD_LABEL}.csv"


def city_climate_annual_data_path(city_key: str) -> Path:
    """도시별 종합 연간 기후통계 CSV 경로를 반환한다."""

    return TABLES_DIR / f"{city_key.lower()}_climate_annual_{ANALYSIS_PERIOD_LABEL}.csv"


def city_climate_monthly_data_path(city_key: str) -> Path:
    """도시별 월 climatology CSV 경로를 반환한다."""

    return TABLES_DIR / f"{city_key.lower()}_climate_monthly_{ANALYSIS_PERIOD_LABEL}.csv"


def city_climate_summary_path(city_key: str) -> Path:
    """도시별 장기 기후요약 CSV 경로를 반환한다."""

    return TABLES_DIR / f"{city_key.lower()}_climate_summary_{ANALYSIS_PERIOD_LABEL}.csv"


def city_annual_data_path(city_key: str) -> Path:
    """도시별 연평균 CSV 경로를 반환한다."""

    return TABLES_DIR / f"{city_key.lower()}_temperature_annual_{ANALYSIS_PERIOD_LABEL}.csv"


def city_annual_trends_data_path(city_key: str) -> Path:
    """도시별 이동평균·추세 확장 CSV 경로를 반환한다."""

    return TABLES_DIR / f"{city_key.lower()}_temperature_annual_trends_{ANALYSIS_PERIOD_LABEL}.csv"


def city_trend_summary_path(city_key: str) -> Path:
    """도시별 선형추세 요약 CSV 경로를 반환한다."""

    return TABLES_DIR / f"{city_key.lower()}_temperature_linear_trend_summary_{ANALYSIS_PERIOD_LABEL}.csv"

RAW_DATA_PATH = city_raw_data_path("seoul")
PROCESSED_DATA_PATH = city_processed_data_path("seoul")
ANNUAL_DATA_PATH = city_annual_data_path("seoul")
ANNUAL_CHART_PATH = CHARTS_DIR / "seoul_annual_mean_temperature.png"
ANNUAL_TRENDS_DATA_PATH = city_annual_trends_data_path("seoul")
TREND_SUMMARY_PATH = city_trend_summary_path("seoul")
MONTHLY_CLIMATOLOGY_PATH = (
    TABLES_DIR / "seoul_temperature_monthly_climatology_1981_2025.csv"
)
YEAR_MONTH_DATA_PATH = TABLES_DIR / "seoul_temperature_year_month_1981_2025.csv"
LONG_TERM_TRENDS_CHART_PATH = CHARTS_DIR / "seoul_temperature_long_term_trends.png"
MONTHLY_CLIMATOLOGY_CHART_PATH = (
    CHARTS_DIR / "seoul_temperature_monthly_climatology.png"
)
YEAR_MONTH_HEATMAP_PATH = CHARTS_DIR / "seoul_temperature_year_month_heatmap.png"
TREND_REPORT_PATH = REPORTS_DIR / "seoul_temperature_trend_summary_1981_2025.md"

CITY_TRENDS_TABLE_PATH = TABLES_DIR / "city_temperature_trends_1981_2025.csv"
CITY_VALIDATION_TABLE_PATH = TABLES_DIR / "city_data_validation_1981_2025.csv"
CITY_ANNUAL_COMPARISON_CHART_PATH = (
    CHARTS_DIR / "city_annual_temperature_comparison.png"
)
CITY_TREND_PER_DECADE_CHART_PATH = (
    CHARTS_DIR / "city_temperature_trend_per_decade.png"
)
CITY_RECENT_VS_PAST_CHART_PATH = (
    CHARTS_DIR / "city_recent_vs_past_temperature.png"
)
CITY_TEMPERATURE_HEATMAP_PATH = CHARTS_DIR / "city_temperature_heatmap.png"

CITY_CLIMATE_ANNUAL_PATH = TABLES_DIR / "city_climate_annual_1981_2025.csv"
CITY_CLIMATE_SUMMARY_PATH = TABLES_DIR / "city_climate_summary_1981_2025.csv"
CITY_MONTHLY_CLIMATOLOGY_PATH = (
    TABLES_DIR / "city_monthly_climatology_1981_2025.csv"
)
CITY_CLIMATE_PAST_VS_RECENT_PATH = TABLES_DIR / "city_climate_past_vs_recent.csv"
DATA_QUALITY_SUMMARY_PATH = TABLES_DIR / "data_quality_summary.csv"
CLIMATE_PARAMETER_METADATA_PATH = TABLES_DIR / "nasa_power_climate_parameter_metadata.csv"

CITY_CLIMATE_TEMPERATURE_CHART_PATH = CHARTS_DIR / "city_temperature_trends.png"
CITY_PRECIPITATION_CHART_PATH = CHARTS_DIR / "city_precipitation_trends.png"
CITY_HUMIDITY_CHART_PATH = CHARTS_DIR / "city_humidity_trends.png"
CITY_WIND_CHART_PATH = CHARTS_DIR / "city_wind_trends.png"
CITY_SOLAR_CHART_PATH = CHARTS_DIR / "city_solar_trends.png"
CITY_HOT_DAYS_33_CHART_PATH = CHARTS_DIR / "city_hot_days_ge_33.png"
CITY_WARM_NIGHTS_25_CHART_PATH = CHARTS_DIR / "city_warm_nights_ge_25.png"
CITY_CLIMATE_TREND_HEATMAP_PATH = CHARTS_DIR / "city_climate_trend_heatmap.png"

CITY_CLIMATE_STATISTICAL_TRENDS_PATH = (
    TABLES_DIR / "city_climate_statistical_trends.csv"
)
CITY_CLIMATE_NORMALS_PATH = TABLES_DIR / "city_climate_normals_1991_2020.csv"
CITY_CLIMATE_ANOMALIES_PATH = TABLES_DIR / "city_climate_anomalies_1981_2025.csv"
CITY_SEASONAL_CLIMATE_TRENDS_PATH = (
    TABLES_DIR / "city_seasonal_climate_trends_1981_2025.csv"
)
CITY_CONSECUTIVE_INDICES_PATH = (
    TABLES_DIR / "city_consecutive_climate_indices_1981_2025.csv"
)
CITY_CLIMATE_CHANGE_RANKINGS_PATH = TABLES_DIR / "city_climate_change_rankings.csv"
BUSAN_JEJU_WARM_NIGHT_VALIDATION_PATH = (
    TABLES_DIR / "busan_jeju_warm_night_validation.csv"
)

CITY_TEMPERATURE_ANOMALY_CHART_PATH = (
    CHARTS_DIR / "city_temperature_anomaly_1991_2020.png"
)
CITY_TEMPERATURE_ANOMALY_HEATMAP_PATH = (
    CHARTS_DIR / "city_temperature_anomaly_heatmap.png"
)
CITY_SEN_SLOPE_TEMPERATURE_CHART_PATH = (
    CHARTS_DIR / "city_sen_slope_temperature.png"
)
CITY_EXTREME_HEAT_SEN_SLOPE_CHART_PATH = (
    CHARTS_DIR / "city_extreme_heat_sen_slope.png"
)
CITY_WARM_NIGHT_SEN_SLOPE_CHART_PATH = (
    CHARTS_DIR / "city_warm_night_sen_slope.png"
)
CITY_SEASONAL_TEMPERATURE_TRENDS_CHART_PATH = (
    CHARTS_DIR / "city_seasonal_temperature_trends.png"
)
CITY_SEASONAL_TREND_HEATMAP_PATH = (
    CHARTS_DIR / "city_seasonal_trend_heatmap.png"
)
CITY_CLIMATE_SIGNIFICANCE_HEATMAP_PATH = (
    CHARTS_DIR / "city_climate_significance_heatmap.png"
)

KMA_STATION_METADATA_PATH = TABLES_DIR / "kma_station_metadata.csv"
NASA_KMA_STATION_MAPPING_PATH = TABLES_DIR / "nasa_kma_station_mapping.csv"
KMA_DATA_QUALITY_PATH = TABLES_DIR / "kma_data_quality_summary.csv"
VALIDATION_METRICS_PATH = TABLES_DIR / "nasa_kma_validation_metrics.csv"
VALIDATION_MONTHLY_BIAS_PATH = TABLES_DIR / "nasa_kma_monthly_validation.csv"
VALIDATION_SEASONAL_BIAS_PATH = TABLES_DIR / "nasa_kma_seasonal_validation.csv"
VALIDATION_ANNUAL_BIAS_PATH = TABLES_DIR / "nasa_kma_annual_bias_1981_2025.csv"
VALIDATION_THRESHOLD_PATH = TABLES_DIR / "nasa_kma_threshold_validation.csv"
VALIDATION_PRECIP_CONTINGENCY_PATH = TABLES_DIR / "nasa_kma_precipitation_contingency.csv"
VALIDATION_GANGNEUNG_CONTINUITY_PATH = (
    TABLES_DIR / "gangneung_station_continuity_validation.csv"
)


def kma_raw_data_path(city_key: str) -> Path:
    """도시별 KMA ASOS 원본 CSV 경로를 반환한다."""

    return KMA_RAW_DIR / f"{city_key.lower()}_asos_daily_{ANALYSIS_PERIOD_LABEL}.csv"


def kma_processed_data_path(city_key: str) -> Path:
    """도시별 KMA ASOS 정제 CSV 경로를 반환한다."""

    return KMA_PROCESSED_DIR / f"{city_key.lower()}_asos_daily_{ANALYSIS_PERIOD_LABEL}.csv"


def validation_matched_path(city_key: str) -> Path:
    """도시별 NASA-KMA 일별 매칭 CSV 경로를 반환한다."""

    return VALIDATION_MATCHED_DIR / f"{city_key.lower()}_nasa_kma_daily_{ANALYSIS_PERIOD_LABEL}.csv"


@dataclass(frozen=True)
class Location:
    """분석 대상 위치의 이름과 좌표."""

    key: str
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class PowerSettings:
    """NASA POWER API 요청과 분석 기간에 사용하는 설정."""

    base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    parameters: tuple[str, ...] = ("T2M", "T2M_MAX", "T2M_MIN")
    community: str = "RE"
    time_standard: str = "LST"
    output_format: str = "JSON"
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 120.0
    max_attempts: int = 4
    retry_backoff_seconds: float = 2.0
    max_retry_wait_seconds: float = 60.0
    missing_values: tuple[float, ...] = (-999.0,)
    test_start: date = date(2020, 1, 1)
    test_end: date = date(2025, 12, 31)
    analysis_start: date = date(1981, 1, 1)
    analysis_end: date = date(2025, 12, 31)

    @property
    def timeout(self) -> tuple[float, float]:
        """requests가 사용할 연결 및 읽기 타임아웃을 반환한다."""

        return (self.connect_timeout_seconds, self.read_timeout_seconds)


SETTINGS = PowerSettings()
CLIMATE_SETTINGS = PowerSettings(parameters=CLIMATE_PARAMETERS)

# NASA POWER Daily API v2.9.7의 응답 metadata(2026-09-01 확인)를 코드의
# 계산 기준과 README가 함께 참조하도록 한 곳에서 관리한다.
CLIMATE_PARAMETER_METADATA: dict[str, dict[str, str]] = {
    "T2M": {
        "long_name": "Temperature at 2 Meters",
        "unit": "C",
        "temporal_resolution": "daily",
        "annual_aggregation": "mean",
    },
    "T2M_MAX": {
        "long_name": "Temperature at 2 Meters Maximum",
        "unit": "C",
        "temporal_resolution": "daily",
        "annual_aggregation": "mean and annual maximum",
    },
    "T2M_MIN": {
        "long_name": "Temperature at 2 Meters Minimum",
        "unit": "C",
        "temporal_resolution": "daily",
        "annual_aggregation": "mean and annual minimum",
    },
    "PRECTOTCORR": {
        "long_name": "Precipitation Corrected",
        "unit": "mm/day",
        "temporal_resolution": "daily",
        "annual_aggregation": "sum",
    },
    "RH2M": {
        "long_name": "Relative Humidity at 2 Meters",
        "unit": "%",
        "temporal_resolution": "daily",
        "annual_aggregation": "mean",
    },
    "WS10M": {
        "long_name": "Wind Speed at 10 Meters",
        "unit": "m/s",
        "temporal_resolution": "daily",
        "annual_aggregation": "mean",
    },
    "ALLSKY_SFC_SW_DWN": {
        "long_name": "All Sky Surface Shortwave Downward Irradiance",
        "unit": "kW-hr/m^2/day",
        "temporal_resolution": "daily",
        "annual_aggregation": "mean",
    },
}

CLIMATE_VALID_RANGES: dict[str, tuple[float, float]] = {
    "T2M": (-90.0, 70.0),
    "T2M_MAX": (-90.0, 70.0),
    "T2M_MIN": (-90.0, 70.0),
    "PRECTOTCORR": (0.0, 2_000.0),
    "RH2M": (0.0, 100.0),
    "WS10M": (0.0, 150.0),
    "ALLSKY_SFC_SW_DWN": (0.0, 50.0),
}


def ensure_directories() -> None:
    """워크플로에 필요한 데이터 및 결과 디렉터리를 생성한다."""

    for path in (
        RAW_DIR,
        PROCESSED_DIR,
        CHARTS_DIR,
        TABLES_DIR,
        REPORTS_DIR,
        KMA_RAW_DIR,
        KMA_PROCESSED_DIR,
        VALIDATION_DIR,
        VALIDATION_MATCHED_DIR,
        VALIDATION_CHARTS_DIR,
        STATION_METADATA_RAW_DIR,
        STATION_METADATA_PROCESSED_DIR,
        NATIONWIDE_ASOS_RAW_DIR,
        NATIONWIDE_CHARTS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def load_locations(path: Path = LOCATIONS_PATH) -> dict[str, Location]:
    """locations.json의 모든 위치를 선언 순서대로 읽는다."""

    with path.open(encoding="utf-8") as file:
        items = json.load(file)

    if not isinstance(items, dict) or not items:
        raise ValueError("위치 설정은 하나 이상의 도시를 가진 JSON 객체여야 합니다.")

    locations: dict[str, Location] = {}
    for raw_key, item in items.items():
        key = str(raw_key).strip().casefold()
        if not key or not isinstance(item, dict):
            raise ValueError(f"위치 설정이 올바르지 않습니다: {raw_key}")
        try:
            location = Location(
                key=key,
                name=str(item["name"]),
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"위치 설정이 올바르지 않습니다: {raw_key}") from exc
        if not -90.0 <= location.latitude <= 90.0:
            raise ValueError(f"위도가 범위를 벗어났습니다: {location.name}")
        if not -180.0 <= location.longitude <= 180.0:
            raise ValueError(f"경도가 범위를 벗어났습니다: {location.name}")
        locations[key] = location
    return locations


def load_location(location_key: str, path: Path = LOCATIONS_PATH) -> Location:
    """locations.json에서 키 또는 도시 이름으로 위치 설정을 읽는다.

    Args:
        location_key: JSON에 등록된 위치 키.
        path: 위치 설정 JSON 파일 경로.

    Raises:
        KeyError: 요청한 위치 키가 없을 때.
        ValueError: 필수 위치 속성이 잘못되었을 때.
    """

    locations = load_locations(path)
    normalized = location_key.strip().casefold()
    if normalized in locations:
        return locations[normalized]
    for location in locations.values():
        if location.name.casefold() == normalized:
            return location
    raise KeyError(f"등록되지 않은 위치입니다: {location_key}")
