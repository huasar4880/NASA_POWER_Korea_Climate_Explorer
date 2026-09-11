"""Conservative station-history and nearby-station review flags."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
import re

import pandas as pd

from src.nationwide.eligibility import ScreeningConfig


def haversine_km(latitude1: float, longitude1: float, latitude2: float, longitude2: float) -> float:
    """Return great-circle distance between two WGS84 coordinate pairs."""

    lat1, lon1, lat2, lon2 = map(radians, (latitude1, longitude1, latitude2, longitude2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(value))


def _normalized_name(value: object) -> str:
    """Normalize punctuation only; do not invent administrative relationships."""

    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value)).casefold()


def _name_related(first: object, second: object) -> bool:
    """Identify exact or directional-prefix name similarity for review only."""

    left = _normalized_name(first)
    right = _normalized_name(second)
    if not left or not right:
        return False
    if left == right:
        return True
    prefixes = ("북", "남", "동", "서", "신", "구")
    variants_left = {left, *(left[1:] for prefix in prefixes if left.startswith(prefix) and len(left) > 2)}
    variants_right = {right, *(right[1:] for prefix in prefixes if right.startswith(prefix) and len(right) > 2)}
    return bool(variants_left & variants_right)


def _interval_overlap_days(
    start1: pd.Timestamp,
    end1: pd.Timestamp | pd.NaT,
    start2: pd.Timestamp,
    end2: pd.Timestamp | pd.NaT,
) -> int:
    max_date = pd.Timestamp.max.normalize()
    left = max(start1, start2)
    right = min(end1 if pd.notna(end1) else max_date, end2 if pd.notna(end2) else max_date)
    return max(0, (right - left).days + 1)


def detect_station_history_flags(
    segments: pd.DataFrame,
    inventory: pd.DataFrame,
    config: ScreeningConfig,
) -> pd.DataFrame:
    """Create review flags without automatically joining any station records."""

    flags: list[dict[str, object]] = []
    for station_id, group in segments.groupby("station_id"):
        if len(group) <= 1:
            continue
        ordered = group.sort_values("segment_start_date")
        coordinates = ordered.dropna(subset=["latitude", "longitude"])
        movement = 0.0
        if len(coordinates) > 1:
            first, last = coordinates.iloc[0], coordinates.iloc[-1]
            movement = haversine_km(first.latitude, first.longitude, last.latitude, last.longitude)
        flags.append(
            {
                "station_id": station_id,
                "station_name": ordered.iloc[-1]["station_name"],
                "history_flag_type": "MULTIPLE_METADATA_SEGMENTS",
                "related_station_id": station_id,
                "related_station_name": ordered.iloc[0]["station_name"],
                "distance_km": movement,
                "date_overlap": pd.NA,
                "note": f"official metadata segments={len(ordered)}; endpoint movement={movement:.3f} km",
            }
        )

    representatives = inventory.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    for left_index in range(len(representatives)):
        left = representatives.iloc[left_index]
        for right_index in range(left_index + 1, len(representatives)):
            right = representatives.iloc[right_index]
            same_name = _normalized_name(left.station_name) == _normalized_name(right.station_name)
            distance = haversine_km(left.latitude, left.longitude, right.latitude, right.longitude)
            name_related = _name_related(left.station_name, right.station_name)
            if not same_name and distance > config.related_station_distance_km:
                continue
            overlap = _interval_overlap_days(
                pd.Timestamp(left.start_date),
                pd.to_datetime(left.end_date, errors="coerce"),
                pd.Timestamp(right.start_date),
                pd.to_datetime(right.end_date, errors="coerce"),
            )
            if same_name:
                flag_type = "DUPLICATE_NAME_DIFFERENT_ID"
            elif name_related:
                flag_type = "NEARBY_RELATED_NAME"
            elif distance <= config.close_station_distance_km:
                flag_type = "NEARBY_WITHIN_5KM"
            else:
                # Wider pairs are retained only when dates overlap or operation transitions closely.
                left_end = pd.to_datetime(left.end_date, errors="coerce")
                right_end = pd.to_datetime(right.end_date, errors="coerce")
                transition_days = min(
                    abs((pd.Timestamp(right.start_date) - left_end).days) if pd.notna(left_end) else 10**9,
                    abs((pd.Timestamp(left.start_date) - right_end).days) if pd.notna(right_end) else 10**9,
                )
                if not name_related and overlap == 0 and transition_days > 366:
                    continue
                flag_type = "NEARBY_WITHIN_20KM"
            for primary, related in ((left, right), (right, left)):
                flags.append(
                    {
                        "station_id": primary.station_id,
                        "station_name": primary.station_name,
                        "history_flag_type": flag_type,
                        "related_station_id": related.station_id,
                        "related_station_name": related.station_name,
                        "distance_km": distance,
                        "date_overlap": overlap,
                        "note": "review candidate only; records are not linked",
                    }
                )
    columns = [
        "station_id",
        "station_name",
        "history_flag_type",
        "related_station_id",
        "related_station_name",
        "distance_km",
        "date_overlap",
        "note",
    ]
    return pd.DataFrame(flags, columns=columns).sort_values(
        ["station_id", "history_flag_type", "related_station_id"]
    ).reset_index(drop=True)


def assign_continuity_risk(
    inventory: pd.DataFrame,
    history_flags: pd.DataFrame,
    config: ScreeningConfig,
) -> pd.DataFrame:
    """Attach low/medium/high/manual_review flags; never splice stations."""

    output = inventory.copy()
    risks: list[str] = []
    review_required: list[bool] = []
    for row in output.itertuples(index=False):
        flags = history_flags.loc[history_flags["station_id"].astype(str).eq(str(row.station_id))]
        risk = "low"
        if bool(row.metadata_invalid):
            risk = "manual_review"
        if not flags.empty:
            types = set(flags["history_flag_type"].astype(str))
            movement = pd.to_numeric(
                flags.loc[flags["history_flag_type"].eq("MULTIPLE_METADATA_SEGMENTS"), "distance_km"],
                errors="coerce",
            )
            if "DUPLICATE_NAME_DIFFERENT_ID" in types or "NEARBY_RELATED_NAME" in types:
                risk = "manual_review"
            elif movement.notna().any() and movement.max() >= config.relocation_distance_km:
                risk = "high"
            elif types:
                risk = "medium"
        risks.append(risk)
        review_required.append(risk in {"high", "manual_review"})
    output["continuity_risk"] = risks
    output["manual_review_required_metadata"] = review_required
    return output


def continuity_review_candidates(inventory: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    """Return only stations requiring explicit continuity review with their evidence."""

    risky = set(
        inventory.loc[
            inventory["continuity_risk"].isin(["high", "manual_review"]), "station_id"
        ].astype(str)
    )
    return flags.loc[flags["station_id"].astype(str).isin(risky)].reset_index(drop=True)
