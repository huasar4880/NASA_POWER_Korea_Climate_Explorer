"""Evidence-constrained research narrative and curated existing figures, not new analysis."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .facts import values

TITLE = 'NASA POWER와 KMA ASOS를 활용한 대한민국 장기 기온변화 및 공간적 특성 분석'
ENGLISH_TITLE = 'Long-Term Temperature Change and Spatial Characteristics in South Korea Using KMA ASOS and NASA POWER'
CAUTION = ('관측소 중앙값은 면적가중 전국 평균이 아닙니다. NASA 격자와 ASOS 지점의 공간대표성이 다릅니다. '
           '상관은 정확도 또는 인과성을 뜻하지 않습니다. 고온일수는 공식 폭염·열대야 통계가 아닌 threshold proxy입니다. '
           '분석기간·관측소 집합·공간가중치를 함께 확인해야 합니다.')
ATTRIBUTION = (
    'NASA POWER: NASA Langley Research Center의 POWER 프로젝트(Earth Science Division 지원), Daily Point 서비스. '
    '기온 변수 T2M/T2M_MAX/T2M_MIN, 단위 °C, 요청 시간기준 LST. '
    'KMA ASOS: 기상청 지상(종관, ASOS) 일자료 조회서비스, 지점 일평균·최고·최저기온(°C). '
    'KHOA coastline: 해양수산부 국립해양조사원 해안선. 해안거리 단위 km. '
    '데이터의 서비스 버전·취득일은 보존된 원본 metadata/manifest를 기준으로 하며 누락 정보는 추정하지 않습니다.'
)
OFFICIAL_LINKS = {
    'NASA POWER referencing':'https://power.larc.nasa.gov/docs/referencing/',
    'KMA ASOS service':'https://www.data.go.kr/data/15059093/openapi.do',
    'KHOA coastline':'https://www.data.go.kr/data/15083948/fileData.do',
}
RULES = ('증거 등급은 프로젝트 운영규칙이며 학계의 표준 등급이 아닙니다. ROBUST는 해당 명제가 적용 가능한 '
         '검증 축에서 유지됨을 뜻하고 모든 통계량이 동일하다는 뜻은 아닙니다. MODERATELY_ROBUST는 반복 방향이 '
         '있으나 일부 지점·모형·유의성이 달라지는 경우, SENSITIVE는 기간·가중치·추론법에 따라 해석이 바뀌는 경우, '
         'DESCRIPTIVE_ONLY는 강건성 검증 밖의 기술적 요약입니다. 적용 불가능하거나 미검증인 축은 통과로 세지 않습니다.')

HIGHLIGHTS = [
    '고정 Tier A의 모든 시작기간에서 TAVG가 증가한 지점은 {{stability_TAVG_positive_all_count}}개입니다. '
    '공통기간에서는 {{common_KMA_TAVG_positive}}/{{common_n}}개 지점이 증가하고 모두 원 MK의 BH-FDR 기준을 충족했습니다.',
    '공통기간 TMIN–TMAX 기울기 차이의 중앙값은 {{contrast_median}} °C/decade이며, '
    'TMIN 상승이 더 큰 지점은 {{contrast_positive}}개입니다. KMA DTR 기울기 중앙값은 {{common_KMA_dtr}} °C/decade입니다.',
    '공통기간 TAVG의 NASA–KMA 추세 방향 일치는 {{agreement_TAVG}}/{{common_n}}개 지점입니다. '
    '그러나 Bias 중앙값 {{validation_TAVG_bias}} °C와 RMSE 중앙값 {{validation_TAVG_rmse}} °C는 절대 수준의 차이를 보여줍니다.',
    'NASA TAVG의 공간구조는 station-linked에서 고유 격자로 바꿔도 양의 유의성이 유지됩니다. '
    '대표 가중치 Moran I는 {{spatial_nasa_tavg_sen_slope_STATION_LINKED_Moran_I}}에서 '
    '{{spatial_nasa_tavg_sen_slope_UNIQUE_GRID_Moran_I}}로 달라지므로 중복의 크기 효과는 무시할 수 없습니다.',
    'Bias·RMSE의 공간구조는 저장된 기간·가중치 검토에서 반복됩니다. 해안거리와의 연관도 반복되지만, '
    '지형·고도·격자 대표성과 분리된 인과효과를 입증한 것은 아닙니다.',
    'KMA TAVG 공간군집은 {{trajectory_kma_tavg_sen_slope_STATION_LINKED_period_robustness}}로 분류됩니다. '
    '고정 Tier A의 가장 긴 기간과 가장 짧은 기간 기울기 중앙값은 각각 '
    '{{window_1981_KMA_TAVG_median}}, {{window_2001_KMA_TAVG_median}} °C/decade로 다릅니다. 이를 가속화로 단정하지 않습니다.',
]

METHODS = [
    ('자료 품질','일력·중복·결측·이상범위·연 completeness·관측소 이력을 점검한 기존 screening을 사용합니다. '
     'Tier B는 짧은 자료를 장기 Tier A에 접합하지 않고 공통기간에서만 결합합니다. 결측을 임의로 보간하거나 영으로 채우지 않습니다.'),
    ('효과크기와 검정','Sen slope는 연간 값의 시점쌍 기울기 중앙값이며 °C/decade로 환산된 저장값을 사용합니다. '
     'Mann–Kendall은 단조 추세 검정입니다. 원 MK의 raw p에 설정된 비교군별 BH-FDR가 주 추론이고, '
     '자기상관 진단과 Hamed–Rao modified MK는 보조 결과입니다. 표본·기간 변경 때 비교군도 함께 확인합니다.'),
    ('TMIN/TMAX contrast와 DTR','contrast는 저장된 TMIN Sen 기울기에서 TMAX Sen 기울기를 뺀 값입니다. '
     'DTR은 각 지점·자료원·연도의 연평균 TMAX에서 연평균 TMIN을 뺀 연간 시계열에 적합했던 Sen 기울기입니다. '
     '두 기온 Sen 기울기의 차이와 DTR Sen은 같은 연산이 아니므로 서로 대체하지 않습니다. '
     '지점별 contrast의 중앙값도 두 전국 지점 중앙값을 뺀 값과 일반적으로 다릅니다. 단위는 모두 °C/decade입니다.'),
    ('Normal·계절·proxy','Climate Normal {{normal}} 대비 anomaly를 사용합니다. 계절은 DJF/MAM/JJA/SON이며 '
     '겨울 연도 귀속과 completeness는 기존 방법 문서에 따릅니다. TMAX ≥ 33°C와 TMIN ≥ 25°C 일수는 '
     '유효한 matched daily pair의 proxy입니다. 공식 폭염·열대야 정의나 관측시간 조건을 대체하지 않습니다.'),
    ('교차검증','차이를 NASA−KMA로 정의합니다. Bias는 차이 평균, MAE는 절대차 평균, RMSE는 제곱차 평균의 제곱근입니다. '
     'Pearson과 Spearman은 각각 선형·순위 동조성을 나타냅니다. 모든 pair는 양쪽 유효일을 기준으로 합니다. '
     '최종 표의 중앙값은 지점별 지표의 중앙값으로, 전체 일자료를 합친 pooled 오차가 아닙니다.'),
    ('공간 통계','Global Moran I는 저장된 순열검정 결과, Local Moran은 다중검정 보정과 패턴 안정성을 함께 읽습니다. '
     '대표 directed KNN과 대칭 KNN·거리 가중치 민감도를 구분합니다. Global/해안 상관의 탐색적 raw p를 '
     '지점 추세의 FDR q와 혼용하지 않습니다. 추정 NASA native 중심과 동일 일시계열 검증으로 격자 중복을 점검했습니다.'),
    ('해안·모형 진단','공식 KHOA 해안선으로 계산된 거리와 연속 상관·해안/내륙 구분을 읽습니다. '
     'OLS classical p보다 HC3 추론을 우선하고, HC3가 공간상관까지 보정하는 것은 아님을 명시합니다. '
     'SAR/SEM은 수렴·경계·스펙트럼·정렬·solver 진단을 통과한 범위에서만 보조 해석합니다. '
     '수치적 실패나 비유의를 삭제하거나 다른 specification의 유의성으로 덮지 않습니다.'),
    ('기간 민감성','동일 Tier A 집합, 고정 종료연도에서 저장된 시작기간을 비교합니다. 기간들은 중첩되고 '
     '시작연도와 길이가 함께 변합니다. 유의 기간 수는 독립 반복실험의 확률이 아닙니다. '
     '최종 통합에서는 저장 추정치의 중앙값·건수만 집계하고 새 기울기·검정·회귀를 계산하지 않습니다.'),
]
LIMITATIONS = [
    '전국으로 분포한 관측소 집합이지 면적가중 대한민국 평균이나 균등한 공간표본이 아닙니다.',
    'NASA 격자의 지형·고도·해안 대표성과 ASOS 지점관측, 시간기준 및 관측소 이력이 차이를 만들 수 있습니다.',
    '격자 공유는 관측소 간 독립성을 약화시킵니다. 고유 격자 비교는 공간구조의 크기 민감성을 없애지 않습니다.',
    'Tier B는 소표본입니다. Tier A의 공통기간 재분석과 전체 공통기간 집합은 관측소 수가 다릅니다.',
    '기간 중첩, 잔여 결측, 연 completeness, 자기상관, 다중검정은 유의성과 크기 해석에 영향을 줍니다.',
    '공간가중치와 Local Moran의 다중검정 결과에 민감한 패턴을 확정 군집으로 부르지 않습니다.',
    '해안거리 상관은 관측적 연관입니다. HC3·모형·numerical review에서 비유의·실패인 결과는 핵심 인과결론이 아닙니다.',
    '고온 threshold는 분석 proxy입니다. 강수·습도·풍속·일사는 기존 기능으로 보존하되 최종 전국 기온 연구의 범위를 넓히지 않습니다.',
    '종료연도 민감성, 인과귀속, 미래 시나리오·예측은 검증하지 않았습니다. 상승 크기의 기간 차이는 가속화의 증거가 아닙니다.',
]
QUESTIONS = [
    '장기 TAVG의 지점별 변화 방향은 얼마나 일관되는가?', 'TAVG/TMAX/TMIN 상승속도는 어떻게 다른가?',
    'TMIN 우세 및 DTR 감소는 얼마나 유지되는가?', '계절별 추세는 어떻게 다른가?',
    '고온 threshold proxy는 어떻게 변하는가?', 'NASA–KMA 추세 방향은 얼마나 일치하는가?',
    'Bias·RMSE에 어떤 공간구조가 있는가?', '격자 공유가 공간 통계량에 어떤 영향을 주는가?',
    'KMA TAVG 군집은 가중치에 견고한가?', '해안거리와의 연관은 반복되는가?',
    '시작연도는 기울기·유의성·Moran에 어떤 영향을 주는가?', '어떤 결론이 여러 검증 축에서 유지되는가?',
]


def references(template: str) -> list[str]:
    """List fact tokens used by an authored narrative."""
    return re.findall(r'\{\{([A-Za-z0-9_]+)\}\}',template)


def format_value(value: object) -> str:
    """Round only presentation, never the stored fact layer."""
    if isinstance(value,float):
        if value.is_integer():return str(int(value))
        return f'{value:.3g}' if 0<abs(value)<0.0001 else f'{value:.4f}'
    if isinstance(value,list):
        return '–'.join(str(x) for x in value)
    return str(value)


def plain(template: str, facts: pd.DataFrame, citation: bool = True) -> str:
    """Render fact tokens; unknown IDs fail closed rather than inventing a value."""
    lookup=values(facts)
    return re.sub(r'\{\{([A-Za-z0-9_]+)\}\}',lambda m:format_value(lookup[m[1]])+
                  (f' <!-- fact:{m[1]} -->' if citation else ''),template)


def evidence(facts: pd.DataFrame) -> pd.DataFrame:
    """Classify the exact claims, using explicit applicable axes and conservative model scope."""
    v=values(facts)
    a=v['stability_TAVG_positive_all_count']==v['tier_a'] and v['common_KMA_TAVG_positive']==v['common_n'] and v['common_KMA_TAVG_fdr']==v['common_n']
    c=v['agreement_TAVG']==v['common_n'] and all(v[f'period_agreement_{w["start_year"]}_TAVG_same_direction_count']==v['tier_a'] for w in v['windows'])
    e=all(v[f'weights_nasa_tavg_sen_slope_{rep}_robustness_class']=='ROBUST_POSITIVE'
          and v[f'allweights_nasa_tavg_sen_slope_{rep}_stable']==v[f'allweights_nasa_tavg_sen_slope_{rep}_total']
          for rep in ('STATION_LINKED','UNIQUE_GRID'))
    # Stored robustness labels are checked, never inferred from a hand-selected p value.
    f=all(v[f'weights_{var}_STATION_LINKED_robustness_class']=='ROBUST_POSITIVE'
          and v[f'trajectory_{var}_STATION_LINKED_period_robustness']=='SPATIALLY_STABLE_POSITIVE'
          and v[f'allweights_{var}_STATION_LINKED_stable']==v[f'allweights_{var}_STATION_LINKED_total']
          for var in ('tavg_bias','tavg_rmse'))
    specs=[
        ('A',HIGHLIGHTS[0],['stability_TAVG_positive_all_count','common_KMA_TAVG_positive','common_KMA_TAVG_fdr'], 'all stored windows','not a spatial claim','KMA claim; not applicable','not a regression claim','ROBUST' if a else 'SENSITIVE'),
        ('B',HIGHLIGHTS[1],['contrast_positive','common_KMA_dtr','period_dtr_2001_KMA_negative_count'], 'majority, not every station','not a clustering claim','NASA contrast differs; no cross-product generalization','not a regression claim','MODERATELY_ROBUST'),
        ('C',HIGHLIGHTS[2],['agreement_TAVG','period_agreement_2001_TAVG_same_direction_count','validation_TAVG_rmse'], 'direction agreement repeated','not a clustering claim','station-linked direction only; not independent grids','not a regression claim','ROBUST' if c else 'SENSITIVE'),
        ('D','KMA TAVG 공간군집은 기간·가중치에 민감하며 고정된 전국 군집을 주장할 수 없습니다.',
         ['weights_kma_tavg_sen_slope_STATION_LINKED_robustness_class','trajectory_kma_tavg_sen_slope_STATION_LINKED_period_robustness'], 'direction sensitive','inconsistent direction','not applicable','HC3 does not rescue marginal spatial claims','SENSITIVE'),
        ('E',HIGHLIGHTS[3],['weights_nasa_tavg_sen_slope_STATION_LINKED_robustness_class','weights_nasa_tavg_sen_slope_UNIQUE_GRID_robustness_class','trajectory_nasa_tavg_sen_slope_UNIQUE_GRID_period_robustness','allweights_nasa_tavg_sen_slope_UNIQUE_GRID_stable','allweights_nasa_tavg_sen_slope_UNIQUE_GRID_total'],
         'positive spatial structure repeated','positive across stored weights','significance retained; magnitude changes','not a regression claim','ROBUST' if e else 'SENSITIVE'),
        ('F','NASA–KMA Bias·RMSE의 양의 공간구조는 저장된 기간·가중치에서 반복됩니다.',
         ['weights_tavg_bias_STATION_LINKED_robustness_class','weights_tavg_rmse_STATION_LINKED_robustness_class','trajectory_tavg_bias_STATION_LINKED_period_robustness','trajectory_tavg_rmse_STATION_LINKED_period_robustness','allweights_tavg_bias_STATION_LINKED_stable','allweights_tavg_rmse_STATION_LINKED_stable'],
         'positive significance repeated','positive across stored weights','error is station-paired; shared-grid split descriptive only','spatial claim, not coastal coefficient significance','ROBUST' if f else 'SENSITIVE'),
        ('G','해안거리와 Bias·RMSE 연관은 반복되지만 RMSE의 통제모형 유의성까지 강건한 것은 아닙니다.',
         ['period_coast_tavg_bias_period_interpretation','period_coast_tavg_rmse_period_interpretation','model_tavg_bias_hc3_p','model_tavg_rmse_hc3_p'],
         'association repeated','not a weight-based causal test','shared-grid dependence remains','Bias HC3 supported; RMSE model-sensitive; unsupported SAR/SEM excluded','MODERATELY_ROBUST'),
        ('H',HIGHLIGHTS[5],['window_1981_KMA_TAVG_median','window_2001_KMA_TAVG_median','stability_TAVG_median'],
         'magnitude sensitive','not a clustering claim','both products depend on period','not acceleration model','SENSITIVE'),
    ]
    rows=[]
    for cid,statement,ids,period,weight,grid,model,level in specs:
        if not set(ids).issubset(v):raise ValueError(f'Missing evidence for {cid}')
        rows.append({'conclusion_id':cid,'statement':plain(statement,facts,False),
                     'supporting_stages':'11;16;17;18' if cid not in ('G',) else '13;14;14.5;17;18',
                     'main_metrics':';'.join(sorted(set(ids+references(statement)))),
                     'period_robustness':period,'weight_robustness':weight,'grid_duplication_robustness':grid,
                     'HC3/model_robustness':model,'limitations':CAUTION,'final_evidence_class':level})
    return pd.DataFrame(rows)


def figures(facts: pd.DataFrame) -> pd.DataFrame:
    """Choose existing PNGs, preserving original sources and recording interpretable captions."""
    common='output/charts/common_period/'; spatial='output/charts/common_period_spatial/'; period='output/charts/period_sensitivity/'
    entries=[
        ('TMAX·TMIN 비교',common+'common_period_tmax_tmin_trends.png','common','°C/decade','변수 간 차이; 지점별 이질성'),
        ('NASA–KMA TAVG 추세',common+'common_period_kma_nasa_tavg_scatter.png','common','°C/decade','방향 일치와 크기 차이 분리'),
        ('기온 anomaly',common+'common_period_anomaly_heatmap.png','common','°C','normal 대비 anomaly; 관측소 행렬'),
        ('NASA–KMA Bias·RMSE',common+'common_period_bias_rmse.png','common','°C','일별 유효 pair의 오차; pooled 통계 아님'),
        ('NASA station/grid 공간구조',spatial+'nasa_station_vs_grid_moran.png','common','Moran I (dimensionless)','격자 중복의 영향; 동일 표본수 아님'),
        ('KMA TAVG Moran 기간 민감성',period+'kma_tavg_moran_trajectory.png','long','Moran I (dimensionless)','기간 중첩; raw permutation p'),
        ('KMA TAVG 기울기 기간 민감성',period+'kma_tavg_median_slope_by_start_year.png','long','°C/decade','기울기 크기 변화; 가속화 추론 아님'),
        ('계절별 기울기 기간 민감성',period+'seasonal_median_slope_by_start_year.png','long','°C/decade','계절·기간에 따른 차이'),
        ('해안거리와 Bias',spatial+'coastal_distance_vs_bias.png','common','km; °C','관측적 연관; 인과해석 불가'),
        ('해안거리와 RMSE',spatial+'coastal_distance_vs_rmse.png','common','km; °C','상관과 통제모형 추론 분리'),
    ]
    rows=[]
    for i,(title,path,cohort,unit,why) in enumerate(entries,1):
        scope=('공통기간 {{common_period}}, ASOS N={{common_n}}, NASA unique grids={{grid_n}}.' if cohort=='common'
               else '고정 Tier A {{long_period}}, N={{tier_a}}, 시작연도별 중첩기간, NASA unique grids={{long_grid_n}}.')
        caption=plain(scope,facts)+f' 단위: {unit}. {why}. '
        if 'anomaly' in path:caption+=plain('Climate Normal: {{normal}}.',facts)
        rows.append(dict(figure_id=f'Figure-{i:02}',title=title,source_path=path,caption=caption,
                         report_section='주요 결과',why_selected=why))
    return pd.DataFrame(rows)
