"""Deterministic numerical-review charts and a separate technical report."""
from __future__ import annotations
from html import escape
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.spatial.robustness_reporting import markdown_table

CHARTS=['weight_eigenvalue_summary.png','inverse_distance_weight_distribution.png',
        'parameter_boundary_distance.png','inverse_distance_model_stability.png',
        'likelihood_profile_bias_sem.png','likelihood_profile_rmse_sar.png','likelihood_profile_rmse_sem.png']
SHORT={'directed_knn_k4':'Directed KNN4','symmetric_knn_k4':'Symmetric KNN4','distance_band_x1':'Distance band',
       'inverse_distance_p1_row':'IDW1 row','inverse_distance_p1_raw':'IDW1 raw',
       'inverse_distance_p1_cutoff_row':'IDW1 cutoff row','inverse_distance_p2_row':'IDW2 row',
       'inverse_distance_p2_raw':'IDW2 raw','inverse_distance_p2_cutoff_row':'IDW2 cutoff row'}


def create_charts(tables: dict, inventory: dict, root: Path) -> list[str]:
    """Save seven scientific diagnostics; profiles are not alternative fitted estimates."""
    directory=root/'output/charts/spatial_models_numerical';directory.mkdir(parents=True,exist_ok=True)
    paths=[]

    def save(fig: plt.Figure,name: str) -> None:
        """Finalize deterministic PNG layout."""
        fig.tight_layout();path=directory/name;fig.savefig(path,dpi=160,facecolor='white');plt.close(fig)
        paths.append(path.relative_to(root).as_posix())

    diag=tables['inverse_distance_weight_diagnostics']
    fig,ax=plt.subplots(figsize=(10,6))
    for i,row in enumerate(diag.itertuples()):
        ax.plot([row.eigenvalue_min_real_part,row.eigenvalue_max_real_part],[i,i],color='#26758c',linewidth=3)
        ax.scatter(row.spectral_radius,i,color='#d17a21',marker='x',s=60)
    ax.set_yticks(range(len(diag)),[SHORT[k] for k in diag.weight_type]);ax.axvline(0,color='#999999',linewidth=1)
    ax.set_xlabel('Eigenvalue real-part range; orange x = spectral radius')
    ax.set_title('Weight spectra: raw scale and row standardization are distinct')
    save(fig,CHARTS[0])
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    for ax,variant in zip(axes,['row','raw']):
        for power,color in [(1,'#26758c'),(2,'#d17a21')]:
            w=inventory[f'inverse_distance_p{power}_{variant}']['matrix'];values=w[w>0]
            ax.hist(np.log10(values),bins=30,alpha=.55,label=f'p={power}',color=color)
        ax.set_title(f'IDW {variant}: nonzero directed entries');ax.set_xlabel('log10(weight)');ax.set_ylabel('Entry count');ax.legend()
    save(fig,CHARTS[1])
    boundary=tables['spatial_boundary_diagnostics']
    boundary=boundary[boundary.weight_type.eq('inverse_distance_p1_row')]
    fig,ax=plt.subplots(figsize=(10,4.5))
    names=[r.outcome.replace('kma_tavg_sen_slope','TAVG').replace('tavg_','').upper()+' '+r.model_type for r in boundary.itertuples()]
    x=np.arange(len(boundary))
    ax.scatter(x-.12,boundary.relative_boundary_distance,label='Nonsingularity interval',color='#26758c')
    ax.scatter(x+.12,boundary.solver_relative_boundary_distance,label='Fixed solver interval',color='#d17a21')
    ax.axhline(.01,color='#26758c',linestyle=':',label='1% nonsingularity rule')
    ax.axhline(.05,color='#d17a21',linestyle=':',label='5% solver rule')
    ax.set_yscale('log');ax.set_xticks(x,names,rotation=20);ax.set_ylabel('Relative nearest-boundary distance (log scale)')
    ax.set_title('IDW1: solver boundary is NOT the matrix singularity boundary');ax.legend(fontsize=8)
    save(fig,CHARTS[2])
    stability=tables['spatial_model_numerical_stability']
    classes=['STABLE','CONVERGED_NEAR_BOUNDARY','NUMERICALLY_UNSTABLE','FAILED','NOT_SUPPORTED']
    counts=stability.groupby(['weight_type','numerical_class']).size().unstack(fill_value=0).reindex(diag.weight_type).reindex(columns=classes,fill_value=0)
    fig,ax=plt.subplots(figsize=(11,6));left=np.zeros(len(counts))
    for label,color in zip(classes,['#33845a','#e1b33b','#d17a21','#ab4050','#888888']):
        values=counts[label].to_numpy();ax.barh(range(len(counts)),values,left=left,label=label,color=color);left+=values
    ax.set_yticks(range(len(counts)),[SHORT[k] for k in counts.index]);ax.set_xlabel('Outcome × model count (3 outcomes × SAR/SEM)')
    ax.set_title('Fixed numerical specification review; no p-value-based selection');ax.legend(fontsize=8,loc='upper center',bbox_to_anchor=(.5,-.1),ncol=2)
    save(fig,CHARTS[3])
    profiles=tables['spatial_likelihood_profiles']
    for outcome,family,name in [('tavg_bias','SEM',CHARTS[4]),('tavg_rmse','SAR',CHARTS[5]),('tavg_rmse','SEM',CHARTS[6])]:
        sub=profiles[profiles.outcome.eq(outcome)&profiles.model_type.eq(family)]
        fig,axes=plt.subplots(1,2,figsize=(11,4.5))
        for ax,(scope,frame) in zip(axes,sub.groupby('scope',sort=False)):
            ax.plot(frame.parameter,frame.negative_log_likelihood,color='#26758c')
            ax.axvline(-1,color='#ab4050',linestyle='--',label='Library lower bound -1')
            ax.set_xlabel('rho' if family=='SAR' else 'lambda');ax.set_ylabel('Profile negative log likelihood (lower is better)')
            ax.set_title('Unchanged library window' if scope=='library_window' else 'Wider nonsingular component: diagnostic only')
            ax.legend(fontsize=8)
        fig.suptitle(f'{outcome} {family} | no replacement estimate, no expanded-bound fit',fontsize=11)
        save(fig,name)
    return paths


def report_sections(tables: dict,manifest: dict) -> list[tuple[str,str,pd.DataFrame | None]]:
    """Eleven evidence-based sections; prioritize saved HC3 and preserve Stage14 reports."""
    solver=tables['spatial_solver_diagnostics']
    failed=solver[solver.weight_type.eq('inverse_distance_p1_row') & solver.numerical_class.isin(['FAILED','NUMERICALLY_UNSTABLE'])]
    columns=['outcome','model_type','diagnostic_estimate','estimate','solver_success','solver_iterations','solver_evaluations',
             'relative_boundary_distance','solver_relative_boundary_distance','autoregressive_matrix_condition',
             'neumann_radius_at_candidate','first_power_norm_increase_iteration','numerical_class','failure_reason']
    return [
        ('1. 문제 배경',f"Final Tier A {manifest['station_count']} station, 기존 Stage14 값/보고서 수정 없음. NASA/KMA API 0. 목적은 수치 실패의 진단이며 새로운 기후계수나 p-value를 만들지 않습니다.",tables['stage14_numerical_reproduction']),
        ('2. Inverse-distance weights','W_ij=d_ij^(-p), i≠j. km 단위. 밀도는 nnz/[n(n−1)]. 행표준화 전후를 구분하며 유효 이웃 수는 1/Σ(normalized w_ij²). cutoff는 기존 MST 연결 distance-band와 같은 단 하나의 반경입니다.',tables['inverse_distance_weight_diagnostics']),
        ('3. Spectral diagnostics','Spectral radius만으로 안정성을 판정하지 않습니다. row-standardized 비음수 W는 보통 radius=1이지만 음의 고유값·비정규성이 다릅니다. W 자체의 높은 condition number/낮은 rank는 I−theta W의 singularity와 다릅니다. Directed W는 복소 고유값의 실수부 범위와 허수부를 구분해 저장합니다.',tables['spatial_weight_spectral_properties']),
        ('4. Admissible parameter range','여기서 admissible은 0을 포함하는 (I−theta W) 비특이 실수 구간입니다. 양/음의 실고유값 역수 중 가까운 경계로 계산합니다. 전체 비특이 집합은 이 구간 밖에도 있을 수 있습니다. Neumann 급수 수렴조건 |theta|·radius(W)<1 및 현재 spreg의 고정 (-1,1) 최적화 범위와 구별해야 합니다. p1의 -1 부근을 singular boundary라고 부르지 않습니다.',tables['spatial_parameter_admissible_ranges']),
        ('5. Failed models / likelihood','Native minimize_scalar를 관찰만 하고 인자·tolerance·bounds를 변경하지 않았습니다. diagnostic_estimate는 solver 후보의 감사용 값이며 정상 estimate가 아닙니다. 실패/근접경계 estimate는 NaN입니다. derivative_at_lower>0이면 음의 로그우도가 -1의 왼쪽에서 더 낮아질 가능성을 뜻합니다. 넓은 구간의 81점 profile은 모양 확인 전용이며 외부 구간의 최적화·대체계수 산출은 하지 않습니다. SAR의 power expansion은 increment norm이 한 번 증가해도 예외를 내므로 이 예외만으로 수학적 급수 발산을 단정할 수 없습니다.',failed[columns]),
        ('6. p=1 vs p=2','행표준화한 두 지수만 비교합니다. p2가 안정적이어도 과학적으로 우수하거나 main이라는 결론은 아닙니다.',tables['inverse_distance_power_sensitivity'][['weight_type','outcome','model_type','diagnostic_estimate','estimate','numerical_class']]),
        ('7. Cutoff / row-standardization sensitivity','Cutoff는 결과와 무관하게 기존 거리대역 반경 하나로 고정했습니다. Raw weights도 라이브러리가 그대로 받아들이지만 고정 solver bounds의 상대적 크기·공간 모수 단위가 달라집니다. Raw p1/p2를 성공시키기 위한 bound 재조정은 하지 않았습니다.',tables['spatial_model_numerical_stability'][solver.weight_type.str.startswith('inverse_distance')]),
        ('8. KNN / distance-band comparison','STABLE은 반환값 유한·native optimizer success·내부해·유효 잔차·재현성을 뜻할 뿐 과학적 타당성의 증명이 아닙니다. 비특이 구간 1% 또는 solver 구간 5% 이내는 CONVERGED_NEAR_BOUNDARY; solver 경계 1e−6 이내는 NUMERICALLY_UNSTABLE. Distance-band의 경계 근접 행은 해석에 사용하지 않는 제한적 sensitivity입니다.',tables['spatial_model_numerical_stability'][solver.weight_type.isin(['directed_knn_k4','symmetric_knn_k4','distance_band_x1'])]),
        ('9. Final recommended specifications','Main 승격은 기존 directed KNN baseline만 허용합니다. hard failure/solver boundary가 있으면 NOT_RECOMMENDED_NUMERICAL. 그 외는 sensitivity이며 near-boundary 행을 정상 추정으로 사용하지 않습니다. 이 권장은 현재 station/config/library 범위의 수치적 운영규칙입니다.',tables['spatial_model_final_specification_recommendation']),
        ('10. Interpretation update / HC3 baseline','Non-spatial primary inference는 HC3 robust SE입니다. Classical OLS p는 descriptive/reference. 모든 coefficient/p-value는 기존 Stage14 CSV에서 읽었습니다. RMSE의 model-sensitive 상태를 수치 안정화만으로 robust로 올리지 않습니다.',tables['stage14_model_interpretation_status']),
        ('11. Limitations / reproducibility','54개 사전 지정 조합을 동일 seed 재실행 및 입력 shuffle 후 canonical 재구성으로 검증했습니다. Station 값은 변경하지 않았습니다. 81점 profile은 전역 최적성 증명이 아닙니다. 유한값/수렴 성공은 추정불확실성, 이분산, small-n 점근검정, 관측소 대표성 또는 인과문제를 해결하지 않습니다. OLS HC3도 공간상관 보정 자체는 아닙니다. Bound 확대/solver tolerance 완화/다른 라이브러리 시도/기후값 대체는 하지 않았습니다.',tables['spatial_model_ordering_reproducibility']),
    ]


def write_reports(tables: dict,manifest: dict,root: Path) -> list[str]:
    """Separate short HTML/Markdown technical review, never overwrite Stage14 reports."""
    title='Spatial Model Numerical Robustness Review · Stage 14.5'
    md=[f'# {title}\n'];html=[f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{title}</title><style>body{{font:15px/1.65 system-ui;max-width:1250px;margin:36px auto;padding:0 24px;color:#233c49}}.table{{overflow:auto}}table{{border-collapse:collapse;font-size:11px;white-space:nowrap}}td,th{{border:1px solid #ccd5da;padding:5px}}p{{white-space:pre-wrap}}img{{max-width:100%}}h1,h2{{color:#14576b}}</style><body><h1>{title}</h1>']
    for heading,prose,frame in report_sections(tables,manifest):
        md.extend([f'\n## {heading}\n',prose+'\n']);html.append(f'<h2>{escape(heading)}</h2><p>{escape(prose)}</p>')
        if frame is not None:
            # Large audit tables live in CSV; keep the technical report short.
            if len(frame)>24:
                text=f'총 {len(frame)}행; 아래는 처음 12행입니다. 전체 감사 결과는 manifest의 CSV 참조.'
                md.append(text);html.append(f'<p>{text}</p>');frame=frame.head(12)
            md.append(markdown_table(frame));html.append('<div class="table">'+frame.to_html(index=False,escape=True,float_format=lambda x:f'{x:.6g}')+'</div>')
    for name in manifest.get('generated_charts',[]):
        relative='../../charts/spatial_models_numerical/'+Path(name).name
        md.append(f'\n[{Path(name).name}]({relative})\n');html.append(f'<p><img src="{relative}" alt="{escape(Path(name).stem)}"></p>')
    sources=[('PySAL ML_Lag source','https://pysal.org/spreg/_modules/spreg/ml_lag.html'),
             ('PySAL ML_Error source','https://pysal.org/spreg/_modules/spreg/ml_error.html'),
             ('PySAL spatial weights','https://pysal.org/spreg/notebooks/4_spatial_weights.html')]
    md.append('\n## 공식 구현 근거\n');html.append('<h2>공식 구현 근거</h2>')
    for label,url in sources:
        md.append(f'[{label}]({url})');html.append(f'<p><a href="{url}">{label}</a></p>')
    html.append('</body></html>');directory=root/'output/reports/spatial_models_numerical';directory.mkdir(parents=True,exist_ok=True)
    paths=[]
    for ext,text in [('md','\n'.join(md)),('html','\n'.join(html))]:
        path=directory/f'spatial_model_numerical_robustness_review.{ext}';path.write_text(text,encoding='utf-8');paths.append(path.relative_to(root).as_posix())
    return paths
