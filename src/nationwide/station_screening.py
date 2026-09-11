"""ASOS daily probes, station cache, request estimates, and restart state."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import json
import math
from pathlib import Path
import time
from typing import Any, Callable

import pandas as pd
import requests

from src.config import NATIONWIDE_ASOS_RAW_DIR, kma_raw_data_path
from src.kma_asos import KmaAsosClient, KmaAsosError, chunk_date_ranges
from src.nationwide.eligibility import ScreeningConfig
from src.station_metadata import load_kma_stations


PROBE_DIR = NATIONWIDE_ASOS_RAW_DIR / "probes"
STATION_CACHE_DIR = NATIONWIDE_ASOS_RAW_DIR / "stations"
SCREENING_STATE_PATH = NATIONWIDE_ASOS_RAW_DIR / "screening_state.json"


class CountingSession:
    """Count actual HTTP GET attempts without retaining credential-bearing URLs."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.request_count = 0

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        self.request_count += 1
        return self.session.get(url, **kwargs)


def load_screening_state(path: Path = SCREENING_STATE_PATH) -> dict[str, Any]:
    """Load resumable station status; malformed/missing state starts empty."""

    if not path.exists():
        return {"stations": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"stations": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("stations", {}), dict):
        return {"stations": {}}
    return payload


def save_screening_state(state: dict[str, Any], path: Path = SCREENING_STATE_PATH) -> Path:
    """Atomically persist status without endpoint URLs or credentials."""

    path.parent.mkdir(parents=True, exist_ok=True)

    def sanitized(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: sanitized(item)
                for key, item in value.items()
                if str(key).casefold() not in {"api_key", "apikey", "servicekey"}
            }
        if isinstance(value, list):
            return [sanitized(item) for item in value]
        return value

    safe = sanitized(state)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def probe_ranges(record: pd.Series | dict[str, Any], config: ScreeningConfig) -> list[tuple[date, date]]:
    """Build small start, baseline, middle, normal-end, recent/end availability windows."""

    start = pd.to_datetime(record.get("start_date"), errors="coerce")
    end = pd.to_datetime(record.get("end_date"), errors="coerce")
    active = bool(record.get("is_active", False))
    if pd.isna(start):
        return []
    effective_end = pd.Timestamp(config.analysis_end) if active or pd.isna(end) else end
    anchors = [
        max(start, pd.Timestamp(config.analysis_start)),
        max(start, pd.Timestamp(config.normal_start)),
        max(start, pd.Timestamp(date(2000, 1, 1))),
        max(start, pd.Timestamp(date(config.normal_end_year, 1, 1))),
        max(start, pd.Timestamp(date(config.analysis_end_year, 1, 1))),
    ]
    if pd.notna(end):
        anchors.append(max(start, end - pd.Timedelta(days=config.probe_window_days - 1)))
    ranges: list[tuple[date, date]] = []
    seen: set[tuple[date, date]] = set()
    for anchor in anchors:
        if anchor > effective_end:
            continue
        window_end = min(anchor + pd.Timedelta(days=config.probe_window_days - 1), effective_end)
        item = (anchor.date(), window_end.date())
        if item not in seen:
            seen.add(item)
            ranges.append(item)
    return ranges


def _probe_path(station_id: str, start_date: date, end_date: date) -> Path:
    return PROBE_DIR / f"{station_id}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv"


def _read_cache(path: Path) -> pd.DataFrame | None:
    """Return a structurally usable cache, otherwise let the caller refresh it."""

    try:
        data = pd.read_csv(path, dtype={"stnId": "string"}, low_memory=False)
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return None
    return data if {"tm", "stnId"}.issubset(data.columns) else None


def _write_cache(data: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically so interruption cannot leave a completed-looking file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    data.to_csv(temporary, index=False)
    temporary.replace(path)


def probe_station_availability(
    record: pd.Series | dict[str, Any],
    client: KmaAsosClient,
    config: ScreeningConfig,
    *,
    request_interval_seconds: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, object]]:
    """Probe small official daily windows and reuse each completed probe cache."""

    station_id = str(record.get("station_id"))
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for index, (start_date, end_date) in enumerate(probe_ranges(record, config)):
        path = _probe_path(station_id, start_date, end_date)
        source = "cache"
        data = _read_cache(path) if path.exists() else None
        if data is None:
            if index and request_interval_seconds > 0:
                sleep(request_interval_seconds)
            try:
                rows = client.fetch_period(
                    station_id,
                    start_date,
                    end_date,
                    rows_per_page=config.daily_rows_per_page,
                    page_interval_seconds=request_interval_seconds,
                )
            except KmaAsosError as exc:
                if exc.result_code != "03":
                    raise
                # Official NO_DATA means this requested window has zero rows.  Cache
                # that fact and continue other probes; it is not a station-wide error.
                rows = []
            data = pd.DataFrame(rows)
            if data.empty:
                data = pd.DataFrame(columns=["tm", "stnId"])
            data["_station_id"] = station_id
            data["_request_start"] = start_date.isoformat()
            data["_request_end"] = end_date.isoformat()
            _write_cache(data, path)
            source = "api"
        dates = pd.to_datetime(data.get("tm", pd.Series(dtype="object")), errors="coerce")
        results.append(
            {
                "station_id": station_id,
                "probe_start": start_date.isoformat(),
                "probe_end": end_date.isoformat(),
                "row_count": len(data),
                "first_date": dates.min().date().isoformat() if dates.notna().any() else pd.NA,
                "last_date": dates.max().date().isoformat() if dates.notna().any() else pd.NA,
                "has_data": bool(dates.notna().any()),
                "source": source,
            }
        )
    return results


def screening_period(record: pd.Series | dict[str, Any], config: ScreeningConfig) -> tuple[date, date] | None:
    """Return the detailed period for preliminary Tier A/B candidates."""

    tier = str(record.get("metadata_tier"))
    if tier == "A":
        return config.analysis_start, config.analysis_end
    if tier == "B":
        end = pd.to_datetime(record.get("end_date"), errors="coerce")
        active = bool(record.get("is_active", False))
        target_end = config.analysis_end if active or pd.isna(end) or end >= pd.Timestamp(config.analysis_end) else config.normal_end
        return config.normal_start, target_end
    return None


def _v1_station_cache(station_id: str, start_date: date, end_date: date) -> pd.DataFrame | None:
    """Read, but never modify, a matching stable-v1 city cache when it fully covers the period."""

    for key, station in load_kma_stations().items():
        if not any(segment.role == "primary" and segment.station_id == station_id for segment in station.segments):
            continue
        path = kma_raw_data_path(key)
        if not path.exists():
            continue
        raw = pd.read_csv(
            path,
            dtype={"stnId": "string", "_station_id": "string"},
            low_memory=False,
        )
        selected = raw.loc[raw["stnId"].astype("string").str.strip().eq(station_id)].copy()
        dates = pd.to_datetime(selected.get("tm"), errors="coerce")
        if dates.notna().any() and dates.min().date() <= start_date and dates.max().date() >= end_date:
            return selected.loc[dates.between(pd.Timestamp(start_date), pd.Timestamp(end_date))].copy()
    return None


def _station_output_path(station_id: str, start_date: date, end_date: date) -> Path:
    return STATION_CACHE_DIR / station_id / f"{station_id}_asos_daily_{start_date.year}_{end_date.year}.csv"


def _chunk_path(station_id: str, start_date: date, end_date: date) -> Path:
    return STATION_CACHE_DIR / station_id / "chunks" / f"{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv"


def download_station_daily(
    record: pd.Series | dict[str, Any],
    client: KmaAsosClient,
    config: ScreeningConfig,
    state: dict[str, Any],
    *,
    request_interval_seconds: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[pd.DataFrame, str, Path]:
    """Download a candidate with chunk cache and station-level resumable state."""

    station_id = str(record.get("station_id"))
    period = screening_period(record, config)
    if period is None:
        raise ValueError("detailed screening은 metadata Tier A/B에만 적용합니다.")
    start_date, end_date = period
    output_path = _station_output_path(station_id, start_date, end_date)
    station_state = state.setdefault("stations", {}).get(station_id, {})
    completed_cache = _read_cache(output_path) if output_path.exists() else None
    if (
        completed_cache is not None
        and station_state.get("status") == "completed"
        and station_state.get("start_date") == start_date.isoformat()
        and station_state.get("end_date") == end_date.isoformat()
    ):
        return completed_cache, "station_cache", output_path

    reused = _v1_station_cache(station_id, start_date, end_date)
    if reused is not None:
        _write_cache(reused, output_path)
        source = "v1_city_cache"
        data = reused
    else:
        parts: list[pd.DataFrame] = []
        api_chunk_index = 0
        for chunk_start, chunk_end in chunk_date_ranges(start_date, end_date):
            path = _chunk_path(station_id, chunk_start, chunk_end)
            part = _read_cache(path) if path.exists() else None
            if part is None:
                if api_chunk_index and request_interval_seconds > 0:
                    sleep(request_interval_seconds)
                try:
                    rows = client.fetch_period(
                        station_id,
                        chunk_start,
                        chunk_end,
                        rows_per_page=config.daily_rows_per_page,
                        page_interval_seconds=request_interval_seconds,
                    )
                except KmaAsosError as exc:
                    if exc.result_code != "03":
                        raise
                    # Preserve an official no-row interval as an empty raw chunk so
                    # the expected calendar later counts it as missing availability.
                    rows = []
                part = pd.DataFrame(rows)
                if part.empty:
                    part = pd.DataFrame(columns=["tm", "stnId"])
                part["_station_id"] = station_id
                part["_request_start"] = chunk_start.isoformat()
                part["_request_end"] = chunk_end.isoformat()
                _write_cache(part, path)
                api_chunk_index += 1
            parts.append(part)
        data = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["tm", "stnId"])
        _write_cache(data, output_path)
        source = "api_or_chunk_cache"

    state.setdefault("stations", {})[station_id] = {
        "status": "completed",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "row_count": len(data),
        "source": source,
        "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    save_screening_state(state)
    return data, source, output_path


def mark_station_failed(state: dict[str, Any], station_id: str, error_type: str) -> None:
    """Persist a safe failure category without traceback, URL or credential material."""

    state.setdefault("stations", {})[str(station_id)] = {
        "status": "failed",
        "error_type": error_type,
        "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    save_screening_state(state)


def estimate_daily_requests(inventory: pd.DataFrame, config: ScreeningConfig) -> dict[str, int]:
    """Estimate lower-bound HTTP calls, discounting existing probe/chunk/v1 caches."""

    probe_requests = 0
    detailed_requests = 0
    detailed_stations = 0
    for row in inventory.to_dict("records"):
        station_id = str(row["station_id"])
        for start_date, end_date in probe_ranges(row, config):
            probe_requests += int(not _probe_path(station_id, start_date, end_date).exists())
        period = screening_period(row, config)
        if period is None:
            continue
        detailed_stations += 1
        start_date, end_date = period
        output = _station_output_path(station_id, start_date, end_date)
        if output.exists():
            continue
        if _v1_station_cache(station_id, start_date, end_date) is not None:
            continue
        detailed_requests += sum(
            math.ceil(
                ((chunk_end - chunk_start).days + 1)
                / config.daily_rows_per_page
            )
            if not _chunk_path(station_id, chunk_start, chunk_end).exists()
            else 0
            for chunk_start, chunk_end in chunk_date_ranges(start_date, end_date)
        )
    return {
        "asos_stations": len(inventory),
        "preliminary_tier_ab": int(inventory["metadata_tier"].isin(["A", "B"]).sum()),
        "detailed_screening_stations": detailed_stations,
        "estimated_probe_requests": probe_requests,
        "estimated_detailed_requests": detailed_requests,
        "estimated_api_requests": probe_requests + detailed_requests,
    }


def select_sample_station_ids(inventory: pd.DataFrame) -> list[str]:
    """Select Seoul plus non-v1 long, recent-start, and historical examples."""

    primary_by_id = {
        segment.station_id
        for station in load_kma_stations().values()
        for segment in station.primary_segments
    }
    seoul_id = next(
        (
            segment.station_id
            for station in load_kma_stations().values()
            if station.key == "seoul"
            for segment in station.primary_segments
        ),
        None,
    )
    selected = [seoul_id] if seoul_id and seoul_id in set(inventory["station_id"].astype(str)) else []
    outside = inventory.loc[~inventory["station_id"].astype(str).isin(primary_by_id)]
    for subset in (
        outside.loc[outside["metadata_tier"].isin(["A", "B"])],
        outside.loc[(outside["metadata_tier"] == "D") & outside["is_active"].astype(bool)],
        outside.loc[~outside["is_active"].astype(bool)],
    ):
        if not subset.empty:
            candidate = str(subset.iloc[0]["station_id"])
            if candidate not in selected:
                selected.append(candidate)
    return selected


def existing_v1_station_matches(inventory: pd.DataFrame) -> pd.DataFrame:
    """Verify all configured v1 primary station IDs against official inventory names."""

    by_id = inventory.set_index(inventory["station_id"].astype(str), drop=False)
    rows: list[dict[str, object]] = []
    for station in load_kma_stations().values():
        for segment in station.primary_segments:
            found = segment.station_id in by_id.index
            official_name = by_id.loc[segment.station_id, "station_name"] if found else pd.NA
            rows.append(
                {
                    "city": station.city,
                    "station_id": segment.station_id,
                    "configured_name": segment.station_name,
                    "official_station_name": official_name,
                    "inventory_match": bool(found),
                }
            )
    return pd.DataFrame(rows)
