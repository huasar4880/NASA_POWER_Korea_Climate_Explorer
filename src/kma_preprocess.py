"""KMA ASOS 원본 일자료를 공통 단위의 tidy schema로 정제한다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.station_metadata import CityStation


KMA_FIELD_MAP = {
    "avgTa": "avg_temperature",
    "maxTa": "max_temperature",
    "minTa": "min_temperature",
    "sumRn": "precipitation",
    "avgRhm": "relative_humidity",
    "avgWs": "wind_speed",
    "sumGsr": "solar_radiation_mj",
}
PROCESSED_VALUE_COLUMNS = (
    "avg_temperature",
    "max_temperature",
    "min_temperature",
    "precipitation",
    "relative_humidity",
    "wind_speed",
    "solar_radiation",
)
SUSPICIOUS_RANGES = {
    "avg_temperature": (-90.0, 60.0),
    "max_temperature": (-90.0, 60.0),
    "min_temperature": (-90.0, 60.0),
    "precipitation": (0.0, 2_000.0),
    "relative_humidity": (0.0, 100.0),
    "wind_speed": (0.0, 100.0),
    "solar_radiation": (0.0, 20.0),
}


class KmaPreprocessError(ValueError):
    """KMA raw schema 또는 기간 연결이 올바르지 않을 때 발생한다."""


@dataclass(frozen=True)
class KmaDataQuality:
    """한 도시의 KMA 처리 자료 품질 요약."""

    city: str
    start_date: str | None
    end_date: str | None
    row_count: int
    duplicate_dates: int
    missing_dates: int
    station_change: bool
    station_ids: str
    missing_counts: dict[str, int]
    suspicious_counts: dict[str, int]


def solar_mj_to_kwh(values: pd.Series) -> pd.Series:
    """KMA 일사합 MJ/m²/day를 NASA 공통 단위 kWh/m²/day로 변환한다."""

    return pd.to_numeric(values, errors="coerce") / 3.6


def _station_name_map(city_station: CityStation) -> dict[str, str]:
    """관측소 번호별 공식 이름 매핑을 반환한다."""

    return {segment.station_id: segment.station_name for segment in city_station.segments}


def preprocess_kma_data(raw: pd.DataFrame, city_station: CityStation) -> pd.DataFrame:
    """ASOS raw 행을 기간별 관측소 규칙에 따라 선택하고 공통 schema로 변환한다.

    빈 문자열과 JSON null은 숫자 변환 과정에서 NaN으로 유지한다. 관측 강수 0은
    유효한 0 mm 값이므로 그대로 보존하고, 결측값을 보간하거나 0으로 채우지 않는다.
    """

    if not {"tm", "stnId"}.issubset(raw.columns):
        raise KmaPreprocessError("KMA raw에 tm과 stnId가 필요합니다.")
    working = raw.copy(deep=True)
    working["date"] = pd.to_datetime(working["tm"], format="%Y-%m-%d", errors="coerce")
    if working["date"].isna().any():
        raise KmaPreprocessError("KMA raw의 날짜 형식이 YYYY-MM-DD가 아닙니다.")
    working["station_id"] = working["stnId"].astype("string").str.strip()

    selected_parts: list[pd.DataFrame] = []
    for segment in city_station.primary_segments:
        mask = (
            working["station_id"].eq(segment.station_id)
            & working["date"].between(
                pd.Timestamp(segment.use_start), pd.Timestamp(segment.use_end), inclusive="both"
            )
        )
        selected_parts.append(working.loc[mask].copy())
    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else working.iloc[0:0]
    if selected.empty:
        raise KmaPreprocessError(f"{city_station.city} 사용기간에 해당하는 KMA 행이 없습니다.")
    duplicate_count = int(selected["date"].duplicated(keep=False).sum())
    if duplicate_count:
        raise KmaPreprocessError(
            f"{city_station.city} 기간 연결 후 중복 날짜가 {duplicate_count}행 있습니다."
        )

    output = pd.DataFrame(
        {
            "date": selected["date"],
            "city": city_station.city,
            "station_id": selected["station_id"],
            "station_name": selected["station_id"].map(_station_name_map(city_station)),
        }
    )
    for source, target in KMA_FIELD_MAP.items():
        if source in selected:
            output[target] = pd.to_numeric(selected[source], errors="coerce")
        else:
            output[target] = np.nan
    output["solar_radiation"] = solar_mj_to_kwh(output.pop("solar_radiation_mj"))
    output["year"] = output["date"].dt.year
    output["month"] = output["date"].dt.month
    output["day"] = output["date"].dt.day
    ordered = [
        "date",
        "city",
        "station_id",
        "station_name",
        "year",
        "month",
        "day",
        *PROCESSED_VALUE_COLUMNS,
    ]
    return output.loc[:, ordered].sort_values("date").reset_index(drop=True)


def assess_kma_quality(
    dataframe: pd.DataFrame,
    city_station: CityStation,
    *,
    expected_start: date,
    expected_end: date,
) -> KmaDataQuality:
    """결측·중복·누락일·의심 범위를 세되 관측값을 제거하지 않는다."""

    dates = pd.to_datetime(dataframe["date"], errors="coerce")
    expected = pd.date_range(expected_start, expected_end, freq="D")
    actual_dates = pd.DatetimeIndex(dates.dropna().unique())
    missing_counts = {
        column: int(dataframe[column].isna().sum()) for column in PROCESSED_VALUE_COLUMNS
    }
    suspicious_counts = {}
    for column, (lower, upper) in SUSPICIOUS_RANGES.items():
        values = pd.to_numeric(dataframe[column], errors="coerce")
        suspicious_counts[column] = int(((values < lower) | (values > upper)).sum())
    station_ids = sorted(dataframe["station_id"].dropna().astype(str).unique())
    return KmaDataQuality(
        city=city_station.city,
        start_date=dates.min().strftime("%Y-%m-%d") if dates.notna().any() else None,
        end_date=dates.max().strftime("%Y-%m-%d") if dates.notna().any() else None,
        row_count=len(dataframe),
        duplicate_dates=int(dates.duplicated().sum()),
        missing_dates=len(expected.difference(actual_dates)),
        station_change=len(station_ids) > 1,
        station_ids="|".join(station_ids),
        missing_counts=missing_counts,
        suspicious_counts=suspicious_counts,
    )


def quality_to_record(quality: KmaDataQuality) -> dict[str, object]:
    """중첩 품질 객체를 CSV 한 행으로 평탄화한다."""

    record: dict[str, object] = {
        "city": quality.city,
        "start_date": quality.start_date,
        "end_date": quality.end_date,
        "row_count": quality.row_count,
        "duplicate_dates": quality.duplicate_dates,
        "missing_dates": quality.missing_dates,
        "station_change": quality.station_change,
        "station_ids": quality.station_ids,
    }
    record.update({f"missing_{key}": value for key, value in quality.missing_counts.items()})
    record.update(
        {f"suspicious_{key}": value for key, value in quality.suspicious_counts.items()}
    )
    return record


def save_kma_processed(dataframe: pd.DataFrame, path: Path) -> Path:
    """정제 ASOS 자료를 raw와 분리된 CSV로 저장한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False, date_format="%Y-%m-%d")
    return path
