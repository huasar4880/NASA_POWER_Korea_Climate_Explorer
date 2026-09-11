"""Mocked KMA ASOS API, pagination, retry, key, and cache tests."""

from __future__ import annotations

from datetime import date
import traceback

import pandas as pd
import pytest
import requests

from src.kma_asos import (
    KmaApiKeyError,
    KmaAsosClient,
    KmaAsosError,
    build_kma_params,
    chunk_date_ranges,
    download_city_asos,
    get_kma_api_key,
)
from src.station_metadata import load_city_station


class FakeResponse:
    """Minimal requests.Response substitute."""

    def __init__(
        self, payload: dict | None, status_code: int = 200, text: str = ""
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        if self.payload is None:
            raise ValueError("not JSON")
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeSession:
    """Return queued fake responses and retain request arguments."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def get(self, _url: str, **kwargs) -> FakeResponse:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def payload(rows: list[dict], total: int) -> dict:
    """Build the official public-data response envelope."""

    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {"items": {"item": rows}, "totalCount": total},
        }
    }


def test_official_query_chunks_and_parameters() -> None:
    """The 1981-2025 range follows official maximum ten-year chunks."""

    chunks = list(chunk_date_ranges(date(1981, 1, 1), date(2025, 12, 31)))
    assert chunks == [
        (date(1981, 1, 1), date(1990, 12, 31)),
        (date(1991, 1, 1), date(2000, 12, 31)),
        (date(2001, 1, 1), date(2010, 12, 31)),
        (date(2011, 1, 1), date(2020, 12, 31)),
        (date(2021, 1, 1), date(2025, 12, 31)),
    ]
    params = build_kma_params("secret", "108", chunks[0][0], chunks[0][1], page_no=2)
    assert params["stnIds"] == "108"
    assert params["dataCd"] == "ASOS"
    assert params["dateCd"] == "DAY"
    assert params["startDt"] == "19810101"
    assert params["pageNo"] == 2

    encoded_params = build_kma_params(
        "sample%2Fkey%2Bvalue%3D", "108", chunks[0][0], chunks[0][1]
    )
    prepared = requests.Request("GET", "https://example.test", params=encoded_params).prepare()
    assert encoded_params["ServiceKey"] == "sample/key+value="
    assert "%252F" not in (prepared.url or "")


def test_api_pagination_and_retry_without_real_network() -> None:
    """429 is retried and totalCount controls pagination."""

    session = FakeSession(
        [
            FakeResponse({}, 429),
            FakeResponse(payload([{"tm": "2020-01-01"}, {"tm": "2020-01-02"}], 3)),
            FakeResponse(payload([{"tm": "2020-01-03"}], 3)),
        ]
    )
    waits: list[float] = []
    client = KmaAsosClient(
        "secret", session=session, max_attempts=2, retry_backoff_seconds=0.1, sleep=waits.append
    )
    rows = client.fetch_period("108", date(2020, 1, 1), date(2020, 1, 3), rows_per_page=2)
    assert [row["tm"] for row in rows] == ["2020-01-01", "2020-01-02", "2020-01-03"]
    assert waits == [0.1]
    assert [call["params"]["pageNo"] for call in session.calls] == [1, 1, 2]


def test_missing_api_key_has_safe_message() -> None:
    """Missing authentication is explicit without exposing any key."""

    with pytest.raises(KmaApiKeyError, match="KMA_API_KEY"):
        get_kma_api_key({})


def test_valid_raw_cache_is_reused_without_client_call(tmp_path) -> None:
    """A valid city raw file prevents unnecessary API calls."""

    path = tmp_path / "seoul_asos.csv"
    pd.DataFrame(
        {
            "tm": ["1981-01-01"],
            "stnId": ["108"],
            "_station_id": ["108"],
            "_request_start": ["1981-01-01"],
            "_request_end": ["2025-12-31"],
        }
    ).to_csv(path, index=False)

    class NeverClient:
        def fetch_period(self, *_args, **_kwargs):
            raise AssertionError("cache reuse must not call API")

    result = download_city_asos(
        load_city_station("Seoul"), client=NeverClient(), output_path=path
    )
    assert result.source == "cache"
    assert len(result.dataframe) == 1


@pytest.mark.parametrize("status_code", [200, 403])
@pytest.mark.parametrize("response_format", ["JSON", "XML"])
@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"),
        ("22", "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"),
    ],
)
def test_gateway_auth_and_daily_limit_errors_are_reported_without_retry(
    status_code: int, response_format: str, code: str, message: str
) -> None:
    """HTTP 200/403 gateway errors retain codes, hide keys, and are not retried."""

    fields = {
        "errMsg": message,
        "returnAuthMsg": "등록되지 않은 서비스키" if code == "30" else "일일 호출량 초과",
        "returnReasonCode": code,
    }
    # A reflected URL/key must never leak through an error or traceback.
    fields["returnAuthMsg"] += " ServiceKey=sample%252Fprivate%252Bkey%253D"
    if response_format == "JSON":
        response = FakeResponse(
            {"OpenAPI_ServiceResponse": {"cmmMsgHeader": fields}}, status_code
        )
    else:
        xml = "<OpenAPI_ServiceResponse><cmmMsgHeader>" + "".join(
            f"<{name}>{value}</{name}>" for name, value in fields.items()
        ) + "</cmmMsgHeader></OpenAPI_ServiceResponse>"
        response = FakeResponse(None, status_code, xml)
    session = FakeSession([response])
    waits: list[float] = []
    client = KmaAsosClient("sample%2Fprivate%2Bkey%3D", session=session, sleep=waits.append)

    with pytest.raises(KmaAsosError) as caught:
        client.fetch_period("159", date(2020, 1, 1), date(2020, 1, 1))

    error = caught.value
    assert error.http_status == status_code
    assert error.result_code == code
    assert message in str(error)
    assert f"HTTP status={status_code}" in str(error)
    assert "ServiceKey=REDACTED" in str(error)
    assert "sample" not in "".join(traceback.format_exception(error))
    assert error.retryable is False
    assert len(session.calls) == 1
    assert waits == []


@pytest.mark.parametrize("status_code", [200, 403])
@pytest.mark.parametrize("response_format", ["JSON", "XML"])
def test_per_second_error_23_uses_backoff(
    status_code: int, response_format: str
) -> None:
    """Code 23 triggers backoff even in HTTP 200 or a body-less error envelope."""

    header = {
        "resultCode": "23",
        "resultMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR",
    }
    if response_format == "JSON":
        response = FakeResponse({"response": {"header": header}}, status_code)
    else:
        xml = "<response><header>" + "".join(
            f"<{name}>{value}</{name}>" for name, value in header.items()
        ) + "</header></response>"
        response = FakeResponse(None, status_code, xml)
    session = FakeSession(
        [response, response, FakeResponse(payload([{"tm": "2020-01-01"}], 1))]
    )
    waits: list[float] = []
    client = KmaAsosClient("secret", session=session, sleep=waits.append)

    assert client.fetch_period("159", date(2020, 1, 1), date(2020, 1, 1)) == [
        {"tm": "2020-01-01"}
    ]
    assert waits == [2.0, 4.0]
    assert len(session.calls) == 3


def test_http_error_without_official_code_reports_status_without_body() -> None:
    """A permanent HTTP error is not retried and untrusted response text is omitted."""

    session = FakeSession([FakeResponse(None, 403, "Forbidden ServiceKey=private-key")])
    client = KmaAsosClient("private-key", session=session)
    with pytest.raises(KmaAsosError) as caught:
        client.fetch_period("159", date(2020, 1, 1), date(2020, 1, 1))
    assert caught.value.http_status == 403
    assert caught.value.result_code is None
    assert "private-key" not in str(caught.value)
    assert len(session.calls) == 1


def test_network_exception_traceback_does_not_reveal_request_key() -> None:
    """requests exceptions can include the full URL; the public error must not."""

    class FailingSession:
        def get(self, _url: str, **_kwargs) -> None:
            raise requests.ConnectionError("Failed: https://example.test?ServiceKey=private-key")

    client = KmaAsosClient("private-key", session=FailingSession(), max_attempts=1)
    with pytest.raises(KmaAsosError) as caught:
        client.fetch_period("159", date(2020, 1, 1), date(2020, 1, 1))
    rendered = "".join(traceback.format_exception(caught.value))
    assert "ConnectionError" in str(caught.value)
    assert "ServiceKey=REDACTED" in str(caught.value)
    assert "private-key" not in rendered


def test_failed_download_preserves_existing_incomplete_cache(tmp_path) -> None:
    """Partial raw is not resumable, but a failed replacement leaves it untouched."""

    path = tmp_path / "busan_asos.csv"
    pd.DataFrame(
        {
            "tm": ["1981-01-01"],
            "stnId": ["159"],
            "_station_id": ["159"],
            "_request_start": ["1981-01-01"],
            "_request_end": ["1990-12-31"],
        }
    ).to_csv(path, index=False)
    original = path.read_bytes()
    session = FakeSession(
        [
            FakeResponse(payload([{"tm": "1981-01-01", "stnId": "159"}], 1)),
            FakeResponse({"response": {"header": {"resultCode": "30", "resultMsg": "UNREGISTERED"}}}, 403),
        ]
    )
    client = KmaAsosClient("secret", session=session)
    with pytest.raises(KmaAsosError):
        download_city_asos(
            load_city_station("Busan"), client=client, output_path=path,
            request_interval_seconds=0,
        )
    assert path.read_bytes() == original
    assert [call["params"]["startDt"] for call in session.calls] == ["19810101", "19910101"]
