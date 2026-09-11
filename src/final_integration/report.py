"""Generate a portable report and lightweight Markdown from one fact-bound content model."""
from __future__ import annotations

import base64
from html import escape
import json
from pathlib import Path
import re
import shutil

import pandas as pd

from .content import (ATTRIBUTION, CAUTION, ENGLISH_TITLE, HIGHLIGHTS, LIMITATIONS, METHODS,
                      OFFICIAL_LINKS, QUESTIONS, RULES, TITLE, format_value, plain)
from .facts import FINAL, values

REPORT_STEM='NASA_POWER_KMA_Korea_Climate_Final_Report'


def write_text(path: Path, text: str) -> None:
    """Write a generated artifact, leaving identical content and its mtime untouched."""
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.is_file() or path.read_text(encoding='utf-8')!=text:
        path.write_text(text,encoding='utf-8')


def table_md(frame: pd.DataFrame) -> str:
    """Render a small Markdown table without adding a tabulate dependency."""
    def cell(value: object) -> str:
        return str(value).replace('|','\\|').replace('\n',' ')
    rows=['| '+' | '.join(map(cell,frame.columns))+' |','| '+' | '.join(['---']*len(frame.columns))+' |']
    rows.extend('| '+' | '.join(map(cell,row))+' |' for row in frame.itertuples(index=False,name=None))
    return '\n'.join(rows)


def research_tables(facts: pd.DataFrame, evidence: pd.DataFrame) -> list[tuple[str,pd.DataFrame]]:
    """Create nine concise result tables exclusively by selecting fact IDs."""
    v=values(facts)
    def label(row: pd.Series) -> str:
        """Explain source dimensions in prose while retaining the exact machine fact ID."""
        metadata=json.loads(row.notes);filters=metadata.get('filters',{})
        dimensions=' · '.join(str(filters[k]) for k in ('source','metric','outcome','variable','representation','season','threshold','numerical_class') if k in filters)
        names={'sen_slope_per_decade':'Sen 기울기','median':'기울기 중앙값','positive_count':'증가 지점수',
               'significant_fdr':'FDR 유의 지점수','Moran_I':'Moran I','permutation_p':'순열 p',
               'n_spatial_units':'공간 단위 수','bias':'Bias','mae':'MAE','rmse':'RMSE','pearson_r':'Pearson r',
               'spearman_rho':'Spearman rho','n_pairs':'유효 일별 pair 수','hc3_p':'HC3 p',
               'median_difference':'해안−내륙 중앙값 차이','coastal_n':'해안 지점수','inland_n':'내륙 지점수',
               'tmin_minus_tmax':'TMIN−TMAX 기울기 차이','tier_a_count':'Tier A 수','tier_b_count':'Tier B 수',
               'station_count':'공통기간 지점수','unique_NASA_grid_count':'NASA 고유 격자 수',
               'analysis_period':'분석기간','normal_period':'Climate Normal'}
        text=names.get(row.metric,row.metric.replace('_',' '))
        if row.fact_id=='inventory_n':text='공식 ASOS inventory'
        if row.fact_id=='grid_n':text='공통기간 NASA 고유 격자 수'
        if row.fact_id=='long_grid_n':text='고정 Tier A NASA 고유 격자 수'
        if metadata.get('operation')=='count_rows':text+=' · 행 수'
        if metadata.get('operation')=='median':text+=' · 지점 중앙값'
        if metadata.get('operation')=='positive_count':text+=' · 양수 지점수'
        if metadata.get('operation')=='negative_count':text+=' · 음수 지점수'
        return (dimensions+' · ' if dimensions else '')+text
    def get(ids: list[str]) -> pd.DataFrame:
        subset=facts.set_index('fact_id').loc[ids].reset_index()
        subset['value']=subset.fact_id.map(lambda x:format_value(v[x]))
        subset['지표']=subset.apply(label,axis=1)
        return subset[['지표','value','unit','analysis_period','fact_id']].rename(columns={'value':'값 (표시 반올림)','unit':'단위','analysis_period':'분석기간'})
    tables=[
        ('자료와 분석범위',get(['inventory_n','tier_a','tier_b','common_n','grid_n','long_grid_n','long_period','common_period','normal'])),
        ('공통기간 기온추세: 지점 중앙값',get([f'common_{s}_{m}_{stat}' for s in ('KMA','NASA') for m in ('TAVG','TMAX','TMIN') for stat in ('median','positive','fdr')])),
        ('TMIN–TMAX·DTR·계절',get(['contrast_median','contrast_positive','common_KMA_dtr','common_KMA_dtr_negative']+[f'common_KMA_{s}' for s in ('DJF','MAM','JJA','SON')])),
        ('NASA–KMA 일별 validation: 지점 지표 중앙값',get([f'validation_{m}_{c}' for m in ('TAVG','TMAX','TMIN') for c in ('bias','mae','rmse','pearson_r','spearman_rho','n_pairs')])),
        ('공간구조: 대표 directed KNN',get([f'spatial_{var}_{rep}_{col}' for var,rep in [('kma_tavg_sen_slope','STATION_LINKED'),('tavg_bias','STATION_LINKED'),('tavg_rmse','STATION_LINKED'),('nasa_tavg_sen_slope','STATION_LINKED'),('nasa_tavg_sen_slope','UNIQUE_GRID')] for col in ('Moran_I','permutation_p','n_spatial_units')])),
        ('고정 Tier A 시작기간별 TAVG·고온 proxy',get([f'window_{w["start_year"]}_KMA_TAVG_median' for w in v['windows']]+[f'threshold_{w["start_year"]}_KMA_{m}_median' for w in v['windows'] for m in ('TMAX_GE_33','TMIN_GE_25')])),
        ('해안 연관과 통제모형: 서로 다른 추론 범위',get([f'coast_{x}_spearman_rho' for x in ('kma_tavg_sen_slope','tavg_bias','tavg_rmse')]+[f'model_{x}_hc3_p' for x in ('kma_tavg_sen_slope','tavg_bias','tavg_rmse')]+[x for x in v if x.startswith('model_count_')])),
        ('증거 등급: 강건성과 민감성',evidence[['conclusion_id','statement','final_evidence_class']]),
        ('해안/내륙과 오차의 기간 안정성',get([f'coast_group_{x}_{c}' for x in ('tavg_bias','tavg_rmse') for c in ('median_difference','fdr_q','coastal_n','inland_n')]+[f'period_coast_{x}_period_interpretation' for x in ('tavg_bias','tavg_rmse')]+[f'period_validation_{w["start_year"]}_TAVG_{c}' for w in v['windows'] for c in ('bias_median','rmse_median')])),
    ]
    return tables[:-2]+[tables[-1],tables[-2]]


def sections() -> list[tuple[str,list[str]]]:
    """Author the report's fifteen sections; quantitative claims use explicit fact tokens."""
    return [
        ('초록 / Abstract',[
            '본 연구는 장기 기온변화의 방향과 공간적 특성을 공공 지점관측 및 NASA 격자자료로 교차검증합니다. '
            '공식 ASOS inventory {{inventory_n}}개에서 선정된 Tier A {{tier_a}}개와 Tier B {{tier_b}}개를 '
            '장기 및 공통기간으로 구분했습니다. Sen slope, MK/FDR와 공간·기간 민감성 검토 결과, '
            '기온 상승 방향과 NASA–KMA 오차의 공간구조는 반복되지만 KMA 추세 군집과 기울기 크기는 조건에 민감했습니다. '
            '자료 대표성·표본·기간·검정방법을 함께 명시하는 재현 가능한 해석이 본 연구의 핵심입니다.',
            'This study compares long-term station temperature changes with NASA POWER gridded estimates. '
            'The common-period network comprises {{common_n}} ASOS stations linked to {{grid_n}} distinct NASA grids. '
            'Saved Sen slopes, rank-based tests, multiple-testing corrections and spatial sensitivity checks '
            'support consistent warming directions, while station-level clustering and trend magnitudes depend on analytical choices. '
            'Grid–station differences and coastal associations do not establish causal attribution. The contribution is an auditable '
            'integration of evidence, including non-significant findings and numerical model failures.']),
        ('Executive Summary',HIGHLIGHTS),
        ('연구 배경',['도시별 다운로드·정제·분석에서 출발하여 전국 관측망의 품질조건과 공통기간을 통제하는 플랫폼으로 확장했습니다. '
            '핵심 문제는 더 많은 유의한 결과를 찾는 것이 아니라, 동일 자료에서 무엇이 검증 조건을 바꿔도 남는지 분리하는 것입니다. '
            '최종 단계는 검증된 산출물의 통합이며 새로운 통계모형이나 자료를 추가하지 않습니다.']),
        ('연구 질문',QUESTIONS),
        ('데이터',[ATTRIBUTION,'ASOS inventory {{inventory_n}}, Tier A {{tier_a}}, Tier B {{tier_b}}, 공통기간 {{common_n}} 지점입니다. '
            '공통기간의 NASA 고유 격자는 {{grid_n}}개이고 고정 Tier A 기간 민감성의 격자는 {{long_grid_n}}개입니다. '
            '격자 수가 다른 표본을 혼합하지 않습니다. screening은 기간 충족·결측·연 completeness·이력을 반영하며 '
            '선택 편향이 없는 전국 대표표본임을 뜻하지 않습니다.']),
        ('분석기간',['장기 기간 {{long_period}}와 공통기간 {{common_period}}를 구분합니다. Climate Normal은 {{normal}}입니다. '
            '고정 Tier A의 시작연도 변경 비교와 Tier B를 합친 공통기간 비교는 서로 다른 실험입니다.']),
        ('방법론',[title+': '+body for title,body in METHODS]),
        ('주요 결과',HIGHLIGHTS+[
            '공통기간 KMA 계절별 TAVG 기울기 중앙값은 DJF {{common_KMA_DJF}}, MAM {{common_KMA_MAM}}, '
            'JJA {{common_KMA_JJA}}, SON {{common_KMA_SON}} °C/decade입니다. 겨울이 항상 가장 빠르다고 일반화할 수 없습니다.',
            '고온 proxy의 기울기·증가 지점수와 시작기간별 변화는 근거표에 보존했습니다. 일별 최고·최저기온으로 집계한 proxy를 '
            '공식 경보 기준으로 바꾸거나 높은 지역을 종합 위험 순위로 해석하지 않습니다.',
            '해안거리의 기존 TAVG 통제모형은 classical p={{model_kma_tavg_sen_slope_classical_p}}, '
            'HC3 p={{model_kma_tavg_sen_slope_hc3_p}}입니다. classical 유의성을 최종 강건 결론으로 올리지 않았습니다. '
            'RMSE HC3 p={{model_tavg_rmse_hc3_p}} 역시 단순 상관과 다른 해석을 요구합니다.']),
        ('강건한 결과와 민감한 결과',[RULES,
            '증거표의 ROBUST는 주장 자체의 적용 범위에 한정됩니다. TAVG 증가 방향, NASA 공간구조, '
            'Bias·RMSE 공간구조와 달리 TMIN/DTR는 지점 다수의 경향이고, 해안 연관은 인과효과가 아닙니다. '
            '민감한 KMA 군집·기간별 크기·통제모형 결과는 별도로 표시합니다.']),
        ('방법론적 검증',[
            '기존 단계 테스트를 유지하고 원본 결과의 SHA256 및 mtime을 보호합니다. 각 fact는 파일·영기준 행 또는 JSON key·열·'
            '선택조건·기술적 집계 연산까지 재생 검증합니다. 상위 manifest의 해시가 있는 CSV는 그 해시도 대조합니다.',
            '수치 검토에서는 안정 {{model_count_STABLE}}, 수치 불안정 {{model_count_NUMERICALLY_UNSTABLE}}, '
            '경계 근처 수렴 {{model_count_CONVERGED_NEAR_BOUNDARY}}, 실패 {{model_count_FAILED}} 조합이 기록됐습니다. '
            '이 조합들은 독립 표본이 아니며, 실패 결과를 숨기거나 유의한 specification만 선택하지 않습니다.',
            '실행별 전체 테스트·의존성·대시보드·보호파일 상태는 final_integration_manifest와 final_test_summary에서 '
            '확인합니다. 보고서 생성과 실제 QA 완료는 별도 상태로 기록합니다.']),
        ('연구 한계',LIMITATIONS),
        ('활용 가능성',['지역 기후자료의 탐색, 기관 간 자료 비교, 통계적 재현성 교육과 연구 포트폴리오에 사용할 수 있습니다. '
            '재난 경보, 개별 지점의 미래예측, 정책의 인과효과 판단에는 사용할 수 없습니다.']),
        ('결론',[HIGHLIGHTS[i] for i in (0,1,2,3,5)]+[
            '방법론적 교훈은 상승 방향의 일관성과 공간군집·변화량의 조건 의존성을 동시에 전달해야 한다는 것입니다. '
            '표준오차·격자 중복·분석기간의 점검은 결과를 약화시키는 부록이 아니라 결론의 범위를 정하는 핵심입니다.']),
        ('Reproducibility',['기존 분석 cache가 있는 환경에서 python scripts/build_final_integration.py를 실행하면 '
            '새 통계 추정 없이 이 보고서를 재생성합니다. 외부 요청은 실행 중 차단됩니다. '
            'HTML은 선택 PNG를 내장해 단독 열람할 수 있고 Markdown은 동봉된 assets 폴더가 필요합니다. '
            '공개 요약만 가진 환경은 Home·Reports와 보고서를 읽을 수 있지만 전체 분석의 재현 검증에는 원래 cache가 필요합니다. '
            '자세한 환경·실행·자료 정책은 docs/REPRODUCIBILITY.md에 있습니다.']),
        ('Appendix / 주요 산출물',[
            'final_research_fact_layer.csv: 전체 scalar provenance; final_research_fact_manifest.json: 출처 해시와 파일 수정시각(취득일 아님); '
            'final_evidence_matrix.csv: 주장별 검증 축; final_figure_registry.csv: 원본 그림과 선정 이유; '
            'final_test_summary.csv: 실제 실행 테스트 요약. Fact ID는 표와 문장 markup에서 연결됩니다.',
            ATTRIBUTION]),
    ]


def html_text(template: str, facts: pd.DataFrame) -> str:
    """Escape authored prose and attach machine-checkable fact spans."""
    lookup=values(facts)
    return re.sub(r'\{\{([A-Za-z0-9_]+)\}\}',lambda m:
        f'<span class="fact" data-fact="{m[1]}" title="fact: {m[1]}">{escape(format_value(lookup[m[1]]))}</span>',escape(template))


def html_table(table: pd.DataFrame) -> str:
    """Keep human-readable table labels and attach exact fact IDs to scalar value cells."""
    columns=[c for c in table if c!='fact_id']
    parts=['<table><thead><tr>'+''.join('<th scope="col">'+escape(c)+'</th>' for c in columns)+'</tr></thead><tbody>']
    for row in table.to_dict('records'):
        cells=[]
        for col in columns:
            text=escape(str(row[col]))
            if col=='값 (표시 반올림)' and 'fact_id' in row:
                fid=escape(row['fact_id']);text=f'<span class="fact" data-fact="{fid}" title="fact: {fid}">{text}</span>'
            cells.append('<td>'+text+'</td>')
        parts.append('<tr>'+''.join(cells)+'</tr>')
    return ''.join(parts)+'</tbody></table>'


def render_report(root: Path, facts: pd.DataFrame, ev: pd.DataFrame, registry: pd.DataFrame) -> dict:
    """Render shared sections, nine tables, and copied/embedded existing charts deterministically."""
    target=root/FINAL/'report'; target.mkdir(parents=True,exist_ok=True)
    tables=research_tables(facts,ev); parts=[]; md=[f'# {TITLE}',ENGLISH_TITLE]
    subtitle=plain('{{long_period}} 장기 관측과 {{common_period}} · {{common_n}}개 공통기간 관측소',facts)
    md.append(subtitle)
    table_slots={5:[0],8:[1,2,3,4,5,6,7],9:[8]}
    for number,(title,paragraphs) in enumerate(sections(),1):
        block=[f'<section id="section-{number}"><h2>{number}. {escape(title)}</h2>']
        md.append(f'## {number}. {title}')
        for paragraph in paragraphs:
            block.append('<p>'+html_text(paragraph,facts)+'</p>');md.append(plain(paragraph,facts))
        for idx in table_slots.get(number,[]):
            name,table=tables[idx]
            block.append(f'<h3>Table {idx+1}. {escape(name)}</h3><div class="table-wrap">'+html_table(table)+'</div>')
            md.extend([f'### Table {idx+1}. {name}',table_md(table)])
        if number==8:
            for figure in registry.to_dict('records'):
                source=root/figure['source_path']; data=source.read_bytes()
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Not a PNG: '+source.name)
                dest=target/'assets'/source.name;dest.parent.mkdir(exist_ok=True)
                if not dest.exists() or dest.read_bytes()!=data:shutil.copyfile(source,dest)
                caption=re.sub(r'\s*<!-- fact:.*? -->','',figure['caption'])
                block.append(f'<figure id="{figure["figure_id"]}"><img alt="{escape(figure["title"])}" '
                    f'src="data:image/png;base64,{base64.b64encode(data).decode()}"><figcaption>'
                    f'{figure["figure_id"]}. {escape(figure["title"])} — {escape(caption)}</figcaption></figure>')
                md.extend([f'![{figure["title"]}](assets/{source.name})',f'{figure["figure_id"]}. {figure["caption"]}'])
        if number==15:
            block.append('<ul>'+''.join(f'<li><a href="{url}">{escape(name)}</a></li>' for name,url in OFFICIAL_LINKS.items())+'</ul>')
            md.extend(f'[{name}]({url})' for name,url in OFFICIAL_LINKS.items())
        block.append('</section>');parts.append('\n'.join(block))
    toc=''.join(f'<li><a href="#section-{i}">{escape(title)}</a></li>' for i,(title,_) in enumerate(sections(),1))
    html='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    html+=f'<title>{escape(TITLE)}</title><style>body{{font-family:system-ui,sans-serif;color:#163047;background:#f4f7f9;margin:0;line-height:1.75}}'
    html+='main{max-width:1080px;margin:auto;padding:48px 28px;background:white}header{border-top:8px solid #168b87;padding-top:22px}'
    html+='h1{font-size:2rem;line-height:1.4}h1,h2,h3,p{word-break:keep-all;overflow-wrap:break-word}h2{margin-top:48px;border-bottom:2px solid #d8e9ed;padding-bottom:8px}h3{font-size:1.1rem}'
    html+='p{max-width:95ch}.warning{padding:18px;background:#fff3d9}.fact{border-bottom:1px dotted #168b87}'
    html+='nav ol{columns:2}a{color:#087b79}img{width:100%;height:auto}figure{margin:32px 0}figcaption{font-size:.9rem;color:#526574}'
    html+='table{border-collapse:collapse;font-size:.78rem;width:100%}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left;overflow-wrap:anywhere}'
    html+='.table-wrap{overflow:auto}th{background:#edf5f5}@media print{body{background:white}main{padding:0}figure, tr{break-inside:avoid}nav{display:none}}'
    html+='@media(max-width:600px){main{padding:22px 14px}nav ol{columns:1}h1{font-size:1.55rem}}</style></head><body><main><header>'
    html+=f'<p>RESEARCH SYNTHESIS · READ ONLY</p><h1>{escape(TITLE)}</h1><p>{escape(ENGLISH_TITLE)}</p>'
    html+=f'<p>{html_text("{{long_period}} / {{common_period}} · {{common_n}} common-period stations",facts)}</p></header>'
    html+=f'<p class="warning">{escape(CAUTION)}</p><nav aria-label="목차"><ol>{toc}</ol></nav>'+''.join(parts)+'</main></body></html>'
    write_text(target/f'{REPORT_STEM}.html',html)
    write_text(target/f'{REPORT_STEM}.md','\n\n'.join(md)+'\n')
    executive='# Executive Summary\n\n'+TITLE+'\n\n## 목적과 범위\n\n'+plain(sections()[0][1][0],facts)
    executive+='\n\n## 핵심 결과\n\n'+'\n\n'.join('- '+plain(x,facts) for x in HIGHLIGHTS)
    executive+='\n\n## 방법과 근거\n\n저장된 Sen/MK/BH-FDR, validation, 공간가중치·격자 공유·기간 민감성 결과를 fact layer와 연결했습니다. '
    executive+=RULES+'\n\n## 한계와 활용\n\n'+CAUTION+' 연구 탐색·자료 비교·재현성 교육에 활용하되 인과귀속·미래예측에는 사용하지 않습니다.\n'
    write_text(root/FINAL/'EXECUTIVE_SUMMARY.md',executive)
    return {'sections':len(sections()),'figures':len(registry),'tables':len(tables),
            'html':(FINAL/'report'/f'{REPORT_STEM}.html').as_posix(),
            'markdown':(FINAL/'report'/f'{REPORT_STEM}.md').as_posix()}
