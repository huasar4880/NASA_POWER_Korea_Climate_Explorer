"""End-to-end nationwide ASOS inventory, screening, and shortlist workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
import time
from typing import Any

import pandas as pd

from src.config import NATIONWIDE_CHARTS_DIR, TABLES_DIR, ensure_directories
from src.kma_asos import KmaAsosClient, KmaAsosError
from src.nationwide.completeness import (
    calculate_daily_quality,
    parse_daily_availability,
)
from src.nationwide.eligibility import ScreeningConfig, decide_eligibility, load_screening_config
from src.nationwide.nationwide_visualization import create_station_inventory_map
from src.nationwide.station_history import (
    assign_continuity_risk,
    continuity_review_candidates,
    detect_station_history_flags,
)
from src.nationwide.station_inventory import (
    MetadataCollectionResult,
    PROCESSED_INVENTORY_PATH,
    PUBLIC_INVENTORY_PATH,
    StationMetadataClient,
    collect_station_metadata,
)
from src.nationwide.station_screening import (
    CountingSession,
    SCREENING_STATE_PATH,
    download_station_daily,
    estimate_daily_requests,
    existing_v1_station_matches,
    load_screening_state,
    mark_station_failed,
    probe_station_availability,
    save_screening_state,
    screening_period,
    select_sample_station_ids,
)


HISTORY_FLAGS_PATH = TABLES_DIR / "nationwide_station_history_flags.csv"
CONTINUITY_REVIEW_PATH = TABLES_DIR / "nationwide_station_continuity_review_candidates.csv"
MASTER_PATH = TABLES_DIR / "nationwide_asos_station_master.csv"
SHORTLIST_PATH = TABLES_DIR / "nationwide_asos_longterm_shortlist.csv"
EXCLUDED_PATH = TABLES_DIR / "nationwide_asos_excluded_or_review.csv"
REGIONAL_COVERAGE_PATH = TABLES_DIR / "nationwide_asos_regional_coverage.csv"
SCREENING_SUMMARY_PATH = TABLES_DIR / "nationwide_asos_screening_summary.csv"
DATA_QUALITY_PATH = TABLES_DIR / "nationwide_asos_data_quality.csv"
ANNUAL_COMPLETENESS_PATH = TABLES_DIR / "nationwide_asos_annual_completeness.csv"
PROBES_PATH = TABLES_DIR / "nationwide_asos_availability_probes.csv"
ELEVATION_SUMMARY_PATH = TABLES_DIR / "nationwide_asos_elevation_summary.csv"
V1_MAPPING_CHECK_PATH = TABLES_DIR / "nationwide_asos_v1_station_mapping_check.csv"
INVENTORY_MAP_PATH = NATIONWIDE_CHARTS_DIR / "asos_station_inventory_map.html"


@dataclass(frozen=True)
class NationwideInventoryResult:
    """Official inventory plus history/continuity screening products."""

    metadata: MetadataCollectionResult
    inventory: pd.DataFrame
    history_flags: pd.DataFrame
    continuity_review: pd.DataFrame
    v1_mapping: pd.DataFrame


@dataclass(frozen=True)
class NationwideScreeningResult:
    """Nationwide screening outputs and request accounting."""

    inventory_result: NationwideInventoryResult
    master: pd.DataFrame
    shortlist: pd.DataFrame
    excluded: pd.DataFrame
    summary: pd.DataFrame
    estimates: dict[str, int]
    actual_api_requests: int
    dry_run: bool
    daily_screening_skipped: bool


def build_nationwide_inventory(
    *,
    refresh: bool = False,
    config: ScreeningConfig | None = None,
    metadata_client: StationMetadataClient | None = None,
) -> NationwideInventoryResult:
    """Collect ASOS-only metadata, add conservative history risks, and save inventory products."""

    ensure_directories()
    config = config or load_screening_config()
    metadata = collect_station_metadata(config, refresh=refresh, client=metadata_client)
    history = detect_station_history_flags(metadata.segments, metadata.inventory, config)
    inventory = assign_continuity_risk(metadata.inventory, history, config)
    continuity = continuity_review_candidates(inventory, history)
    v1_mapping = existing_v1_station_matches(inventory)
    inventory.to_csv(PROCESSED_INVENTORY_PATH, index=False, date_format="%Y-%m-%d")
    inventory.to_csv(PUBLIC_INVENTORY_PATH, index=False, date_format="%Y-%m-%d")
    history.to_csv(HISTORY_FLAGS_PATH, index=False)
    continuity.to_csv(CONTINUITY_REVIEW_PATH, index=False)
    v1_mapping.to_csv(V1_MAPPING_CHECK_PATH, index=False)
    return NationwideInventoryResult(metadata, inventory, history, continuity, v1_mapping)


def _mismatch(
    quality: dict[str, Any], start_date: date, end_date: date, config: ScreeningConfig
) -> tuple[bool, str]:
    """Compare requested eligibility bounds and actual returned bounds without overwriting either."""

    actual_start = pd.to_datetime(quality.get("actual_data_start_date"), errors="coerce")
    actual_end = pd.to_datetime(quality.get("actual_data_end_date"), errors="coerce")
    messages: list[str] = []
    if pd.isna(actual_start) or pd.isna(actual_end):
        return True, "actual daily start/end unavailable"
    if (actual_start - pd.Timestamp(start_date)).days > config.metadata_mismatch_tolerance_days:
        messages.append(f"actual start is {(actual_start - pd.Timestamp(start_date)).days} days late")
    if (pd.Timestamp(end_date) - actual_end).days > config.metadata_mismatch_tolerance_days:
        messages.append(f"actual end is {(pd.Timestamp(end_date) - actual_end).days} days early")
    return bool(messages), "; ".join(messages)


def _empty_master(inventory: pd.DataFrame) -> pd.DataFrame:
    """Build a metadata-only master without inventing daily eligibility."""

    master = inventory.rename(
        columns={"start_date": "metadata_start_date", "end_date": "metadata_end_date"}
    ).copy()
    master["actual_data_start_date"] = pd.NA
    master["actual_data_end_date"] = pd.NA
    for column in (
        "expected_days",
        "expected_dates",
        "actual_rows",
        "avg_temp_missing_rate",
        "max_temp_missing_rate",
        "min_temp_missing_rate",
        "core_temperature_missing_rate",
        "longest_temperature_gap_days",
        "annual_completeness_median",
        "years_ge_90pct_complete",
    ):
        master[column] = pd.NA
    master["data_quality_tier"] = "NOT_SCREENED"
    master["eligibility_tier"] = master["metadata_tier"].where(
        ~master["metadata_tier"].isin(["A", "B"]), "X"
    )
    master["eligible_1981_2025"] = False
    master["eligible_1991_2025"] = False
    master["eligible_1991_2020"] = False
    metadata_review = master.get(
        "manual_review_required_metadata", pd.Series(False, index=master.index)
    ).fillna(False).astype(bool)
    master["manual_review_required"] = master["metadata_tier"].isin(["A", "B"]) | metadata_review

    def metadata_reason(row: pd.Series) -> str:
        tier = str(row["metadata_tier"])
        if tier in {"A", "B"}:
            codes = ["NOT_DETAILED_SCREENED"]
        elif tier == "C":
            start = pd.to_datetime(row.get("metadata_start_date"), errors="coerce")
            codes = [
                "STARTED_AFTER_1981"
                if pd.notna(start) and start > pd.Timestamp("1981-01-01")
                else "ENDED_BEFORE_2025"
            ]
        elif tier == "D":
            codes = ["SHORT_RECORD"]
        else:
            codes = ["METADATA_INVALID"]
        review_value = row.get("manual_review_required_metadata", False)
        if pd.notna(review_value) and bool(review_value):
            codes.append("CONTINUITY_REVIEW")
        return "|".join(dict.fromkeys(codes))

    master["eligibility_reason"] = master.apply(metadata_reason, axis=1)
    master["mismatch_flag"] = False
    master["mismatch_note"] = ""
    return master


def _regional_coverage(master: pd.DataFrame) -> pd.DataFrame:
    """Count tiers by official first-level address; unspecified addresses remain explicit."""

    grouped = master.copy()
    grouped["region"] = grouped["region_level1"].fillna("UNSPECIFIED")
    records: list[dict[str, object]] = []
    for region, data in grouped.groupby("region", dropna=False):
        records.append(
            {
                "region": region,
                "total_asos_stations": len(data),
                "tier_a_count": int(data["eligibility_tier"].eq("A").sum()),
                "tier_b_count": int(data["eligibility_tier"].eq("B").sum()),
                "manual_review_count": int(data["manual_review_required"].astype(bool).sum()),
                "excluded_count": int(
                    (
                        ~data["eligibility_tier"].isin(["A", "B"])
                        & ~data["manual_review_required"].astype(bool)
                    ).sum()
                ),
            }
        )
    return pd.DataFrame(records).sort_values("region").reset_index(drop=True)


def _elevation_summary(master: pd.DataFrame) -> pd.DataFrame:
    """Summarize inventory/shortlist elevation without relating elevation to trends."""

    rows: list[dict[str, object]] = []
    for scope, data in (
        ("all_inventory", master),
        ("longterm_shortlist", master.loc[master["eligibility_tier"].isin(["A", "B"])]),
    ):
        values = pd.to_numeric(data["elevation_m"], errors="coerce").dropna()
        bands = pd.cut(values, [-math.inf, 50, 200, 500, math.inf], right=False, labels=["<50m", "50-200m", "200-500m", ">=500m"])
        rows.append(
            {
                "scope": scope,
                "station_count_with_elevation": len(values),
                "elevation_min_m": values.min() if not values.empty else pd.NA,
                "elevation_median_m": values.median() if not values.empty else pd.NA,
                "elevation_max_m": values.max() if not values.empty else pd.NA,
                "below_50m": int((bands == "<50m").sum()),
                "from_50_to_200m": int((bands == "50-200m").sum()),
                "from_200_to_500m": int((bands == "200-500m").sum()),
                "at_or_above_500m": int((bands == ">=500m").sum()),
            }
        )
    return pd.DataFrame(rows)


def _build_exclusion(master: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for record in master.loc[~master["eligibility_tier"].isin(["A", "B"])].to_dict("records"):
        codes = str(record.get("eligibility_reason", "METADATA_INVALID")).split("|")
        for code in filter(None, codes):
            rows.append(
                {
                    "station_id": record["station_id"],
                    "station_name": record["station_name"],
                    "reason_code": code,
                    "reason_detail": record.get("mismatch_note", "") if code == "METADATA_DATA_MISMATCH" else "See station master and screening rules.",
                }
            )
    return pd.DataFrame(rows, columns=["station_id", "station_name", "reason_code", "reason_detail"])


def _shortlist(master: pd.DataFrame) -> pd.DataFrame:
    selected = master.loc[master["eligibility_tier"].isin(["A", "B"])].copy()
    selected["region"] = (
        selected["region_level1"].fillna("").astype(str)
        .str.cat(selected["region_level2"].fillna("").astype(str), sep=" ")
        .str.strip()
    )
    selected["analysis_start"] = selected["eligibility_tier"].map({"A": "1981-01-01", "B": "1991-01-01"})
    selected["analysis_end"] = selected["eligible_1991_2025"].map({True: "2025-12-31", False: "2020-12-31"})
    selected["recommended_analysis_period"] = selected["analysis_start"] + "~" + selected["analysis_end"]
    selected["temperature_missing_rate"] = selected["core_temperature_missing_rate"]
    selected["annual_completeness"] = selected["annual_completeness_median"]
    selected["nasa_query_latitude"] = selected["latitude"]
    selected["nasa_query_longitude"] = selected["longitude"]
    selected["notes"] = selected["eligibility_reason"]
    return selected.loc[
        :,
        [
            "station_id", "station_name", "region", "latitude", "longitude", "elevation_m",
            "analysis_start", "analysis_end", "eligibility_tier", "temperature_missing_rate",
            "annual_completeness", "continuity_risk", "recommended_analysis_period",
            "nasa_query_latitude", "nasa_query_longitude", "notes",
        ],
    ].sort_values("station_id", key=lambda value: value.astype(int)).reset_index(drop=True)


def _summary(master: pd.DataFrame, detailed_screened: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "total_asos_stations": len(master),
                "active_stations": int(master["is_active"].astype(bool).sum()),
                "historical_inactive_stations": int((~master["is_active"].astype(bool)).sum()),
                "metadata_tier_a": int(master["metadata_tier"].eq("A").sum()),
                "metadata_tier_b": int(master["metadata_tier"].eq("B").sum()),
                "detailed_screened": detailed_screened,
                "final_tier_a": int(master["eligibility_tier"].eq("A").sum()),
                "final_tier_b": int(master["eligibility_tier"].eq("B").sum()),
                "manual_review": int(master["manual_review_required"].astype(bool).sum()),
                "excluded": int((~master["eligibility_tier"].isin(["A", "B"]) & ~master["manual_review_required"].astype(bool)).sum()),
                "eligible_1981_2025": int(master["eligible_1981_2025"].astype(bool).sum()),
                "eligible_1991_2025": int(master["eligible_1991_2025"].astype(bool).sum()),
                "eligible_1991_2020": int(master["eligible_1991_2020"].astype(bool).sum()),
            }
        ]
    )


def _save_products(master: pd.DataFrame, quality: pd.DataFrame, annual: pd.DataFrame, probes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Save all new nationwide tables and the inventory-only map."""

    if master["station_id"].astype(str).duplicated().any():
        raise ValueError("nationwide station master의 station_id가 중복되었습니다.")
    allowed = {"A", "B", "C", "D", "X"}
    invalid_tiers = set(master["eligibility_tier"].dropna().astype(str)) - allowed
    if invalid_tiers:
        raise ValueError(f"허용되지 않은 eligibility tier: {sorted(invalid_tiers)}")
    for column in (
        "avg_temp_missing_rate",
        "max_temp_missing_rate",
        "min_temp_missing_rate",
        "core_temperature_missing_rate",
        "annual_completeness_median",
    ):
        values = pd.to_numeric(master[column], errors="coerce").dropna()
        if not values.between(0, 1).all():
            raise ValueError(f"{column}이 0~1 범위를 벗어났습니다.")

    shortlist = _shortlist(master)
    excluded = _build_exclusion(master)
    regional = _regional_coverage(master)
    elevation = _elevation_summary(master)
    master.to_csv(MASTER_PATH, index=False, date_format="%Y-%m-%d")
    shortlist.to_csv(SHORTLIST_PATH, index=False)
    excluded.to_csv(EXCLUDED_PATH, index=False)
    regional.to_csv(REGIONAL_COVERAGE_PATH, index=False)
    elevation.to_csv(ELEVATION_SUMMARY_PATH, index=False)
    quality.to_csv(DATA_QUALITY_PATH, index=False)
    annual.to_csv(ANNUAL_COMPLETENESS_PATH, index=False)
    probes.to_csv(PROBES_PATH, index=False)
    create_station_inventory_map(master, INVENTORY_MAP_PATH)
    return shortlist, excluded, regional


def run_nationwide_screening(
    *,
    api_key: str | None,
    refresh_stations: bool = False,
    dry_run: bool = False,
    batch_size: int | None = None,
    sample_only: bool = False,
    request_interval_seconds: float = 0.25,
    config: ScreeningConfig | None = None,
    metadata_client: StationMetadataClient | None = None,
    daily_client: KmaAsosClient | None = None,
) -> NationwideScreeningResult:
    """Probe all stations and fully screen only preliminary Tier A/B candidates."""

    config = config or load_screening_config()
    inventory_result = build_nationwide_inventory(
        refresh=refresh_stations, config=config, metadata_client=metadata_client
    )
    inventory = inventory_result.inventory
    estimates = estimate_daily_requests(inventory, config)
    metadata_only = _empty_master(inventory)
    if dry_run or not api_key:
        summary = _summary(metadata_only, 0)
        return NationwideScreeningResult(
            inventory_result,
            metadata_only,
            metadata_only.iloc[0:0].copy(),
            _build_exclusion(metadata_only),
            summary,
            estimates,
            0,
            dry_run,
            not bool(api_key),
        )

    counter: CountingSession | None = None
    if daily_client is None:
        counter = CountingSession()
        daily_client = KmaAsosClient(api_key, session=counter)
    selected_ids = set(select_sample_station_ids(inventory)) if sample_only else set(inventory["station_id"].astype(str))
    selected_inventory = inventory.loc[inventory["station_id"].astype(str).isin(selected_ids)].copy()
    probe_records: list[dict[str, object]] = []
    failed_probe_ids: set[str] = set()
    for position, row in enumerate(selected_inventory.itertuples(index=False), 1):
        if position > 1 and request_interval_seconds > 0:
            time.sleep(request_interval_seconds)
        print(f"[probe {position}/{len(selected_inventory)}] station {row.station_id} {row.station_name}")
        try:
            probe_records.extend(
                probe_station_availability(
                    row._asdict(), daily_client, config, request_interval_seconds=request_interval_seconds
                )
            )
        except KmaAsosError as exc:
            failed_probe_ids.add(str(row.station_id))
            print(
                f"- probe 실패: station={row.station_id}, HTTP={exc.http_status}, "
                f"resultCode={exc.result_code}, message={exc.result_message or type(exc).__name__}"
            )
            if exc.result_code == "22":
                raise
    probes = pd.DataFrame(probe_records)
    if not probes.empty and not sample_only:
        probes.to_csv(PROBES_PATH, index=False)
    probe_any = (
        probes.groupby("station_id")["has_data"].any().to_dict() if not probes.empty else {}
    )

    state = load_screening_state()
    candidates = selected_inventory.loc[selected_inventory["metadata_tier"].isin(["A", "B"])].copy()
    if batch_size is not None and batch_size > 0:
        completed_ids = {
            str(station_id)
            for station_id, item in state.get("stations", {}).items()
            if isinstance(item, dict) and item.get("status") == "completed"
        }
        completed = candidates.loc[candidates["station_id"].astype(str).isin(completed_ids)]
        pending = candidates.loc[~candidates["station_id"].astype(str).isin(completed_ids)].head(batch_size)
        candidates = pd.concat([completed, pending], ignore_index=True).drop_duplicates("station_id")
    quality_records: list[dict[str, object]] = []
    annual_records: list[pd.DataFrame] = []
    decisions: dict[str, dict[str, object]] = {}
    for position, row in enumerate(candidates.itertuples(index=False), 1):
        if request_interval_seconds > 0:
            time.sleep(request_interval_seconds)
        station_id = str(row.station_id)
        print(f"[screen {position}/{len(candidates)}] station {station_id} {row.station_name}")
        if station_id in failed_probe_ids or not bool(probe_any.get(station_id, False)):
            decisions[station_id] = {"tier": "X", "manual": True, "reasons": ["NO_ASOS_DATA"]}
            continue
        try:
            raw, source, _ = download_station_daily(
                row._asdict(), daily_client, config, state, request_interval_seconds=request_interval_seconds
            )
            daily = parse_daily_availability(raw, station_id)
            period = screening_period(row._asdict(), config)
            assert period is not None
            start_date, end_date = period
            quality, annual = calculate_daily_quality(daily, station_id, start_date, end_date)
            quality["cache_source"] = source
            mismatch_flag, mismatch_note = _mismatch(quality, start_date, end_date, config)
            quality["mismatch_flag"] = mismatch_flag
            quality["mismatch_note"] = mismatch_note
            final_tier, manual, reasons = decide_eligibility(
                row.metadata_tier,
                quality,
                annual,
                config,
                continuity_risk=row.continuity_risk,
                mismatch_flag=mismatch_flag,
                probe_has_data=True,
            )
            # A station that misses the full-period rule may still meet the explicit 1991+ rule.
            if row.metadata_tier == "A" and final_tier == "X" and row.continuity_risk not in {"high", "manual_review"}:
                quality_b, annual_b = calculate_daily_quality(daily, station_id, config.normal_start, config.analysis_end)
                mismatch_b, note_b = _mismatch(quality_b, config.normal_start, config.analysis_end, config)
                tier_b, manual_b, reasons_b = decide_eligibility(
                    "B", quality_b, annual_b, config, continuity_risk=row.continuity_risk,
                    mismatch_flag=mismatch_b, probe_has_data=True,
                )
                if tier_b == "B":
                    final_tier, manual, reasons = tier_b, manual_b, reasons_b
                    quality = quality_b
                    annual = annual_b
                    start_date, end_date = config.normal_start, config.analysis_end
                    quality["cache_source"] = source
                    quality["eligibility_quality_period"] = "1991-01-01~2025-12-31"
                    quality["mismatch_flag"] = mismatch_b
                    quality["mismatch_note"] = note_b
            quality_records.append(quality)
            annual = annual.assign(station_id=station_id, screening_start=start_date.isoformat(), screening_end=end_date.isoformat())
            annual_records.append(annual)
            decisions[station_id] = {"tier": final_tier, "manual": manual, "reasons": reasons}
        except (OSError, ValueError, KmaAsosError) as exc:
            mark_station_failed(state, station_id, type(exc).__name__)
            decisions[station_id] = {"tier": "X", "manual": True, "reasons": ["NOT_DETAILED_SCREENED"]}
            if isinstance(exc, KmaAsosError):
                print(
                    f"- 상세검사 실패: station={station_id}, HTTP={exc.http_status}, "
                    f"resultCode={exc.result_code}, message={exc.result_message or type(exc).__name__}"
                )
            else:
                print(f"- 상세검사 실패: station={station_id}, error={type(exc).__name__}")
            if isinstance(exc, KmaAsosError) and exc.result_code == "22":
                raise

    quality_frame = pd.DataFrame(quality_records)
    annual_frame = pd.concat(annual_records, ignore_index=True) if annual_records else pd.DataFrame(
        columns=["year", "expected_days", "valid_days_T2M", "completeness_ratio", "station_id"]
    )
    master = _empty_master(inventory)
    if not quality_frame.empty:
        overlap = [column for column in quality_frame.columns if column != "station_id" and column in master.columns]
        master = master.drop(columns=overlap).merge(quality_frame, on="station_id", how="left", validate="one_to_one")
    for index, row in master.iterrows():
        station_id = str(row["station_id"])
        if station_id in decisions:
            decision = decisions[station_id]
            master.at[index, "eligibility_tier"] = decision["tier"]
            master.at[index, "manual_review_required"] = decision["manual"]
            master.at[index, "eligibility_reason"] = "|".join(decision["reasons"])
            master.at[index, "data_quality_tier"] = decision["tier"] if decision["tier"] in {"A", "B"} else "FAIL_OR_REVIEW"
    master["eligible_1981_2025"] = master["eligibility_tier"].eq("A")
    actual_end = pd.to_datetime(master.get("actual_data_end_date"), errors="coerce")
    master["eligible_1991_2025"] = master["eligibility_tier"].isin(["A", "B"]) & actual_end.ge(pd.Timestamp(config.analysis_end))
    master["eligible_1991_2020"] = master["eligibility_tier"].isin(["A", "B"])
    summary = _summary(master, len(quality_frame))
    if sample_only:
        # A later diagnostic sample must never replace a completed nationwide master.
        shortlist = _shortlist(master)
        excluded = _build_exclusion(master)
    else:
        shortlist, excluded, _ = _save_products(master, quality_frame, annual_frame, probes)
        summary.to_csv(SCREENING_SUMMARY_PATH, index=False)
        state["summary"] = summary.iloc[0].to_dict()
    save_screening_state(state)
    actual_requests = counter.request_count if counter is not None else 0
    return NationwideScreeningResult(
        inventory_result,
        master,
        shortlist,
        excluded,
        summary,
        estimates,
        actual_requests,
        False,
        False,
    )
