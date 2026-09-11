"""Assemble shared report sections and render HTML/Markdown with Jinja2."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from reporting.charts import Chart, city_charts, comparison_charts
from reporting.data_provider import ComparisonFacts, ReportDataProvider, ReportFacts, TREND_COLUMNS, VALIDATION_COLUMNS
from reporting.formatters import format_value, markdown_escape, finite
from reporting.narrative import CONTINUITY_CAVEAT, LIMITATIONS, PRECIPITATION_CAVEAT, bias_sentence, executive_summary, threshold_findings, trend_sentence
from reporting.validation import validate_facts, validate_output_files, validate_rendered

PACKAGE = Path(__file__).resolve().parent
CITY_SECTIONS = [
    "보고서 개요", "Executive Summary", "데이터 및 분석방법", "기온 장기변화", "강수 특성",
    "상대습도·풍속·일사량", "Extreme Climate Proxy", "Climate Anomaly", "계절별 변화",
    "NASA POWER × KMA ASOS Validation", "Threshold Validation", "데이터 품질", "주요 발견", "해석상 한계",
]
COMPARISON_SECTIONS = [
    "Executive Summary", "분석도시 및 지도", "도시별 평균기온 비교", "도시별 T2M Sen 기울기 비교",
    "T2M_MAX / T2M_MIN 변화 비교", "33°C proxy 변화 비교", "warm-night proxy 변화 비교", "강수 변화 비교",
    "상대습도 비교", "풍속 비교", "일사량 비교", "계절별 변화 비교", "1991–2020 anomaly 비교",
    "NASA–KMA T2M validation 비교", "NASA–KMA 기후변수별 validation", "Gangneung station continuity",
    "데이터 품질", "주요 비교 결과", "해석상 한계",
]
SOURCE_LINKS = [
    ("NASA POWER", "https://power.larc.nasa.gov/"),
    ("KMA ASOS 일자료 공식 명세", "https://www.data.go.kr/data/15059093/openapi.do"),
    ("기상자료개방포털 ASOS", "https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36"),
]
LABELS = {
    "city": "도시", "YEAR": "연도", "year": "연도", "MONTH": "월", "month": "월", "metric": "지표",
    "unit": "기본 단위", "series_mean": "기간 평균", "sen_slope_per_decade": "Sen /10년", "sen_ci_lower": "95% CI 하한 /10년", "sen_ci_upper": "95% CI 상한 /10년",
    "linear_slope_per_decade": "선형회귀 /10년", "linear_p_value": "회귀 p", "mk_trend": "MK 방향", "mk_p_value": "MK p", "fdr_q_value": "FDR q", "significant_fdr": "FDR 유의",
    "n_years": "유효 연도 수", "valid_start_year": "유효 시작연도", "valid_end_year": "유효 종료연도",
    "bias": "Bias (NASA−KMA)", "mae": "MAE", "rmse": "RMSE", "pearson_r": "Pearson r", "spearman_rho": "Spearman ρ", "n_pairs": "유효 pair 수",
    "past_mean": "과거 평균", "recent_mean": "최근 평균", "absolute_difference": "최근−과거", "past_period": "과거 기간", "recent_period": "최근 기간",
    "T2M_mean_C": "T2M (°C)", "T2M_MAX_mean_C": "T2M_MAX (°C)", "T2M_MIN_mean_C": "T2M_MIN (°C)", "T2M_MA5_C": "5년 이동평균 (°C)", "T2M_MA10_C": "10년 이동평균 (°C)",
    "missing_precipitation": "일강수량 수치 공란/NaN 수", "missing_dates": "날짜 누락 수", "row_count": "행 수", "duplicate_dates": "중복 날짜 수", "start_date": "시작일", "end_date": "종료일",
    "precipitation_total_mm": "연간 강수량 (mm/년)", "precipitation_monthly_total_mean_mm": "월 강수합 climatology (mm/월)",
    "T2M_anomaly": "T2M anomaly (°C)", "T2M_normal_C": "T2M normal (°C)", "distance_km": "NASA–ASOS 거리 (km)",
    "modified_mk_method": "Modified MK 방법", "modified_mk_status": "적용 상태", "modified_mk_p_value": "Modified MK p",
    "nasa_count": "NASA count", "kma_count": "KMA count", "difference": "NASA−KMA (일)",
}


@dataclass(frozen=True)
class ReportResult:
    """Public paths of one successfully checked report pair and its manifest."""

    html_path: Path
    markdown_path: Path
    manifest_path: Path
    chart_paths: tuple[Path, ...]


def _table(facts: list[ReportFacts], name: str, title: str, columns: tuple[str, ...] | None = None, **filters: Any) -> dict[str, Any]:
    """Prepare a display table exclusively from source-addressable facts."""

    selected = []
    for fact in facts:
        if name not in fact.tables:
            continue
        for row in fact.tables[name].rows:
            if all(row.get(k) in v if isinstance(v, (list, tuple, set)) else row.get(k) == v for k, v in filters.items()):
                selected.append(row)
    source = next(f.tables[name] for f in facts if name in f.tables)
    cols = columns or source.columns
    return {"title": title, "columns": [{"key": c, "label": LABELS.get(c, c)} for c in cols], "rows": selected, "source_file": source.source_file, "source_href": ""}


def _section(title: str, *, paragraphs: list[str] | None = None, tables: list[dict] | None = None, charts: list[str] | None = None, caveat: str = "") -> dict[str, Any]:
    """Construct one identical content section for both output formats."""

    return {"title": title, "paragraphs": paragraphs or [], "tables": tables or [], "charts": charts or [], "caveat": caveat}


def _trend_tables(facts: list[ReportFacts], metrics: list[str]) -> list[dict]:
    """Separate interval estimates from significance diagnostics for readable tables."""

    return [
        _table(facts, "trends", "장기 평균·추세", ("city", "metric", "unit", "series_mean", "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper", "valid_start_year", "valid_end_year"), metric=metrics),
        _table(facts, "trends", "통계검정 — 유의성은 원인이 아님", ("city", "metric", "linear_slope_per_decade", "mk_trend", "mk_p_value", "modified_mk_method", "modified_mk_p_value", "fdr_q_value", "significant_fdr"), metric=metrics),
    ]


def _quality_tables(facts: list[ReportFacts]) -> list[dict]:
    """Separate date completeness from variable-level missing counts."""

    tables = []
    for source, label in [("nasa_quality", "NASA"), ("kma_quality", "KMA")]:
        meta = ("city", "start_date", "end_date", "row_count", "duplicate_dates")
        if source == "kma_quality":
            meta += ("missing_dates",)
        tables.append(_table(facts, source, f"{label} 기간·날짜 품질", meta))
        columns = ("city",) + tuple(c for c in facts[0].tables[source].columns if c.startswith("missing_") and c != "missing_dates")
        tables.append(_table(facts, source, f"{label} 변수별 수치 결측", columns))
    return tables


def _methods(fact: ReportFacts) -> list[str]:
    """Describe previously implemented methods without recalculating them."""

    return [
        "NASA POWER 격자자료와 KMA ASOS 지점관측자료의 기존 결과 CSV를 재사용했다. 보고서 생성은 API와 raw/processed를 읽거나 수정하지 않는다.",
        "기온 T2M·T2M_MAX·T2M_MIN, 강수 PRECTOTCORR, 습도 RH2M, 풍속 WS10M, 일사 ALLSKY_SFC_SW_DWN을 사용한다.",
        "Linear Regression, Mann-Kendall(MK), 자기상관 점검에 따른 Modified Mann-Kendall, Sen's slope 및 95% 신뢰구간, Benjamini-Hochberg FDR의 저장 결과를 표시한다. 여기서 모형을 다시 적합하지 않는다.",
        "기울기와 CI는 모두 10년당 변화량이다. 기온은 °C/10년, 강수는 (mm/년)/10년, 습도는 percentage points/10년, 풍속은 (m/s)/10년, 일사는 (kWh/m²/day)/10년이다. 연간 proxy 일수의 추세는 (일/년)/10년이다.",
        "습도의 기간·계절 평균 단위는 %이며, 습도 추세표의 percentage points는 변화량 단위다. 연속일수 추세는 일/10년이다.",
        "연간 FDR family는 8개 도시의 전체 연간 지표이며 계절 FDR family는 변수별 8개 도시×4계절이다. Modified MK 결과는 별도 진단이며 저장된 FDR 판정을 임의로 바꾸지 않는다.",
        f"Climate normal: {fact.value('normal_start_year')}–{fact.value('normal_end_year')}. 최근 anomaly는 분석 마지막 연도 {fact.value('analysis_end_year')}의 값이다. 최근 10년 평균과 구분한다.",
        "5년·10년 이동평균은 기존 연간표의 저장값을 사용하며 초기 창 부족과 결측을 채우지 않는다. 일사 1981–1983은 NASA fill value 기간으로 유효기간 표를 확인한다.",
        "유일한 표시용 재집계는 기존 7단계 그래프 함수의 T2M 유효 daily pair 연도별 평균이다. threshold 설명은 기존 연도별 차이 중 최대 절대차를 선택하며 새 추세를 계산하지 않는다.",
        "문장 표시 규칙: Pearson r ≥0.9를 높은 시간적 일치도라고 서술하며 정확도 등급을 뜻하지 않는다. threshold의 |연간 차이| ≥10일 강조는 검토용 표시 기준이지 통계검정이나 위험도 기준이 아니다.",
    ]


def city_sections(fact: ReportFacts) -> list[dict[str, Any]]:
    """Compose the fourteen city-report sections from one fact object."""

    f = [fact]
    trend_metrics = ["temperature", "temperature_max_mean", "temperature_min_mean"]
    proxy_metrics = ["hot_day_30", "hot_day_33", "warm_night_25", "heavy_precip_30", "heavy_precip_50", "dry_day_lt_1", "consecutive_hot_days_30", "consecutive_extreme_heat_33", "consecutive_warm_nights_25", "consecutive_dry_days"]
    seasons = [r for r in fact.tables["seasonal"].rows if r["metric"] == "temperature" and finite(r["sen_slope_per_decade"])]
    strongest = max(seasons, key=lambda r: r["sen_slope_per_decade"]) if seasons else None
    findings = [
        trend_sentence("연평균기온", fact.value("temperature_sen_slope"), fact.value("temperature_fdr_significant")),
        trend_sentence("연평균 최고기온", fact.value("tmax_sen_slope"), fact.value("tmax_fdr_significant")),
        trend_sentence("연평균 최저기온", fact.value("tmin_sen_slope"), fact.value("tmin_fdr_significant")),
        f"계절별 T2M Sen 기울기의 최댓값은 {strongest['season']}의 {format_value(strongest['sen_slope_per_decade'], 'sen_slope')} °C/10년이다. 원인은 판단하지 않았다." if strongest else "계절별 추세 자료가 없다.",
        bias_sentence(fact.value("kma_t2m_bias"), fact.value("kma_t2m_rmse"), fact.value("kma_t2m_pearson")),
    ]
    validation_tables = [_table(f, "validation", "전체 변수 agreement", ("metric", "unit", "n_pairs", "bias", "mae", "rmse", "pearson_r", "spearman_rho")),
        _table(f, "contingency", "강수 contingency — 동일한 유효 pair 범위", ("threshold_mm", "n_pairs", "hit", "miss", "false_alarm", "correct_negative", "pod", "far", "csi")),
        _table(f, "validation_monthly", "T2M 월별 오차", ("month", "n_pairs", "bias", "mae", "rmse", "pearson_r"), metric="temperature"),
        _table(f, "validation_seasonal", "T2M 계절별 오차", ("season", "n_pairs", "bias", "mae", "rmse", "pearson_r"), metric="temperature"),
        _table(f, "annual_bias", "T2M 연도별 Bias", ("year", "n_pairs", "bias", "mae", "rmse"), metric="temperature")]
    if "continuity" in fact.tables:
        validation_tables.append(_table(f, "continuity", "Station Continuity: 104−105"))
    return [
        _section(CITY_SECTIONS[0], paragraphs=[f"{fact.city} 기후변화 분석보고서. 대상기간 {fact.value('analysis_start_year')}–{fact.value('analysis_end_year')}. 보고서 생성시점과 관측기간은 서로 다르다."]),
        _section(CITY_SECTIONS[1], paragraphs=executive_summary(fact)),
        _section(CITY_SECTIONS[2], paragraphs=_methods(fact), tables=[_table(f, "station", "좌표·관측소", ("city", "nasa_latitude", "nasa_longitude", "kma_station_id", "kma_station_name", "distance_km", "role")), _table(f, "parameters", "사용 변수와 단위")]),
        _section(CITY_SECTIONS[3], tables=_trend_tables(f, trend_metrics) + [_table(f, "past_recent", "과거 10년과 최근 10년", ("variable", "unit", "past_period", "past_mean", "recent_period", "recent_mean", "absolute_difference"), variable=["T2M", "T2M_MAX", "T2M_MIN"]), _table(f, "annual", "연간 기온·이동평균", ("YEAR", "T2M_mean_C", "T2M_MAX_mean_C", "T2M_MIN_mean_C", "T2M_MA5_C", "T2M_MA10_C"))], charts=["temperature_longterm"]),
        _section(CITY_SECTIONS[4], caveat=PRECIPITATION_CAVEAT, paragraphs=["POD / FAR / CSI도 양쪽 자료에 유효한 강수량 수치가 존재하는 날짜에 한정된 비교다. 강수 공란을 0으로 변환하지 않았다."], tables=_trend_tables(f, ["precipitation", "heavy_precip_30", "heavy_precip_50"]) + [_table(f, "monthly", "월 강수 climatology", ("MONTH", "precipitation_monthly_total_mean_mm"))], charts=["precipitation"]),
        _section(CITY_SECTIONS[5], paragraphs=[f"NASA 일사량 유효 추세기간은 {format_value(fact.value('solar_valid_start_year'), 'valid_start_year')}–{format_value(fact.value('solar_valid_end_year'), 'valid_end_year')}이다. 1981–1983 fill value는 0이 아니다."], tables=_trend_tables(f, ["humidity", "wind", "solar"]) + [_table(f, "seasonal", "계절별 평균과 추세", ("season", "metric", "unit", "seasonal_mean", "sen_slope_per_decade", "significant_fdr"), metric=["humidity", "wind", "solar"])], charts=["monthly_climatology"]),
        _section(CITY_SECTIONS[6], caveat="모든 지표는 분석용 proxy다. 기상청 공식 폭염일수·열대야 통계와 동일한 지표가 아니다.", tables=_trend_tables(f, proxy_metrics), charts=["extreme_proxies"]),
        _section(CITY_SECTIONS[7], paragraphs=[f"최근 anomaly: {fact.value('analysis_end_year')}년 T2M {format_value(fact.value('recent_anomaly'))} °C. 기준 normal {format_value(fact.value('normal_1991_2020'))} °C."], tables=[_table(f, "normals", "연간 climate normal", ("baseline_start_year", "baseline_end_year", "n_years", "T2M_normal_C"), period_type="annual"), _table(f, "anomalies", "연도별 T2M anomaly", ("YEAR", "T2M_value", "T2M_normal", "T2M_anomaly"))], charts=["temperature_anomaly"]),
        _section(CITY_SECTIONS[8], paragraphs=[findings[3], "DJF는 전년 12월을 포함하며 완전하지 않은 첫 계절은 기존 분석에서 제외된다."], tables=[_table(f, "seasonal", "계절별 기온 추세", ("season", "n_years", "valid_start_year", "valid_end_year", "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper", "significant_fdr"), metric="temperature")], charts=["seasonal_trend"]),
        _section(CITY_SECTIONS[9], paragraphs=["Bias = NASA − KMA. correlation은 시간적 동조, MAE/RMSE는 절대오차, Bias는 systematic difference를 보여준다.", findings[4]] + ([CONTINUITY_CAVEAT] if "continuity" in fact.tables else []), caveat=PRECIPITATION_CAVEAT, tables=validation_tables, charts=["t2m_scatter", "t2m_annual_validation", "validation_summary"]),
        _section(CITY_SECTIONS[10], paragraphs=threshold_findings(fact), tables=[_table(f, "threshold", "동일 threshold·유효 pair 기준 연도별 count", ("year", "threshold", "threshold_c", "n_pairs", "nasa_count", "kma_count", "difference"))]),
        _section(CITY_SECTIONS[11], paragraphs=fact.data_quality_notes, tables=_quality_tables(f)),
        _section(CITY_SECTIONS[12], paragraphs=findings),
        _section(CITY_SECTIONS[13], paragraphs=LIMITATIONS, caveat=PRECIPITATION_CAVEAT),
    ]


def comparison_sections(facts: ComparisonFacts) -> list[dict]:
    """Build nineteen comparison sections, retaining indicator-specific ranks only."""

    f = facts.cities
    temperature = [r for c in f for r in c.tables["rankings"].rows if r["metric"] == "temperature"]
    leaders = [r["city"] for r in temperature if r["rank"] == min(r["rank"] for r in temperature)]
    rmses = sorted((c for c in f if finite(c.value("kma_t2m_rmse"))), key=lambda c: c.value("kma_t2m_rmse"))
    summary = [
        "이 보고서는 8개 도시의 특정 기후지표를 비교하며 종합 위험도 점수나 미래 예측을 생성하지 않는다.",
        f"기존 온난화 속도 순위표의 T2M Sen 기울기 상위 도시는 {', '.join(leaders)}이다. 특정 지표의 순위일 뿐이다.",
        "T2M RMSE의 작은 값부터의 순서: " + ", ".join(f"{c.city} ({format_value(c.value('kma_t2m_rmse'))} °C)" for c in rmses) + ".",
        PRECIPITATION_CAVEAT,
        "일사량 1981–1983의 결측과 변수별 유효기간, 강릉 관측소의 공간적 차이를 함께 고려한다.",
    ]
    output = [
        _section(COMPARISON_SECTIONS[0], paragraphs=summary),
        _section(COMPARISON_SECTIONS[1], paragraphs=_methods(f[0]), tables=[_table(f, "summary", "분석 좌표", ("city", "latitude", "longitude")), _table(f, "station", "ASOS 매핑", ("city", "kma_station_id", "kma_station_name", "distance_km", "role"))], charts=["city_locations"]),
        _section(COMPARISON_SECTIONS[2], tables=[_table(f, "summary", "도시별 평균기온", ("city", "temperature_mean")), _table(f, "past_recent", "과거·최근 평균기온", ("city", "past_period", "past_mean", "recent_period", "recent_mean", "absolute_difference"), variable="T2M")]),
        _section(COMPARISON_SECTIONS[3], tables=_trend_tables(f, ["temperature"]) + [_table(f, "rankings", "온난화 속도 순위 — T2M Sen /10년", ("city", "rank", "sen_slope_per_decade", "significant_fdr"), metric="temperature")], charts=["sen_temperature"]),
        _section(COMPARISON_SECTIONS[4], tables=_trend_tables(f, ["temperature_max_mean", "temperature_min_mean"])),
        _section(COMPARISON_SECTIONS[5], tables=_trend_tables(f, ["hot_day_33"]), charts=["hot_day_33"]),
        _section(COMPARISON_SECTIONS[6], tables=_trend_tables(f, ["warm_night_25"]), charts=["warm_night_25"], paragraphs=[c.city + ": " + s for c in f for s in threshold_findings(c) if s.startswith("tmin_ge_25")]),
        _section(COMPARISON_SECTIONS[7], tables=_trend_tables(f, ["precipitation"]), caveat=PRECIPITATION_CAVEAT),
        _section(COMPARISON_SECTIONS[8], tables=_trend_tables(f, ["humidity"])),
        _section(COMPARISON_SECTIONS[9], tables=_trend_tables(f, ["wind"])),
        _section(COMPARISON_SECTIONS[10], tables=_trend_tables(f, ["solar"]), paragraphs=["NASA 1981–1983 fill value는 결측으로 유지했다. 유효 분석기간을 표에 표시했다."]),
        _section(COMPARISON_SECTIONS[11], tables=[_table(f, "seasonal", "계절별 T2M 추세", ("city", "season", "n_years", "sen_slope_per_decade", "sen_ci_lower", "sen_ci_upper", "significant_fdr"), metric="temperature")], charts=["seasonal_heatmap"]),
        _section(COMPARISON_SECTIONS[12], tables=[_table(f, "normals", "1991–2020 normal", ("city", "T2M_normal_C"), period_type="annual"), _table(f, "anomalies", "최근 연도 anomaly", ("city", "YEAR", "T2M_anomaly"), YEAR=f[0].value("analysis_end_year"))], charts=["anomaly_heatmap"]),
        _section(COMPARISON_SECTIONS[13], paragraphs=["Bias = NASA − KMA. 상관계수는 정확도 백분율이 아니다."], tables=[_table(f, "validation", "T2M agreement", ("city",) + VALIDATION_COLUMNS, metric="temperature")], charts=["t2m_bias", "t2m_rmse"]),
        _section(COMPARISON_SECTIONS[14], caveat=PRECIPITATION_CAVEAT, paragraphs=["POD / FAR / CSI도 동일한 유효 강수 pair 범위에 대한 결과다."], tables=[_table(f, "validation", "전체 변수 agreement", ("city",) + VALIDATION_COLUMNS), _table(f, "contingency", "강수 contingency")]),
        _section(COMPARISON_SECTIONS[15], caveat=CONTINUITY_CAVEAT, tables=[_table(f, "continuity", "104−105 중첩기간 비교")]),
        _section(COMPARISON_SECTIONS[16], tables=_quality_tables(f), paragraphs=f[0].data_quality_notes, charts=["data_quality"]),
        _section(COMPARISON_SECTIONS[17], paragraphs=summary[:3]),
        _section(COMPARISON_SECTIONS[18], paragraphs=LIMITATIONS, caveat=PRECIPITATION_CAVEAT),
    ]
    return output


def _environment(html: bool) -> Environment:
    """Enable explicit HTML autoescape and fail on missing template attributes."""

    env = Environment(loader=FileSystemLoader(PACKAGE / "templates"), undefined=StrictUndefined, autoescape=html, keep_trailing_newline=True)
    env.filters["fmt"] = format_value
    env.filters["md"] = markdown_escape
    return env


def _context(facts: list[ReportFacts], sections: list[dict], charts: list[Chart], html_path: Path, final_path: Path, root: Path, generated_at: str, comparison: bool) -> dict:
    """Prepare one shared context; the templates perform no data loading or arithmetic."""

    views = {}
    for chart in charts:
        views[chart.key] = {"title": chart.title, "src": "data:image/png;base64," + base64.b64encode(chart.path.read_bytes()).decode("ascii"), "relative": os.path.relpath(chart.path, html_path.parent), "operation": chart.operation}
    sources = {name: meta for fact in facts for name, meta in fact.sources.items()}
    for section in sections:
        for table in section["tables"]:
            table["source_href"] = os.path.relpath(root / table["source_file"], final_path.parent)
    kpis = []
    selected = [("temperature_mean", "장기 평균기온", "°C"), ("temperature_sen_slope", "T2M Sen 기울기", "°C/10년"), ("normal_1991_2020", "T2M normal", "°C"), ("recent_anomaly", "최근 연도 anomaly", "°C"), ("kma_t2m_bias", "T2M Bias", "°C"), ("kma_t2m_rmse", "T2M RMSE", "°C"), ("kma_t2m_pearson", "T2M Pearson r", ""), ("kma_t2m_n_pairs", "T2M 유효 pair", "일")]
    for fact in facts:
        for key, label, unit in (selected[:2] if comparison else selected):
            cell = fact.metrics[key]
            kpis.append({"id": f"{fact.slug}.{key}", "label": f"{fact.city} · {label}", "value": cell.value, "column": cell.column, "unit": unit, "source": cell.source_file})
    first = facts[0]
    return {
        "title": "대한민국 8개 도시 기후 비교보고서" if comparison else f"{first.city} 기후변화 분석보고서",
        "period": f"{first.value('analysis_start_year')}–{first.value('analysis_end_year')}",
        "normal_period": f"{first.value('normal_start_year')}–{first.value('normal_end_year')}",
        "generated_at": generated_at, "sections": sections, "charts": views, "kpis": kpis,
        "css": (PACKAGE / "static/report.css").read_text(encoding="utf-8"),
        "sources": [{"file": name, "href": os.path.relpath(root / name, final_path.parent), **meta} for name, meta in sorted(sources.items())],
        "source_links": SOURCE_LINKS,
    }


def generate_reports(project_root: Path, *, city: str | None = None, all_cities: bool = False, comparison_only: bool = False, output_root: Path | None = None, generated_at: str | None = None) -> list[ReportResult]:
    """Generate reports transactionally after source and content checks; never run analysis."""

    root = Path(project_root).resolve()
    destination = Path(output_root or root / "output/reports").resolve()
    for protected in (root / "data", root / "output/tables", root / "output/validation", root / "output/charts"):
        if destination == protected or protected in destination.parents:
            raise ValueError("보고서 출력은 기존 데이터·분석결과 폴더와 분리해야 합니다.")
    provider = ReportDataProvider(root)
    if all_cities or comparison_only:
        comparison = provider.comparison_facts()
        facts = comparison.cities
    else:
        facts = [provider.city_facts(city or "Seoul")]
        comparison = None
    checks = {f.city: validate_facts(f, root) for f in facts}
    generated_at = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix=".report-stage-", dir=destination) as temporary:
        stage = Path(temporary)
        jobs: list[tuple[list[ReportFacts], list[dict], list[Chart], str, str, bool]] = []
        if not comparison_only:
            for f in facts:
                plots = city_charts(f, stage / "assets" / f.slug)
                jobs.append(([f], city_sections(f), plots, f"cities/{f.slug}_climate_report", f"{f.slug}_report_manifest", False))
        if comparison is not None:
            plots = comparison_charts(comparison, stage / "assets/comparison")
            jobs.append((facts, comparison_sections(comparison), plots, "korea_8city_climate_comparison_report", "korea_8city_report_manifest", True))
        for job_facts, sections, charts, stem, manifest_stem, is_comparison in jobs:
            html_path = stage / f"{stem}.html"
            md_path = stage / f"{stem}.md"
            manifest_path = stage / f"manifests/{manifest_stem}.json"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            context = _context(job_facts, sections, charts, html_path, destination / f"{stem}.html", root, generated_at, is_comparison)
            template = "comparison_report" if is_comparison else "city_report"
            html = _environment(True).get_template(f"{template}.html.j2").render(context)
            markdown = _environment(False).get_template(f"{template}.md.j2").render(context)
            validation = validate_rendered(html, markdown, job_facts, [s["title"] for s in sections])
            manifest = {
                "report": f"{stem}.html", "markdown": f"{stem}.md", "generated_at": generated_at,
                "engine": "deterministic-csv-reports-v1", "api_calls": 0,
                "sources": {name: info for f in job_facts for name, info in f.sources.items()},
                "metrics": {f.city: {name: asdict(value) for name, value in f.metrics.items()} for f in job_facts},
                "table_provenance": {f.city: {name: {"source_file": t.source_file, "columns": t.columns, "row_key_columns": t.keys, "csv_line_numbers": t.row_numbers} for name, t in f.tables.items()} for f in job_facts},
                "charts": [{"file": os.path.relpath(c.path, stage), "source_files": c.source_files, "operation": c.operation, "sha256": hashlib.sha256(c.path.read_bytes()).hexdigest()} for c in charts],
                "validation": {**validation, "source_facts_checked": {f.city: checks[f.city] for f in job_facts}},
                "generator_files": {str(p.relative_to(PACKAGE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PACKAGE.rglob('*')) if p.suffix in {".py", ".j2", ".css"}},
            }
            html_path.write_text(html, encoding="utf-8")
            md_path.write_text(markdown, encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            validate_output_files(html_path, md_path, manifest_path)
            results.append(ReportResult(destination / f"{stem}.html", destination / f"{stem}.md", destination / manifest_path.relative_to(stage), tuple(destination / c.path.relative_to(stage) for c in charts)))
        # Detect any input change during chart rendering before publishing artifacts.
        for f in facts:
            for relative, info in f.sources.items():
                if hashlib.sha256((root / relative).read_bytes()).hexdigest() != info["sha256"]:
                    raise ValueError("보고서 생성 중 입력 CSV가 변경되어 게시를 중단했습니다.")
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                target = destination / path.relative_to(stage)
                target.parent.mkdir(parents=True, exist_ok=True)
                path.replace(target)
    for result in results:
        validate_output_files(result.html_path, result.markdown_path, result.manifest_path)
    return results
