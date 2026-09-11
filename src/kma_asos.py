"""공식 KMA ASOS 일자료 OpenAPI 다운로드·재시도·캐시 기능."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import quote, unquote
from xml.etree import ElementTree

import pandas as pd
import requests

from src.config import SETTINGS, kma_raw_data_path
from src.station_metadata import CityStation


KMA_ASOS_ENDPOINT = (
    "https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"
)
KMA_API_KEY_ENV = "KMA_API_KEY"
RETRYABLE_API_CODES = {"05", "23"}
SUCCESS_API_CODES = {"00", "0", "NORMAL_SERVICE"}


class KmaAsosError(RuntimeError):
    """KMA ASOS 요청 또는 응답 검증 실패."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        result_code: str | None = None,
        result_message: str | None = None,
        retryable: bool = False,
    ) -> None:
        """인증키나 requests 응답 객체 없이 진단용 오류 정보만 보관한다."""

        super().__init__(message)
        self.http_status = http_status
        self.result_code = result_code
        self.result_message = result_message
        self.retryable = retryable


class KmaApiKeyError(KmaAsosError):
    """KMA API 인증키가 설정되지 않았을 때 발생한다."""


@dataclass(frozen=True)
class KmaDownloadResult:
    """도시별 원본 다운로드 또는 캐시 재사용 결과."""

    dataframe: pd.DataFrame
    source: str
    path: Path


def get_kma_api_key(environ: dict[str, str] | None = None) -> str:
    """환경변수에서 KMA 인증키를 읽되 키 값은 오류 메시지에 포함하지 않는다."""

    values = os.environ if environ is None else environ
    key = values.get(KMA_API_KEY_ENV, "").strip()
    if not key:
        raise KmaApiKeyError(
            "KMA API key가 설정되지 않았습니다. .env.example을 참고하여 "
            "KMA_API_KEY를 설정하세요."
        )
    return key


def chunk_date_ranges(start_date: date, end_date: date) -> Iterator[tuple[date, date]]:
    """ASOS 공식 1회 최대 10년 제한에 맞춰 날짜 범위를 분할한다."""

    if start_date > end_date:
        raise ValueError("KMA 요청 시작일은 종료일보다 늦을 수 없습니다.")
    current = start_date
    while current <= end_date:
        chunk_end = min(date(current.year + 9, 12, 31), end_date)
        yield current, chunk_end
        current = date(chunk_end.year + 1, 1, 1)


def build_kma_params(
    api_key: str,
    station_id: str,
    start_date: date,
    end_date: date,
    page_no: int = 1,
    rows_per_page: int = 999,
) -> dict[str, str | int]:
    """공식 ASOS 일자료 요청 파라미터를 구성한다."""

    return {
        # 공공데이터포털의 URL-encoded 인증키도 requests가 정확히 한 번만
        # 인코딩하도록 decoded 값으로 정규화한다.
        "ServiceKey": unquote(api_key),
        "pageNo": page_no,
        "numOfRows": rows_per_page,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "DAY",
        "startDt": start_date.strftime("%Y%m%d"),
        "endDt": end_date.strftime("%Y%m%d"),
        "stnIds": str(station_id),
    }


def _redact_api_key(value: object, api_key: str) -> str:
    """서버가 인증키를 되돌려 보내도 원문·URL 인코딩 값을 표시하지 않는다."""

    message = str(value)
    variants = {api_key, unquote(api_key)} - {""}
    for _ in range(2):
        variants |= {quote(secret, safe="") for secret in variants}
    for secret in sorted(variants, key=len, reverse=True):
        message = re.sub(re.escape(secret), "REDACTED", message, flags=re.IGNORECASE)
    return re.sub(
        r"(?i)(servicekey\s*[=:]\s*)[^\s&<>\"']+", r"\1REDACTED", message
    )


def _api_response_error(
    payload: Any, http_status: int | None = None, api_key: str = ""
) -> KmaAsosError | None:
    """정상 API header와 공공데이터포털 gateway 오류 구조를 모두 해석한다."""

    if not isinstance(payload, dict):
        return None
    if "returnReasonCode" in payload:
        code = str(payload["returnReasonCode"])
        message = str(payload.get("errMsg", ""))
        detail = str(payload.get("returnAuthMsg", ""))
        message = " / ".join(value for value in (message, detail) if value)
    elif "resultCode" in payload:
        code = str(payload["resultCode"])
        message = str(payload.get("resultMsg", "알 수 없는 오류"))
    else:
        for value in payload.values():
            error = _api_response_error(value, http_status, api_key)
            if error is not None:
                return error
        return None
    if code in SUCCESS_API_CODES:
        return None
    safe_code = _redact_api_key(code, api_key)
    safe_message = _redact_api_key(message, api_key)
    return KmaAsosError(
        f"KMA API 오류(HTTP status={http_status}, resultCode={safe_code}, "
        f"ServiceKey=REDACTED): {safe_message}",
        http_status=http_status,
        result_code=safe_code,
        result_message=safe_message,
        retryable=code in RETRYABLE_API_CODES,
    )


def _xml_error_fields(text: str) -> dict[str, str]:
    """JSON 요청에도 반환될 수 있는 XML 오류에서 진단 필드만 추출한다."""

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return {}
    fields = {"resultCode", "resultMsg", "returnReasonCode", "returnAuthMsg", "errMsg"}
    return {
        node.tag.rsplit("}", 1)[-1]: node.text or ""
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] in fields
    }


def _response_body(
    payload: Any, *, http_status: int | None = None, api_key: str = ""
) -> tuple[list[dict[str, Any]], int]:
    """공공데이터포털 JSON 구조와 결과코드를 검증해 행과 전체 건수를 반환한다."""

    error = _api_response_error(payload, http_status, api_key)
    if error is not None:
        raise error
    try:
        response = payload["response"]
        header = response["header"]
        body = response["body"]
    except (KeyError, TypeError) as exc:
        raise KmaAsosError("KMA API 응답에 response/header/body 구조가 없습니다.") from exc

    result_code = str(header.get("resultCode", ""))
    if result_code not in SUCCESS_API_CODES:
        raise KmaAsosError("KMA API 응답에 정상 resultCode가 없습니다.")

    items = body.get("items", {})
    raw_rows = items.get("item", []) if isinstance(items, dict) else []
    if isinstance(raw_rows, dict):
        rows = [raw_rows]
    elif isinstance(raw_rows, list):
        rows = raw_rows
    elif raw_rows in (None, ""):
        rows = []
    else:
        raise KmaAsosError("KMA API items.item 형식이 올바르지 않습니다.")
    if not all(isinstance(row, dict) for row in rows):
        raise KmaAsosError("KMA API 일자료 행이 JSON 객체가 아닙니다.")
    try:
        total_count = int(body.get("totalCount", len(rows)))
    except (TypeError, ValueError) as exc:
        raise KmaAsosError("KMA API totalCount가 숫자가 아닙니다.") from exc
    return rows, total_count


class KmaAsosClient:
    """재시도와 페이지네이션을 포함한 KMA ASOS 일자료 클라이언트."""

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (10.0, 60.0),
        max_attempts: int = 4,
        retry_backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise KmaApiKeyError("빈 KMA API key는 사용할 수 없습니다.")
        self._api_key = api_key
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep = sleep

    def _request_page(self, params: dict[str, str | int]) -> tuple[list[dict[str, Any]], int]:
        """한 페이지를 요청하고 일시적 오류에 지수형 대기를 적용한다."""

        last_error: KmaAsosError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(KMA_ASOS_ENDPOINT, params=params, timeout=self.timeout)
                try:
                    payload = response.json()
                except ValueError:
                    payload = _xml_error_fields(response.text)
                # HTTP 403/429뿐 아니라 HTTP 200에 포함된 gateway 오류도 먼저 읽는다.
                error = _api_response_error(payload, response.status_code, self._api_key)
                if error is not None:
                    raise error
                if response.status_code >= 400:
                    raise KmaAsosError(
                        f"KMA API HTTP {response.status_code} (ServiceKey=REDACTED). "
                        "응답에 공식 오류코드가 없습니다.",
                        http_status=response.status_code,
                        retryable=response.status_code == 429
                        or 500 <= response.status_code < 600,
                    )
                return _response_body(
                    payload, http_status=response.status_code, api_key=self._api_key
                )
            except KmaAsosError as exc:
                last_error = exc
            except requests.RequestException as exc:
                # requests 예외 원문/원인 체인은 인증키가 포함된 URL을 담을 수 있다.
                last_error = KmaAsosError(
                    f"KMA API 요청에 실패했습니다({type(exc).__name__}, "
                    "ServiceKey=REDACTED). 네트워크 연결을 확인하세요.",
                    retryable=isinstance(exc, (requests.Timeout, requests.ConnectionError)),
                )
            if not last_error.retryable or attempt == self.max_attempts:
                break
            self.sleep(min(self.retry_backoff_seconds * (2 ** (attempt - 1)), 60.0))
        if last_error is not None:
            raise last_error from None
        raise KmaAsosError("KMA API 요청 시도 횟수는 1 이상이어야 합니다.")

    def fetch_period(
        self,
        station_id: str,
        start_date: date,
        end_date: date,
        *,
        rows_per_page: int = 999,
        page_interval_seconds: float = 0.0,
    ) -> list[dict[str, Any]]:
        """한 관측소·기간의 모든 페이지를 순서대로 다운로드한다."""

        rows: list[dict[str, Any]] = []
        page_no = 1
        total_count: int | None = None
        while total_count is None or len(rows) < total_count:
            if page_no > 1 and page_interval_seconds > 0:
                self.sleep(page_interval_seconds)
            params = build_kma_params(
                self._api_key,
                station_id,
                start_date,
                end_date,
                page_no,
                rows_per_page,
            )
            page_rows, total_count = self._request_page(params)
            if not page_rows and len(rows) < total_count:
                raise KmaAsosError("KMA API 페이지가 totalCount보다 먼저 비었습니다.")
            rows.extend(page_rows)
            page_no += 1
        return rows


def _cache_is_usable(path: Path, city_station: CityStation) -> bool:
    """도시 raw 캐시가 요청 관측소와 전체 설정 기간을 담는지 확인한다."""

    if not path.exists():
        return False
    try:
        cached = pd.read_csv(path, dtype={"stnId": "string", "_station_id": "string"})
    except (OSError, pd.errors.ParserError, UnicodeError):
        return False
    required = {"tm", "stnId", "_station_id", "_request_start", "_request_end"}
    if cached.empty or not required.issubset(cached.columns):
        return False
    cached["_station_id"] = cached["_station_id"].astype("string").str.strip()
    cached["_request_start"] = pd.to_datetime(cached["_request_start"], errors="coerce")
    cached["_request_end"] = pd.to_datetime(cached["_request_end"], errors="coerce")
    for segment in city_station.segments:
        station_rows = cached.loc[cached["_station_id"].eq(segment.station_id)]
        if station_rows.empty:
            return False
        minimum = station_rows["_request_start"].min()
        maximum = station_rows["_request_end"].max()
        if pd.isna(minimum) or pd.isna(maximum):
            return False
        if minimum.date() > segment.download_start or maximum.date() < segment.download_end:
            return False
    return True


def download_city_asos(
    city_station: CityStation,
    *,
    client: KmaAsosClient | None = None,
    api_key: str | None = None,
    output_path: Path | None = None,
    force_download: bool = False,
    request_interval_seconds: float = 0.25,
) -> KmaDownloadResult:
    """도시의 기간별 ASOS 원본을 다운로드하거나 검증된 캐시를 재사용한다."""

    path = output_path or kma_raw_data_path(city_station.key)
    if not force_download and _cache_is_usable(path, city_station):
        return KmaDownloadResult(pd.read_csv(path, dtype={"stnId": "string"}), "cache", path)
    client = client or KmaAsosClient(api_key or get_kma_api_key())
    all_rows: list[dict[str, Any]] = []
    request_count = 0
    for segment in city_station.segments:
        for chunk_start, chunk_end in chunk_date_ranges(
            segment.download_start, segment.download_end
        ):
            if request_count and request_interval_seconds > 0:
                client.sleep(request_interval_seconds)
            chunk_rows = client.fetch_period(
                segment.station_id,
                chunk_start,
                chunk_end,
                page_interval_seconds=request_interval_seconds,
            )
            for row in chunk_rows:
                enriched = dict(row)
                enriched.update(
                    {
                        "_city": city_station.city,
                        "_station_id": segment.station_id,
                        "_station_name": segment.station_name,
                        "_segment_start": segment.use_start.isoformat(),
                        "_segment_end": segment.use_end.isoformat(),
                        "_request_start": chunk_start.isoformat(),
                        "_request_end": chunk_end.isoformat(),
                    }
                )
                all_rows.append(enriched)
            request_count += 1
    if not all_rows:
        raise KmaAsosError(f"{city_station.city} KMA API 응답에 일자료가 없습니다.")
    dataframe = pd.DataFrame(all_rows)
    if not {"tm", "stnId"}.issubset(dataframe.columns):
        raise KmaAsosError("KMA raw에 필수 필드 tm 또는 stnId가 없습니다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False)
    return KmaDownloadResult(dataframe, "api", path)
