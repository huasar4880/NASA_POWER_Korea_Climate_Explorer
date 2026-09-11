"""KMA raw parsing, missing values, units, and station transition tests."""

from __future__ import annotations

import pandas as pd
import pytest

from src.kma_preprocess import preprocess_kma_data, solar_mj_to_kwh
from src.station_metadata import load_city_station


def test_raw_parsing_preserves_zero_and_missing() -> None:
    """Observed 0 mm remains zero while blank fields remain NaN."""

    raw = pd.DataFrame(
        {
            "tm": ["1981-01-01", "1981-01-02"],
            "stnId": ["108", "108"],
            "avgTa": ["1.5", ""],
            "maxTa": ["4", "5"],
            "minTa": ["-2", "-1"],
            "sumRn": ["0", ""],
            "avgRhm": ["70", ""],
            "avgWs": ["2", "3"],
            "sumGsr": ["3.6", ""],
        }
    )
    processed = preprocess_kma_data(raw, load_city_station("Seoul"))
    assert processed.loc[0, "precipitation"] == 0.0
    assert pd.isna(processed.loc[1, "precipitation"])
    assert pd.isna(processed.loc[1, "avg_temperature"])
    assert processed.loc[0, "solar_radiation"] == pytest.approx(1.0)


@pytest.mark.parametrize("blank", ["", " ", None, float("nan")])
def test_precipitation_blank_not_inferred_from_other_observations(blank: object) -> None:
    """Normal temperature, humidity and wind do not establish a valid dry-day amount."""

    raw = pd.DataFrame(
        {
            "tm": ["2020-01-03"],
            "stnId": ["108"],
            "avgTa": ["-0.1"],
            "avgRhm": ["56.9"],
            "avgWs": ["1.7"],
            "sumRn": [blank],
            "sumRnDur": [""],
            "avgTca": ["0.0"],
        }
    )
    original = raw.copy(deep=True)
    processed = preprocess_kma_data(raw, load_city_station("Seoul"))
    assert pd.isna(processed.loc[0, "precipitation"])
    assert processed.loc[0, "avg_temperature"] == pytest.approx(-0.1)
    pd.testing.assert_frame_equal(raw, original)


def test_weather_phenomena_do_not_impute_unknown_precipitation_amount() -> None:
    """Observed rain/snow with an empty amount is not automatically a measured zero."""

    raw = pd.DataFrame(
        {
            "tm": ["2023-11-28", "2023-11-29", "2025-05-14"],
            "stnId": ["108"] * 3,
            "sumRn": [""] * 3,
            "sumRnDur": ["0.0", "0.0", "0.5"],
            "iscs": [
                "{눈}1550-1610.",
                "{눈}1340-1445. {눈}1542-1657.",
                "{비}2310-2340.",
            ],
        }
    )
    processed = preprocess_kma_data(raw, load_city_station("Seoul"))
    assert processed["precipitation"].isna().all()


def test_absent_precipitation_field_stays_missing() -> None:
    """An absent precipitation field remains NaN even when another field is present."""

    raw = pd.DataFrame({"tm": ["2020-01-03"], "stnId": ["108"], "avgTa": ["-0.1"]})
    processed = preprocess_kma_data(raw, load_city_station("Seoul"))
    assert pd.isna(processed.loc[0, "precipitation"])


def test_precipitation_amounts_zero_and_null_remain_distinct() -> None:
    """Known numeric amounts are unchanged, and null is never a valid dry day."""

    raw = pd.DataFrame(
        {
            "tm": pd.date_range("2020-01-01", periods=5).strftime("%Y-%m-%d"),
            "stnId": ["108"] * 5,
            "sumRn": ["0", "0.0", "0.1", "46.3", None],
        }
    )
    processed = preprocess_kma_data(raw, load_city_station("Seoul"))
    assert processed["precipitation"].iloc[:4].tolist() == pytest.approx([0, 0, 0.1, 46.3])
    assert pd.isna(processed.loc[4, "precipitation"])


def test_solar_unit_conversion() -> None:
    """3.6 MJ/m²/day equals 1 kWh/m²/day and NaN is retained."""

    converted = solar_mj_to_kwh(pd.Series([3.6, 7.2, None]))
    assert converted.iloc[:2].tolist() == pytest.approx([1.0, 2.0])
    assert pd.isna(converted.iloc[2])


def test_gangneung_station_change_keeps_official_primary_series() -> None:
    """Station 104 overlap is not arbitrarily spliced into primary station 105 temperature."""

    raw = pd.DataFrame(
        {
            "tm": ["2008-07-27", "2008-07-28", "2008-07-28", "2008-07-29"],
            "stnId": ["105", "105", "104", "104"],
            "avgTa": [20.0, 99.0, 21.0, 22.0],
        }
    )
    processed = preprocess_kma_data(raw, load_city_station("Gangneung"))
    assert processed["station_id"].tolist() == ["105", "105"]
    assert processed["avg_temperature"].tolist() == [20.0, 99.0]
