"""KMA station configuration and NASA-point distance tests."""

from __future__ import annotations

import pytest

from src.station_metadata import (
    build_station_mapping_table,
    haversine_km,
    load_city_station,
    load_kma_stations,
)


def test_station_config_parses_expected_ids_and_cities() -> None:
    """All eight NASA cities map to official station IDs; Gangneung has two segments."""

    stations = load_kma_stations()
    assert list(stations) == [
        "seoul",
        "busan",
        "daejeon",
        "daegu",
        "gwangju",
        "gangneung",
        "jeju",
        "jeonju",
    ]
    assert load_city_station("Seoul").segments[0].station_id == "108"
    gangneung = load_city_station("gangneung")
    assert [segment.station_id for segment in gangneung.segments] == ["105", "104"]
    assert [segment.station_id for segment in gangneung.primary_segments] == ["105"]
    assert gangneung.primary_segments[0].use_end.isoformat() == "2025-12-31"
    assert gangneung.segments[1].role == "continuity_only"


def test_haversine_distance_known_values() -> None:
    """One degree of longitude at the equator is about 111.2 km."""

    assert haversine_km(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)
    assert haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.195, rel=1e-3)


def test_mapping_table_has_distance_and_station_periods() -> None:
    """Mapping output includes one row per station segment and no invented exclusion."""

    mapping = build_station_mapping_table()
    assert len(mapping) == 9
    assert mapping["distance_km"].gt(0).all()
    assert {
        "city",
        "kma_station_id",
        "station_start_date",
        "station_end_date",
        "mapping_note",
        "role",
    }.issubset(mapping.columns)
