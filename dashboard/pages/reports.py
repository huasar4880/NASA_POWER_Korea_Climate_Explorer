"""Read-only downloads of already generated climate reports."""

from __future__ import annotations

import streamlit as st

from src.config import PROJECT_ROOT, REPORTS_DIR
from src.final_integration.facts import FINAL
from src.final_integration.report import REPORT_STEM


def render() -> None:
    """Offer existing portable HTML and Markdown; never build reports in Streamlit."""

    st.title("자동 기후분석 보고서")
    st.caption("기존 HTML/Markdown 읽기 전용 · 분석·보고서 생성·API 호출 없음")
    st.subheader("최종 통합 연구보고서")
    for label, relative, mime in (
        ("최종 HTML 다운로드", FINAL / 'report' / f'{REPORT_STEM}.html', 'text/html'),
        ("최종 Markdown 다운로드", FINAL / 'report' / f'{REPORT_STEM}.md', 'text/markdown'),
        ("Executive Summary 다운로드", FINAL / 'EXECUTIVE_SUMMARY.md', 'text/markdown'),
    ):
        final_path = PROJECT_ROOT / relative
        if final_path.is_file():
            st.download_button(label, final_path.read_bytes(), file_name=final_path.name, mime=mime, key=label)
    st.caption("최종 HTML에는 그림이 내장되어 있습니다. Markdown은 report/assets 폴더가 필요합니다.")
    st.subheader("기존 도시·비교 보고서")
    paths = sorted((REPORTS_DIR / "cities").glob("*_climate_report.html"))
    comparison = REPORTS_DIR / "korea_8city_climate_comparison_report.html"
    if comparison.is_file():
        paths.append(comparison)
    if not paths:
        st.info("생성된 보고서가 없습니다. CLI에서 먼저 생성하세요.")
        st.code("python main.py --report --all")
        return
    path = st.selectbox("보고서 선택", paths, format_func=lambda p: p.stem.replace("_", " "))
    st.info("HTML을 내려받아 브라우저에서 열면 표·차트를 오프라인으로 볼 수 있습니다. 인쇄 또는 PDF 저장도 가능합니다.")
    st.download_button("HTML 보고서 다운로드", path.read_bytes(), file_name=path.name, mime="text/html")
    markdown = path.with_suffix(".md")
    if markdown.is_file():
        st.download_button("Markdown 다운로드", markdown.read_bytes(), file_name=markdown.name, mime="text/markdown")
        st.caption("Markdown 차트는 output/reports/assets의 상대경로를 사용합니다. HTML에는 차트가 내장되어 있습니다.")
    st.warning("강수 validation은 유효한 강수 수치가 있는 날짜만의 비교이며, 강수 공란 의미는 미확정입니다.")
