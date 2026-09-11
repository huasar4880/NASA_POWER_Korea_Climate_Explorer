"""저장된 Tier-A 전국 분석표로 API 없이 Markdown/HTML 종합보고서를 생성한다."""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd


def _format_table(dataframe: pd.DataFrame, columns: list[str], rows: int = 20) -> str:
    """Markdown report에 넣을 제한된 표를 만든다."""

    selected = dataframe.loc[:, columns].head(rows)

    def value_text(value: object) -> str:
        if pd.isna(value):
            return "NA"
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            return f"{float(value):.4f}"
        return str(value).replace("|", "\\|")

    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(value_text(value) for value in row) + " |"
        for row in selected.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *body])


def build_nationwide_report_markdown(
    stations: pd.DataFrame,
    summary: pd.DataFrame,
    regional: pd.DataFrame,
    elevation: pd.DataFrame,
    seasonal: pd.DataFrame,
) -> str:
    """전국 분석 방법·결과·필수 caveat를 담은 Markdown을 구성한다."""

    slope = summary["kma_tavg_sen_slope_decade"]
    significant = summary["kma_tavg_fdr_significant"].astype(bool)
    increasing = int((significant & slope.gt(0)).sum())
    decreasing = int((significant & slope.lt(0)).sum())
    seasonal_tavg = seasonal.loc[
        seasonal["source"].eq("KMA") & seasonal["metric"].eq("TAVG")
    ]
    seasonal_summary = seasonal_tavg.groupby("season")["sen_slope_per_decade"].median().reset_index()
    return f"""# Nationwide Tier-A Temperature Analysis

## 1. 분석 개요

- 대상: 10단계 Final Tier A {len(stations)}개 ASOS station
- 공통 분석기간: 1981-01-01~2025-12-31
- Climate Normal: 1991~2020
- 변수: KMA 평균/최고/최저기온과 NASA POWER T2M/T2M_MAX/T2M_MIN
- 분석 단위: station level

## 2. Station 선정 기준

`nationwide_asos_longterm_shortlist.csv`의 Final Tier A이면서 1981~2025 가용,
manual review가 아니고 continuity가 미확정 상태가 아닌 station만 사용했다. Tier B는 제외했다.

## 3. 전국 기온 추세

KMA TAVG Sen slope 범위는 {slope.min():+.4f}~{slope.max():+.4f} °C/10년,
중앙값은 {slope.median():+.4f} °C/10년이다. metric별 station family에 BH FDR을 적용했을 때
유의한 증가 station은 {increasing}개, 유의한 감소 station은 {decreasing}개이다.

## 4. Tmax/Tmin

평균 일최고기온과 평균 일최저기온도 annual mean을 먼저 계산한 뒤 동일한
linear, Mann–Kendall, 필요 시 Hamed–Rao modified MK, Theil–Sen 절차로 분석했다.

## 5. Anomaly

각 station·source·metric의 1991~2020 연평균을 normal로 삼고, 각 연도의
`annual_mean - normal_mean`을 anomaly(°C)로 계산했다.

## 6. 계절

DJF는 12월을 다음 해 season-year에 배정하며, 완전한 달력 season만 사용한다.

{_format_table(seasonal_summary, ["season", "sen_slope_per_decade"], 4)}

## 7. Threshold proxy

TMAX ≥30°C, TMAX ≥33°C, TMIN ≥25°C를 같은 유효 일별 pair에서 재계산했다.
이는 공식 KMA 폭염·열대야 통계가 아니라 비교를 위한 analysis proxy이다.

## 8. NASA–KMA validation

Bias는 NASA−KMA, MAE/RMSE는 °C, Pearson/Spearman은 무차원이다.
NASA POWER는 격자 기반 값이고 KMA ASOS는 station 관측이므로 차이를 단순 관측오류로 해석하지 않는다.
Correlation은 accuracy를 뜻하지 않는다.

## 9. Region summary

{_format_table(regional, ["region", "station_count", "median_kma_tavg_sen_slope", "fdr_significant_station_count"])}

Station 분포는 전국 공간을 균등하게 대표하지 않으며 region 요약은 지역 기후의 참값이 아니다.

## 10. Elevation exploratory summary

{_format_table(elevation, ["elevation_band", "station_count", "median_kma_tavg_sen_slope", "mean_kma_tavg_sen_slope"], 4)}

고도대 비교는 탐색적 연관이며 인과관계를 나타내지 않는다.

## 11. Data quality

10단계의 `temperature_missing_rate`, `annual_completeness`, `continuity_risk`를
station 결과에 연결했다. 원자료의 결측 관측을 임의 생성하거나 보간하지 않았다.

## 12. Limitations

- Tier A station만 분석했고 continuity unresolved/manual-review station과 Tier B를 제외했다.
- station 분포는 공간적으로 균등하지 않다.
- NASA grid와 KMA station의 대표 공간 규모가 다르다.
- threshold 결과는 분석 proxy이다.
- significance는 causality가 아니며 direction consistency는 absolute agreement가 아니다.
- region 평균은 area-weighted regional climate truth가 아니다.
"""


def save_nationwide_report(
    stations: pd.DataFrame,
    summary: pd.DataFrame,
    regional: pd.DataFrame,
    elevation: pd.DataFrame,
    seasonal: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Markdown과 self-contained style HTML 보고서를 저장한다."""

    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = build_nationwide_report_markdown(stations, summary, regional, elevation, seasonal)
    markdown_path = output_dir / "nationwide_temperature_analysis_report.md"
    html_path = output_dir / "nationwide_temperature_analysis_report.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    try:
        import markdown as markdown_library

        body = markdown_library.markdown(markdown, extensions=["tables"])
    except ImportError:
        body = f"<pre>{escape(markdown)}</pre>"
    html = f"""<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">
<title>Nationwide Tier-A Temperature Analysis</title><style>
body{{font-family:Arial,sans-serif;max-width:1100px;margin:2rem auto;line-height:1.6;color:#172033}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #d7dce5;padding:.4rem;text-align:right}}
th:first-child,td:first-child{{text-align:left}}h1,h2{{color:#143d66}}</style></head><body>{body}</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    return html_path, markdown_path
