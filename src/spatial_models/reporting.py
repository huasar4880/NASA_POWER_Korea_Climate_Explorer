"""Saved-result narratives and deterministic Stage-14 reports."""
from __future__ import annotations

from html import escape
from pathlib import Path
import pandas as pd
from src.spatial.robustness_reporting import markdown_table
from src.spatial_models.data import OUTCOMES, PREDICTORS
from src.spatial_models.visualization import baseline_rows, LABELS

LIMITATIONS = ('관측소 수가 작아 coefficient uncertainty, model instability, influential station 및 '
               'asymptotic spatial test 한계가 있습니다. Sen slope 자체의 추정오차를 모형화하지 않았습니다. '
               'SAR 계수는 직접/간접 인과효과가 아니며 lambda는 물리적 전파효과가 아닙니다. '
               'Bias/RMSE는 격자와 지점의 차이이지 특정 지역에서 NASA가 맞거나 틀리다는 판정이 아닙니다. '
               '여러 model/weight 검토는 탐색적이며 비유의는 효과 부재의 증명이 아닙니다.')


def narrative(sample: pd.DataFrame) -> str:
    """Describe observed inference changes without assuming spatial models are superior."""
    rows = sample.set_index('model_type')
    if not rows.converged.all():
        return '실패 또는 불안정 모델이 있어 완전한 강건성 결론을 내릴 수 없습니다.'
    ols, sem = rows.loc['OLS'], rows.loc['SEM']
    text = ('OLS에서 유의했지만 SEM에서는 유의성이 유지되지 않아 모델 선택에 민감합니다.'
            if ols.p_value < .05 <= sem.p_value else
            'OLS/SAR/SEM의 방향·유의성을 아래 수치와 가중치 민감도 표에서 함께 확인합니다.')
    if ols.p_value < .05 <= rows.loc['OLS-HC3','p_value']:
        text += f" OLS-HC3 p={rows.loc['OLS-HC3','p_value']:.6g}로 비유의이므로 이분산 강건 추론까지 유의성이 유지된다고 할 수 없습니다."
    elif rows.loc[['OLS','OLS-HC3','SAR','SEM'],'p_value'].lt(.05).all():
        text += ' 기본 가중치의 OLS/HC3/SAR/SEM에서 해안거리의 유의성은 유지됩니다. 전체 가중치 강건성은 실패 및 민감도 표와 별도로 판단합니다.'
    if ols.residual_moran_p >= .05:
        text += ' 기본 가중치에서 OLS 잔차의 유의한 공간 자기상관이 확인되지 않아 공간보정 필요성은 약합니다.'
    elif rows.loc[['SAR','SEM'], 'residual_moran_p'].ge(.05).all():
        text += ' 공간모형 적용 후 기본 가중치의 잔차 Moran은 비유의입니다.'
    else:
        text += ' 일부 공간모형에도 유의한 잔차구조가 남아 있습니다.'
    return text


def sections(tables: dict, manifest: dict) -> list[tuple[str,str,pd.DataFrame | None]]:
    """Build all requested report sections from stored results only."""
    base = baseline_rows(tables['spatial_model_summary'])
    columns = ['outcome','model_type','coefficient','std_error','p_value','fdr_q','rho','lambda','AIC','BIC','residual_moran_I','residual_moran_p']
    result = [
        ('1. Executive Summary', f"Final Tier A {manifest['station_count']} stations. NASA/KMA API 0. Stable 1.0.0 보존. 독립 적합 시도 36개(main 27 + 경도 9), 표준화는 정확한 재매개화; LOO는 outcome마다 n회. 실패/불안정 {manifest.get('failed_models',0)}개. 실패가 있으면 전체 model/weight 강건성 검증 완료로 표시하지 않습니다. ROBUST_SIGNIFICANT 운영분류는 OLS classical/SAR/SEM만의 12셀 기준으로 HC3 강건성 보장을 뜻하지 않습니다.", tables['spatial_model_coefficient_stability']),
        ('2. Why spatial adjustment?', '13단계 raw outcome Moran과 이번 OLS residual Moran을 구분합니다. 원변수의 군집이 곧 회귀잔차의 군집은 아닙니다.', tables.get('spatial_model_prior_robustness')),
        ('3. Data / station', '12·13단계 저장 CSV 및 Final Tier A만 사용. 결측 predictor/outcome은 자동 대체·삭제하지 않고 중단.', tables['spatial_modeling_master']),
        ('4. Predictor definitions', 'Main: coast km, latitude degree, elevation m. Longitude degree는 기본 가중치 sensitivity만. Predictor z=(x-mean)/population SD; outcome은 원단위. TAVG slope °C/10년, Bias/RMSE °C.', tables['spatial_model_scaling']),
        ('5. OLS baseline', 'Classical t CI와 HC3 t CI를 분리합니다. BP는 studentized Koenker 버전, Cook D>4/n은 자동제외 없는 참고 flag.', tables['spatial_ols_diagnostics']),
        ('6. Residual Moran', '13단계 outcome별 seed·999 permutation·E[I] 중심 양측 검정을 재사용. 회귀잔차는 교환가능하지 않을 수 있어 재적합 없는 permutation p는 탐색적 진단입니다. SEM은 filtered innovation과 structural residual을 별도 저장합니다.', base[columns]),
        ('7. Spatial Lag', 'y=rho Wy+X beta+epsilon. 공간적 outcome 의존성을 포함하며 인과적 spillover가 아닙니다. Gaussian ML의 점근적 z 추론.', base[base.model_type.eq('SAR')][columns]),
        ('8. Spatial Error', 'y=X beta+u, u=lambda Wu+epsilon. Moran 비교에는 epsilon=(I-lambda W)u 사용. u의 Moran도 원표에 저장. lambda를 물리적 확산으로 해석하지 않습니다.', base[base.model_type.eq('SEM')][columns]),
    ]
    for number, outcome in enumerate(OUTCOMES, start=9):
        sample = base[base.outcome.eq(outcome)]
        result.append((f'{number}. {LABELS[outcome]} results', narrative(sample), sample[columns]))
    result.extend([
        ('12. Weight sensitivity', '동일 순서·행표준화 4개 가중치. 분류 우선순위: incomplete→부호불일치→weight민감→model민감→75%유의→방향유지. 중첩 flag를 함께 읽습니다. 유의 비율은 OLS 반복 4개를 포함한 12 model×weight 셀의 운영지표입니다.', tables['spatial_model_weight_sensitivity']),
        ('13. LOO sensitivity', '각 station 하나씩 일시 제외해 OLS 재적합. full sample은 어떤 station도 삭제하지 않습니다.', tables['spatial_model_loo_summary']),
        ('14. Residual maps', '아래 링크는 baseline OLS/SAR/SEM의 세 outcome innovation point map입니다. 같은 outcome은 모형 간 색 범위 동일; 공간보간 없음. Plotly CDN은 표시용 인터넷이 필요합니다.', None),
        ('15. Model selection considerations', 'OLS→HC3→residual Moran→LM→coefficient stability→AIC/BIC→post residual→weights 순으로 검토. Gaussian full likelihood IC는 sigma²까지 포함해 재계산(OLS main k=5; SAR/SEM k=6); library native IC는 별도 보관. R²와 pseudo-R²는 혼합 순위화하지 않습니다. LM robust는 HC3가 아니라 대안 공간모형에 대한 보정입니다.', tables['spatial_model_outcome_comparison']),
        ('15a. LM / VIF / influence', 'LM 결과 하나로 모델을 고르지 않습니다.', tables['spatial_lm_diagnostics']),
        ('15b. VIF', 'VIF>5는 flag; 변수 자동 제거 없음.', tables['spatial_model_vif']),
        ('15c. Influential stations', 'Cook D>4/n; 원자료 및 main station set은 유지.', tables['spatial_model_influence_diagnostics'].query("specification == 'main' and influential")),
        ('15d. Longitude sensitivity', '4 predictors, baseline weight에서만 수행. 작은 n과 다중공선성에 유의.', tables['spatial_model_summary'].query("specification == 'longitude_sensitivity' and scale == 'original' and predictor == 'distance_to_coast_km'")[columns]),
        ('16. Limitations', LIMITATIONS + ' Primary BH-FDR은 baseline 원단위 coast의 3 outcome만 OLS/HC3/SAR/SEM별로 별도 적용합니다. 나머지는 미보정 탐색적 p입니다. 정적 해안선, 관측소 대표성 및 누락된 공변량의 한계도 남습니다.', tables['spatial_model_failures']),
        ('17. Conclusions', '\n'.join(LABELS[y]+': '+narrative(base[base.outcome.eq(y)]) for y in OUTCOMES), tables['spatial_model_coefficient_stability']),
    ])
    return result


def write_reports(tables: dict, manifest: dict, root: Path) -> list[str]:
    """Write only Stage-14 reports; reports depend on saved, rounded-identically CSV values."""
    title = 'Spatial Dependence–Adjusted Modeling · Experimental Stage 14'
    md = [f'# {title}\n']
    html = [f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{title}</title><style>body{{font:16px/1.65 system-ui;max-width:1250px;margin:40px auto;padding:0 24px;color:#253749}}h1,h2{{color:#146077}}.table{{overflow:auto}}table{{border-collapse:collapse;white-space:nowrap;font-size:12px}}td,th{{border:1px solid #ccd5da;padding:6px}}p{{white-space:pre-wrap}}img{{max-width:100%}}</style><body><h1>{title}</h1>']
    for heading, prose, frame in sections(tables, manifest):
        md.extend([f'\n## {heading}\n', prose+'\n'])
        html.append(f'<h2>{escape(heading)}</h2><p>{escape(prose)}</p>')
        if frame is not None:
            md.append(markdown_table(frame)+'\n')
            html.append('<div class="table">'+frame.to_html(index=False, escape=True, float_format=lambda v:f'{v:.6g}')+'</div>')
    for name in manifest.get('generated_charts', []):
        link = '../../charts/spatial_models/' + Path(name).name
        md.append(f'\n[{Path(name).name}]({link})\n')
        html.append(f'<p><a href="{escape(link)}">{escape(Path(name).name)}</a></p>')
        if name.endswith('.png'):
            html.append(f'<img src="{escape(link)}" alt="{escape(Path(name).stem)}">')
    html.append('</body></html>')
    folder = root / 'output/reports/spatial_models'
    folder.mkdir(parents=True, exist_ok=True)
    result = []
    for ext, text in [('md','\n'.join(md)), ('html','\n'.join(html))]:
        path = folder / f'spatial_dependence_adjusted_modeling_report.{ext}'
        path.write_text(text, encoding='utf-8')
        result.append(path.relative_to(root).as_posix())
    return result
