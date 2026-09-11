"""Configurable nationwide ASOS metadata and daily-data eligibility rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import NATIONWIDE_SCREENING_CONFIG_PATH


ALLOWED_TIERS = {"A", "B", "C", "D", "X"}
REASON_CODES = {
    "ELIGIBLE_FULL_PERIOD",
    "ELIGIBLE_1991_PLUS",
    "STARTED_AFTER_1981",
    "ENDED_BEFORE_2025",
    "SHORT_RECORD",
    "HIGH_TEMP_MISSING",
    "LONG_TEMP_GAP",
    "LOW_ANNUAL_COMPLETENESS",
    "CONTINUITY_REVIEW",
    "NO_ASOS_DATA",
    "METADATA_DATA_MISMATCH",
    "METADATA_INVALID",
    "NOT_DETAILED_SCREENED",
}


@dataclass(frozen=True)
class ScreeningConfig:
    """Thresholds used by this project; these are not official KMA grades."""

    analysis_start_year: int = 1981
    analysis_end_year: int = 2025
    normal_start_year: int = 1991
    normal_end_year: int = 2020
    max_temperature_missing_rate: float = 0.05
    min_annual_completeness: float = 0.90
    min_fraction_years_complete: float = 0.90
    max_long_gap_days: int = 90
    minimum_years_for_trend: int = 20
    metadata_mismatch_tolerance_days: int = 31
    related_station_distance_km: float = 20.0
    close_station_distance_km: float = 5.0
    relocation_distance_km: float = 1.0
    probe_window_days: int = 31
    daily_rows_per_page: int = 999

    @property
    def analysis_start(self) -> date:
        return date(self.analysis_start_year, 1, 1)

    @property
    def analysis_end(self) -> date:
        return date(self.analysis_end_year, 12, 31)

    @property
    def normal_start(self) -> date:
        return date(self.normal_start_year, 1, 1)

    @property
    def normal_end(self) -> date:
        return date(self.normal_end_year, 12, 31)


def load_screening_config(path: Path = NATIONWIDE_SCREENING_CONFIG_PATH) -> ScreeningConfig:
    """Load and validate nationwide screening thresholds from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    config = ScreeningConfig(**payload)
    for value, label in (
        (config.max_temperature_missing_rate, "max_temperature_missing_rate"),
        (config.min_annual_completeness, "min_annual_completeness"),
        (config.min_fraction_years_complete, "min_fraction_years_complete"),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{label}는 0~1 범위여야 합니다.")
    if config.analysis_start_year > config.analysis_end_year:
        raise ValueError("analysis_start_year가 analysis_end_year보다 늦습니다.")
    if config.normal_start_year > config.normal_end_year:
        raise ValueError("normal_start_year가 normal_end_year보다 늦습니다.")
    if config.max_long_gap_days < 1 or config.minimum_years_for_trend < 1:
        raise ValueError("gap 및 최소 연수 기준은 1 이상이어야 합니다.")
    return config


def classify_metadata_tier(record: dict[str, Any] | pd.Series, config: ScreeningConfig) -> str:
    """Classify official metadata coverage without claiming daily-data eligibility."""

    if bool(record.get("metadata_invalid", False)):
        return "X"
    start = pd.to_datetime(record.get("start_date"), errors="coerce")
    end = pd.to_datetime(record.get("end_date"), errors="coerce")
    active = bool(record.get("is_active", False))
    effective_end = pd.Timestamp(config.analysis_end) if active or pd.isna(end) else end
    if pd.isna(start) or pd.isna(effective_end):
        return "X"
    if start <= pd.Timestamp(config.analysis_start) and effective_end >= pd.Timestamp(config.analysis_end):
        return "A"
    if start <= pd.Timestamp(config.normal_start) and effective_end >= pd.Timestamp(config.normal_end):
        return "B"
    years = max(0.0, (min(effective_end, pd.Timestamp(config.analysis_end)) - start).days / 365.2425)
    return "C" if years >= config.minimum_years_for_trend else "D"


def evaluate_period_quality(
    quality: dict[str, Any] | pd.Series,
    annual: pd.DataFrame,
    config: ScreeningConfig,
) -> tuple[bool, list[str]]:
    """Apply temperature missing, annual completeness and long-gap rules."""

    reasons: list[str] = []
    rates = [
        float(quality.get("avg_temp_missing_rate", math.nan)),
        float(quality.get("max_temp_missing_rate", math.nan)),
        float(quality.get("min_temp_missing_rate", math.nan)),
    ]
    if any(math.isnan(rate) or rate > config.max_temperature_missing_rate for rate in rates):
        reasons.append("HIGH_TEMP_MISSING")
    longest = float(quality.get("longest_temperature_gap_days", math.inf))
    if math.isnan(longest) or longest >= config.max_long_gap_days:
        reasons.append("LONG_TEMP_GAP")
    if annual.empty:
        reasons.append("LOW_ANNUAL_COMPLETENESS")
    else:
        good = int((annual["completeness_ratio"] >= config.min_annual_completeness).sum())
        required = math.ceil(len(annual) * config.min_fraction_years_complete)
        if good < required:
            reasons.append("LOW_ANNUAL_COMPLETENESS")
    return not reasons, reasons


def decide_eligibility(
    metadata_tier: str,
    quality: dict[str, Any] | pd.Series | None,
    annual: pd.DataFrame,
    config: ScreeningConfig,
    *,
    continuity_risk: str = "low",
    mismatch_flag: bool = False,
    probe_has_data: bool = True,
) -> tuple[str, bool, list[str]]:
    """Return final tier, manual-review flag, and standardized reason codes."""

    if metadata_tier not in ALLOWED_TIERS:
        raise ValueError(f"허용되지 않은 metadata tier입니다: {metadata_tier}")
    if not probe_has_data:
        return "X", True, ["NO_ASOS_DATA"]
    if quality is None:
        if metadata_tier in {"A", "B"}:
            return "X", True, ["NOT_DETAILED_SCREENED"]
        code = "STARTED_AFTER_1981" if metadata_tier == "C" else "SHORT_RECORD"
        return metadata_tier, False, [code]
    reasons: list[str] = []
    if continuity_risk in {"high", "manual_review"}:
        reasons.append("CONTINUITY_REVIEW")
    if mismatch_flag:
        reasons.append("METADATA_DATA_MISMATCH")
    quality_ok, quality_reasons = evaluate_period_quality(quality, annual, config)
    reasons.extend(quality_reasons)
    if reasons or not quality_ok:
        return "X", True, list(dict.fromkeys(reasons))
    if metadata_tier == "A":
        return "A", False, ["ELIGIBLE_FULL_PERIOD"]
    if metadata_tier == "B":
        return "B", False, ["ELIGIBLE_1991_PLUS"]
    return metadata_tier, False, ["STARTED_AFTER_1981" if metadata_tier == "C" else "SHORT_RECORD"]
