"""여러 도시의 다운로드, 정제, 검증 및 장기 기온 분석 workflow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from src.analysis import (
    build_annual_trend_table,
    calculate_annual_means,
    save_analysis_table,
    save_annual_statistics,
)
from src.config import (
    SETTINGS,
    Location,
    PowerSettings,
    city_annual_data_path,
    city_annual_trends_data_path,
    city_processed_data_path,
    city_raw_data_path,
    city_trend_summary_path,
)
from src.nasa_power import DownloadResult, NasaPowerError, download_daily_data
from src.preprocess import preprocess_daily_data, save_processed_data


@dataclass(frozen=True)
class CityDataValidation:
    """도시별 정제 일별 데이터 검증 결과."""

    city: str
    start_date: str
    end_date: str
    row_count: int
    has_t2m: bool
    has_t2m_max: bool
    has_t2m_min: bool
    missing_t2m: int
    missing_t2m_max: int
    missing_t2m_min: int
    abnormal_t2m: int
    abnormal_t2m_max: int
    abnormal_t2m_min: int
    duplicate_dates: int

    def to_record(self) -> dict[str, str | int | bool]:
        """CSV 저장에 사용할 평면 사전을 반환한다."""

        return {
            "city": self.city,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "row_count": self.row_count,
            "has_t2m": self.has_t2m,
            "has_t2m_max": self.has_t2m_max,
            "has_t2m_min": self.has_t2m_min,
            "missing_t2m": self.missing_t2m,
            "missing_t2m_max": self.missing_t2m_max,
            "missing_t2m_min": self.missing_t2m_min,
            "abnormal_t2m": self.abnormal_t2m,
            "abnormal_t2m_max": self.abnormal_t2m_max,
            "abnormal_t2m_min": self.abnormal_t2m_min,
            "duplicate_dates": self.duplicate_dates,
        }


@dataclass(frozen=True)
class CityAnalysisResult:
    """도시 한 곳의 데이터와 분석 결과."""

    location: Location
    raw_path: Path
    processed_path: Path
    processed_data: pd.DataFrame
    annual_data: pd.DataFrame
    annual_trends: pd.DataFrame
    trend_summary: pd.DataFrame
    validation: CityDataValidation
    download_source: str
    status_code: int | None


def validate_city_data(
    location: Location,
    daily_data: pd.DataFrame,
    settings: PowerSettings = SETTINGS,
    valid_temperature_range_c: tuple[float, float] = (-90.0, 70.0),
) -> CityDataValidation:
    """도시별 날짜 범위, 컬럼, 결측치, 이상값과 중복을 검증한다.

    결측치는 개수를 기록하며 pandas 집계에서 자동 제외된다. 보수적인 물리 범위
    밖의 값은 분석을 중단해 결과에 포함되지 않도록 한다.
    """

    required_columns = {"DATE", *settings.parameters}
    missing_columns = required_columns.difference(daily_data.columns)
    if missing_columns:
        raise ValueError(f"{location.name} 데이터에 필수 컬럼이 없습니다: {sorted(missing_columns)}")
    if daily_data.empty:
        raise ValueError(f"{location.name} 정제 데이터가 비어 있습니다.")

    dates = pd.to_datetime(daily_data["DATE"], errors="coerce")
    invalid_dates = int(dates.isna().sum())
    if invalid_dates:
        raise ValueError(f"{location.name} 데이터에 잘못된 날짜가 {invalid_dates}개 있습니다.")

    duplicate_dates = int(dates.duplicated().sum())
    start_date = dates.min().date()
    end_date = dates.max().date()
    expected_rows = (settings.analysis_end - settings.analysis_start).days + 1
    if start_date != settings.analysis_start or end_date != settings.analysis_end:
        raise ValueError(
            f"{location.name} 날짜 범위가 올바르지 않습니다: {start_date} ~ {end_date}"
        )
    if len(daily_data) != expected_rows:
        raise ValueError(
            f"{location.name} 행 수가 올바르지 않습니다: "
            f"expected={expected_rows}, actual={len(daily_data)}"
        )
    if duplicate_dates:
        raise ValueError(f"{location.name} 데이터에 중복 날짜가 {duplicate_dates}개 있습니다.")

    minimum, maximum = valid_temperature_range_c
    missing_counts: dict[str, int] = {}
    abnormal_counts: dict[str, int] = {}
    for parameter in settings.parameters:
        values = pd.to_numeric(daily_data[parameter], errors="coerce")
        missing_counts[parameter] = int(values.isna().sum())
        abnormal_counts[parameter] = int(
            (values.notna() & ~values.between(minimum, maximum, inclusive="both")).sum()
        )
    if any(abnormal_counts.values()):
        raise ValueError(
            f"{location.name} 데이터에 허용 범위({minimum}~{maximum} °C) 밖의 값이 있습니다: "
            f"{abnormal_counts}"
        )

    return CityDataValidation(
        city=location.name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        row_count=len(daily_data),
        has_t2m="T2M" in daily_data.columns,
        has_t2m_max="T2M_MAX" in daily_data.columns,
        has_t2m_min="T2M_MIN" in daily_data.columns,
        missing_t2m=missing_counts["T2M"],
        missing_t2m_max=missing_counts["T2M_MAX"],
        missing_t2m_min=missing_counts["T2M_MIN"],
        abnormal_t2m=abnormal_counts["T2M"],
        abnormal_t2m_max=abnormal_counts["T2M_MAX"],
        abnormal_t2m_min=abnormal_counts["T2M_MIN"],
        duplicate_dates=duplicate_dates,
    )


def download_city_data(
    location: Location,
    force: bool = False,
    session: requests.Session | None = None,
    settings: PowerSettings = SETTINGS,
) -> DownloadResult:
    """도시 좌표로 전체기간 raw 데이터를 다운로드하거나 캐시에서 읽는다."""

    return download_daily_data(
        latitude=location.latitude,
        longitude=location.longitude,
        start=settings.analysis_start,
        end=settings.analysis_end,
        output_path=city_raw_data_path(location.key),
        settings=settings,
        force=force,
        session=session,
    )


def process_city_data(
    location: Location,
    raw_data: pd.DataFrame,
    settings: PowerSettings = SETTINGS,
) -> tuple[pd.DataFrame, CityDataValidation]:
    """공통 전처리 pipeline을 적용하고 도시별 processed CSV를 저장한다."""

    processed_data = preprocess_daily_data(
        raw_data,
        parameters=settings.parameters,
        missing_values=settings.missing_values,
    )
    validation = validate_city_data(location, processed_data, settings)
    save_processed_data(processed_data, city_processed_data_path(location.key))
    return processed_data, validation


def calculate_city_statistics(
    location: Location,
    processed_data: pd.DataFrame,
    save_outputs: bool = True,
    settings: PowerSettings = SETTINGS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """한 도시의 연평균, 이동평균과 선형추세를 동일한 계산식으로 산출한다."""

    annual_data = calculate_annual_means(processed_data, settings.parameters)
    annual_trends, trend_summary = build_annual_trend_table(
        annual_data,
        parameters=settings.parameters,
    )
    if save_outputs:
        save_annual_statistics(annual_data, city_annual_data_path(location.key))
        save_analysis_table(annual_trends, city_annual_trends_data_path(location.key))
        save_analysis_table(trend_summary, city_trend_summary_path(location.key))
    return annual_data, annual_trends, trend_summary


def analyze_city(
    location: Location,
    force_download: bool = False,
    session: requests.Session | None = None,
    settings: PowerSettings = SETTINGS,
) -> CityAnalysisResult:
    """도시 한 곳의 다운로드부터 추세 분석까지 전체 pipeline을 실행한다."""

    download = download_city_data(
        location,
        force=force_download,
        session=session,
        settings=settings,
    )
    processed_data, validation = process_city_data(location, download.dataframe, settings)
    annual_data, annual_trends, trend_summary = calculate_city_statistics(
        location,
        processed_data,
        settings=settings,
    )
    return CityAnalysisResult(
        location=location,
        raw_path=city_raw_data_path(location.key),
        processed_path=city_processed_data_path(location.key),
        processed_data=processed_data,
        annual_data=annual_data,
        annual_trends=annual_trends,
        trend_summary=trend_summary,
        validation=validation,
        download_source=download.source,
        status_code=download.status_code,
    )


def analyze_cities(
    locations: Iterable[Location],
    force_download: bool = False,
    request_interval_seconds: float = 1.0,
    session: requests.Session | None = None,
    settings: PowerSettings = SETTINGS,
) -> tuple[list[CityAnalysisResult], dict[str, str]]:
    """여러 도시를 순차 분석하며 개별 실패 후에도 나머지 도시를 계속 처리한다."""

    if request_interval_seconds < 0:
        raise ValueError("API 요청 간 대기시간은 0 이상이어야 합니다.")

    client = session or requests.Session()
    results: list[CityAnalysisResult] = []
    errors: dict[str, str] = {}
    network_request_count = 0

    for location in locations:
        will_request_api = force_download or not city_raw_data_path(location.key).exists()
        if will_request_api and network_request_count > 0 and request_interval_seconds > 0:
            print(f"NASA 서버 보호를 위해 {request_interval_seconds:.1f}초 대기합니다.")
            time.sleep(request_interval_seconds)

        print(f"\n[{location.name}] 분석 시작 ({location.latitude}, {location.longitude})")
        try:
            result = analyze_city(
                location,
                force_download=force_download,
                session=client,
                settings=settings,
            )
            results.append(result)
            source_text = "NASA POWER API" if result.download_source == "api" else "raw 캐시"
            print(
                f"[{location.name}] 완료: {source_text}, {result.validation.row_count:,}행, "
                f"결측 T2M={result.validation.missing_t2m}"
            )
        except (NasaPowerError, OSError, ValueError) as exc:
            errors[location.name] = str(exc)
            print(f"[{location.name}] 실패: {exc}")
        finally:
            if will_request_api:
                network_request_count += 1

    return results, errors


def build_city_comparison_table(
    results: Iterable[CityAnalysisResult],
    first_period: tuple[int, int] = (1981, 1990),
    last_period: tuple[int, int] = (2016, 2025),
) -> pd.DataFrame:
    """도시별 대표 기온과 과거·최근 10년 및 선형추세 비교표를 만든다."""

    rows: list[dict[str, float | str]] = []
    for result in results:
        annual = result.annual_data.sort_values("YEAR")
        first = annual.loc[annual["YEAR"].between(*first_period), "T2M"]
        last = annual.loc[annual["YEAR"].between(*last_period), "T2M"]
        expected_first_years = first_period[1] - first_period[0] + 1
        expected_last_years = last_period[1] - last_period[0] + 1
        if len(first) != expected_first_years or len(last) != expected_last_years:
            raise ValueError(
                f"{result.location.name}의 과거 또는 최근 10년 연평균 자료가 완전하지 않습니다."
            )
        t2m_trend = result.trend_summary.loc[
            result.trend_summary["PARAMETER"] == "T2M"
        ]
        if len(t2m_trend) != 1:
            raise ValueError(f"{result.location.name} T2M 추세 결과가 하나가 아닙니다.")

        first_mean = float(first.mean())
        last_mean = float(last.mean())
        rows.append(
            {
                "city": result.location.name,
                "latitude": result.location.latitude,
                "longitude": result.location.longitude,
                "mean_temperature": float(annual["T2M"].mean()),
                "first_10yr_mean": first_mean,
                "last_10yr_mean": last_mean,
                "temperature_difference": last_mean - first_mean,
                "trend_per_decade": float(t2m_trend.iloc[0]["CHANGE_C_PER_DECADE"]),
                "min_annual_temperature": float(annual["T2M"].min()),
                "max_annual_temperature": float(annual["T2M"].max()),
            }
        )

    if not rows:
        raise ValueError("도시 비교표를 만들 분석 결과가 없습니다.")
    return pd.DataFrame(rows)


def build_city_annual_table(results: Iterable[CityAnalysisResult]) -> pd.DataFrame:
    """도시 비교 그래프용 city·YEAR·T2M long-form 표를 만든다."""

    frames: list[pd.DataFrame] = []
    for result in results:
        frame = result.annual_data.loc[:, ["YEAR", "T2M"]].copy()
        frame.insert(0, "city", result.location.name)
        frames.append(frame)
    if not frames:
        raise ValueError("도시 연평균 결합표를 만들 분석 결과가 없습니다.")
    return pd.concat(frames, ignore_index=True)


def build_city_validation_table(results: Iterable[CityAnalysisResult]) -> pd.DataFrame:
    """모든 도시의 데이터 품질 검증 결과를 표로 결합한다."""

    records = [result.validation.to_record() for result in results]
    if not records:
        raise ValueError("결합할 도시 검증 결과가 없습니다.")
    return pd.DataFrame(records)

