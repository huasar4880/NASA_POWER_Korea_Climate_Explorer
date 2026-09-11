"""NASA POWER 클라이언트와 MVP 분석 핵심 동작 테스트."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from src.analysis import calculate_annual_means
from src.nasa_power import build_api_url, response_to_dataframe


def test_build_api_url_contains_expected_query_parameters() -> None:
    """요청 URL에 좌표, 기간, 변수 및 API 설정이 정확히 포함된다."""

    url = build_api_url(37.5665, 126.9780, "20200101", "20251231")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.path == "/api/temporal/daily/point"
    assert query["parameters"] == ["T2M,T2M_MAX,T2M_MIN"]
    assert query["community"] == ["RE"]
    assert query["latitude"] == ["37.5665"]
    assert query["longitude"] == ["126.978"]
    assert query["start"] == ["20200101"]
    assert query["end"] == ["20251231"]
    assert query["time-standard"] == ["LST"]
    assert query["format"] == ["JSON"]


def test_response_to_dataframe_converts_parameter_series() -> None:
    """NASA 형식의 날짜별 변수 사전이 열 중심 DataFrame으로 변환된다."""

    payload = {
        "properties": {
            "parameter": {
                "T2M": {"20200101": 0.1, "20200102": 1.2},
                "T2M_MAX": {"20200101": 4.0, "20200102": 5.1},
                "T2M_MIN": {"20200101": -3.2, "20200102": -2.0},
            }
        }
    }

    result = response_to_dataframe(payload)

    assert list(result.columns) == ["DATE", "T2M", "T2M_MAX", "T2M_MIN"]
    assert result["DATE"].tolist() == ["20200101", "20200102"]
    assert result.loc[1, "T2M"] == pytest.approx(1.2)
    assert len(result) == 2


def test_calculate_annual_means_groups_by_year() -> None:
    """일별 기온 세 변수가 연도별 평균으로 집계된다."""

    daily = pd.DataFrame(
        {
            "YEAR": [2020, 2020, 2021, 2021],
            "T2M": [10.0, 12.0, 14.0, 16.0],
            "T2M_MAX": [15.0, 17.0, 19.0, 21.0],
            "T2M_MIN": [5.0, 7.0, 9.0, 11.0],
        }
    )

    result = calculate_annual_means(daily)

    assert result["YEAR"].tolist() == [2020, 2021]
    assert result["T2M"].tolist() == pytest.approx([11.0, 15.0])
    assert result["T2M_MAX"].tolist() == pytest.approx([16.0, 20.0])
    assert result["T2M_MIN"].tolist() == pytest.approx([6.0, 10.0])

