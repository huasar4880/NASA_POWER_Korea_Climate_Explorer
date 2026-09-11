"""저장 가능한 Stage-12 Markdown/HTML 공간분석 보고서."""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd


def _markdown_table(dataframe: pd.DataFrame, columns: list[str], rows: int = 20) -> str:
    """보고서에 삽입할 제한된 Markdown 표를 만든다."""

    selected = dataframe.loc[:, [column for column in columns if column in dataframe]].head(rows)
    headers = selected.columns.tolist()
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in selected.itertuples(index=False, name=None):
        values = []
        for value in row:
            if pd.isna(value):
                values.append("NA")
            elif isinstance(value, float):
                values.append(f"{value:.5f}")
            else:
                values.append(str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _moran_sentence(row: pd.Series, alpha: float) -> str:
    """Global Moran 유의성에 따른 제한된 deterministic 문장을 반환한다."""

    if float(row["permutation_p"]) <= alpha:
        direction = "양의" if float(row["moran_i"]) > 0 else "음의"
        return (
            f"{row['label']}에서 {direction} 공간 자기상관이 관찰되었다 "
            f"(I={row['moran_i']:.4f}, permutation p={row['permutation_p']:.4f}). "
            "이는 선택한 station network와 weight 정의에서의 공간적 연관이며 원인 설명이 아니다."
        )
    return (
        f"선택한 spatial weight 정의에서는 {row['label']}의 유의한 global spatial "
        f"autocorrelation이 확인되지 않았다 (I={row['moran_i']:.4f}, "
        f"permutation p={row['permutation_p']:.4f})."
    )


def build_spatial_report_markdown(
    master: pd.DataFrame,
    global_morans: pd.DataFrame,
    local_morans: pd.DataFrame,
    latitude: pd.DataFrame,
    elevation: pd.DataFrame,
    contrast: pd.DataFrame,
    dtr: pd.DataFrame,
    seasonal: pd.DataFrame,
    seasonal_morans: pd.DataFrame,
    dominant: pd.DataFrame,
    threshold: pd.DataFrame,
    validation: pd.DataFrame,
    regional: pd.DataFrame,
    sensitivity: pd.DataFrame,
    config: dict[str, object],
    coastal_reason: str,
) -> str:
    """공간분석 결과와 필수 caveat를 포함하는 deterministic Markdown을 만든다."""

    alpha = float(config["fdr_alpha"])
    tavg_global = global_morans.loc[global_morans["variable"].eq("kma_tavg_sen_slope")].iloc[0]
    local_tavg = local_morans.loc[local_morans["variable"].eq("kma_tavg_sen_slope")]
    cluster_counts = local_tavg["cluster_type_fdr"].value_counts()
    tmin_faster = int(contrast["contrast_direction"].eq("TMIN warming faster").sum())
    tmax_faster = int(contrast["contrast_direction"].eq("TMAX warming faster").sum())
    dtr_kma = dtr.loc[dtr["source"].eq("KMA")]
    seasonal_medians = seasonal.groupby("season", sort=False)["sen_slope_per_decade"].median().reset_index()
    dominant_counts = dominant["dominant_warming_season"].value_counts().rename_axis("season").reset_index(name="station_count")
    sensitivity_tavg = sensitivity.loc[sensitivity["variable"].eq("kma_tavg_sen_slope")]
    sensitivity_consistent = sensitivity_tavg["permutation_p"].le(alpha).nunique() == 1
    return f"""# Nationwide Spatial Climate Pattern Analysis

## 1. Executive Summary

- 분석 대상: Final Tier A {len(master)}개 station, 1981–2025 Stage-11 결과
- 기본 공간가중치: {config['spatial_weights_method']} k={config['knn_k']}, directed row-standardized
- 거리: Haversine 대권거리(km), station point 분석, 공간보간 없음
- {_moran_sentence(tavg_global, alpha)}
- TMIN warming이 TMAX보다 빠른 station {tmin_faster}개, 반대 방향 {tmax_faster}개다.
- Coastline 분석: {coastal_reason}

## 2. 분석 station 및 공간분포

Final Tier A 목록만 사용했다. station 분포는 전국에 균등하지 않고 station 평균은 면적가중
지역기후값이 아니다. 최근접 거리 중앙값은 {master['nearest_neighbor_distance_km'].median():.2f} km다.

## 3. Spatial method

위경도에 Haversine을 적용했다. 기본 weight는 각 station의 최근접 {config['knn_k']}개를 향하는
directed KNN이며 행 합을 1로 표준화했다. Global Moran은 two-sided permutation
({config['moran_permutations']}회), Local Moran은 permutation({config['local_moran_permutations']}회)
후 station family에 Benjamini–Hochberg FDR을 적용했다. seed는 {config['random_seed']}이다.

## 4. KMA TAVG 공간패턴

{_moran_sentence(tavg_global, alpha)}

{_markdown_table(global_morans.loc[global_morans['variable'].isin(['kma_tavg_sen_slope','kma_tmax_sen_slope','kma_tmin_sen_slope'])], ['variable','n_stations','k','moran_i','expected_i','permutation_p'], 3)}

## 5. TMAX/TMIN contrast

TMAX Sen slope 중앙값은 {contrast['tmax_slope'].median():+.4f}, TMIN은
{contrast['tmin_slope'].median():+.4f} °C/10년이며 TMIN−TMAX 중앙값은
{contrast['tmin_minus_tmax'].median():+.4f} °C/10년이다. 방향 차이만 설명하며 도시화 등 원인을 추정하지 않는다.

## 6. Seasonal spatial pattern

{_markdown_table(seasonal_medians, ['season','sen_slope_per_decade'], 4)}

{_markdown_table(seasonal_morans, ['season','moran_i','permutation_p','k'], 4)}

## 7. Extreme-temperature proxy

TMAX ≥33°C와 TMIN ≥25°C는 동일 threshold 기반 분석 proxy이며 공식 폭염일수·열대야 통계가 아니다.

{_markdown_table(threshold, ['threshold','source','n_stations_used','median_slope_per_decade','moran_i','permutation_p'], 4)}

## 8. NASA-KMA Bias spatial pattern

Bias는 NASA−KMA이다. 양수는 NASA 값이 상대적으로 높고 음수는 낮음을 뜻하며 NASA 오류로 단정하지 않는다.

{_markdown_table(validation.loc[validation['validation_metric'].eq('tavg_bias')], ['validation_metric','median','minimum','maximum','moran_i','permutation_p'], 1)}

## 9. NASA-KMA RMSE spatial pattern

높은 RMSE의 원인을 지형 또는 해안성으로 자동 설명하지 않는다.

{_markdown_table(validation.loc[validation['validation_metric'].eq('tavg_rmse')], ['validation_metric','median','minimum','maximum','moran_i','permutation_p'], 1)}

## 10. Moran's I

Global Moran은 유사한 값이 spatial neighbors에 함께 나타나는 경향을 평가한다. 양의 I만으로
cluster를 단정하지 않고 permutation p를 함께 본다.

{_markdown_table(global_morans, ['variable','n_stations','weights_method','k','moran_i','expected_i','z_score','permutation_p'], 8)}

## 11. Local spatial clusters

TAVG의 BH-FDR 유의 category 수는 High-High {int(cluster_counts.get('High-High', 0))},
Low-Low {int(cluster_counts.get('Low-Low', 0))}, High-Low {int(cluster_counts.get('High-Low', 0))},
Low-High {int(cluster_counts.get('Low-High', 0))}개다. 유의하지 않은 station을 cluster로 부르지 않는다.

## 12. Latitude / elevation associations

{_markdown_table(latitude, ['climate_metric','n_stations_used','pearson_r','pearson_p','spearman_rho','spearman_p','regression_r_squared'], 5)}

{_markdown_table(elevation, ['climate_metric','n_stations_used','pearson_r','pearson_p','spearman_rho','spearman_p','regression_r_squared'], 8)}

모든 관계는 탐색적 연관이며 인과관계가 아니다. 위도·고도와 다른 요인의 confounding 가능성이 있다.

## 13. Coastal / inland comparison

{coastal_reason}. 도시명·행정구역을 이용한 임의 수동분류는 수행하지 않았다.

## 14. Regional exploratory summary

{_markdown_table(regional, ['region_level1','station_count','tavg_median','tavg_iqr','tavg_fdr_significant_count','small_sample_region'], 20)}

station_count < 3인 region은 `small_sample_region=True`이며 대표성 해석이 매우 제한된다.

## 15. Data quality

Stage-11 `temperature_missing_rate`, `annual_completeness`, `continuity_risk`를 그대로 연결했다.
Tier B, manual-review, continuity unresolved station은 포함하지 않았고 입력값을 재계산하거나 보간하지 않았다.

## 16. Limitations

- Tier A station만 사용했으며 station 공간분포가 불균등하다.
- station은 면적 표본이 아니고 point map은 전국 연속 surface가 아니다.
- spatial weights 선택에 따라 Moran 결과가 달라질 수 있다. k=3/4/5 유의성 일관성: {sensitivity_consistent}.
- Local Moran은 multiple testing이 있어 BH-FDR 결과를 우선한다.
- NASA grid와 KMA station은 공간대표성이 다르다.
- 공간 연관은 인과관계가 아니며 latitude/elevation association에는 confounding이 가능하다.
- 해안 분류는 검증된 geometry가 있을 때에도 operational definition이다.
- threshold 지표는 분석 proxy다.
- 보간값을 전국 실제 관측값으로 해석해서는 안 된다. 이번 단계는 보간하지 않았다.

### DTR 참고

KMA DTR Sen slope 중앙값은 {dtr_kma['sen_slope_per_decade'].median():+.4f} °C/10년이며
증가 방향 {int(dtr_kma['sen_slope_per_decade'].gt(0).sum())}개, 감소 방향
{int(dtr_kma['sen_slope_per_decade'].lt(0).sum())}개다.

### Dominant warming season

정확한 동률은 DJF→MAM→JJA→SON 고정 순서로 처리했다.

{_markdown_table(dominant_counts, ['season','station_count'], 4)}
"""


def save_spatial_report(markdown: str, output_dir: Path) -> tuple[Path, Path]:
    """공간분석 Markdown과 동일 내용의 portable HTML을 저장한다."""

    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "nationwide_spatial_climate_analysis_report.md"
    html_path = output_dir / "nationwide_spatial_climate_analysis_report.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    try:
        import markdown as markdown_library

        body = markdown_library.markdown(markdown, extensions=["tables"])
    except ImportError:
        body = f"<pre>{escape(markdown)}</pre>"
    html = f"""<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">
<title>Nationwide Spatial Climate Pattern Analysis</title><style>
body{{font-family:Arial,sans-serif;max-width:1120px;margin:2rem auto;line-height:1.6;color:#172033}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}th,td{{border:1px solid #d7dce5;padding:.4rem;text-align:right}}
th:first-child,td:first-child{{text-align:left}}h1,h2{{color:#143d66}}</style></head><body>{body}</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    return html_path, markdown_path
