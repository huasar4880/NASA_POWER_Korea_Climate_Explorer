"""Fail-closed source consistency, safe content and rendered report checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

import pandas as pd

from reporting.formatters import format_value

if TYPE_CHECKING:
    from reporting.data_provider import ReportFacts


class ReportValidationError(ValueError):
    """Report output or its numeric provenance is not trustworthy."""


def reject_unsafe_text(text: str) -> None:
    """Reject credentials without echoing secret values in exceptions."""

    key = os.environ.get("KMA_API_KEY", "")
    variants = {key, unquote(key), quote(unquote(key), safe="")} if key else set()
    if any(secret and secret in text for secret in variants) or re.search(
        r"(?i)(?:servicekey|authkey|api[_-]?key)\s*[=:\"']", text
    ):
        raise ReportValidationError("민감정보로 의심되는 값이 있어 보고서 생성을 중단했습니다. 값은 출력하지 않습니다.")


def validate_facts(facts: ReportFacts, root: Path) -> int:
    """Compare every scalar fact to a fresh read of the unchanged source CSV."""

    frames = {}
    for relative, metadata in facts.sources.items():
        payload = (root / relative).read_bytes()
        if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
            raise ReportValidationError(f"보고서 준비 중 source CSV 변경: {relative}")
        frames[relative] = pd.read_csv(root / relative)
    for label, fact in facts.metrics.items():
        frame = frames[fact.source_file]
        selected = frame
        for col, value in fact.row_key.items():
            selected = selected.loc[selected[col].isna() if value is None else selected[col].eq(value)]
        if len(selected) != 1:
            raise ReportValidationError(f"source row 불일치: {facts.city}.{label}")
        actual = selected.iloc[0][fact.column]
        actual = None if pd.isna(actual) else actual
        if actual != fact.value:
            raise ReportValidationError(f"source 숫자 불일치: {facts.city}.{label}")
    for table in facts.tables.values():
        frame = frames[table.source_file]
        if len(table.rows) != len(table.row_numbers):
            raise ReportValidationError("source row 위치 누락")
        original = frame.iloc[[line - 2 for line in table.row_numbers]].loc[:, table.columns].reset_index(drop=True)
        supplied = pd.DataFrame(table.rows, columns=table.columns)
        try:
            pd.testing.assert_frame_equal(original, supplied, check_dtype=False, check_exact=True)
        except AssertionError:
            raise ReportValidationError(f"source table 셀 불일치: {table.source_file}") from None
    return len(facts.metrics)


class ReportHTMLParser(HTMLParser):
    """Extract report headings, images and numeric fact markers for validation."""

    def __init__(self) -> None:
        """Initialize an HTML parser without executing scripts."""

        super().__init__()
        self.images: list[str] = []
        self.fact_text: dict[str, str] = {}
        self.current: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect image references and fact-tagged span values."""

        attributes = dict(attrs)
        if tag == "img":
            self.images.append(attributes.get("src") or "")
        if "data-fact" in attributes:
            self.current = attributes["data-fact"]
            self.fact_text[self.current] = ""

    def handle_data(self, data: str) -> None:
        """Collect the textual representation of a marked scalar fact."""

        if self.current:
            self.fact_text[self.current] += data

    def handle_endtag(self, tag: str) -> None:
        """Finish a fact span without treating layout markup as numeric content."""

        if tag == "span":
            self.current = None


def validate_rendered(html: str, markdown: str, facts: list[ReportFacts], section_titles: list[str]) -> dict[str, int]:
    """Check required content, placeholders, unsafe claims and exact KPI rendering."""

    for text in (html, markdown):
        reject_unsafe_text(text)
        text = re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "embedded-image", text)
        if not text.strip() or any(token in text for token in ("{{", "}}", "{%", "%}")):
            raise ReportValidationError("빈 보고서 또는 미처리 template placeholder")
        if re.search(r"(?<![\w])(?:nan|[+-]?inf|infinity)(?![\w])", text, re.I):
            # The explicit precipitation caveat uses the conventional NaN label.
            cleaned = text.replace("공란/NaN", "공란/결측")
            if re.search(r"(?<![\w])(?:nan|[+-]?inf|infinity)(?![\w])", cleaned, re.I):
                raise ReportValidationError("보고서에 숫자 결측/무한대 문자열이 노출되었습니다.")
        for forbidden in ("기후변화 때문에 발생했다", "NASA 자료가 틀렸다", "ASOS가 절대적인 참값이다", "정확도 99%", "미래에는 반드시 증가한다", "특정 도시가 가장 위험하다"):
            if forbidden in text:
                raise ReportValidationError("허용되지 않은 인과·위험·정확도 표현")
        for title in section_titles:
            if title not in text:
                raise ReportValidationError(f"필수 보고서 section 누락: {title}")
        for fact in facts:
            if fact.city not in text:
                raise ReportValidationError("도시명 누락")
            period = f"{fact.value('analysis_start_year')}–{fact.value('analysis_end_year')}"
            if period not in text:
                raise ReportValidationError("분석기간 누락")
    parser = ReportHTMLParser()
    parser.feed(html)
    known = {f"{f.slug}.{k}": value for f in facts for k, value in f.metrics.items()}
    if not parser.fact_text:
        raise ReportValidationError("검증 가능한 핵심 숫자 marker 없음")
    for marker, text in parser.fact_text.items():
        expected = format_value(known[marker].value, known[marker].column)
        if text.strip() != expected or f"<!-- fact:{marker} -->{expected}<!-- /fact -->" not in markdown:
            raise ReportValidationError(f"HTML/Markdown 핵심 숫자 불일치: {marker}")
    if not parser.images or any(not value.startswith("data:image/png;base64,") for value in parser.images):
        raise ReportValidationError("HTML 차트는 오프라인 PNG로 포함되어야 합니다.")
    return {"sections": len(section_titles), "images": len(parser.images), "checked_rendered_facts": len(parser.fact_text)}


def validate_output_files(html_path: Path, md_path: Path, manifest_path: Path) -> None:
    """Validate saved artifacts and local Markdown image targets."""

    for path in (html_path, md_path, manifest_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise ReportValidationError(f"보고서 파일 생성 실패: {path.name}")
    text = md_path.read_text(encoding="utf-8")
    for relative in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        image_path = (md_path.parent / relative).resolve()
        if not image_path.is_file() or image_path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise ReportValidationError("Markdown 차트 경로 또는 PNG 형식 오류")
    payload = manifest_path.read_text(encoding="utf-8")
    reject_unsafe_text(payload)
    json.loads(payload, parse_constant=lambda value: (_ for _ in ()).throw(ReportValidationError("manifest 비유한 숫자")))
