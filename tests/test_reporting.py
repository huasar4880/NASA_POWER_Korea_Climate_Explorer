"""Offline report regressions: source cells, safe language and complete artifacts."""

from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import socket

import pandas as pd
import pytest
import requests

from reporting.charts import Chart
from reporting.data_provider import ReportDataError, ReportDataProvider
from reporting.formatters import MISSING, format_value, markdown_escape
from reporting.narrative import CONTINUITY_CAVEAT, PRECIPITATION_CAVEAT, bias_sentence, executive_summary, threshold_findings, trend_sentence
from reporting.report_builder import CITY_SECTIONS, COMPARISON_SECTIONS, city_sections, comparison_sections, generate_reports
from reporting.validation import ReportHTMLParser, ReportValidationError, reject_unsafe_text, validate_facts, validate_output_files

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_report_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any attempted API request or network connection fails every report test."""

    def forbidden(*args: object, **kwargs: object) -> None:
        """Reject unexpected network I/O without echoing request parameters."""

        raise AssertionError("Report tests must not access a network")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture(scope="module")
def provider() -> ReportDataProvider:
    """Use existing CSV artifacts as a read-only integration fixture."""

    return ReportDataProvider(ROOT)


@pytest.fixture(scope="module")
def seoul(provider: ReportDataProvider):
    """Load Seoul once while keeping mutations isolated in individual tests."""

    return provider.city_facts("Seoul")


@pytest.fixture(scope="module")
def comparison(provider: ReportDataProvider):
    """Load the eight existing city fact sets without raw/processed access."""

    return provider.comparison_facts()


@pytest.fixture
def fast_charts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace rendering only with tiny PNG fixtures; real charts are CLI-verified."""

    pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aH1sAAAAASUVORK5CYII=")

    def build(facts: object, directory: Path, keys: list[str]) -> list[Chart]:
        """Provide every required plot key without performing expensive rendering."""

        directory.mkdir(parents=True, exist_ok=True)
        results = []
        for key in keys:
            path = directory / f"{key}.png"
            path.write_bytes(pixel)
            results.append(Chart(key, key, path, ("output/tables/city_climate_annual_1981_2025.csv",)))
        return results
    monkeypatch.setattr("reporting.report_builder.city_charts", lambda f, d: build(f, d, ["temperature_longterm", "temperature_anomaly", "monthly_climatology", "extreme_proxies", "seasonal_trend", "t2m_scatter", "t2m_annual_validation", "validation_summary", "precipitation"]))
    monkeypatch.setattr("reporting.report_builder.comparison_charts", lambda f, d: build(f, d, ["sen_temperature", "hot_day_33", "warm_night_25", "t2m_bias", "t2m_rmse", "anomaly_heatmap", "seasonal_heatmap", "data_quality", "city_locations"]))


def test_loader_returns_defensive_copy(provider) -> None:
    """Caller mutations cannot corrupt later CSV-backed facts."""

    first = provider.load("summary")
    first.loc[0, "temperature_mean"] = -12345
    assert provider.load("summary").loc[0, "temperature_mean"] != -12345


def test_missing_result_explains_upstream_workflow(tmp_path) -> None:
    """Missing data never triggers automatic generation or a download."""

    with pytest.raises(ReportDataError, match="python main.py --all"):
        ReportDataProvider(tmp_path).load("summary")
    with pytest.raises(ReportDataError, match="validate-kma"):
        ReportDataProvider(tmp_path).load("validation")


def test_invalid_schema_is_rejected(tmp_path) -> None:
    """Schema diagnostics identify the upstream result rather than inventing facts."""

    folder = tmp_path / "output/tables"
    folder.mkdir(parents=True)
    (folder / "city_climate_summary_1981_2025.csv").write_text("city\nSeoul\n", encoding="utf-8")
    with pytest.raises(ReportDataError, match="필수 컬럼"):
        ReportDataProvider(tmp_path).load("summary")


def test_duplicate_source_keys_are_rejected(tmp_path) -> None:
    """A fact cannot silently select the first of duplicate source rows."""

    folder = tmp_path / "output/tables"
    folder.mkdir(parents=True)
    (folder / "city_climate_summary_1981_2025.csv").write_text("city,latitude,longitude,temperature_mean\nSeoul,37,127,11\nSeoul,37,127,12\n", encoding="utf-8")
    with pytest.raises(ReportDataError, match="중복 row key"):
        ReportDataProvider(tmp_path).load("summary")


@pytest.mark.parametrize("fact_name,table,column,metric", [
    ("temperature_sen_slope", "trends", "sen_slope_per_decade", "temperature"),
    ("temperature_sen_ci_lower", "trends", "sen_ci_lower", "temperature"),
    ("temperature_fdr_significant", "trends", "significant_fdr", "temperature"),
    ("tmax_sen_slope", "trends", "sen_slope_per_decade", "temperature_max_mean"),
    ("tmin_sen_slope", "trends", "sen_slope_per_decade", "temperature_min_mean"),
    ("kma_t2m_rmse", "validation", "rmse", "temperature"),
    ("kma_t2m_bias", "validation", "bias", "temperature"),
    ("kma_precip_pearson", "validation", "pearson_r", "precipitation"),
])
def test_report_fact_mapping_matches_csv(seoul, provider, fact_name, table, column, metric) -> None:
    """Key report facts equal their exact CSV source cells, not hardcoded expectations."""

    source = provider.load(table)
    row = source.loc[source.city.eq("Seoul") & source.metric.eq(metric)].iloc[0]
    assert seoul.value(fact_name) == row[column]
    assert seoul.metrics[fact_name].column == column
    assert seoul.metrics[fact_name].row_key == {"city": "Seoul", "metric": metric}


def test_fact_period_normal_and_recent_mapping(seoul, provider) -> None:
    """Latest annual anomaly and ten-year comparisons remain distinct."""

    annual = provider.load("annual").query("city == 'Seoul'")
    assert seoul.value("analysis_start_year") == annual.YEAR.min()
    assert seoul.value("analysis_end_year") == annual.YEAR.max()
    anomalies = provider.load("anomalies").query("city == 'Seoul'").sort_values("YEAR")
    assert seoul.value("recent_anomaly") == anomalies.iloc[-1].T2M_anomaly
    assert seoul.metrics["recent_mean"].row_key["variable"] == "T2M"
    assert seoul.value("normal_start_year") == 1991


def test_comparison_fact_mapping(comparison, provider) -> None:
    """All eight cities map to source result rows without a hardcoded rank."""

    assert [f.city for f in comparison.cities] == provider.city_names()
    assert len(comparison.cities) == 8
    values = {f.city: f.value("kma_t2m_rmse") for f in comparison.cities}
    expected = provider.load("validation").query("metric == 'temperature'").set_index("city").rmse.to_dict()
    assert values == expected


def test_source_consistency_validates_every_scalar_and_table_cell(seoul) -> None:
    """A full report fact layer is checked against unchanged input hashes and cells."""

    assert validate_facts(seoul, ROOT) == len(seoul.metrics)
    changed = deepcopy(seoul)
    changed.metrics["temperature_sen_slope"] = replace(changed.metrics["temperature_sen_slope"], value=9.9)
    with pytest.raises(ReportValidationError, match="숫자 불일치"):
        validate_facts(changed, ROOT)


def test_table_tampering_fails_consistency(seoul) -> None:
    """Chart/table input mutations also fail, not just headline scalar changes."""

    changed = deepcopy(seoul)
    changed.tables["annual"].rows[0]["T2M_mean_C"] = 99.0
    with pytest.raises(ReportValidationError, match="table 셀 불일치"):
        validate_facts(changed, ROOT)


def test_positive_significant_narrative() -> None:
    """Positive FDR-significant slopes produce conservative observational language."""

    text = trend_sentence("기온", 0.3, True)
    assert "증가 추세가 관찰" in text and "유의성이 확인" in text
    assert "때문에" not in text


def test_positive_nonsignificant_narrative() -> None:
    """Non-significance is not stated as absence of climate change."""

    text = trend_sentence("기온", 0.3, False)
    assert "증가 방향" in text and "유의성은 확인되지" in text
    assert "기후변화가 없다" not in text


def test_negative_and_missing_trend_narrative() -> None:
    """Negative, missing-significance and missing-slope cases are distinct."""

    assert "감소" in trend_sentence("기온", -0.3, True)
    assert "판단하지" in trend_sentence("기온", None, True)
    assert "유의성 자료가 없어" in trend_sentence("기온", 0.3, None)


def test_bias_narrative_separates_correlation_and_error() -> None:
    """High correlation does not become an accuracy percentage."""

    text = bias_sentence(-1.6, 2.0, 0.993)
    assert "시간적 변화 패턴의 일치도는 높지만" in text
    assert "절대값 차이" in text and "-1.60" in text
    assert "정확도" not in text
    assert "보류" in bias_sentence(None, 2.0, 0.993)


def test_precipitation_and_continuity_caveats(seoul, comparison) -> None:
    """Caveats are mandatory in city and comparison reports including Gangneung."""

    assert PRECIPITATION_CAVEAT in executive_summary(seoul)
    gangneung = next(f for f in comparison.cities if f.city == "Gangneung")
    city_text = json.dumps(city_sections(gangneung), ensure_ascii=False)
    all_text = json.dumps(comparison_sections(comparison), ensure_ascii=False)
    assert CONTINUITY_CAVEAT in city_text and CONTINUITY_CAVEAT in all_text
    assert PRECIPITATION_CAVEAT in city_text and PRECIPITATION_CAVEAT in all_text
    assert "공란/NaN" in city_text


def test_threshold_gap_uses_stored_counts(comparison) -> None:
    """Large annual gaps are selected from stored results with no causal claims."""

    for fact in comparison.cities:
        text = " ".join(threshold_findings(fact))
        assert "원인은 추정하지 않는다" in text
        assert "과대예측" not in text


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf")])
def test_missing_formatting(value) -> None:
    """Missing/non-finite display values never leak nan or inf tokens."""

    assert format_value(value) == MISSING


def test_table_formatting() -> None:
    """Units and precision rules preserve zero and format counts as integers."""

    assert format_value(0.0) == "0.00"
    assert format_value(-0.0, "sen_slope_per_decade") == "0.000"
    assert format_value(16436.0, "n_pairs") == "16436"
    assert format_value(0.99258487, "pearson_r") == "0.993"
    assert format_value(0.123456, "sen_slope_per_decade") == "0.123"
    assert "e-" in format_value(1e-8, "fdr_q_value")
    assert markdown_escape("a|<b>") == "a\\|&lt;b&gt;"


def test_sensitive_values_rejected_without_echo(monkeypatch) -> None:
    """Credential detection also recognizes URL-encoded variants."""

    secret = "test-private/value+not-real"
    monkeypatch.setenv("KMA_API_KEY", secret)
    for text in [secret, "test-private%2Fvalue%2Bnot-real", "serviceKey=example"]:
        with pytest.raises(ReportValidationError) as error:
            reject_unsafe_text(text)
        assert secret not in str(error.value)


def test_render_html_markdown_manifest_and_paths(tmp_path, fast_charts, monkeypatch) -> None:
    """Generate real templates, validate sections/values and prevent any data writes."""

    monkeypatch.setenv("KMA_API_KEY", "DO-NOT-LEAK-REPORT-TEST-KEY")
    paths = [p for folder in (ROOT / "data", ROOT / "output/tables") for p in folder.rglob("*.csv")]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    reports = generate_reports(ROOT, city="Seoul", output_root=tmp_path, generated_at="2026-09-03T00:00:00+00:00")
    assert len(reports) == 1
    report = reports[0]
    assert report.html_path == tmp_path / "cities/seoul_climate_report.html"
    assert report.markdown_path == tmp_path / "cities/seoul_climate_report.md"
    html = report.html_path.read_text(encoding="utf-8")
    md = report.markdown_path.read_text(encoding="utf-8")
    for title in CITY_SECTIONS:
        assert title in html and title in md
    assert "{{" not in html and "{{" not in md
    assert "DO-NOT-LEAK-REPORT-TEST-KEY" not in html + md + report.manifest_path.read_text()
    assert PRECIPITATION_CAVEAT in html and PRECIPITATION_CAVEAT in md
    parser = ReportHTMLParser()
    parser.feed(html)
    assert parser.fact_text["seoul.kma_t2m_bias"] == "-1.62"
    assert parser.fact_text["seoul.kma_t2m_pearson"] == "0.993"
    assert parser.fact_text["seoul.kma_t2m_n_pairs"] == "16436"
    assert len(parser.images) == 9
    manifest = json.loads(report.manifest_path.read_text())
    assert manifest["metrics"]["Seoul"]["kma_t2m_rmse"]["source_file"].endswith("nasa_kma_validation_metrics.csv")
    validate_output_files(report.html_path, report.markdown_path, report.manifest_path)
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    first_html, first_md = html, md
    again = generate_reports(ROOT, city="Seoul", output_root=tmp_path, generated_at="2026-09-03T00:00:00+00:00")[0]
    assert again.html_path.read_text() == first_html
    assert again.markdown_path.read_text() == first_md


def test_all_city_generation_and_comparison(tmp_path, fast_charts) -> None:
    """All-city mode emits eight city reports plus the complete comparison report."""

    reports = generate_reports(ROOT, all_cities=True, output_root=tmp_path, generated_at="2026-09-03T00:00:00+00:00")
    assert len(reports) == 9
    assert len(list((tmp_path / "cities").glob("*.html"))) == 8
    assert len(list((tmp_path / "cities").glob("*.md"))) == 8
    html = reports[-1].html_path.read_text()
    md = reports[-1].markdown_path.read_text()
    for title in COMPARISON_SECTIONS:
        assert title in html and title in md
    assert CONTINUITY_CAVEAT in html
    assert len(list((tmp_path / "manifests").glob("*.json"))) == 9


def test_output_cannot_overwrite_source_directories() -> None:
    """Refuse a report destination inside protected input folders."""

    with pytest.raises(ValueError, match="분리"):
        generate_reports(ROOT, output_root=ROOT / "output/tables")


def test_report_cli_dispatch(monkeypatch) -> None:
    """The report action never enters existing NASA or KMA workflows."""

    import main
    called = {}
    def generate(root: Path, **kwargs: object) -> list:
        """Record report-only dispatch with no rendering or I/O."""

        called.update(kwargs)
        return []
    monkeypatch.setattr("reporting.report_builder.generate_reports", generate)
    monkeypatch.setattr("sys.argv", ["main.py", "--report", "--all"])
    assert main.main() == 0
    assert called["all_cities"] is True
    monkeypatch.setattr("sys.argv", ["main.py", "--report", "--all", "--force-download"])
    assert main.main() == 1


def test_streamlit_report_page_is_read_only() -> None:
    """A report download page runs without loading the generator or analysis workflows."""

    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string("from dashboard.pages.reports import render\nrender()", default_timeout=20).run()
    assert not app.exception
    assert "보고서" in app.title[0].value


def test_zero_sen_does_not_override_fdr() -> None:
    """Zero median slope and significant rank test can coexist in a saved series."""

    text = trend_sentence("proxy", -0.0, True)
    assert "기후변화가 없다는 결론을 뜻하지 않는다" in text
    assert "MK 기반 FDR 검정은 유의하다" in text
    assert "-0.000" not in text


def test_comparison_cli_dispatch(monkeypatch) -> None:
    """Comparison-only action dispatches without triggering analysis or city reports."""

    import main
    called = {}

    def generate(root: Path, **kwargs: object) -> list:
        """Record report arguments without I/O."""

        called.update(kwargs)
        return []

    monkeypatch.setattr("reporting.report_builder.generate_reports", generate)
    monkeypatch.setattr("sys.argv", ["main.py", "--report-comparison"])
    assert main.main() == 0
    assert called["comparison_only"] is True
    monkeypatch.setattr("sys.argv", ["main.py", "--report-comparison", "--city", "Seoul"])
    assert main.main() == 1


def test_report_requires_explicit_selection(monkeypatch) -> None:
    """A report request without city/all gives a helpful error instead of fetching data."""

    import main
    monkeypatch.setattr("sys.argv", ["main.py", "--report"])
    assert main.main() == 1
