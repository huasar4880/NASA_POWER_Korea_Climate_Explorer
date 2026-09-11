"""Tier-A 전국 기온분석의 station 선택, cache, 정제와 일별 매칭."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, SETTINGS
from src.nasa_power import fetch_daily_data, load_raw_csv


ANALYSIS_START = date(1981, 1, 1)
ANALYSIS_END = date(2025, 12, 31)
NORMAL_START_YEAR = 1991
NORMAL_END_YEAR = 2020
EXPECTED_DAYS = (ANALYSIS_END - ANALYSIS_START).days + 1

SHORTLIST_PATH = PROJECT_ROOT / "output" / "tables" / "nationwide_asos_longterm_shortlist.csv"
MASTER_PATH = PROJECT_ROOT / "output" / "tables" / "nationwide_asos_station_master.csv"
STATION_SET_PATH = PROJECT_ROOT / "output" / "tables" / "nationwide_tier_a_analysis_stations.csv"
KMA_RAW_ROOT = PROJECT_ROOT / "data" / "nationwide_asos_raw" / "stations"
NASA_RAW_DIR = PROJECT_ROOT / "data" / "nationwide_nasa_raw"
NASA_PROCESSED_DIR = PROJECT_ROOT / "data" / "nationwide_nasa_processed"
KMA_PROCESSED_DIR = PROJECT_ROOT / "data" / "nationwide_kma_processed"
MATCHED_DIR = PROJECT_ROOT / "data" / "nationwide_matched"
NASA_STATE_PATH = NASA_RAW_DIR / "download_state.json"
MANIFEST_PATH = PROJECT_ROOT / "output" / "manifests" / "nationwide_analysis_manifest.json"

TEMPERATURE_RANGES = {
    "T2M": (-90.0, 70.0),
    "T2M_MAX": (-90.0, 70.0),
    "T2M_MIN": (-90.0, 70.0),
    "avg_temperature": (-90.0, 70.0),
    "max_temperature": (-90.0, 70.0),
    "min_temperature": (-90.0, 70.0),
}


@dataclass(frozen=True)
class DownloadPlan:
    """전국 NASA cache 상태와 예상 API 호출량."""

    station_count: int
    cache_hits: int
    downloads_needed: int
    estimated_api_requests: int


@dataclass(frozen=True)
class PreparedStation:
    """한 station의 분리 저장된 기온 자료와 실행 출처."""

    station_id: str
    station_name: str
    nasa_source: str
    nasa_raw_path: Path
    nasa_processed_path: Path
    kma_processed_path: Path
    matched_path: Path
    nasa: pd.DataFrame
    kma: pd.DataFrame
    matched: pd.DataFrame


def _atomic_csv(dataframe: pd.DataFrame, path: Path) -> Path:
    """완성된 CSV만 보이도록 임시 파일에서 원자적으로 교체한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    dataframe.to_csv(temporary, index=False, date_format="%Y-%m-%d")
    temporary.replace(path)
    return path


def _atomic_json(payload: dict[str, Any], path: Path) -> Path:
    """secret이 없는 상태 JSON을 원자적으로 저장한다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    temporary.replace(path)
    return path


def _to_bool(series: pd.Series) -> pd.Series:
    """CSV의 bool/string 혼합 표현을 엄격한 boolean으로 바꾼다."""

    return series.astype(str).str.strip().str.casefold().isin({"true", "1", "yes"})


def load_tier_a_stations(
    shortlist_path: Path = SHORTLIST_PATH,
    master_path: Path = MASTER_PATH,
) -> pd.DataFrame:
    """10단계 결과에서 검증 완료된 Final Tier A만 동적으로 선택한다.

    shortlist는 station 후보의 source of truth이고, master의 실제 가용기간·manual
    review flag를 일대일로 결합한다. Tier B와 continuity 미확정 station은 제외한다.
    """

    shortlist = pd.read_csv(shortlist_path, dtype={"station_id": "string"})
    master = pd.read_csv(master_path, dtype={"station_id": "string"})
    tier_a = shortlist.loc[
        shortlist["eligibility_tier"].astype(str).str.strip().eq("A")
    ].copy()
    master_columns = [
        "station_id",
        "region_level1",
        "region_level2",
        "actual_data_start_date",
        "actual_data_end_date",
        "core_temperature_missing_rate",
        "annual_completeness_median",
        "eligible_1981_2025",
        "manual_review_required",
    ]
    selected = tier_a.merge(
        master.loc[:, master_columns], on="station_id", how="left", validate="one_to_one"
    )
    eligible = _to_bool(selected["eligible_1981_2025"])
    manual = _to_bool(selected["manual_review_required"])
    risk = selected["continuity_risk"].fillna("unresolved").astype(str).str.casefold()
    allowed_risk = ~risk.isin({"high", "manual_review", "unresolved", "unknown"})
    starts = pd.to_datetime(selected["actual_data_start_date"], errors="coerce")
    ends = pd.to_datetime(selected["actual_data_end_date"], errors="coerce")
    availability = starts.le(pd.Timestamp(ANALYSIS_START)) & ends.ge(pd.Timestamp(ANALYSIS_END))
    selected = selected.loc[eligible & ~manual & allowed_risk & availability].copy()
    if selected.empty:
        raise ValueError("분석 가능한 Final Tier A station이 없습니다.")
    selected["temperature_missing_rate"] = pd.to_numeric(
        selected["core_temperature_missing_rate"], errors="coerce"
    )
    selected["annual_completeness"] = pd.to_numeric(
        selected["annual_completeness_median"], errors="coerce"
    )
    selected["nasa_query_latitude"] = pd.to_numeric(selected["latitude"], errors="coerce")
    selected["nasa_query_longitude"] = pd.to_numeric(selected["longitude"], errors="coerce")
    required_numeric = ["latitude", "longitude", "elevation_m", "nasa_query_latitude", "nasa_query_longitude"]
    if selected[required_numeric].isna().any().any():
        raise ValueError("Tier A station의 위경도 또는 고도 metadata가 누락되었습니다.")
    output_columns = [
        "station_id",
        "station_name",
        "region_level1",
        "region_level2",
        "latitude",
        "longitude",
        "elevation_m",
        "actual_data_start_date",
        "actual_data_end_date",
        "temperature_missing_rate",
        "annual_completeness",
        "continuity_risk",
        "nasa_query_latitude",
        "nasa_query_longitude",
    ]
    return selected.loc[:, output_columns].sort_values(
        "station_id", key=lambda values: values.astype(int)
    ).reset_index(drop=True)


def nasa_raw_path(station_id: str) -> Path:
    """station ID가 포함된 전국 NASA 원본 cache 경로를 반환한다."""

    return NASA_RAW_DIR / f"{station_id}_nasa_power_temperature_1981_2025.csv"


def nasa_query_coordinates(station: pd.Series | dict[str, Any]) -> tuple[float, float]:
    """station metadata에 저장된 NASA point query 위도·경도를 반환한다."""

    return float(station["nasa_query_latitude"]), float(station["nasa_query_longitude"])


def nasa_processed_path(station_id: str) -> Path:
    """station별 NASA 정제 기온 경로를 반환한다."""

    return NASA_PROCESSED_DIR / f"{station_id}_nasa_temperature_1981_2025.csv"


def kma_raw_path(station_id: str) -> Path:
    """10단계에서 생성된 ASOS station raw cache 경로를 반환한다."""

    return KMA_RAW_ROOT / station_id / f"{station_id}_asos_daily_1981_2025.csv"


def kma_processed_path(station_id: str) -> Path:
    """station별 KMA 정제 기온 경로를 반환한다."""

    return KMA_PROCESSED_DIR / f"{station_id}_asos_temperature_1981_2025.csv"


def matched_path(station_id: str) -> Path:
    """station별 NASA-KMA 일별 매칭 경로를 반환한다."""

    return MATCHED_DIR / f"{station_id}_nasa_kma_temperature_1981_2025.csv"


def validate_nasa_cache(path: Path) -> bool:
    """NASA cache가 공통기간·필수 schema·중복 없음 조건을 만족하는지 확인한다."""

    if not path.exists():
        return False
    try:
        data = load_raw_csv(path)
        dates = pd.to_datetime(data["DATE"], format="%Y%m%d", errors="raise")
        return bool(
            len(data) == EXPECTED_DAYS
            and {"T2M", "T2M_MAX", "T2M_MIN"}.issubset(data.columns)
            and not dates.duplicated().any()
            and dates.min().date() == ANALYSIS_START
            and dates.max().date() == ANALYSIS_END
        )
    except (OSError, ValueError, KeyError):
        return False


def build_download_plan(stations: pd.DataFrame) -> DownloadPlan:
    """API 호출 없이 전국 NASA cache hit/miss와 예상 요청 수를 계산한다."""

    hits = sum(validate_nasa_cache(nasa_raw_path(str(value))) for value in stations["station_id"])
    needed = len(stations) - hits
    return DownloadPlan(len(stations), hits, needed, needed)


def load_download_state(path: Path = NASA_STATE_PATH) -> dict[str, Any]:
    """NASA resume state를 읽되 손상되었으면 명확히 실패한다."""

    if not path.exists():
        return {"version": 1, "stations": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("stations", {}), dict):
        raise ValueError(f"NASA download state 형식이 올바르지 않습니다: {path}")
    payload.setdefault("version", 1)
    payload.setdefault("stations", {})
    return payload


def _record_state(
    state: dict[str, Any], station_id: str, *, status: str, path: Path, error: str | None = None
) -> None:
    """민감정보 없이 한 station의 NASA 상태를 기록한다."""

    record: dict[str, Any] = {
        "status": status,
        "path": str(path.relative_to(PROJECT_ROOT)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        record["error_type"] = error
    state.setdefault("stations", {})[station_id] = record
    _atomic_json(state, NASA_STATE_PATH)


def download_nasa_station(
    station: pd.Series | dict[str, Any], *, force: bool = False, session: Any = None
) -> tuple[pd.DataFrame, str, int]:
    """한 station의 NASA 자료를 cache 우선으로 받고 실제 API 호출 수를 반환한다."""

    station_id = str(station["station_id"])
    path = nasa_raw_path(station_id)
    state = load_download_state()
    if not force and validate_nasa_cache(path):
        _record_state(state, station_id, status="completed", path=path)
        return load_raw_csv(path), "cache", 0
    _record_state(state, station_id, status="pending", path=path)
    try:
        latitude, longitude = nasa_query_coordinates(station)
        result = fetch_daily_data(
            latitude,
            longitude,
            ANALYSIS_START,
            ANALYSIS_END,
            session=session,
        )
        _atomic_csv(result.dataframe, path)
        if not validate_nasa_cache(path):
            raise ValueError(f"NASA cache 검증 실패: station={station_id}")
        _record_state(state, station_id, status="completed", path=path)
        return result.dataframe, "api", 1
    except Exception as exc:
        _record_state(state, station_id, status="failed", path=path, error=type(exc).__name__)
        raise


def preprocess_nasa_temperature(raw: pd.DataFrame, station: pd.Series | dict[str, Any]) -> pd.DataFrame:
    """NASA raw를 변형하지 않고 fill/range 값을 NaN으로 둔 tidy 기온표를 만든다."""

    required = {"DATE", "T2M", "T2M_MAX", "T2M_MIN"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"NASA 기온 raw 필수 컬럼 누락: {sorted(missing)}")
    output = pd.DataFrame({
        "date": pd.to_datetime(raw["DATE"].astype(str), format="%Y%m%d", errors="raise"),
        "station_id": str(station["station_id"]),
        "station_name": str(station["station_name"]),
    })
    for column in ("T2M", "T2M_MAX", "T2M_MIN"):
        values = pd.to_numeric(raw[column], errors="coerce").replace(SETTINGS.missing_values, np.nan)
        lower, upper = TEMPERATURE_RANGES[column]
        output[column] = values.where(values.between(lower, upper))
    _validate_daily_frame(output, ("T2M", "T2M_MAX", "T2M_MIN"), "NASA")
    return output.sort_values("date").reset_index(drop=True)


def preprocess_kma_temperature(raw: pd.DataFrame, station: pd.Series | dict[str, Any]) -> pd.DataFrame:
    """10단계 ASOS raw에서 동일 station의 기온 3종만 별도 processed 표로 만든다."""

    required = {"tm", "stnId", "avgTa", "maxTa", "minTa"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"KMA 기온 raw 필수 컬럼 누락: {sorted(missing)}")
    station_id = str(station["station_id"])
    selected = raw.loc[raw["stnId"].astype(str).str.strip().eq(station_id)].copy()
    output = pd.DataFrame({
        "date": pd.to_datetime(selected["tm"], format="%Y-%m-%d", errors="raise"),
        "station_id": station_id,
        "station_name": str(station["station_name"]),
    })
    mapping = {"avgTa": "avg_temperature", "maxTa": "max_temperature", "minTa": "min_temperature"}
    for source, target in mapping.items():
        values = pd.to_numeric(selected[source], errors="coerce").replace(-999.0, np.nan)
        lower, upper = TEMPERATURE_RANGES[target]
        output[target] = values.where(values.between(lower, upper))
    # 일부 적격 station에는 관측 행 자체가 없는 날짜가 소수 존재한다. 공통 달력을
    # 유지하되 그 날짜의 관측값은 생성하지 않고 NaN으로 명시한다.
    calendar = pd.DataFrame({"date": pd.date_range(ANALYSIS_START, ANALYSIS_END, freq="D")})
    output = calendar.merge(output, on="date", how="left", validate="one_to_one")
    output["station_id"] = station_id
    output["station_name"] = str(station["station_name"])
    output = output.loc[:, [
        "date", "station_id", "station_name", "avg_temperature", "max_temperature",
        "min_temperature",
    ]]
    _validate_daily_frame(
        output, ("avg_temperature", "max_temperature", "min_temperature"), "KMA"
    )
    return output.sort_values("date").reset_index(drop=True)


def _validate_daily_frame(dataframe: pd.DataFrame, values: Iterable[str], source: str) -> None:
    """공통기간, 행수, 날짜 중복과 필수값 존재를 검사한다."""

    dates = pd.to_datetime(dataframe["date"], errors="raise")
    if len(dataframe) != EXPECTED_DAYS:
        raise ValueError(f"{source} 일자료 행 수 불일치: {len(dataframe)}/{EXPECTED_DAYS}")
    if dates.duplicated().any():
        raise ValueError(f"{source} 일자료에 중복 날짜가 있습니다.")
    if dates.min().date() != ANALYSIS_START or dates.max().date() != ANALYSIS_END:
        raise ValueError(f"{source} 일자료 기간이 1981-01-01~2025-12-31이 아닙니다.")
    if not pd.DatetimeIndex(pd.date_range(ANALYSIS_START, ANALYSIS_END)).difference(dates).empty:
        raise ValueError(f"{source} 일자료에 누락 날짜가 있습니다.")
    if any(dataframe[column].notna().sum() == 0 for column in values):
        raise ValueError(f"{source} 기온 변수에 유효 관측값이 없습니다.")


def match_station_temperature(
    nasa: pd.DataFrame, kma: pd.DataFrame, station: pd.Series | dict[str, Any]
) -> pd.DataFrame:
    """한 station의 NASA/KMA 기온을 날짜 기준 one-to-one inner join한다."""

    station_id = str(station["station_id"])
    nasa_part = nasa.loc[:, ["date", "T2M", "T2M_MAX", "T2M_MIN"]].rename(
        columns={"T2M": "nasa_T2M", "T2M_MAX": "nasa_T2M_MAX", "T2M_MIN": "nasa_T2M_MIN"}
    )
    kma_part = kma.loc[:, ["date", "avg_temperature", "max_temperature", "min_temperature"]].rename(
        columns={"avg_temperature": "kma_T2M", "max_temperature": "kma_TMAX", "min_temperature": "kma_TMIN"}
    )
    matched = nasa_part.merge(kma_part, on="date", how="inner", validate="one_to_one")
    matched.insert(1, "station_id", station_id)
    matched.insert(2, "station_name", str(station["station_name"]))
    if len(matched) != EXPECTED_DAYS or matched["date"].duplicated().any():
        raise ValueError(f"station {station_id}의 일별 매칭 기간 또는 중복이 올바르지 않습니다.")
    return matched


def prepare_station(
    station: pd.Series | dict[str, Any], *, force_nasa: bool = False, session: Any = None
) -> tuple[PreparedStation, int]:
    """한 station의 NASA download, 두 source 정제와 matching을 완료한다."""

    station_id = str(station["station_id"])
    nasa_raw, source, api_calls = download_nasa_station(station, force=force_nasa, session=session)
    source_kma_path = kma_raw_path(station_id)
    if not source_kma_path.exists():
        raise FileNotFoundError(
            f"station {station_id}의 10단계 KMA cache가 없습니다. "
            "KMA_API_KEY가 있으면 먼저 --screen-nationwide-asos를 완료하세요."
        )
    kma_raw = pd.read_csv(source_kma_path, low_memory=False)
    nasa = preprocess_nasa_temperature(nasa_raw, station)
    kma = preprocess_kma_temperature(kma_raw, station)
    matched = match_station_temperature(nasa, kma, station)
    nasa_path = nasa_processed_path(station_id)
    kma_path = kma_processed_path(station_id)
    pair_path = matched_path(station_id)
    _atomic_csv(nasa, nasa_path)
    _atomic_csv(kma, kma_path)
    _atomic_csv(matched, pair_path)
    return PreparedStation(
        station_id,
        str(station["station_name"]),
        source,
        nasa_raw_path(station_id),
        nasa_path,
        kma_path,
        pair_path,
        nasa,
        kma,
        matched,
    ), api_calls


def save_analysis_manifest(stations: dict[str, dict[str, Any]]) -> Path:
    """station별 단계 완료 상태를 secret 없이 저장한다."""

    payload = {
        "version": 1,
        "analysis_period": f"{ANALYSIS_START}~{ANALYSIS_END}",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stations": stations,
    }
    return _atomic_json(payload, MANIFEST_PATH)


def load_analysis_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """전국 분석 manifest를 읽어 resume 상태 확인에 사용한다."""

    if not path.exists():
        return {"version": 1, "stations": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("stations", {}), dict):
        raise ValueError(f"전국 분석 manifest 형식이 올바르지 않습니다: {path}")
    return payload


def save_station_set(stations: pd.DataFrame, path: Path = STATION_SET_PATH) -> Path:
    """실제 분석 대상 Tier A station set을 nationwide 입력 기록으로 저장한다."""

    return _atomic_csv(stations, path)
