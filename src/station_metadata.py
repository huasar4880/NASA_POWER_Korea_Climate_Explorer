"""KMA ASOS 관측소 메타데이터와 NASA 지점 매핑을 관리한다."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import KMA_STATIONS_PATH, LOCATIONS_PATH, Location, load_locations


@dataclass(frozen=True)
class StationSegment:
    """한 기간에 사용할 KMA ASOS 관측소 설정."""

    station_id: str
    station_name: str
    latitude: float
    longitude: float
    elevation_m: float
    observation_start: date
    use_start: date
    use_end: date
    download_start: date
    download_end: date
    role: str
    metadata_url: str


@dataclass(frozen=True)
class CityStation:
    """도시와 하나 이상의 기간별 ASOS 관측소 연결."""

    key: str
    city: str
    segments: tuple[StationSegment, ...]
    mapping_note: str = ""

    @property
    def primary_segments(self) -> tuple[StationSegment, ...]:
        """실제 도시 validation 시계열에 사용하는 관측소 구간만 반환한다."""

        return tuple(segment for segment in self.segments if segment.role == "primary")


def _parse_date(value: object, field: str, city_key: str) -> date:
    """ISO 날짜 설정을 검증해 ``date``로 변환한다."""

    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{city_key}의 {field} 날짜가 올바르지 않습니다: {value}") from exc


def load_kma_stations(path: Path = KMA_STATIONS_PATH) -> dict[str, CityStation]:
    """공식 출처를 기록한 KMA 관측소 설정을 읽고 기간 규칙을 검증한다."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"KMA 관측소 설정을 읽을 수 없습니다: {path}") from exc
    station_items = payload.get("stations") if isinstance(payload, dict) else None
    if not isinstance(station_items, dict) or not station_items:
        raise ValueError("KMA 관측소 설정에는 stations 객체가 필요합니다.")

    result: dict[str, CityStation] = {}
    for raw_key, item in station_items.items():
        key = str(raw_key).strip().casefold()
        if not isinstance(item, dict) or not isinstance(item.get("segments"), list):
            raise ValueError(f"KMA 관측소 설정이 올바르지 않습니다: {raw_key}")
        segments: list[StationSegment] = []
        for raw_segment in item["segments"]:
            try:
                segment = StationSegment(
                    station_id=str(raw_segment["station_id"]),
                    station_name=str(raw_segment["station_name"]),
                    latitude=float(raw_segment["latitude"]),
                    longitude=float(raw_segment["longitude"]),
                    elevation_m=float(raw_segment["elevation_m"]),
                    observation_start=_parse_date(
                        raw_segment["observation_start"], "observation_start", key
                    ),
                    use_start=_parse_date(raw_segment["use_start"], "use_start", key),
                    use_end=_parse_date(raw_segment["use_end"], "use_end", key),
                    download_start=_parse_date(
                        raw_segment.get("download_start", raw_segment["use_start"]),
                        "download_start",
                        key,
                    ),
                    download_end=_parse_date(
                        raw_segment.get("download_end", raw_segment["use_end"]),
                        "download_end",
                        key,
                    ),
                    role=str(raw_segment.get("role", "primary")),
                    metadata_url=str(raw_segment["metadata_url"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"KMA 관측소 세부 설정이 올바르지 않습니다: {key}") from exc
            if segment.use_start > segment.use_end:
                raise ValueError(f"KMA 관측소 사용 기간이 역전되었습니다: {key}")
            if segment.download_start > segment.use_start or segment.download_end < segment.use_end:
                raise ValueError(f"KMA 관측소 다운로드 기간이 사용 기간을 포함하지 않습니다: {key}")
            if segment.role not in {"primary", "continuity_only"}:
                raise ValueError(f"알 수 없는 KMA 관측소 역할입니다: {key}/{segment.role}")
            if not -90 <= segment.latitude <= 90 or not -180 <= segment.longitude <= 180:
                raise ValueError(f"KMA 관측소 좌표가 범위를 벗어났습니다: {key}")
            segments.append(segment)
        segments.sort(key=lambda value: value.use_start)
        primary_segments = [segment for segment in segments if segment.role == "primary"]
        if not primary_segments:
            raise ValueError(f"KMA primary 관측소가 없습니다: {key}")
        for previous, current in zip(primary_segments, primary_segments[1:]):
            if (current.use_start - previous.use_end).days != 1:
                raise ValueError(f"KMA 관측소 연결 기간이 연속적이지 않습니다: {key}")
        result[key] = CityStation(
            key=key,
            city=str(item["city"]),
            segments=tuple(segments),
            mapping_note=str(item.get("mapping_note", "")),
        )
    return result


def load_city_station(city_name: str, path: Path = KMA_STATIONS_PATH) -> CityStation:
    """도시 키 또는 이름에 대응하는 KMA 관측소 연결을 반환한다."""

    stations = load_kma_stations(path)
    normalized = city_name.strip().casefold()
    if normalized in stations:
        return stations[normalized]
    for station in stations.values():
        if station.city.casefold() == normalized:
            return station
    raise KeyError(f"KMA 관측소가 등록되지 않은 도시입니다: {city_name}")


def haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """두 WGS84 좌표 사이 대권거리를 Haversine 공식으로 계산한다."""

    radius_km = 6371.0088
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lon = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(value))


def build_station_metadata_table(
    stations: dict[str, CityStation] | None = None,
    locations: dict[str, Location] | None = None,
) -> pd.DataFrame:
    """관측소별 좌표·고도·사용기간·공식 출처 표를 만든다."""

    stations = stations or load_kma_stations()
    locations = locations or load_locations(LOCATIONS_PATH)
    rows = []
    for station in stations.values():
        for segment in station.segments:
            rows.append(
                {
                    "city": station.city,
                    "station_id": segment.station_id,
                    "station_name": segment.station_name,
                    "latitude": segment.latitude,
                    "longitude": segment.longitude,
                    "elevation_m": segment.elevation_m,
                    "observation_start": segment.observation_start.isoformat(),
                    "observation_end": None,
                    "use_start": segment.use_start.isoformat(),
                    "use_end": segment.use_end.isoformat(),
                    "download_start": segment.download_start.isoformat(),
                    "download_end": segment.download_end.isoformat(),
                    "role": segment.role,
                    "NASA_point_distance_km": haversine_km(
                        locations[station.key].latitude,
                        locations[station.key].longitude,
                        segment.latitude,
                        segment.longitude,
                    ),
                    "metadata_url": segment.metadata_url,
                    "mapping_note": station.mapping_note,
                }
            )
    return pd.DataFrame(rows)


def build_station_mapping_table(
    locations: dict[str, Location] | None = None,
    stations: dict[str, CityStation] | None = None,
) -> pd.DataFrame:
    """NASA POWER 도시 좌표와 연결된 KMA 관측소·거리를 표로 만든다."""

    locations = locations or load_locations(LOCATIONS_PATH)
    stations = stations or load_kma_stations()
    if set(locations) != set(stations):
        missing = sorted(set(locations).symmetric_difference(stations))
        raise ValueError(f"NASA 위치와 KMA 관측소 도시 구성이 다릅니다: {missing}")
    rows = []
    for key, location in locations.items():
        city_station = stations[key]
        for segment in city_station.segments:
            rows.append(
                {
                    "city": location.name,
                    "nasa_latitude": location.latitude,
                    "nasa_longitude": location.longitude,
                    "kma_station_id": segment.station_id,
                    "kma_station_name": segment.station_name,
                    "kma_latitude": segment.latitude,
                    "kma_longitude": segment.longitude,
                    "distance_km": haversine_km(
                        location.latitude,
                        location.longitude,
                        segment.latitude,
                        segment.longitude,
                    ),
                    "station_start_date": segment.observation_start.isoformat(),
                    "station_end_date": None,
                    "use_start": segment.use_start.isoformat(),
                    "use_end": segment.use_end.isoformat(),
                    "source": segment.metadata_url,
                    "role": segment.role,
                    "mapping_note": city_station.mapping_note,
                }
            )
    return pd.DataFrame(rows)
