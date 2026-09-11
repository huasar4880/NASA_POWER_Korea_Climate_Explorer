"""Read-only result loading and source-addressable report facts; no analysis/API imports."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from reporting.formatters import finite


class ReportDataError(ValueError):
    """Required, unambiguous precomputed report inputs are unavailable."""


TABLE_FILES = {
    "annual": "city_climate_annual_1981_2025.csv",
    "summary": "city_climate_summary_1981_2025.csv",
    "monthly": "city_monthly_climatology_1981_2025.csv",
    "past_recent": "city_climate_past_vs_recent.csv",
    "trends": "city_climate_statistical_trends.csv",
    "normals": "city_climate_normals_1991_2020.csv",
    "anomalies": "city_climate_anomalies_1981_2025.csv",
    "seasonal": "city_seasonal_climate_trends_1981_2025.csv",
    "rankings": "city_climate_change_rankings.csv",
    "consecutive": "city_consecutive_climate_indices_1981_2025.csv",
    "validation": "nasa_kma_validation_metrics.csv",
    "validation_monthly": "nasa_kma_monthly_validation.csv",
    "validation_seasonal": "nasa_kma_seasonal_validation.csv",
    "annual_bias": "nasa_kma_annual_bias_1981_2025.csv",
    "threshold": "nasa_kma_threshold_validation.csv",
    "contingency": "nasa_kma_precipitation_contingency.csv",
    "kma_quality": "kma_data_quality_summary.csv",
    "continuity": "gangneung_station_continuity_validation.csv",
    "station": "nasa_kma_station_mapping.csv",
    "nasa_quality": "data_quality_summary.csv",
    "parameters": "nasa_power_climate_parameter_metadata.csv",
}
TREND_COLUMNS = (
    "metric", "unit", "series_mean", "n_years", "valid_start_year", "valid_end_year",
    "linear_slope_per_decade", "linear_p_value", "mk_trend", "mk_p_value",
    "modified_mk_method", "modified_mk_status", "modified_mk_p_value",
    "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper", "fdr_q_value", "significant_fdr",
)
VALIDATION_COLUMNS = ("metric", "unit", "n_pairs", "bias", "mae", "rmse", "pearson_r", "spearman_rho")
ANNUAL_COLUMNS = (
    "YEAR", "T2M_mean_C", "T2M_MAX_mean_C", "T2M_MIN_mean_C", "T2M_MA5_C", "T2M_MA10_C",
    "precipitation_total_mm", "RH2M_mean_pct", "WS10M_mean_m_s", "solar_mean_kWh_m2_day",
    "days_tmax_ge_30", "days_tmax_ge_33", "days_tmin_ge_25", "days_precip_ge_30",
    "days_precip_ge_50", "days_precip_lt_1",
)
KEY_COLUMNS = {
    "annual": ("city", "YEAR"), "summary": ("city",), "monthly": ("city", "MONTH"),
    "past_recent": ("city", "variable"), "trends": ("city", "metric"),
    "normals": ("city", "period_type", "month"), "anomalies": ("city", "YEAR"),
    "seasonal": ("city", "season", "metric"), "rankings": ("city", "metric"),
    "consecutive": ("city", "YEAR"), "validation": ("city", "metric"),
    "validation_monthly": ("city", "month", "metric"),
    "validation_seasonal": ("city", "season", "metric"), "annual_bias": ("city", "year", "metric"),
    "threshold": ("city", "year", "threshold"), "contingency": ("city",),
    "kma_quality": ("city",), "nasa_quality": ("city",),
    "station": ("city", "role", "kma_station_id"), "continuity": ("comparison",),
    "parameters": ("short_name",), "matched": ("city", "date"),
}
REQUIRED = {
    "annual": ANNUAL_COLUMNS, "summary": ("latitude", "longitude", "temperature_mean"),
    "monthly": ("MONTH", "T2M_mean_C", "precipitation_monthly_total_mean_mm", "RH2M_mean_pct", "WS10M_mean_m_s", "solar_mean_kWh_m2_day"),
    "past_recent": ("variable", "unit", "past_period", "recent_period", "past_mean", "recent_mean", "absolute_difference"),
    "trends": TREND_COLUMNS, "normals": ("period_type", "month", "baseline_start_year", "baseline_end_year", "T2M_normal_C"),
    "anomalies": ("YEAR", "T2M_value", "T2M_normal", "T2M_anomaly"),
    "seasonal": tuple(c for c in TREND_COLUMNS if c != "series_mean") + ("season", "seasonal_mean"),
    "rankings": ("rank", "metric", "sen_slope_per_decade"),
    "consecutive": ("YEAR", "max_consecutive_tmax_ge_30", "max_consecutive_tmax_ge_33", "max_consecutive_tmin_ge_25", "max_consecutive_precip_lt_1"),
    "validation": VALIDATION_COLUMNS, "validation_monthly": VALIDATION_COLUMNS + ("month",),
    "validation_seasonal": VALIDATION_COLUMNS + ("season",),
    "annual_bias": ("year", "metric", "unit", "n_pairs", "bias", "mae", "rmse"),
    "threshold": ("year", "threshold", "threshold_c", "n_pairs", "nasa_count", "kma_count", "difference"),
    "contingency": ("threshold_mm", "n_pairs", "hit", "miss", "false_alarm", "correct_negative", "pod", "far", "csi"),
    "kma_quality": ("start_date", "end_date", "row_count", "duplicate_dates", "missing_dates", "missing_precipitation"),
    "nasa_quality": ("start_date", "end_date", "row_count", "duplicate_dates", "missing_ALLSKY_SFC_SW_DWN"),
    "station": ("role", "kma_station_id", "kma_station_name", "distance_km", "nasa_latitude", "nasa_longitude"),
    "continuity": ("comparison", "n_overlap_pairs", "overlap_start", "overlap_end", "mean_difference_104_minus_105_c", "mae_c", "rmse_c", "pearson_r"),
    "parameters": ("short_name", "long_name", "unit", "annual_aggregation"),
}


def native(value: Any) -> Any:
    """Convert pandas/numpy scalars into strict JSON-compatible values."""

    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


@dataclass(frozen=True)
class Fact:
    """A single number or label with its exact source cell address."""

    value: Any
    source_file: str
    row_key: dict[str, Any]
    column: str


@dataclass
class SourcedTable:
    """Rows retained from one result table, including their original CSV row positions."""

    source_file: str
    columns: tuple[str, ...]
    rows: list[dict[str, Any]]
    row_numbers: list[int]
    keys: tuple[str, ...]


@dataclass
class ReportFacts:
    """Only input to narratives, report sections and charts; no downstream CSV reads."""

    city: str
    slug: str
    metrics: dict[str, Fact]
    tables: dict[str, SourcedTable]
    sources: dict[str, dict[str, Any]]
    data_quality_notes: list[str] = field(default_factory=list)

    def value(self, name: str) -> Any:
        """Return an explicit fact, failing on a programming/mapping error."""

        return self.metrics[name].value


@dataclass
class ComparisonFacts:
    """The configured cities in source order, without any composite risk scoring."""

    cities: list[ReportFacts]


class ReportDataProvider:
    """Load saved CSVs from output only and validate unique source keys."""

    def __init__(self, project_root: Path) -> None:
        """Set an explicit root, allowing isolated fixture projects in tests."""

        self.root = Path(project_root).resolve()
        self.frames: dict[str, pd.DataFrame] = {}
        self.sources: dict[str, dict[str, Any]] = {}

    def _read(self, relative: str, required: tuple[str, ...], keys: tuple[str, ...]) -> pd.DataFrame:
        """Reject missing/empty/ambiguous inputs; never trigger an upstream workflow."""

        from reporting.validation import reject_unsafe_text

        path = self.root / relative
        workflow = "python main.py --validate-kma --all" if any(x in relative for x in ("kma", "continuity")) else "python main.py --all"
        if not path.is_file():
            raise ReportDataError(f"필수 분석파일 없음: {relative}. 선행 실행: {workflow}")
        try:
            payload = path.read_bytes()
            reject_unsafe_text(payload.decode("utf-8-sig"))
            import io
            data = pd.read_csv(io.BytesIO(payload))
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
            raise ReportDataError(f"CSV를 읽을 수 없습니다: {relative}") from exc
        missing = set(required).union(keys) - set(data.columns)
        if missing or data.empty:
            raise ReportDataError(f"분석파일 비어 있음 또는 필수 컬럼 누락: {relative}: {sorted(missing)}. 선행 실행: {workflow}")
        if data.duplicated(list(keys)).any():
            raise ReportDataError(f"중복 row key: {relative}")
        self.sources[relative] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "row_count": len(data),
        }
        return data

    def load(self, name: str) -> pd.DataFrame:
        """Return a defensive copy of a validated result table."""

        if name not in self.frames:
            self.frames[name] = self._read(f"output/tables/{TABLE_FILES[name]}", REQUIRED[name], KEY_COLUMNS[name])
        return self.frames[name].copy(deep=True)

    def city_names(self) -> list[str]:
        """Read available cities from the existing summary, preserving source order."""

        names = self.load("summary")["city"].astype(str).tolist()
        import re
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z _-]*", name) for name in names):
            raise ReportDataError("안전하지 않은 도시명: 보고서 파일명을 구성할 수 없습니다.")
        return names

    def city_facts(self, city: str) -> ReportFacts:
        """Map all city facts once; renderer and narrative consume only this layer."""

        names = self.city_names()
        canonical = next((n for n in names if n.casefold() == city.casefold()), None)
        if canonical is None:
            raise ReportDataError(f"도시 결과가 없습니다. 선택 가능: {', '.join(names)}")
        city = canonical
        slug = city.casefold().replace(" ", "_")
        tables: dict[str, SourcedTable] = {}
        metrics: dict[str, Fact] = {}
        for name in TABLE_FILES:
            if name == "continuity" and city != "Gangneung":
                continue
            data = self.load(name)
            selected = data.loc[data["city"].eq(city)] if "city" in data else data
            if selected.empty:
                raise ReportDataError(f"{city} 결과 행 없음: {TABLE_FILES[name]}. 선행 workflow를 전체 도시로 실행하세요.")
            tables[name] = SourcedTable(
                f"output/tables/{TABLE_FILES[name]}", tuple(selected.columns),
                [{k: native(v) for k, v in row.items()} for row in selected.to_dict("records")],
                [int(i) + 2 for i in selected.index], KEY_COLUMNS[name],
            )
        matched_path = f"output/validation/matched/{slug}_nasa_kma_daily_1981_2025.csv"
        matched = self._read(matched_path, ("date", "city", "nasa_T2M", "kma_T2M"), KEY_COLUMNS["matched"])
        if not matched["city"].eq(city).all():
            raise ReportDataError("일별 매칭 파일의 도시가 일치하지 않습니다.")
        if pd.to_datetime(matched["date"], errors="coerce").isna().any():
            raise ReportDataError("일별 매칭 파일에 잘못된 날짜가 있습니다.")
        keep = ("date", "city", "nasa_T2M", "kma_T2M")
        tables["matched"] = SourcedTable(matched_path, keep,
            [{k: native(v) for k, v in row.items()} for row in matched.loc[:, keep].to_dict("records")],
            list(range(2, len(matched) + 2)), KEY_COLUMNS["matched"])

        def put(label: str, table: str, column: str, **filters: Any) -> None:
            """Bind an exact source cell after enforcing a unique row selection."""

            source = tables[table]
            rows = [row for row in source.rows if all(row.get(k) == v for k, v in filters.items())]
            if len(rows) != 1 or column not in rows[0]:
                raise ReportDataError(f"보고서 fact 매핑 실패: {table}.{column}, {city}")
            row = rows[0]
            metrics[label] = Fact(row[column], source.source_file, {k: row[k] for k in source.keys}, column)

        for name in ("latitude", "longitude", "temperature_mean"):
            put(name, "summary", name)
        for name, source_metric in {
            "temperature": "temperature", "tmax": "temperature_max_mean", "tmin": "temperature_min_mean",
            "precipitation": "precipitation", "humidity": "humidity", "wind": "wind", "solar": "solar",
            "days_tmax_ge_33": "hot_day_33", "days_tmin_ge_25": "warm_night_25",
        }.items():
            for suffix, col in {"sen_slope": "sen_slope_per_decade", "sen_ci_lower": "sen_ci_lower", "sen_ci_upper": "sen_ci_upper", "mk_trend": "mk_trend", "fdr_significant": "significant_fdr", "mean": "series_mean", "valid_start_year": "valid_start_year", "valid_end_year": "valid_end_year"}.items():
                if f"{name}_{suffix}" not in metrics:
                    put(f"{name}_{suffix}", "trends", col, metric=source_metric)
        first = min(row["YEAR"] for row in tables["annual"].rows)
        last = max(row["YEAR"] for row in tables["annual"].rows)
        if sorted(row["YEAR"] for row in tables["annual"].rows) != list(range(first, last + 1)):
            raise ReportDataError(f"{city}: 연간 분석표의 연도 누락")
        put("analysis_start_year", "annual", "YEAR", YEAR=first)
        put("analysis_end_year", "annual", "YEAR", YEAR=last)
        for label, column in [("normal_1991_2020", "T2M_normal_C"), ("normal_start_year", "baseline_start_year"), ("normal_end_year", "baseline_end_year")]:
            put(label, "normals", column, period_type="annual")
        put("recent_anomaly", "anomalies", "T2M_anomaly", YEAR=last)
        for name in ("past_mean", "recent_mean", "past_period", "recent_period"):
            put(name, "past_recent", name, variable="T2M")
        for prefix, metric in {"t2m": "temperature", "tmax": "maximum_temperature", "tmin": "minimum_temperature", "precip": "precipitation", "humidity": "relative_humidity", "wind": "wind_speed", "solar": "solar_radiation"}.items():
            for col in ("bias", "mae", "rmse", "pearson_r", "spearman_rho", "n_pairs"):
                suffix = {"pearson_r": "pearson", "spearman_rho": "spearman"}.get(col, col)
                put(f"kma_{prefix}_{suffix}", "validation", col, metric=metric)
        for label, col in [("kma_station_id", "kma_station_id"), ("kma_station_distance", "distance_km")]:
            put(label, "station", col, role="primary")
        for table in ("nasa_quality", "kma_quality"):
            for col in tables[table].columns:
                if col != "city":
                    put(f"{table}_{col}", table, col)
        used = {t.source_file for t in tables.values()}
        facts = ReportFacts(city, slug, metrics, tables, {name: self.sources[name] for name in sorted(used)})
        facts.data_quality_notes = [
            "날짜 누락과 변수 결측은 서로 다른 항목이다.",
            "NASA 품질 CSV에는 날짜 누락 수 필드가 없어 별도 수치로 표시하지 않는다. 존재하지 않는 품질값을 0으로 가정하지 않는다.",
            "KMA 일강수량 수치 공란/NaN 비율은 실제 관측누락률로 확정한 값이 아니다.",
            "NASA 일사량의 1981–1983 fill value는 0으로 채우지 않았다. 유효기간은 변수별 통계표를 따른다.",
        ]
        return facts

    def comparison_facts(self) -> ComparisonFacts:
        """Require all eight stored cities for the named eight-city comparison."""

        names = self.city_names()
        if len(names) != 8:
            raise ReportDataError("8개 도시 종합 결과가 필요합니다. 선행 실행: python main.py --all")
        return ComparisonFacts([self.city_facts(city) for city in names])
