"""3단계 다도시 기온 분석 기능 테스트."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import src.city_analysis as city_module
from src.analysis import build_annual_trend_table
from src.city_analysis import (
    CityAnalysisResult,
    CityDataValidation,
    analyze_cities,
    build_city_annual_table,
    build_city_comparison_table,
    calculate_city_statistics,
)
from src.config import Location, load_location, load_locations


def _validation(city: str) -> CityDataValidation:
    """API 없는 단위 테스트용 정상 검증 결과를 만든다."""

    return CityDataValidation(
        city=city,
        start_date="1981-01-01",
        end_date="2025-12-31",
        row_count=16_436,
        has_t2m=True,
        has_t2m_max=True,
        has_t2m_min=True,
        missing_t2m=0,
        missing_t2m_max=0,
        missing_t2m_min=0,
        abnormal_t2m=0,
        abnormal_t2m_max=0,
        abnormal_t2m_min=0,
        duplicate_dates=0,
    )


def _city_result(location: Location, base: float, slope: float) -> CityAnalysisResult:
    """1981-2025 선형 연평균을 가진 도시 결과를 만든다."""

    years = list(range(1981, 2026))
    offsets = [year - 1981 for year in years]
    annual = pd.DataFrame(
        {
            "YEAR": years,
            "T2M": [base + slope * offset for offset in offsets],
            "T2M_MAX": [base + 5.0 + slope * offset for offset in offsets],
            "T2M_MIN": [base - 5.0 + slope * offset for offset in offsets],
        }
    )
    annual_trends, summary = build_annual_trend_table(annual)
    return CityAnalysisResult(
        location=location,
        raw_path=Path(f"{location.key}_raw.csv"),
        processed_path=Path(f"{location.key}_processed.csv"),
        processed_data=pd.DataFrame(),
        annual_data=annual,
        annual_trends=annual_trends,
        trend_summary=summary,
        validation=_validation(location.name),
        download_source="cache",
        status_code=None,
    )


def test_load_locations_reads_all_configured_cities() -> None:
    """locations.json에서 요청된 8개 도시를 선언 순서대로 읽는다."""

    locations = load_locations()

    assert list(locations) == [
        "seoul",
        "busan",
        "daejeon",
        "daegu",
        "gwangju",
        "gangneung",
        "jeju",
        "jeonju",
    ]
    assert [location.name for location in locations.values()] == [
        "Seoul",
        "Busan",
        "Daejeon",
        "Daegu",
        "Gwangju",
        "Gangneung",
        "Jeju",
        "Jeonju",
    ]


def test_load_location_returns_city_coordinates_case_insensitively() -> None:
    """도시 이름의 대소문자와 관계없이 정확한 좌표를 반환한다."""

    busan = load_location("Busan")
    jeju = load_location("jEjU")

    assert (busan.latitude, busan.longitude) == pytest.approx((35.1796, 129.0756))
    assert (jeju.latitude, jeju.longitude) == pytest.approx((33.4996, 126.5312))


def test_calculate_city_statistics_reuses_common_annual_pipeline() -> None:
    """도시별 일별 입력에 공통 연간·이동평균·추세 계산이 적용된다."""

    location = Location("sample", "Sample", 36.0, 127.0)
    daily = pd.DataFrame(
        {
            "YEAR": range(2000, 2010),
            "T2M": range(1, 11),
            "T2M_MAX": range(6, 16),
            "T2M_MIN": range(-4, 6),
        }
    )

    annual, annual_trends, summary = calculate_city_statistics(
        location,
        daily,
        save_outputs=False,
    )

    assert len(annual) == 10
    assert annual_trends.loc[9, "T2M_MA10"] == pytest.approx(5.5)
    t2m = summary.loc[summary["PARAMETER"] == "T2M"].iloc[0]
    assert t2m["CHANGE_C_PER_DECADE"] == pytest.approx(10.0)


def test_analyze_cities_handles_multiple_cities_without_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """mock 분석기로 여러 도시를 모두 처리하며 NASA API를 호출하지 않는다."""

    locations = [
        Location("alpha", "Alpha", 35.0, 127.0),
        Location("beta", "Beta", 36.0, 128.0),
    ]

    def fake_analyze_city(
        location: Location,
        force_download: bool = False,
        session: object | None = None,
        settings: object | None = None,
    ) -> CityAnalysisResult:
        del force_download, session, settings
        return _city_result(location, base=10.0, slope=0.03)

    monkeypatch.setattr(city_module, "analyze_city", fake_analyze_city)
    monkeypatch.setattr(
        city_module,
        "city_raw_data_path",
        lambda key: tmp_path / f"{key}.csv",
    )

    results, errors = analyze_cities(locations, request_interval_seconds=0)

    assert errors == {}
    assert [result.location.name for result in results] == ["Alpha", "Beta"]
    assert len(build_city_annual_table(results)) == 90


def test_city_comparison_calculates_trend_and_past_recent_means() -> None:
    """다도시 표의 10년당 추세와 과거·최근 10년 평균 차이를 검증한다."""

    seoul = _city_result(Location("seoul", "Seoul", 37.5665, 126.9780), 10.0, 0.1)
    busan = _city_result(Location("busan", "Busan", 35.1796, 129.0756), 15.0, 0.05)

    comparison = build_city_comparison_table([seoul, busan])
    seoul_row = comparison.loc[comparison["city"] == "Seoul"].iloc[0]

    assert comparison["city"].tolist() == ["Seoul", "Busan"]
    assert seoul_row["first_10yr_mean"] == pytest.approx(10.45)
    assert seoul_row["last_10yr_mean"] == pytest.approx(13.95)
    assert seoul_row["temperature_difference"] == pytest.approx(3.5)
    assert seoul_row["trend_per_decade"] == pytest.approx(1.0)

