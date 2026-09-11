"""Deterministic Stage-13 Markdown and self-contained HTML reports."""
from __future__ import annotations

from html import escape
import json
import pandas as pd
from src.config import PROJECT_ROOT

NARRATIVES = {
    'ROBUST_POSITIVE':'여러 공간가중치 정의에서 양의 공간 자기상관이 반복 확인됐습니다(운영상 75% 기준).',
    'WEIGHT_SENSITIVE':'유의성이 공간가중치 정의에 따라 달라지는 탐색적 결과입니다.',
    'ROBUST_NON_SIGNIFICANT':'검토 설정의 75% 이상에서 비유의입니다. 효과가 없다는 증명은 아닙니다.',
    'INCONSISTENT_DIRECTION':'가중치에 따라 Moran I의 부호가 바뀝니다. 유의성 및 I 크기도 함께 보십시오.',
}


def markdown_table(frame: pd.DataFrame) -> str:
    """Render compact escaped Markdown without optional tabulate dependency."""
    clean = frame.copy()
    for column in clean:
        clean[column] = clean[column].map(lambda v: f'{v:.6g}' if isinstance(v,float) else str(v))
    clean = clean.astype(str).replace({'nan':'—'})
    rows=[' | '.join(clean.columns), ' | '.join(['---']*len(clean.columns))]
    rows.extend(' | '.join(str(v).replace('|','/').replace('\n',' ') for v in row) for row in clean.itertuples(index=False,name=None))
    return '\n'.join('| '+row+' |' for row in rows)


def report_sections(tables: dict, coastal: dict, manifest: dict) -> list[tuple[str,str,pd.DataFrame | None]]:
    """Create all 17 requested sections using actual results, not prewritten conclusions."""
    summary=tables['summary']; weights=tables['weights']; local=tables['local']
    coast=manifest['coastline']
    sections=[('1. Executive Summary',f"Final Tier A {manifest['station_count']} stations, {len(manifest['weight_configurations'])} weight configurations. NASA/KMA API 호출 0. Stable VERSION 1.0.0. Coastal available={coast['available']}.",summary),
              ('2. 왜 robustness 분석이 필요한가','단일 가중치의 유의성으로 일반화하지 않습니다. 12단계 baseline과 같은 seed/검정으로 재검증합니다.',None),
              ('3. Spatial weight definitions','Directed KNN k=3/4/5/6; union-adjacency symmetric KNN k=3/4/5/6. Symmetric adjacency라도 row normalization 후 수치 행렬은 비대칭일 수 있습니다. Distance band는 MST 전체 연결 최소거리 ×1/1.1/1.25. Inverse distance는 cutoff 없이 p=1/2, self/zero distance 제외. 모두 row-standardized.',tables['network'])]
    for title,variables in [('4. KMA TAVG robustness',['kma_tavg_sen_slope']),('5. TMAX / TMIN robustness',['kma_tmax_sen_slope','kma_tmin_sen_slope']),
                            ('6. Threshold proxy robustness',['days_tmax_ge_33_kma_slope','days_tmin_ge_25_kma_slope']),('7. NASA-KMA Bias/RMSE robustness',['tavg_bias','tavg_rmse'])]:
        sub=summary[summary.variable.isin(variables)]
        prose='\n'.join(f'{r.variable}: {NARRATIVES[r.robustness_class]}' for r in sub.itertuples())
        sections.append((title,prose,weights[weights.variable.isin(variables)]))
    stable=local[local.stable_local_pattern].station_id.nunique()
    local_counts=local.groupby(['weight_variant','cluster_type_fdr']).size().reset_index(name='n')
    sections.append(('8. Local Moran robustness',f'모든 6개 주요 설정에서 같은 FDR 유의 군집을 유지한 station: {stable}. 각 설정별 45개 지점에 BH-FDR 적용. 한 설정만 유의하면 stable cluster가 아닙니다. 조건부 permutation은 focal 값을 고정하며 |local I| 꼬리검정을 사용합니다.',local_counts))
    inje=local[local.station_name.eq('인제')][['station_id','station_name','weight_variant','local_p','local_fdr_q','cluster_type_fdr','stable_local_pattern']]
    sections.append(('8a. 인제 재검증','이름은 조회 목적으로만 사용하며 결론은 재계산 결과입니다.',inje))
    coast_fields={k:v for k,v in coast.items() if k not in ('source_crs_wkt','component_hashes')}
    sections.append(('9. Official coastline data',json.dumps(coast_fields,ensure_ascii=False,indent=2),None))
    if coastal:
        d=coastal['station_coastal_distance'].distance_to_coast_km
        main=coastal['coastal_inland_comparison']
        threshold=main.threshold_km.iloc[0]
        association=coastal['coastal_continuous_associations'].set_index('variable')
        adjusted=coastal['coastal_multivariable_models']
        contrast_notes=[]
        if 'term' in adjusted:
            for row in adjusted[adjusted.term.eq('distance_to_coast_km')].itertuples():
                simple=association.loc[row.variable]
                changed=(simple.regression_p < .05) != (row.p_value < .05)
                contrast_notes.append(f'{row.variable}: 단변량 OLS p={simple.regression_p:.6g}, 위도·고도 포함 OLS p={row.p_value:.6g}; '+
                                      ('유의성 판단이 달라집니다.' if changed else '유의성 판단이 같습니다.'))
        sections.extend([
            ('10. Station coastal distance',f'Min {d.min():.6f}, median {d.median():.6f}, max {d.max():.6f} km. 전체 공식 선에 대한 최단거리; 섬 해안선 유지. 지도 단순화는 표시 전용입니다.',coastal['station_coastal_distance']),
            ('11. Coastal/Inland comparison',f'Main {threshold:g} km, Coastal {int(main.coastal_n.iloc[0])}, Inland {int(main.inland_n.iloc[0])}. 결과 p값을 보지 않고 30 km 우선 및 최소 집단 n=5 규칙으로 선정. MWU는 중앙값 자체가 아니라 분포를 검정합니다. 양의 효과크기/차이는 Coastal이 더 큼을 뜻합니다.',main),
            ('12. Threshold sensitivity','20/30/50 km 각각 9개 지표에 BH-FDR. 전체 27개 검정의 통합 FDR은 아니므로 threshold를 골라 유의성을 주장하지 않습니다.',coastal['coastal_threshold_sensitivity']),
            ('13. Continuous coastal-distance associations','이분화보다 연속거리 관계를 우선합니다. Pearson/Spearman p 및 단순 OLS CI는 지점 독립을 가정한 탐색적 값이며 공간 의존성을 보정하지 않았습니다.',coastal['coastal_continuous_associations']),
            ('14. Multivariable exploratory analysis','사전지정: TAVG/TMIN/Bias ~ 해안거리 + 위도 + 고도. 계수는 인과적 해안효과가 아닙니다.\n'+'\n'.join(contrast_notes),coastal['coastal_multivariable_models']),
            ('14a. Group composition','위도·고도·지역 구성이 다를 수 있어 집단 차이를 해안의 효과로 단정하지 않습니다.',coastal['coastal_group_characteristics'])])
    else:
        for title in ('10. Station coastal distance','11. Coastal/Inland comparison','12. Threshold sensitivity','13. Continuous coastal-distance associations','14. Multivariable exploratory analysis'):
            sections.append((title,'공식 coastline geometry가 검증되지 않아 Coastal/Inland 분석을 표시할 수 없습니다.',None))
    sections.extend([
        ('15. Data quality','Final A source CSV와 Stage-12 station set 일치, 좌표·고도 일치, missing/inf metric은 임의 대체 없이 중단. 가중치: diagonal 0, nonnegative finite, row sum 1, isolates 0. 입력·결과 SHA256은 manifest에 기록.',None),
        ('16. Methodological limitations','운영상 분류 기준은 학계 표준이 아닙니다. 설정들은 서로 독립이 아니며 동등한 한 표씩 집계합니다. Global p는 변수·가중치 전체에 다중검정 보정되지 않았고 유의 설정을 탐색하는 목적입니다. Local FDR은 설정별 family입니다. Sen slope 추정불확실성, 시계열/공간 의존성, 지형, 해안의 방향, 지역 구성, 대표성 및 관측소 이력을 모두 해결한 분석이 아닙니다. 2025 기준 정적 해안선을 1981~2025 특성에 대응시키므로 과거 해안 변화는 반영하지 않습니다. 행정경계/도시이름 분류, 공간보간, 예측, 인과 주장을 하지 않습니다.',None),
        ('17. Conclusions','\n'.join(f'{r.variable}: {r.robustness_class} — {NARRATIVES[r.robustness_class]}' for r in summary.itertuples()),None)])
    return sections


def write_reports(tables: dict, coastal: dict, manifest: dict) -> list[str]:
    """Write deterministic Markdown + HTML only inside Stage-13 report directory."""
    sections=report_sections(tables,coastal,manifest)
    title='전국 공간통계 강건성 및 공식 해안선 기반 해안성 분석 (Experimental Stage 13)'
    markdown=[f'# {title}\n']
    html=[f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{title}</title><style>body{{font:16px/1.65 system-ui;max-width:1300px;margin:40px auto;padding:0 24px;color:#243445}}h1,h2{{color:#14576b}}table{{border-collapse:collapse;font-size:12px;white-space:nowrap}}td,th{{padding:6px;border:1px solid #ccd5da}}.table{{overflow:auto}}p{{white-space:pre-wrap}}img{{max-width:100%}}</style><body><h1>{title}</h1>']
    for heading,prose,frame in sections:
        markdown.extend([f'\n## {heading}\n',prose+'\n'])
        html.extend([f'<h2>{escape(heading)}</h2><p>{escape(prose)}</p>'])
        if frame is not None:
            markdown.append(markdown_table(frame)+'\n')
            html.append('<div class="table">'+frame.to_html(index=False,escape=True,float_format=lambda x:f'{x:.6g}')+'</div>')
    html.append('</body></html>')
    directory=PROJECT_ROOT/'output/reports/robustness'; directory.mkdir(parents=True,exist_ok=True)
    paths=[]
    for ext,text in [('md','\n'.join(markdown)),('html','\n'.join(html))]:
        path=directory/f'nationwide_spatial_robustness_coastal_report.{ext}'
        path.write_text(text,encoding='utf-8'); paths.append(path.relative_to(PROJECT_ROOT).as_posix())
    return paths
