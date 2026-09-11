"""Unit coverage for experimental nationwide ASOS station screening."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.nationwide.completeness import (
    calculate_annual_completeness,
    calculate_daily_quality,
    count_missing_gaps,
    expected_day_count,
    longest_missing_streak,
    parse_daily_availability,
)
from src.nationwide.eligibility import (
    ScreeningConfig,
    classify_metadata_tier,
    decide_eligibility,
)
from src.nationwide.nationwide_workflow import (
    NationwideInventoryResult,
    _build_exclusion,
    _mismatch,
    run_nationwide_screening,
)
from src.nationwide.station_history import (
    assign_continuity_risk,
    detect_station_history_flags,
    haversine_km,
)
from src.nationwide.station_inventory import (
    KMA_ASOS_CLASS_CODE,
    _metadata_form,
    build_station_inventory,
    parse_station_metadata,
)
from src.nationwide.station_screening import (
    download_station_daily,
    estimate_daily_requests,
    existing_v1_station_matches,
    load_screening_state,
    probe_station_availability,
    save_screening_state,
)
from src.kma_asos import KmaAsosError
from src.station_metadata import load_kma_stations


OFFICIAL_COLUMNS = {
    "지점": "108",
    "시작일": "1907-10-01",
    "종료일": "",
    "지점명": "서울",
    "지점주소": "서울특별시 종로구 송월동",
    "관리관서": "수도권기상청(119)",
    "위도": 37.5714,
    "경도": 126.9658,
    "노장해발고도(m)": 85.67,
}


def _segments(*, second: bool = False) -> pd.DataFrame:
    rows = [
        {
            "station_id": "108",
            "segment_start_date": pd.Timestamp("1907-10-01"),
            "segment_end_date": pd.NaT if not second else pd.Timestamp("1999-12-31"),
            "station_name": "서울",
            "station_address": "서울특별시 종로구 송월동",
            "managing_office": "수도권기상청(119)",
            "latitude": 37.5714,
            "longitude": 126.9658,
            "elevation_m": 85.67,
            "network": "ASOS",
            "station_type": "종관기상관측",
        }
    ]
    if second:
        rows.append(
            {
                **rows[0],
                "segment_start_date": pd.Timestamp("2000-01-01"),
                "segment_end_date": pd.NaT,
                "latitude": 37.60,
                "longitude": 127.00,
            }
        )
    return pd.DataFrame(rows)


def _inventory(config: ScreeningConfig | None = None, *, second: bool = False) -> pd.DataFrame:
    return build_station_inventory(
        _segments(second=second),
        config or ScreeningConfig(),
        retrieved_at="2026-01-01T00:00:00+00:00",
    )


def _raw_daily(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tm": dates,
            "stnId": ["108"] * len(dates),
            "avgTa": [1.0] * len(dates),
            "maxTa": [3.0] * len(dates),
            "minTa": [-1.0] * len(dates),
            "sumRn": [np.nan] * len(dates),
            "avgRhm": [60.0] * len(dates),
            "avgWs": [2.0] * len(dates),
            "sumGsr": [np.nan] * len(dates),
        }
    )


def _good_quality() -> dict[str, float]:
    return {
        "avg_temp_missing_rate": 0.0,
        "max_temp_missing_rate": 0.0,
        "min_temp_missing_rate": 0.0,
        "longest_temperature_gap_days": 0,
    }


def _good_annual() -> pd.DataFrame:
    return pd.DataFrame({"year": [2024, 2025], "completeness_ratio": [1.0, 0.99]})


def test_a_station_metadata_parsing(tmp_path: Path) -> None:
    path = tmp_path / "stations.csv"
    pd.DataFrame([OFFICIAL_COLUMNS]).to_csv(path, index=False, encoding="cp949")
    parsed = parse_station_metadata(path)
    assert parsed.loc[0, "station_id"] == "108"
    assert parsed.loc[0, "station_name"] == "서울"
    assert parsed.loc[0, "network"] == "ASOS"


def test_b_official_form_filters_asos_only() -> None:
    form = _metadata_form("csv")
    assert KMA_ASOS_CLASS_CODE == "SFC01"
    assert form["mddlClssCd"] == KMA_ASOS_CLASS_CODE
    assert form["serviceSe"] == "F00101"


def test_c_station_start_and_end_dates() -> None:
    row = _inventory().iloc[0]
    assert row.start_date == pd.Timestamp("1907-10-01")
    assert pd.isna(row.end_date)


def test_d_active_station_classification() -> None:
    row = _inventory().iloc[0]
    assert bool(row.is_active)
    assert bool(row.available_through_2025_metadata)


def test_e_duplicate_station_name_detection() -> None:
    inventory = pd.DataFrame(
        [
            {"station_id": "1", "station_name": "동일", "start_date": pd.Timestamp("1980-01-01"), "end_date": pd.NaT, "latitude": 36.0, "longitude": 127.0},
            {"station_id": "2", "station_name": "동일", "start_date": pd.Timestamp("1990-01-01"), "end_date": pd.NaT, "latitude": 36.1, "longitude": 127.1},
        ]
    )
    flags = detect_station_history_flags(pd.DataFrame(columns=_segments().columns), inventory, ScreeningConfig())
    assert set(flags["history_flag_type"]) == {"DUPLICATE_NAME_DIFFERENT_ID"}


def test_f_related_station_distance() -> None:
    assert haversine_km(37.5, 127.0, 37.5, 127.0) == pytest.approx(0.0)
    assert haversine_km(37.5, 127.0, 37.5, 127.1) == pytest.approx(8.83, rel=0.02)


def test_g_metadata_tier_a_classification() -> None:
    assert classify_metadata_tier({"start_date": "1980-01-01", "end_date": None, "is_active": True}, ScreeningConfig()) == "A"


def test_h_metadata_tier_b_classification() -> None:
    assert classify_metadata_tier({"start_date": "1985-01-01", "end_date": "2020-12-31", "is_active": False}, ScreeningConfig()) == "B"


def test_i_actual_daily_availability_parsing() -> None:
    parsed = parse_daily_availability(_raw_daily(["2025-01-01"]), "108")
    assert parsed.loc[0, "avg_temperature"] == 1.0
    assert parsed.loc[0, "solar_radiation"] is np.nan or pd.isna(parsed.loc[0, "solar_radiation"])


def test_j_missing_date_count() -> None:
    daily = parse_daily_availability(_raw_daily(["2025-01-01", "2025-01-03"]), "108")
    quality, _ = calculate_daily_quality(daily, "108", date(2025, 1, 1), date(2025, 1, 3))
    assert quality["missing_dates"] == 1


def test_k_annual_completeness() -> None:
    dates = pd.date_range("2025-01-01", "2025-12-31")
    daily = parse_daily_availability(_raw_daily(dates.strftime("%Y-%m-%d").tolist()), "108")
    result = calculate_annual_completeness(daily, date(2025, 1, 1), date(2025, 12, 31))
    assert result.loc[0, "valid_days_T2M"] == 365
    assert result.loc[0, "completeness_ratio"] == 1.0


def test_l_leap_year_expected_day_count() -> None:
    assert expected_day_count(date(2024, 1, 1), date(2024, 12, 31)) == 366


def test_m_longest_missing_streak() -> None:
    assert longest_missing_streak(pd.Series([1.0, np.nan, np.nan, 2.0, np.nan])) == 2


def test_n_gap_at_least_30_days() -> None:
    values = pd.Series([1.0] + [np.nan] * 30 + [2.0])
    assert count_missing_gaps(values, 30) == 1
    assert count_missing_gaps(values, 31) == 0


def test_o_temperature_missing_rate() -> None:
    raw = _raw_daily(["2025-01-01", "2025-01-02", "2025-01-03"])
    raw.loc[1, "avgTa"] = np.nan
    quality, _ = calculate_daily_quality(parse_daily_availability(raw, "108"), "108", date(2025, 1, 1), date(2025, 1, 3))
    assert quality["avg_temp_missing_rate"] == pytest.approx(1 / 3)
    assert quality["core_temperature_missing_rate"] == pytest.approx(1 / 9)


def test_p_eligibility_rule_tier_a() -> None:
    tier, manual, reasons = decide_eligibility("A", _good_quality(), _good_annual(), ScreeningConfig())
    assert (tier, manual, reasons) == ("A", False, ["ELIGIBLE_FULL_PERIOD"])


def test_q_eligibility_rule_tier_b() -> None:
    tier, manual, reasons = decide_eligibility("B", _good_quality(), _good_annual(), ScreeningConfig())
    assert (tier, manual, reasons) == ("B", False, ["ELIGIBLE_1991_PLUS"])


def test_r_exclusion_reason_code() -> None:
    tier, manual, reasons = decide_eligibility("A", {**_good_quality(), "avg_temp_missing_rate": 0.2}, _good_annual(), ScreeningConfig())
    assert tier == "X" and manual and "HIGH_TEMP_MISSING" in reasons
    master = pd.DataFrame([{"station_id": "108", "station_name": "서울", "eligibility_tier": tier, "eligibility_reason": "|".join(reasons), "mismatch_note": ""}])
    assert "HIGH_TEMP_MISSING" in set(_build_exclusion(master)["reason_code"])


def test_s_continuity_risk_flag() -> None:
    config = ScreeningConfig()
    segments = _segments(second=True)
    inventory = build_station_inventory(segments, config, retrieved_at="2026-01-01T00:00:00+00:00")
    flags = detect_station_history_flags(segments, inventory, config)
    result = assign_continuity_risk(inventory, flags, config)
    assert result.loc[0, "continuity_risk"] == "high"


def test_t_metadata_vs_actual_mismatch() -> None:
    mismatch, note = _mismatch({"actual_data_start_date": "1981-03-15", "actual_data_end_date": "2025-12-31"}, date(1981, 1, 1), date(2025, 12, 31), ScreeningConfig())
    assert mismatch and "late" in note


def test_u_station_cache_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.nationwide.station_screening as module

    monkeypatch.setattr(module, "STATION_CACHE_DIR", tmp_path)
    output = tmp_path / "108" / "108_asos_daily_1981_2025.csv"
    output.parent.mkdir(parents=True)
    _raw_daily(["2025-01-01"]).to_csv(output, index=False)
    state = {"stations": {"108": {"status": "completed", "start_date": "1981-01-01", "end_date": "2025-12-31"}}}

    class NoNetwork:
        def fetch_period(self, *_args: object, **_kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("cache reuse must not call API")

    data, source, path = download_station_daily({"station_id": "108", "metadata_tier": "A"}, NoNetwork(), ScreeningConfig(), state)
    assert len(data) == 1 and source == "station_cache" and path == output


def test_v_restart_state_is_safe(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    save_screening_state({"api_key": "secret", "serviceKey": "secret", "stations": {"108": {"status": "completed"}}}, path)
    text = path.read_text(encoding="utf-8")
    assert "secret" not in text
    assert load_screening_state(path)["stations"]["108"]["status"] == "completed"


def test_w_dry_run_api_estimate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.nationwide.station_screening as module

    monkeypatch.setattr(module, "PROBE_DIR", tmp_path / "probes")
    monkeypatch.setattr(module, "STATION_CACHE_DIR", tmp_path / "stations")
    inventory = pd.DataFrame([{"station_id": "999", "start_date": pd.Timestamp("2020-01-01"), "end_date": pd.NaT, "is_active": True, "metadata_tier": "D"}])
    estimate = estimate_daily_requests(inventory, ScreeningConfig())
    assert estimate["estimated_probe_requests"] == 2
    assert estimate["estimated_detailed_requests"] == 0


def test_x_kma_key_missing_skips_daily_screening(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.nationwide.nationwide_workflow as module

    inventory = _inventory()
    inventory["continuity_risk"] = "low"
    inventory["manual_review_required_metadata"] = False
    result = NationwideInventoryResult(None, inventory, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())  # type: ignore[arg-type]
    monkeypatch.setattr(module, "build_nationwide_inventory", lambda **_kwargs: result)
    monkeypatch.setattr(module, "estimate_daily_requests", lambda *_args: {"estimated_api_requests": 1})
    screened = run_nationwide_screening(api_key=None)
    assert screened.daily_screening_skipped and screened.actual_api_requests == 0


def test_y_existing_eight_station_mapping() -> None:
    rows = []
    for station in load_kma_stations().values():
        for segment in station.primary_segments:
            rows.append({"station_id": segment.station_id, "station_name": segment.station_name})
    mapping = existing_v1_station_matches(pd.DataFrame(rows).drop_duplicates("station_id"))
    assert len(mapping) == 8
    assert mapping["inventory_match"].all()


def test_z_precipitation_blank_does_not_exclude_station() -> None:
    daily = parse_daily_availability(_raw_daily(["2025-01-01", "2025-01-02"]), "108")
    assert daily["precipitation"].isna().all()
    tier, manual, _ = decide_eligibility("A", _good_quality(), _good_annual(), ScreeningConfig())
    assert tier == "A" and not manual


def test_aa_solar_missing_does_not_exclude_station() -> None:
    daily = parse_daily_availability(_raw_daily(["2025-01-01", "2025-01-02"]), "108")
    assert daily["solar_radiation"].isna().all()
    tier, manual, _ = decide_eligibility("B", _good_quality(), _good_annual(), ScreeningConfig())
    assert tier == "B" and not manual


def test_no_data_probe_is_cached_as_empty_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Official code 03 applies to one window and must not abort all station probes."""

    import src.nationwide.station_screening as module

    monkeypatch.setattr(module, "PROBE_DIR", tmp_path)

    class NoDataClient:
        def fetch_period(self, *_args: object, **_kwargs: object) -> list[dict[str, object]]:
            raise KmaAsosError("NO_DATA", result_code="03", result_message="NO_DATA")

    record = {
        "station_id": "999",
        "start_date": pd.Timestamp("2025-01-01"),
        "end_date": pd.NaT,
        "is_active": True,
    }
    results = probe_station_availability(
        record,
        NoDataClient(),  # type: ignore[arg-type]
        ScreeningConfig(),
        request_interval_seconds=0,
    )
    assert results and not any(result["has_data"] for result in results)
    assert len(list(tmp_path.glob("*.csv"))) == len(results)
