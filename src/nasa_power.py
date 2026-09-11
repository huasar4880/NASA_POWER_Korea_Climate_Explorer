"""NASA POWER Daily Point API 클라이언트."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import requests

from src.config import PowerSettings, SETTINGS


class NasaPowerError(RuntimeError):
    """NASA POWER 요청 또는 응답 검증 실패를 나타낸다."""


@dataclass(frozen=True)
class FetchResult:
    """API 호출 한 번의 결과."""

    dataframe: pd.DataFrame
    status_code: int
    request_url: str


@dataclass(frozen=True)
class DownloadResult:
    """다운로드 또는 캐시 로드 결과."""

    dataframe: pd.DataFrame
    source: str
    status_code: int | None
    request_url: str | None


def _format_api_date(value: date | str) -> str:
    """날짜를 NASA POWER의 YYYYMMDD 형식으로 변환한다."""

    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"날짜는 YYYYMMDD 형식이어야 합니다: {value}") from exc


def build_request_params(
    latitude: float,
    longitude: float,
    start: date | str,
    end: date | str,
    settings: PowerSettings = SETTINGS,
) -> dict[str, str | float]:
    """Daily Point API 쿼리 파라미터를 구성한다."""

    start_text = _format_api_date(start)
    end_text = _format_api_date(end)
    if start_text > end_text:
        raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")

    return {
        "parameters": ",".join(settings.parameters),
        "community": settings.community,
        "longitude": longitude,
        "latitude": latitude,
        "start": start_text,
        "end": end_text,
        "format": settings.output_format,
        "time-standard": settings.time_standard,
    }


def build_api_url(
    latitude: float,
    longitude: float,
    start: date | str,
    end: date | str,
    settings: PowerSettings = SETTINGS,
) -> str:
    """검사와 로깅에 사용할 완전한 NASA POWER 요청 URL을 생성한다."""

    params = build_request_params(latitude, longitude, start, end, settings)
    request = requests.Request("GET", settings.base_url, params=params).prepare()
    if request.url is None:
        raise NasaPowerError("NASA POWER 요청 URL을 생성하지 못했습니다.")
    return request.url


def _retry_wait_seconds(
    response: requests.Response,
    attempt: int,
    settings: PowerSettings,
) -> float:
    """Retry-After 또는 지수형 backoff를 이용해 재시도 대기 시간을 계산한다."""

    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(float(retry_after), settings.max_retry_wait_seconds)
        except ValueError:
            pass
    wait = settings.retry_backoff_seconds * (2 ** (attempt - 1))
    return min(wait, settings.max_retry_wait_seconds)


def _response_detail(response: requests.Response, limit: int = 300) -> str:
    """오류 메시지에 넣을 짧은 응답 본문을 반환한다."""

    detail = response.text.strip().replace("\n", " ")
    return detail[:limit] if detail else "응답 본문 없음"


def _request_payload(
    params: Mapping[str, str | float],
    settings: PowerSettings,
    session: requests.Session | None = None,
) -> tuple[dict[str, Any], int, str]:
    """재시도 정책을 적용해 API JSON을 요청한다."""

    client = session or requests.Session()
    last_error: Exception | None = None

    for attempt in range(1, settings.max_attempts + 1):
        try:
            response = client.get(
                settings.base_url,
                params=dict(params),
                timeout=settings.timeout,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt == settings.max_attempts:
                break
            time.sleep(min(settings.retry_backoff_seconds * attempt, settings.max_retry_wait_seconds))
            continue
        except requests.RequestException as exc:
            raise NasaPowerError(f"NASA POWER API 요청에 실패했습니다: {exc}") from exc

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == settings.max_attempts:
                raise NasaPowerError(
                    "NASA POWER API 재시도 한도를 초과했습니다 "
                    f"(HTTP {response.status_code}): {_response_detail(response)}"
                )
            time.sleep(_retry_wait_seconds(response, attempt, settings))
            continue

        if response.status_code != 200:
            raise NasaPowerError(
                f"NASA POWER API가 HTTP {response.status_code}를 반환했습니다: "
                f"{_response_detail(response)}"
            )

        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise NasaPowerError("NASA POWER 응답이 유효한 JSON이 아닙니다.") from exc

        if not isinstance(payload, dict):
            raise NasaPowerError("NASA POWER JSON 최상위 구조가 객체가 아닙니다.")
        return payload, response.status_code, response.url

    raise NasaPowerError(
        "NASA POWER API에 연결하지 못했습니다. 네트워크 연결, DNS, 방화벽 또는 "
        f"타임아웃 설정을 확인하세요. 마지막 오류: {last_error}"
    ) from last_error


def validate_api_response(
    payload: Mapping[str, Any],
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> Mapping[str, Mapping[str, Any]]:
    """응답 구조와 요청한 기상 변수의 존재 여부를 검사한다."""

    try:
        parameter_data = payload["properties"]["parameter"]
    except (KeyError, TypeError) as exc:
        messages = payload.get("messages", [])
        raise NasaPowerError(
            f"NASA POWER 응답에 properties.parameter가 없습니다. messages={messages}"
        ) from exc

    if not isinstance(parameter_data, Mapping):
        raise NasaPowerError("NASA POWER parameter 데이터 구조가 객체가 아닙니다.")

    for parameter in parameters:
        series = parameter_data.get(parameter)
        if not isinstance(series, Mapping) or not series:
            raise NasaPowerError(f"NASA POWER 응답에 유효한 {parameter} 시계열이 없습니다.")

    return parameter_data


def response_to_dataframe(
    payload: Mapping[str, Any],
    parameters: tuple[str, ...] = SETTINGS.parameters,
) -> pd.DataFrame:
    """NASA POWER JSON의 날짜별 변수 사전을 원본 보존용 표로 펼친다.

    값의 형 변환이나 결측치 치환은 하지 않으며, 전처리는 별도 모듈이 담당한다.
    """

    parameter_data = validate_api_response(payload, parameters)
    date_keys = sorted(
        {str(key) for parameter in parameters for key in parameter_data[parameter].keys()}
    )
    if not date_keys:
        raise NasaPowerError("NASA POWER 응답에 날짜 데이터가 없습니다.")

    invalid_dates = [key for key in date_keys if len(key) != 8 or not key.isdigit()]
    if invalid_dates:
        raise NasaPowerError(f"유효하지 않은 날짜 키가 있습니다: {invalid_dates[:3]}")

    rows: dict[str, list[Any]] = {"DATE": date_keys}
    for parameter in parameters:
        rows[parameter] = [parameter_data[parameter].get(key) for key in date_keys]
    return pd.DataFrame(rows)


def fetch_daily_data(
    latitude: float,
    longitude: float,
    start: date | str,
    end: date | str,
    settings: PowerSettings = SETTINGS,
    session: requests.Session | None = None,
) -> FetchResult:
    """NASA POWER Daily API를 호출하고 검증된 DataFrame을 반환한다."""

    params = build_request_params(latitude, longitude, start, end, settings)
    payload, status_code, request_url = _request_payload(params, settings, session)
    dataframe = response_to_dataframe(payload, settings.parameters)
    return FetchResult(dataframe, status_code, request_url)


def load_raw_csv(path: Path) -> pd.DataFrame:
    """기존 원본 CSV를 날짜 문자열을 보존하며 읽는다."""

    if not path.exists():
        raise FileNotFoundError(f"원본 CSV가 없습니다: {path}")
    dataframe = pd.read_csv(path, dtype={"DATE": "string"})
    if dataframe.empty:
        raise NasaPowerError(f"원본 CSV가 비어 있습니다: {path}")
    return dataframe


def download_daily_data(
    latitude: float,
    longitude: float,
    start: date | str,
    end: date | str,
    output_path: Path,
    settings: PowerSettings = SETTINGS,
    force: bool = False,
    session: requests.Session | None = None,
) -> DownloadResult:
    """일별 데이터를 저장하되, 기존 raw 파일이 있으면 재사용한다."""

    if output_path.exists() and not force:
        return DownloadResult(load_raw_csv(output_path), "cache", None, None)

    result = fetch_daily_data(
        latitude=latitude,
        longitude=longitude,
        start=start,
        end=end,
        settings=settings,
        session=session,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.dataframe.to_csv(output_path, index=False)
    return DownloadResult(
        result.dataframe,
        "api",
        result.status_code,
        result.request_url,
    )

