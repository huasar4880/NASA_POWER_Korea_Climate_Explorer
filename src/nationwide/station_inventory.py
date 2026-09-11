"""Official KMA ASOS station-history metadata collection and inventory parsing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Callable

import pandas as pd
import requests

from src.config import STATION_METADATA_DIR, STATION_METADATA_PROCESSED_DIR, STATION_METADATA_RAW_DIR
from src.nationwide.eligibility import ScreeningConfig, classify_metadata_tier


KMA_STATION_METADATA_PAGE = "https://data.kma.go.kr/tmeta/stn/selectStnList.do?pgmNo=123"
KMA_STATION_METADATA_LIST = "https://data.kma.go.kr/tmeta/stn/selectStnList.do"
KMA_STATION_METADATA_DOWNLOAD = "https://data.kma.go.kr/tmeta/stn/selectStnListDownload.do"
KMA_ASOS_CLASS_CODE = "SFC01"
RAW_METADATA_PATH = STATION_METADATA_RAW_DIR / "kma_station_metadata_raw.csv"
METADATA_MANIFEST_PATH = STATION_METADATA_RAW_DIR / "metadata_manifest.json"
PROCESSED_INVENTORY_PATH = STATION_METADATA_PROCESSED_DIR / "kma_asos_station_inventory.csv"
PUBLIC_INVENTORY_PATH = STATION_METADATA_DIR / "kma_asos_station_inventory.csv"

OFFICIAL_COLUMN_MAP = {
    "지점": "station_id",
    "시작일": "segment_start_date",
    "종료일": "segment_end_date",
    "지점명": "station_name",
    "지점주소": "station_address",
    "관리관서": "managing_office",
    "위도": "latitude",
    "경도": "longitude",
    "노장해발고도(m)": "elevation_m",
}


class StationMetadataError(RuntimeError):
    """Official station metadata could not be collected or parsed."""


@dataclass(frozen=True)
class MetadataCollectionResult:
    """ASOS metadata segments and consolidated station inventory."""

    segments: pd.DataFrame
    inventory: pd.DataFrame
    source: str
    request_count: int
    retrieved_at: str


def _metadata_form(file_type: str = "") -> dict[str, str]:
    """Return the official portal form selecting ASOS (`SFC01`) only."""

    return {
        "fileType": file_type,
        "pageIndex": "1",
        "schListCnt": "10",
        "mddlClssCd": KMA_ASOS_CLASS_CODE,
        "stnIds": "",
        "serviceSe": "F00101",
        "txtStnNm": "",
        "txtElementNm": "",
        "dTreeId": "",
        "gTreeId": "",
        "mddlClssCdDiff": "",
        "pgmNo": "123",
    }


class StationMetadataClient:
    """Small retrying client for the official session-backed CSV export."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (10.0, 60.0),
        max_attempts: int = 4,
        backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep
        self.request_count = 0

    def _post(self, url: str, data: dict[str, str]) -> requests.Response:
        """POST with bounded retry for transport, 429 and server errors."""

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.request_count += 1
                response = self.session.post(url, data=data, timeout=self.timeout)
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                self.sleep(min(self.backoff_seconds * 2 ** (attempt - 1), 60.0))
        raise StationMetadataError(
            f"KMA 공식 station metadata 요청 실패({type(last_error).__name__ if last_error else 'unknown'})."
        ) from None

    def fetch_asos_csv(self) -> bytes:
        """Initialize the official ASOS-filtered session and return CSV bytes."""

        self._post(KMA_STATION_METADATA_LIST, _metadata_form())
        response = self._post(KMA_STATION_METADATA_DOWNLOAD, _metadata_form("csv"))
        content_type = response.headers.get("Content-Type", "").lower()
        content = response.content
        if "csv" not in content_type or b"<html" in content[:512].lower():
            raise StationMetadataError("KMA station metadata 응답이 CSV가 아닙니다.")
        return content


def _read_manifest(path: Path = METADATA_MANIFEST_PATH) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_station_metadata(path: Path) -> pd.DataFrame:
    """Parse the official MS949 CSV into normalized ASOS history segments."""

    try:
        raw = pd.read_csv(path, encoding="cp949", dtype={"지점": "string"})
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise StationMetadataError(f"KMA station metadata CSV를 읽을 수 없습니다: {exc}") from exc
    missing = sorted(set(OFFICIAL_COLUMN_MAP) - set(raw.columns))
    if missing:
        raise StationMetadataError(f"KMA station metadata 필수 컬럼 누락: {', '.join(missing)}")
    segments = raw.rename(columns=OFFICIAL_COLUMN_MAP).loc[:, list(OFFICIAL_COLUMN_MAP.values())].copy()
    segments["station_id"] = segments["station_id"].astype("string").str.strip()
    segments["station_name"] = segments["station_name"].astype("string").str.strip()
    segments["station_address"] = segments["station_address"].astype("string").str.strip()
    segments["managing_office"] = segments["managing_office"].astype("string").str.strip()
    for column in ("segment_start_date", "segment_end_date"):
        segments[column] = pd.to_datetime(segments[column], errors="coerce")
    for column in ("latitude", "longitude", "elevation_m"):
        segments[column] = pd.to_numeric(segments[column], errors="coerce")
    segments = segments.dropna(subset=["station_id", "segment_start_date"]).copy()
    if segments.empty:
        raise StationMetadataError("ASOS metadata segment가 없습니다.")
    segments["network"] = "ASOS"
    segments["station_type"] = "종관기상관측"
    return segments.sort_values(["station_id", "segment_start_date"]).reset_index(drop=True)


def _region_from_address(address: object) -> tuple[object, object]:
    """Use official address tokens only; never infer a region from station name."""

    if pd.isna(address) or not str(address).strip():
        return pd.NA, pd.NA
    tokens = str(address).strip().split()
    return tokens[0], tokens[1] if len(tokens) > 1 else pd.NA


def _metadata_invalid(row: pd.Series) -> bool:
    """Flag impossible dates or implausible Korean station coordinates without deleting them."""

    start = row["segment_start_date"]
    end = row["segment_end_date"]
    bad_dates = pd.notna(end) and end < start
    lat = row["latitude"]
    lon = row["longitude"]
    bad_coordinates = pd.isna(lat) or pd.isna(lon) or not (32.0 <= lat <= 39.5 and 124.0 <= lon <= 132.0)
    return bool(bad_dates or bad_coordinates)


def build_station_inventory(
    segments: pd.DataFrame,
    config: ScreeningConfig,
    *,
    retrieved_at: str,
) -> pd.DataFrame:
    """Consolidate official history segments to one ASOS inventory row per station ID."""

    rows: list[dict[str, object]] = []
    for station_id, group in segments.groupby("station_id", sort=True):
        ordered = group.sort_values("segment_start_date")
        open_segments = ordered.loc[ordered["segment_end_date"].isna()]
        representative = (open_segments if not open_segments.empty else ordered).iloc[-1]
        active = not open_segments.empty
        end = pd.NaT if active else ordered["segment_end_date"].max()
        region1, region2 = _region_from_address(representative["station_address"])
        invalid = bool(ordered.apply(_metadata_invalid, axis=1).any())
        start = ordered["segment_start_date"].min()
        effective_end = pd.Timestamp(config.analysis_end) if active else end
        years = (
            max(0.0, (effective_end - start).days / 365.2425)
            if pd.notna(start) and pd.notna(effective_end)
            else float("nan")
        )
        record: dict[str, object] = {
            "station_id": str(station_id),
            "station_name": representative["station_name"],
            "start_date": start,
            "end_date": end,
            "is_active": active,
            "observation_years_metadata": years,
            "latitude": representative["latitude"],
            "longitude": representative["longitude"],
            "elevation_m": representative["elevation_m"],
            "elevation_outlier_flag": bool(
                pd.notna(representative["elevation_m"])
                and not (-100.0 <= float(representative["elevation_m"]) <= 3000.0)
            ),
            "station_address": representative["station_address"],
            "managing_office": representative["managing_office"],
            "region_level1": region1,
            "region_level2": region2,
            "network": "ASOS",
            "station_type": "종관기상관측",
            "metadata_source": KMA_STATION_METADATA_PAGE,
            "metadata_retrieved_at": retrieved_at,
            "metadata_segment_count": len(ordered),
            "metadata_invalid": invalid,
            "has_1981_metadata": bool(start <= pd.Timestamp(config.analysis_start) <= effective_end),
            "has_1991_metadata": bool(start <= pd.Timestamp(config.normal_start) <= effective_end),
            "available_through_2025_metadata": bool(effective_end >= pd.Timestamp(config.analysis_end)),
            "metadata_start_before_1981": bool(start <= pd.Timestamp(config.analysis_start)),
            "metadata_end_after_2025": bool(effective_end >= pd.Timestamp(config.analysis_end)),
            "metadata_full_period_candidate": bool(
                start <= pd.Timestamp(config.analysis_start) and effective_end >= pd.Timestamp(config.analysis_end)
            ),
            "has_full_1991_2020_metadata": bool(
                start <= pd.Timestamp(config.normal_start) and effective_end >= pd.Timestamp(config.normal_end)
            ),
            "notes": "multiple official history segments" if len(ordered) > 1 else "",
        }
        record["metadata_tier"] = classify_metadata_tier(record, config)
        rows.append(record)
    inventory = pd.DataFrame(rows)
    if inventory["station_id"].duplicated().any():
        raise StationMetadataError("station inventory의 station_id가 중복되었습니다.")
    return inventory.sort_values("station_id", key=lambda value: value.astype(int)).reset_index(drop=True)


def collect_station_metadata(
    config: ScreeningConfig,
    *,
    refresh: bool = False,
    client: StationMetadataClient | None = None,
) -> MetadataCollectionResult:
    """Download or reuse the official ASOS-only metadata cache and save inventory CSVs."""

    STATION_METADATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    STATION_METADATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    source = "cache"
    request_count = 0
    if refresh or not RAW_METADATA_PATH.exists():
        metadata_client = client or StationMetadataClient()
        content = metadata_client.fetch_asos_csv()
        temporary = RAW_METADATA_PATH.with_suffix(".csv.tmp")
        temporary.write_bytes(content)
        temporary.replace(RAW_METADATA_PATH)
        retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        manifest = {
            "metadata_source": KMA_STATION_METADATA_PAGE,
            "download_endpoint": KMA_STATION_METADATA_DOWNLOAD,
            "network_filter": "ASOS",
            "official_class_code": KMA_ASOS_CLASS_CODE,
            "metadata_retrieved_at": retrieved_at,
        }
        METADATA_MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        source = "official_download"
        request_count = metadata_client.request_count
    manifest = _read_manifest()
    retrieved_at = str(
        manifest.get(
            "metadata_retrieved_at",
            datetime.fromtimestamp(RAW_METADATA_PATH.stat().st_mtime, UTC).replace(microsecond=0).isoformat(),
        )
    )
    segments = parse_station_metadata(RAW_METADATA_PATH)
    inventory = build_station_inventory(segments, config, retrieved_at=retrieved_at)
    inventory.to_csv(PROCESSED_INVENTORY_PATH, index=False, date_format="%Y-%m-%d")
    inventory.to_csv(PUBLIC_INVENTORY_PATH, index=False, date_format="%Y-%m-%d")
    return MetadataCollectionResult(segments, inventory, source, request_count, retrieved_at)
