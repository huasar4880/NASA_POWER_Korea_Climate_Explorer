"""Final Tier-A 전국 1981–2025 기온분석의 실행 orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT
from src.nationwide.tier_a_analysis import NationwideAnalysisProducts, build_nationwide_products
from src.nationwide.tier_a_pipeline import (
    MANIFEST_PATH,
    PreparedStation,
    build_download_plan,
    load_analysis_manifest,
    load_tier_a_stations,
    prepare_station,
    save_analysis_manifest,
    save_station_set,
)


TABLE_DIR = PROJECT_ROOT / "output" / "tables" / "nationwide"
CHART_DIR = PROJECT_ROOT / "output" / "charts" / "nationwide_analysis"
REPORT_DIR = PROJECT_ROOT / "output" / "reports" / "nationwide"

TABLE_PATHS = {
    "annual": TABLE_DIR / "nationwide_annual_temperature_1981_2025.csv",
    "trends": TABLE_DIR / "nationwide_station_temperature_trends.csv",
    "normals": TABLE_DIR / "nationwide_temperature_normals_1991_2020.csv",
    "anomalies": TABLE_DIR / "nationwide_temperature_anomalies_1981_2025.csv",
    "seasonal": TABLE_DIR / "nationwide_seasonal_temperature_trends.csv",
    "thresholds_annual": TABLE_DIR / "nationwide_temperature_threshold_annual.csv",
    "threshold_comparison": TABLE_DIR / "nationwide_temperature_threshold_comparison.csv",
    "validation": TABLE_DIR / "nationwide_nasa_kma_temperature_validation.csv",
    "summary": TABLE_DIR / "nationwide_station_temperature_summary.csv",
    "rankings": TABLE_DIR / "nationwide_temperature_change_rankings.csv",
    "regional": TABLE_DIR / "nationwide_regional_temperature_summary.csv",
    "elevation": TABLE_DIR / "nationwide_elevation_temperature_summary.csv",
    "spatial_associations": TABLE_DIR / "nationwide_validation_spatial_associations.csv",
    "trend_consistency": TABLE_DIR / "nationwide_nasa_kma_trend_consistency.csv",
}


@dataclass(frozen=True)
class NationwideRunResult:
    """CLI가 보고할 전국 분석 결과와 cache/API 집계."""

    stations: pd.DataFrame
    products: NationwideAnalysisProducts | None
    cache_hits: int
    api_calls: int
    prepared_count: int
    table_paths: dict[str, Path]
    map_paths: dict[str, Path]
    chart_paths: dict[str, Path]
    report_paths: tuple[Path, Path] | None
    dry_run: bool


def _atomic_csv(dataframe: pd.DataFrame, path: Path) -> Path:
    """집계표를 완성 후 원자적으로 교체한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    dataframe.to_csv(temporary, index=False)
    temporary.replace(path)
    return path


def _manifest_records() -> dict[str, dict[str, Any]]:
    """기존 station manifest 기록을 유지해 resume 상태를 반환한다."""

    payload = load_analysis_manifest()
    records = payload.get("stations", {})
    return records if isinstance(records, dict) else {}


def _update_manifest(
    records: dict[str, dict[str, Any]], station: pd.Series, prepared: PreparedStation
) -> None:
    """한 station의 다운로드·KMA·matching 상태를 completed로 기록한다."""

    records[str(station["station_id"])] = {
        "station_name": str(station["station_name"]),
        "nasa_download": "completed",
        "nasa_source": prepared.nasa_source,
        "kma_data": "completed",
        "matching": "completed",
        "trend_analysis": records.get(str(station["station_id"]), {}).get(
            "trend_analysis", "pending"
        ),
        "validation": records.get(str(station["station_id"]), {}).get("validation", "pending"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_analysis_manifest(records)


def prepare_selected_stations(
    stations: pd.DataFrame,
    *,
    force_nasa: bool = False,
    request_interval_seconds: float = 1.0,
    session: Any = None,
) -> tuple[list[PreparedStation], int, int]:
    """station별 실패 격리와 진행 로그를 적용해 모든 자료를 준비한다."""

    prepared_items: list[PreparedStation] = []
    api_calls = 0
    cache_hits = 0
    records = _manifest_records()
    failures: list[str] = []
    for position, (_, station) in enumerate(stations.iterrows(), 1):
        station_id = str(station["station_id"])
        print(f"[{position}/{len(stations)}] {station_id} {station['station_name']}")
        try:
            prepared, calls = prepare_station(station, force_nasa=force_nasa, session=session)
            print(f"NASA cache: {'hit' if prepared.nasa_source == 'cache' else 'miss'}")
            print("KMA cache: hit")
            print("analysis data: prepared")
            prepared_items.append(prepared)
            api_calls += calls
            cache_hits += int(calls == 0)
            _update_manifest(records, station, prepared)
            if calls and request_interval_seconds > 0 and position < len(stations):
                time.sleep(request_interval_seconds)
        except Exception as exc:
            records[station_id] = {
                "station_name": str(station["station_name"]),
                "nasa_download": "failed",
                "kma_data": "unknown",
                "matching": "failed",
                "trend_analysis": "pending",
                "validation": "pending",
                "error_type": type(exc).__name__,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            save_analysis_manifest(records)
            failures.append(f"{station_id} {type(exc).__name__}: {exc}")
    if failures:
        raise RuntimeError(
            "일부 Tier A station 준비에 실패했습니다. 완료 cache는 유지됩니다: "
            + "; ".join(failures)
        )
    return prepared_items, cache_hits, api_calls


def save_products(products: NationwideAnalysisProducts) -> dict[str, Path]:
    """전국 분석표를 nationwide namespace에만 atomic save한다."""

    saved: dict[str, Path] = {}
    for name, path in TABLE_PATHS.items():
        saved[name] = _atomic_csv(getattr(products, name), path)
    return saved


def generate_report_from_saved_tables() -> tuple[Path, Path]:
    """API를 호출하지 않고 저장된 분석표만 읽어 전국 보고서를 재생성한다."""

    stations = load_tier_a_stations()
    required = ("summary", "regional", "elevation", "seasonal")
    missing = [str(TABLE_PATHS[name]) for name in required if not TABLE_PATHS[name].exists()]
    if missing:
        raise FileNotFoundError("전국 보고서 입력표가 없습니다: " + ", ".join(missing))
    from src.nationwide.tier_a_reporting import save_nationwide_report

    return save_nationwide_report(
        stations,
        pd.read_csv(TABLE_PATHS["summary"]),
        pd.read_csv(TABLE_PATHS["regional"]),
        pd.read_csv(TABLE_PATHS["elevation"]),
        pd.read_csv(TABLE_PATHS["seasonal"]),
        REPORT_DIR,
    )


def run_nationwide_tier_a(
    *,
    dry_run: bool = False,
    force_nasa: bool = False,
    request_interval_seconds: float = 1.0,
    station_id: str | None = None,
    publish: bool = True,
    session: Any = None,
) -> NationwideRunResult:
    """Final Tier A 전체 또는 debugging용 한 station의 분석 workflow를 실행한다."""

    all_stations = load_tier_a_stations()
    stations = all_stations
    if station_id is not None:
        stations = all_stations.loc[all_stations["station_id"].astype(str).eq(str(station_id))].copy()
        if stations.empty:
            raise KeyError(f"Final Tier A에 없는 station ID입니다: {station_id}")
    plan = build_download_plan(stations)
    if dry_run:
        return NationwideRunResult(
            stations, None, plan.cache_hits, 0, 0, {}, {}, {}, None, True
        )
    if station_id is None and publish:
        save_station_set(stations)
    prepared, cache_hits, api_calls = prepare_selected_stations(
        stations,
        force_nasa=force_nasa,
        request_interval_seconds=request_interval_seconds,
        session=session,
    )
    products = build_nationwide_products(prepared, stations)
    from src.nationwide.tier_a_reporting import save_nationwide_report
    from src.nationwide.tier_a_visualization import save_interactive_maps, save_static_charts

    table_paths = save_products(products) if publish else {}
    map_paths = save_interactive_maps(products.summary, CHART_DIR) if publish else {}
    chart_paths = save_static_charts(
        products.summary, products.anomalies, products.regional, CHART_DIR
    ) if publish else {}
    report_paths = save_nationwide_report(
        stations, products.summary, products.regional, products.elevation,
        products.seasonal, REPORT_DIR,
    ) if publish else None
    records = _manifest_records()
    for station in stations.itertuples(index=False):
        record = records.setdefault(str(station.station_id), {})
        record["trend_analysis"] = "completed"
        record["validation"] = "completed"
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_analysis_manifest(records)
    return NationwideRunResult(
        stations, products, cache_hits, api_calls, len(prepared), table_paths,
        map_paths, chart_paths, report_paths, False,
    )
