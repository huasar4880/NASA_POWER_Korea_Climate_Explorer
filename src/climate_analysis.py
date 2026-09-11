"""NASA POWER 7변수 다도시 종합 기후분석 workflow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from src.analysis import save_analysis_table
from src.climate_indices import (
    calculate_annual_climate_statistics,
    calculate_annual_metric_trends,
    calculate_monthly_climate_climatology,
    calculate_past_vs_recent,
)
from src.config import (
    CLIMATE_PARAMETER_METADATA,
    CLIMATE_SETTINGS,
    CLIMATE_VALID_RANGES,
    Location,
    PowerSettings,
    city_climate_annual_data_path,
    city_climate_monthly_data_path,
    city_climate_processed_data_path,
    city_climate_raw_data_path,
    city_climate_summary_path,
)
from src.nasa_power import DownloadResult, NasaPowerError, download_daily_data
from src.preprocess import preprocess_daily_data, save_processed_data


@dataclass(frozen=True)
class ClimateDataQuality:
    """도시별 7변수 데이터 품질 검사 결과."""

    city: str
    start_date: str
    end_date: str
    row_count: int
    duplicate_dates: int
    missing_counts: dict[str, int]
    fill_value_counts: dict[str, int]
    abnormal_counts: dict[str, int]

    def to_record(self) -> dict[str, str | int]:
        """data_quality_summary.csv용 평면 레코드를 반환한다."""

        record: dict[str, str | int] = {
            "city": self.city,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "row_count": self.row_count,
            "duplicate_dates": self.duplicate_dates,
        }
        for parameter in CLIMATE_SETTINGS.parameters:
            record[f"missing_{parameter}"] = self.missing_counts[parameter]
            record[f"fill_value_{parameter}"] = self.fill_value_counts[parameter]
            record[f"abnormal_{parameter}"] = self.abnormal_counts[parameter]
        return record


@dataclass(frozen=True)
class CityClimateResult:
    """한 도시의 종합 기후분석 결과."""

    location: Location
    raw_path: Path
    processed_path: Path
    processed_data: pd.DataFrame
    annual_data: pd.DataFrame
    monthly_climatology: pd.DataFrame
    trend_data: pd.DataFrame
    past_vs_recent: pd.DataFrame
    quality: ClimateDataQuality
    download_source: str
    status_code: int | None


def read_valid_climate_raw_cache(
    path: Path,
    settings: PowerSettings = CLIMATE_SETTINGS,
) -> tuple[pd.DataFrame | None, str]:
    """다변수 raw 캐시의 컬럼·기간·행 수·중복을 검사해 유효할 때만 읽는다."""

    if not path.exists():
        return None, "파일 없음"
    try:
        dataframe = pd.read_csv(path, dtype={"DATE": "string"})
    except (OSError, pd.errors.ParserError) as exc:
        return None, f"CSV 읽기 실패: {exc}"

    required = {"DATE", *settings.parameters}
    missing_columns = required.difference(dataframe.columns)
    if missing_columns:
        return None, f"필수 컬럼 누락: {sorted(missing_columns)}"
    if dataframe.empty:
        return None, "빈 CSV"

    dates = pd.to_datetime(dataframe["DATE"], format="%Y%m%d", errors="coerce")
    if dates.isna().any():
        return None, f"잘못된 날짜 {int(dates.isna().sum())}개"
    expected_rows = (settings.analysis_end - settings.analysis_start).days + 1
    if len(dataframe) != expected_rows:
        return None, f"행 수 불일치: {len(dataframe)}/{expected_rows}"
    if dates.min().date() != settings.analysis_start or dates.max().date() != settings.analysis_end:
        return None, f"기간 불일치: {dates.min().date()}~{dates.max().date()}"
    duplicate_dates = int(dates.duplicated().sum())
    if duplicate_dates:
        return None, f"중복 날짜 {duplicate_dates}개"
    return dataframe, "유효한 raw 캐시"


def download_city_climate_data(
    location: Location,
    force: bool = False,
    session: requests.Session | None = None,
    settings: PowerSettings = CLIMATE_SETTINGS,
) -> DownloadResult:
    """도시의 7개 변수를 한 번의 API 요청으로 받거나 검증된 캐시를 사용한다."""

    output_path = city_climate_raw_data_path(location.key)
    if not force:
        cached, reason = read_valid_climate_raw_cache(output_path, settings)
        if cached is not None:
            return DownloadResult(cached, "cache", None, None)
        if output_path.exists():
            print(f"[{location.name}] climate raw 캐시 무효({reason}); 다시 다운로드합니다.")

    return download_daily_data(
        latitude=location.latitude,
        longitude=location.longitude,
        start=settings.analysis_start,
        end=settings.analysis_end,
        output_path=output_path,
        settings=settings,
        force=True,
        session=session,
    )


def preprocess_city_climate_data(
    location: Location,
    raw_data: pd.DataFrame,
    settings: PowerSettings = CLIMATE_SETTINGS,
) -> tuple[pd.DataFrame, ClimateDataQuality]:
    """7개 변수 공통 전처리, 이상값 제외, 품질검사와 processed 저장을 수행한다."""

    fill_counts: dict[str, int] = {}
    for parameter in settings.parameters:
        raw_values = pd.to_numeric(raw_data[parameter], errors="coerce")
        fill_counts[parameter] = int(raw_values.isin(settings.missing_values).sum())

    processed = preprocess_daily_data(
        raw_data,
        parameters=settings.parameters,
        missing_values=settings.missing_values,
    )
    dates = pd.to_datetime(processed["DATE"], errors="coerce")
    if dates.isna().any():
        raise ValueError(f"{location.name} climate 데이터에 잘못된 날짜가 있습니다.")

    expected_rows = (settings.analysis_end - settings.analysis_start).days + 1
    duplicate_dates = int(dates.duplicated().sum())
    if len(processed) != expected_rows:
        raise ValueError(f"{location.name} climate 행 수 불일치: {len(processed)}/{expected_rows}")
    if dates.min().date() != settings.analysis_start or dates.max().date() != settings.analysis_end:
        raise ValueError(
            f"{location.name} climate 기간 불일치: {dates.min().date()}~{dates.max().date()}"
        )
    if duplicate_dates:
        raise ValueError(f"{location.name} climate 중복 날짜: {duplicate_dates}개")

    abnormal_counts: dict[str, int] = {}
    for parameter in settings.parameters:
        minimum, maximum = CLIMATE_VALID_RANGES[parameter]
        values = processed[parameter]
        abnormal = values.notna() & ~values.between(minimum, maximum, inclusive="both")
        abnormal_counts[parameter] = int(abnormal.sum())
        processed.loc[abnormal, parameter] = float("nan")

    missing_counts = {
        parameter: int(processed[parameter].isna().sum())
        for parameter in settings.parameters
    }
    quality = ClimateDataQuality(
        city=location.name,
        start_date=dates.min().date().isoformat(),
        end_date=dates.max().date().isoformat(),
        row_count=len(processed),
        duplicate_dates=duplicate_dates,
        missing_counts=missing_counts,
        fill_value_counts=fill_counts,
        abnormal_counts=abnormal_counts,
    )
    save_processed_data(processed, city_climate_processed_data_path(location.key))
    return processed, quality


def analyze_city_climate(
    location: Location,
    force_download: bool = False,
    session: requests.Session | None = None,
    settings: PowerSettings = CLIMATE_SETTINGS,
) -> CityClimateResult:
    """도시 한 곳의 7변수 수집부터 연간·월별·추세 분석까지 실행한다."""

    download = download_city_climate_data(location, force_download, session, settings)
    processed, quality = preprocess_city_climate_data(location, download.dataframe, settings)
    annual = calculate_annual_climate_statistics(processed)
    monthly = calculate_monthly_climate_climatology(processed)
    trends = calculate_annual_metric_trends(annual)
    past_vs_recent = calculate_past_vs_recent(annual)

    annual_output = annual.copy()
    annual_output.insert(0, "city", location.name)
    monthly_output = monthly.copy()
    monthly_output.insert(0, "city", location.name)
    trend_output = trends.copy()
    trend_output.insert(0, "city", location.name)
    save_analysis_table(annual_output, city_climate_annual_data_path(location.key))
    save_analysis_table(monthly_output, city_climate_monthly_data_path(location.key))
    save_analysis_table(trend_output, city_climate_summary_path(location.key))

    return CityClimateResult(
        location=location,
        raw_path=city_climate_raw_data_path(location.key),
        processed_path=city_climate_processed_data_path(location.key),
        processed_data=processed,
        annual_data=annual,
        monthly_climatology=monthly,
        trend_data=trends,
        past_vs_recent=past_vs_recent,
        quality=quality,
        download_source=download.source,
        status_code=download.status_code,
    )


def analyze_climate_cities(
    locations: Iterable[Location],
    force_download: bool = False,
    request_interval_seconds: float = 1.0,
    session: requests.Session | None = None,
    settings: PowerSettings = CLIMATE_SETTINGS,
) -> tuple[list[CityClimateResult], dict[str, str]]:
    """여러 도시 기후분석을 순차 실행하고 실패 도시와 성공 도시를 분리한다."""

    if request_interval_seconds < 0:
        raise ValueError("API 요청 간 대기시간은 0 이상이어야 합니다.")
    client = session or requests.Session()
    results: list[CityClimateResult] = []
    errors: dict[str, str] = {}
    network_requests = 0

    for location in locations:
        cached, _ = read_valid_climate_raw_cache(
            city_climate_raw_data_path(location.key), settings
        )
        will_request = force_download or cached is None
        if will_request and network_requests > 0 and request_interval_seconds > 0:
            print(f"NASA 서버 보호를 위해 {request_interval_seconds:.1f}초 대기합니다.")
            time.sleep(request_interval_seconds)

        print(f"\n[{location.name}] 4단계 종합 기후분석 시작")
        try:
            result = analyze_city_climate(
                location,
                force_download=force_download,
                session=client,
                settings=settings,
            )
            results.append(result)
            source = "NASA POWER API" if result.download_source == "api" else "climate raw 캐시"
            total_missing = sum(result.quality.missing_counts.values())
            print(
                f"[{location.name}] 4단계 완료: {source}, "
                f"{result.quality.row_count:,}행, 전체 결측={total_missing}"
            )
        except (NasaPowerError, OSError, ValueError) as exc:
            errors[location.name] = str(exc)
            print(f"[{location.name}] 4단계 실패: {exc}")
        finally:
            if will_request:
                network_requests += 1
    return results, errors


def combine_city_climate_annual(results: Iterable[CityClimateResult]) -> pd.DataFrame:
    """도시별 연간 기후통계를 long-format 단일 표로 결합한다."""

    frames: list[pd.DataFrame] = []
    for result in results:
        frame = result.annual_data.copy()
        frame.insert(0, "city", result.location.name)
        frames.append(frame)
    if not frames:
        raise ValueError("결합할 연간 기후통계가 없습니다.")
    return pd.concat(frames, ignore_index=True)


def combine_city_monthly_climatology(results: Iterable[CityClimateResult]) -> pd.DataFrame:
    """도시별 12개월 climatology를 단일 표로 결합한다."""

    frames: list[pd.DataFrame] = []
    for result in results:
        frame = result.monthly_climatology.copy()
        frame.insert(0, "city", result.location.name)
        frames.append(frame)
    if not frames:
        raise ValueError("결합할 월 climatology가 없습니다.")
    return pd.concat(frames, ignore_index=True)


def combine_city_past_vs_recent(results: Iterable[CityClimateResult]) -> pd.DataFrame:
    """도시별 과거·최근 비교를 long-format 단일 표로 결합한다."""

    frames: list[pd.DataFrame] = []
    for result in results:
        frame = result.past_vs_recent.copy()
        frame.insert(0, "city", result.location.name)
        frames.append(frame)
    if not frames:
        raise ValueError("결합할 과거·최근 비교 결과가 없습니다.")
    return pd.concat(frames, ignore_index=True)


def build_data_quality_summary(results: Iterable[CityClimateResult]) -> pd.DataFrame:
    """도시별 기후 데이터 품질 레코드를 결합한다."""

    records = [result.quality.to_record() for result in results]
    if not records:
        raise ValueError("결합할 데이터 품질 결과가 없습니다.")
    return pd.DataFrame(records)


def parameter_metadata_table() -> pd.DataFrame:
    """NASA POWER 공식 응답 metadata 기반 변수 설명표를 반환한다."""

    rows = []
    for short_name, metadata in CLIMATE_PARAMETER_METADATA.items():
        rows.append({"short_name": short_name, **metadata})
    return pd.DataFrame(rows)


def _trend_row(result: CityClimateResult, metric: str) -> pd.Series:
    """도시 결과에서 특정 metric 추세 한 행을 반환한다."""

    selected = result.trend_data.loc[result.trend_data["metric"] == metric]
    if len(selected) != 1:
        raise ValueError(f"{result.location.name}의 {metric} 추세가 하나가 아닙니다.")
    return selected.iloc[0]


def build_city_climate_summary(results: Iterable[CityClimateResult]) -> pd.DataFrame:
    """도시별 대표 기후 평균, 10년당 추세, R²와 p-value를 wide table로 만든다."""

    rows: list[dict[str, float | str]] = []
    mean_specs = {
        "temperature": ("T2M_mean_C", "temperature_mean", "temperature_trend_per_decade"),
        "precipitation": (
            "precipitation_total_mm",
            "precipitation_annual_mean",
            "precipitation_trend_per_decade",
        ),
        "humidity": ("RH2M_mean_pct", "humidity_mean", "humidity_trend_per_decade"),
        "wind": ("WS10M_mean_m_s", "wind_speed_mean", "wind_speed_trend_per_decade"),
        "solar": ("solar_mean_kWh_m2_day", "solar_mean", "solar_trend_per_decade"),
        "hot_day_30": ("days_tmax_ge_30", "hot_day_30_mean", "hot_day_30_trend"),
        "hot_day_33": ("days_tmax_ge_33", "hot_day_33_mean", "hot_day_33_trend"),
        "warm_night_25": (
            "days_tmin_ge_25",
            "warm_night_25_mean",
            "warm_night_25_trend",
        ),
    }
    for result in results:
        row: dict[str, float | str] = {
            "city": result.location.name,
            "latitude": result.location.latitude,
            "longitude": result.location.longitude,
        }
        for metric, (column, mean_name, trend_name) in mean_specs.items():
            trend = _trend_row(result, metric)
            row[mean_name] = float(result.annual_data[column].mean())
            row[trend_name] = float(trend["trend_per_decade"])
            row[f"{metric}_r_squared"] = float(trend["r_squared"])
            row[f"{metric}_p_value"] = float(trend["p_value"])
        rows.append(row)
    if not rows:
        raise ValueError("도시 기후요약을 만들 결과가 없습니다.")
    return pd.DataFrame(rows)
