"""Fact-bound publication and portfolio documents generated from the final evidence package."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import pandas as pd

from .content import (ATTRIBUTION, CAUTION, HIGHLIGHTS, LIMITATIONS, METHODS,
                      OFFICIAL_LINKS, RULES, TITLE, plain)
from .facts import FINAL, values
from .report import REPORT_STEM, research_tables, table_md, write_text

REPRO = '''# Reproducibility

## 환경과 설치

Python 3.11 이상을 사용합니다. 저장소 주소는 아직 결정되지 않았으므로 clone URL을 임의로 제시하지 않습니다.
공개 승인된 저장소를 clone하거나 제공받은 소스 폴더에서 실행합니다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

의존성은 범위 고정이므로 다른 환경의 비트 단위 동일성을 보장하지 않습니다.
실제 검증 환경은 output/final/qa/environment.json에 기록합니다. API 키는 .env에만 두며 저장소에 올리지 않습니다.
최종 보고서와 Dashboard의 저장 결과 열람에는 키나 네트워크가 필요하지 않습니다.

## 저장 cache 기반 전체 재현

기존 data/와 output/의 manifest-검증된 cache를 보유한 환경에서만 최종 package를 재생성할 수 있습니다.
raw/processed를 내려받거나 기존 분석을 다시 실행하는 과정은 이번 통합 실행에 포함되지 않습니다.

```bash
python scripts/build_final_integration.py
python -m pytest -q
python -m pip check
streamlit run streamlit_app.py
```

생성기는 외부 HTTP를 차단하며 final namespace와 생성 문서·선택 그림 사본만 갱신합니다.
source CSV 값과 row/key·column·operation을 재생 검증하고 상위 manifest 해시를 대조합니다.
mtime은 변경 탐지용이지 자료 관측일이나 다운로드일이 아닙니다. generation time 외 research facts/report 내용은 결정적입니다.

## 공개 요약 열람과 한계

공개 후보는 코드·문서·output/final 요약과 선택 차트입니다. 원본 cache는 기본 Git 제외 대상입니다.
final summary만으로 HTML 단독 열람과 Home/Reports의 읽기 전용 요약을 이용할 수 있습니다.
다른 분석 페이지와 전체 integration 재생성·실자료 회귀 테스트에는 원래 cache가 필요합니다.
cache가 없으면 새 다운로드를 자동 실행하지 않고 자료 부족을 표시합니다. 이것은 전체 분석 demo가 아닙니다.
Markdown 보고서는 report/assets를 함께 제공해야 하고 HTML은 그림이 내장돼 있습니다.

## 실제 검증과 보호

```bash
python scripts/verify_final_integration.py --baseline PROTECTED_SNAPSHOT_JSON
```

PROTECTED_SNAPSHOT_JSON은 작업 전 생성한 해시·mtime snapshot 경로로 바꿉니다. 다른 시점의 snapshot을 재사용하지 않습니다.
검증기는 이전 분석을 재실행하지 않고 facts·보고서 재생성 동일성, 모든 기존 페이지의 상호작용,
외부 HTTP 차단, 전체 pytest 결과, pip check, 보호파일을 확인합니다.
실제 Streamlit localhost HTTP 응답은 별도 QA에 기록합니다. 최종 승인 여부는 manifest의 completed를 확인합니다.

기존 단계 CLI 및 상세 설치·변수 설명: [단계별 기록](STAGE_HISTORY.md), [문서 색인](INDEX.md).
라이선스와 공개 결정은 실행 재현성과 별도입니다. VERSION 변경·git init·remote·push는 수행하지 않습니다.
'''

STORIES = [
    ('격자 중복', '여러 관측소가 같은 NASA 격자와 연결되어 공간구조를 독립 관측소 결과처럼 해석할 위험이 있었습니다.',
     '관측소 연결과 고유 격자 표현의 차이를 분리해야 했습니다.',
     'native 중심 추정과 같은 일시계열 검증을 거쳐 두 공간표현의 저장 결과를 비교하고 표본수와 해시를 기록했습니다.',
     '공통기간 {{common_n}}개 지점은 {{grid_n}}개 NASA 격자에 연결됐습니다. 양의 공간구조는 유지되지만 Moran 크기는 달라졌습니다.'),
    ('기간 민감성', '장기 분석의 공간군집을 공통기간으로 옮기자 같은 결론이 유지되지 않았습니다.',
     '관측소 집합 변화와 기간 변화가 뒤섞이지 않도록 검증해야 했습니다.',
     'Tier A 집합과 종료연도를 고정한 시작기간 비교를 별도 namespace에서 수행하고 이전 결과를 보호했습니다.',
     'TAVG 상승 방향은 {{stability_TAVG_positive_all_count}}개 Tier A 지점에서 모든 기간에 유지됐지만 군집 방향과 기울기 크기는 민감했습니다.'),
    ('수치 불안정', '공간모형에서 라이브러리의 수렴 표시만으로 신뢰하기 어려운 경계·solver 차이가 발견됐습니다.',
     '좋은 결과만 선택하지 않고 기존 결론의 사용 가능 범위를 분류해야 했습니다.',
     '관측소 정렬, 스펙트럼 허용구간, likelihood, solver와 잔차를 검토하고 HC3를 별도 추론으로 유지했습니다.',
     '수치 불안정 {{model_count_NUMERICALLY_UNSTABLE}}개 및 실패 {{model_count_FAILED}}개 조합을 명시적으로 남겨 핵심결론에서 제외했습니다.'),
]


def markdown_sections(title: str, sections: list[tuple[str,str]]) -> str:
    """Assemble readable Markdown with stable heading order."""
    return '# '+title+'\n\n'+'\n\n'.join('## '+name+'\n\n'+body for name,body in sections)+'\n'


def generate_documents(root: Path, facts: pd.DataFrame, ev: pd.DataFrame, registry: pd.DataFrame) -> list[str]:
    """Generate research and portfolio docs, leaving historical technical instructions linked."""
    v=values(facts)
    def render(text: str) -> str:return plain(text,facts)
    def bullets(items: list[str]) -> str:return '\n\n'.join('- '+render(x) for x in items)
    summary=bullets(HIGHLIGHTS)
    scale=render('공식 inventory {{inventory_n}}개, Tier A {{tier_a}}개, Tier B {{tier_b}}개, '
                 '공통기간 {{common_n}}개 지점 및 NASA 고유 격자 {{grid_n}}개. 장기 {{long_period}}, '
                 '공통기간 {{common_period}}, normal {{normal}}.')
    tech=('Python, pandas, NumPy, SciPy, statsmodels, pymannkendall로 정제·기술통계·검정을 구성하고 '
          'requests로 API cache/retry/오류 응답을 처리했습니다. Shapely·PyProj·PyShp와 libpysal/spreg는 '
          '해안거리 및 공간 진단에, matplotlib·Plotly는 저장 차트에, Streamlit은 읽기 전용 UI에 사용됩니다. '
          'pytest mock, SHA256, mtime, manifest, deterministic fact layer로 재현성과 변경 탐지를 분리합니다.')
    architecture='''```mermaid
flowchart LR
  A[공식 API와 metadata] --> B[raw cache · checkpoint]
  B --> C[정제 · screening · 품질]
  C --> D[추세 · validation · 공간분석]
  D --> E[기간 · 격자 · 모형 검증]
  E --> F[검증된 CSV와 manifest]
  F --> G[Final fact · evidence layer]
  G --> H[보고서 · 포트폴리오 · read-only UI]
```

최종 통합 경로는 저장된 CSV에서 시작합니다. 앞 단계 API·추정 경로는 다시 실행하지 않습니다.'''
    stories='\n\n'.join('### '+name+'\n\n**Situation:** '+s+'\n\n**Task:** '+t+'\n\n**Action:** '+a+'\n\n**Result:** '+render(r)
                          for name,s,t,a,r in STORIES)
    portfolio=markdown_sections('Final Portfolio',[
        ('프로젝트 한 줄','자료 수집부터 검정·강건성 검증·전달까지 출처를 추적하는 전국 기온 연구 플랫폼.'),
        ('문제','기관·도시·기간마다 다른 데이터 처리와 검정이 결과 비교를 어렵게 만듭니다.'),
        ('선정 이유','공공 관측자료와 접근 가능한 과학 격자자료를 연결해 동조성과 차이를 함께 검증할 수 있습니다.'),
        ('데이터',scale+'\n\n'+ATTRIBUTION),('시스템',architecture),('기술',tech),
        ('진행 과정','단일 도시 MVP → 다도시·기후통계 → KMA validation → 전국 screening → Tier별 공통기간 → '
         '공간·해안·모형 진단 → 기간 민감성 → 최종 fact 기반 통합. 기존 기능과 cache를 단계별 회귀 테스트로 보호했습니다.'),
        ('주요 발견',summary),('실패와 비유의 결과',render('공간모형 수치 불안정 {{model_count_NUMERICALLY_UNSTABLE}}개 조합과 '
         '실패 {{model_count_FAILED}}개 조합을 보존했습니다. classical p와 HC3의 해석 차이도 숨기지 않았습니다.')),
        ('기술적 과제','격자 중복, 기간·집합 교란, 공간모형 수치 불안정, 제한된 API 예산과 안전한 cache 재사용.'),
        ('해결 사례 — STAR',stories),('재현성','실제 결과는 [재현 가이드](REPRODUCIBILITY.md)와 final manifest에서 확인합니다. '
         '코드가 존재한다는 것과 전체 실행이 성공했다는 것을 구분합니다.'),
        ('결과물','[연구결과 요약](FINAL_RESULTS_SUMMARY.md), [방법](FINAL_METHODS_SUMMARY.md), '
         '[보고서](../output/final/report/'+REPORT_STEM+'.html), Streamlit Home·Reports 및 기존 분석 페이지.'),
        ('한계',bullets(LIMITATIONS)),('다음 단계','사용자 검토 후 코드 라이선스·공개 범위·release 버전을 결정합니다. '
         '미래예측이나 인과모형은 이번 결과에서 수행했다고 주장하지 않습니다.')])
    technical=markdown_sections('Technical Portfolio Summary',[
        ('범위',scale),('Stack',tech),('공통 파이프라인',architecture),
        ('API와 실패 복구','도시/지점 설정과 공통 downloader, raw cache·chunk checkpoint, timeout·재시도·호출 제한을 분리합니다. '
         '인증정보는 .env로 제한하고 실제 키를 로그에 출력하지 않습니다. 최종 통합은 API 접근 자체를 차단합니다.'),
        ('검정과 추론',render('\n\n'.join(t+': '+b for t,b in METHODS))),
        ('공간 진단','KNN·거리 기반 가중치, Global/Local Moran, 격자 중복, HC3 및 SAR/SEM 수치 검토를 '
         '하나의 유의성으로 합치지 않습니다. 원본 추정치와 실패기록을 모두 유지합니다.'),
        ('테스트·재현성','입력 schema·결측·일력·통계 known-answer·API mock·Dashboard·보안·provenance 테스트를 구분합니다. '
         '실제 실행 수는 output/final/final_test_summary.csv, 전체 gate는 final_integration_manifest.json에 기록합니다.'),
        ('품질 기준','코드 줄 수나 유의한 결과 수를 품질 성과로 내세우지 않습니다. 결과의 적용 범위와 실패 복구 가능성을 기준으로 설명합니다.')])
    resume_ko=[
        'NASA POWER·KMA ASOS 공공 API 수집부터 cache·정제·screening·시각화까지 재사용 가능한 Python 기후분석 파이프라인 구현.',
        '공식 ASOS inventory {{inventory_n}}개를 출발점으로 Tier A {{tier_a}}개와 Tier B {{tier_b}}개를 구분하고, '
        '{{common_n}}개 공통기간 관측소 비교의 기간·품질 조건을 관리.',
        'Sen slope, Mann–Kendall, BH-FDR 및 NASA–KMA Bias·MAE·RMSE·상관으로 장기 기온변화와 자료 차이를 분리하여 검증.',
        '{{common_n}}개 지점에 연결된 {{grid_n}}개 NASA 격자를 비교하고 공간가중치·기간·수치모형 민감성을 별도로 검토.',
        '통계적으로 불안정한 결과를 제외 기준과 함께 보존하고, source-addressable fact layer·SHA256·회귀 테스트로 보고서 재현성 구축.',
        '읽기 전용 Streamlit 대시보드, 최종 연구보고서, 공개 범위·비밀정보 검사를 연결한 전달 패키지 구성.',
    ]
    resume_en=[
        'Built a reusable Python pipeline for NASA POWER and KMA ASOS ingestion, caching, quality screening and visualization.',
        'Organized an official inventory of {{inventory_n}} ASOS stations into a {{tier_a}}-station long-period cohort and '
        'a {{tier_b}}-station shorter-period cohort for a {{common_n}}-station common-period comparison.',
        'Combined saved Sen slopes, Mann–Kendall tests and BH-FDR with Bias, MAE, RMSE and correlation to separate trend agreement from absolute differences.',
        'Audited {{grid_n}} unique NASA grids linked to {{common_n}} stations and documented spatial-weight, period and numerical-model sensitivity.',
        'Preserved failed model diagnostics and implemented source-addressable facts, checksums and regression tests for reproducible reporting.',
        'Integrated a read-only Streamlit interface, research report and publication-safety documentation without rerunning data downloads.',
    ]
    qa=[
        ('왜 NASA와 KMA인가?', '같은 기후현상을 격자자료와 지점관측으로 비교해 방향 일치와 절대 차이를 구분하기 위해서입니다.',
         'NASA는 균일한 API로 장기간 자료를 제공하지만 지점관측과 생산 방식이 다릅니다. KMA도 무조건적인 참값이 아니라 '
         '관측소 이력과 품질을 확인할 비교 자료로 사용했습니다. 일별 pair의 오차와 장기 추세 일치를 별도로 보고했습니다.'),
        ('관측소 규모가 달라지는 이유는?', '장기 조건을 만족한 Tier A와 짧은 공통기간을 만족한 Tier B가 다르기 때문입니다.',
         '공식 inventory {{inventory_n}}개가 모두 분석 지점은 아닙니다. Tier A {{tier_a}}개, Tier B {{tier_b}}개를 '
         '합친 공통기간 {{common_n}}개를 구분하고 고정 Tier A 기간 민감성은 별도로 수행했습니다.'),
        ('Tier A/B는 어떻게 다른가?', '기간과 자료 품질의 적합성을 구분한 운영 분류입니다.',
         '더 좋은 도시라는 순위가 아닙니다. metadata만으로 확정하지 않고 실제 일자료의 결측·연 completeness·연속성과 '
         '이력을 함께 확인했습니다. 짧은 자료를 장기자료로 채워 넣지 않았습니다.'),
        ('왜 Sen slope와 MK인가?', '효과크기와 추세 유의성을 분리할 수 있기 때문입니다.',
         'Sen은 시점쌍 기울기의 중앙값이고 MK는 단조 관계 검정입니다. 자기상관이 무시되는 것은 아니므로 '
         'modified MK를 보조로 확인했습니다. 원 MK/FDR 주 결과와 다른 검정의 가정을 명확히 구분했습니다.'),
        ('BH-FDR가 필요한 이유는?', '여러 지점·변수를 동시에 검사하는 상황에서 우연한 발견을 통제하기 위해서입니다.',
         '보정군 정의를 저장하고 raw p와 q를 함께 보존했습니다. 군을 바꾸면 q가 달라질 수 있으므로 '
         '공통기간 집합과 작은 부분집합의 결과를 단순히 비교하지 않습니다. 공간 순열 p도 별도 탐색 결과입니다.'),
        ('격자 중복은 어떤 문제인가?', '서로 다른 지점이 같은 NASA 시계열을 공유할 수 있습니다.',
         '공통기간 {{common_n}}개 지점은 {{grid_n}}개 고유 격자에 연결됐습니다. station-linked와 unique-grid의 '
         'Moran 크기를 비교했고 양의 공간구조가 남아도 동일한 독립 표본이라고 주장하지 않았습니다.'),
        ('TAVG Moran이 바뀐 이유는?', '기간·지점 집합·가중치가 다르면 추세의 상대적 공간배열이 달라질 수 있습니다.',
         '상승 방향이 같다는 것과 상승속도가 군집한다는 것은 다른 명제입니다. 지점 집합을 고정한 시작기간 비교에서도 '
         '군집 방향이 민감했으므로 특정 기간의 유의성을 전국의 영구적 패턴으로 확대하지 않았습니다.'),
        ('Bias/RMSE 공간패턴은 무엇을 뜻하는가?', '자료 간 차이가 공간적으로 무작위가 아닐 수 있다는 탐색 결과입니다.',
         '지형·고도·해안·격자 대표성·시간기준의 영향을 분리한 인과효과는 아닙니다. Bias는 NASA−KMA로 정의했고 '
         'RMSE는 절대 차이 규모입니다. 높은 상관은 낮은 RMSE를 보장하지 않습니다.'),
        ('SAR/SEM 실패는 어떻게 처리했나?', '실패와 경계 근처 해를 별도 상태로 보존하고 핵심결론에서 제외했습니다.',
         '정렬·스펙트럼·허용구간·solver·likelihood와 잔차를 비교했습니다. 불안정한 낮은 AIC나 유의한 계수로 '
         'HC3 비유의를 덮지 않았습니다. 모형의 반환값이 존재한다는 것과 사용 가능한 추론이라는 것을 구분했습니다.'),
        ('가장 어려운 기술 문제는?', '원본을 보존하면서 실패 복구와 검증 가능한 단계별 확장을 양립시키는 일이었습니다.',
         'API 부분 cache를 지우지 않고 상태를 기록했고 새 분석은 별도 namespace에 저장했습니다. '
         '최종 문장은 저장 결과를 직접 복사하지 않고 fact ID로 연결하여 숫자 불일치와 오래된 문서를 줄였습니다.'),
        ('결측은 어떻게 처리했나?', '관측누락을 임의 영값으로 채우지 않고 유효 pair와 completeness 조건을 사용했습니다.',
         '변수별 blank 의미는 다를 수 있습니다. 기존 품질 규칙과 원자료를 보존하고 어떤 날짜가 빠졌는지 '
         '기록했습니다. 기온 최종 통합은 이미 검증된 결과만 읽으며 강수 blank에 새 해석을 추가하지 않았습니다.'),
        ('핵심 발견은?', '상승 방향의 일관성과 변화량·공간군집의 조건 의존성이 동시에 관찰됐습니다.',
         '공통기간 {{common_KMA_TAVG_positive}}개 지점에서 TAVG가 증가했습니다. 그러나 NASA와의 방향 일치가 '
         '절대 온도 일치를 뜻하지 않고, KMA 공간군집은 기간에 민감합니다. 강건함의 적용 범위를 명제로 한정했습니다.'),
        ('한계는?', '전국 면적평균·인과귀속·미래예측을 제공하지 않습니다.',
         '관측망은 불균등하고 Tier B는 소표본입니다. NASA 격자 공유, 관측소 이력, 기간 중첩, 공간가중치와 '
         '모형 불안정성이 남습니다. 민감도 검사는 모든 불확실성을 제거한 것이 아닙니다.'),
        ('다음에 무엇을 할 것인가?', '우선 라이선스와 공개 범위를 승인받고 검증된 범위의 release를 마무리합니다.',
         '새 분석은 별도 질문·검증계획을 먼저 세웁니다. 이번에 수행하지 않은 예측이나 인과분석을 성과로 '
         '적지 않습니다. 공개 요약과 전체 cache 재현 모드를 구분하고 다음 단계에서도 기존 결과를 보호합니다.'),
    ]
    interview='# Interview Notes\n\n짧은 답은 약 30초용, 확장 답은 약 90초 설명의 핵심 개요입니다. 실제 발화 속도에 맞춰 조정하세요.\n\n'
    interview+='\n\n'.join('## '+q+'\n\n### 30초\n\n'+render(a)+'\n\n### 90초 확장 개요\n\n'+render(b)+
        '\n\n설명할 때 해당 근거표와 실패·한계 사례를 함께 보여주고, 직접 담당한 역할과 도구 지원 범위를 구분합니다.' for q,a,b in qa)
    pitch_ko=('이 프로젝트는 한국의 장기 기온변화를 분석하면서, 어떤 결론을 믿을 수 있는지도 함께 검증한 플랫폼입니다. '
        '공식 관측소 목록을 실제 자료 품질로 선별하고 NASA 격자자료와 KMA 지점관측을 비교했습니다. '
        '공통기간 {{common_n}}개 지점에서 평균기온 상승 방향은 일관됐습니다. 하지만 공간군집이나 상승 크기는 '
        '분석기간과 표현 방법에 따라 달라졌습니다. 이 차이를 숨기지 않고 격자 중복, 다중검정, 모형 실패를 별도로 점검했습니다. '
        '최종 보고서와 대시보드의 숫자는 원본 결과의 행·열까지 추적할 수 있습니다. 핵심 성과는 유의한 결과를 많이 찾은 것이 아니라, '
        '강건한 발견과 조건부 발견을 재현 가능한 제품으로 구분해 전달한 것입니다.')
    pitch_en=('This project examines long-term temperature change in Korea and asks which conclusions survive methodological checks. '
        'It connects quality-screened KMA observations with NASA POWER grids in a reproducible Python pipeline. '
        'Across the {{common_n}}-station common-period network, mean-temperature trends consistently increased. '
        'However, spatial clustering and trend magnitudes depended on the period and representation. '
        'I present grid sharing, multiple testing and numerical model failures as part of the evidence, not as details to hide. '
        'Every quantitative finding in the final report is linked to a saved source row and column. '
        'The result is a read-only dashboard and research package that distinguishes stable findings from conditional ones. '
        'It supports exploration and reproducibility, without claiming causal attribution or future prediction.')
    story=markdown_sections('Project Story — 약 3분 설명 개요',[
        ('문제','기온이 올랐다는 그래프만으로는 기관·지점·기간이 달라질 때 어떤 결론을 유지할 수 있는지 알기 어려웠습니다.'),
        ('데이터',scale+' 원본 cache와 정제 결과를 분리하고 실제 품질조건으로 관측망을 선별했습니다.'),
        ('파이프라인','도시별 복사 코드를 늘리는 대신 공통 수집·정제·검정 함수를 사용하고 단계별 결과를 별도 보존했습니다.'),
        ('분석','효과크기와 유의성, 일별 오차와 장기 방향, 공간구조와 해안 연관을 구분했습니다.'),
        ('예상 밖의 문제',stories),('강건성','올랐다는 방향은 일관됐지만 어느 지역이 더 빠른지, 그 속도가 얼마나 되는지는 '
         '조건에 민감했습니다. 검증 결과는 성공·비유의·실패를 함께 기록했습니다.'),
        ('성과','원자료에서 보고서 문장까지 출처를 추적하는 fact layer, 회귀 테스트와 읽기 전용 UI로 전달했습니다. '
         '이 설명은 실제 담당 역할에 맞게 조정하며 자료의 한계와 미실행 기능을 숨기지 않습니다.')])
    docs={
        'docs/FINAL_PORTFOLIO.md':portfolio,
        'docs/TECHNICAL_PORTFOLIO_SUMMARY.md':technical,
        'docs/FINAL_METHODS_SUMMARY.md':markdown_sections('Final Methods Summary',[(t,render(b)) for t,b in METHODS]+[('자료 출처',ATTRIBUTION)]),
        'docs/FINAL_LIMITATIONS.md':'# Final Limitations\n\n'+bullets(LIMITATIONS)+'\n\n'+RULES+'\n',
        'docs/REPRODUCIBILITY.md':REPRO,
        'docs/RESUME_BULLETS.md':'# Resume Bullets\n\n실제 담당 역할과 검증 가능한 기여 범위에 맞춰 사용하세요.\n\n## 한국어\n\n'+bullets(resume_ko)+'\n\n## English\n\n'+bullets(resume_en)+'\n',
        'docs/INTERVIEW_NOTES.md':interview+'\n',
        'docs/PROJECT_STORY_3MIN.md':story,
        'docs/PROJECT_PITCH_60SEC.md':'# Project Pitch — 약 60초\n\n개인 기여를 확인하고 본인의 발화 속도에 맞게 조정하세요.\n\n## 한국어\n\n'+render(pitch_ko)+'\n\n## English\n\n'+render(pitch_en)+'\n',
    }
    result='# Final Results Summary\n\n'+scale+'\n\n'+summary+'\n\n'+RULES
    for title,table in research_tables(facts,ev):result+='\n\n## '+title+'\n\n'+table_md(table)
    docs['docs/FINAL_RESULTS_SUMMARY.md']=result+'\n'
    checks=root/FINAL/'final_test_summary.csv'
    test_text='최종 전체 테스트 결과는 아직 기록 전입니다. package 생성과 검증 완료를 구분합니다.'
    if checks.is_file():
        tests=pd.read_csv(checks);test_text=f"실제 전체 pytest: {int(tests.passed.sum())}/{int(tests.collected.sum())} 통과. 출처: output/final/final_test_summary.csv."
    preview=[]
    for name in ('common_period_kma_nasa_tavg_scatter.png','kma_tavg_median_slope_by_start_year.png','nasa_station_vs_grid_moran.png'):
        source=root/registry.loc[registry.source_path.str.endswith('/'+name),'source_path'].iloc[0]
        dest=root/'docs/assets/final'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or dest.read_bytes()!=source.read_bytes():shutil.copyfile(source,dest)
        preview.append(f'![{name.replace("_"," ")}](docs/assets/final/{name})')
    docs['README.md']=markdown_sections('NASA POWER Korea Climate Explorer',[
        ('한눈에 보기','전국 장기 기온변화의 강건한 발견과 조건부 발견을 구분하는 NASA POWER × KMA ASOS 연구 플랫폼.\n\n'+scale+'\n\n'+test_text),
        ('핵심 결과',summary),('미리보기','\n\n'.join(preview)),('구조',architecture),
        ('데이터와 방법',ATTRIBUTION+'\n\nSen/MK/BH-FDR, normal/anomaly, 계절·threshold proxy, '
         'Bias/MAE/RMSE·상관, Global/Local Moran, 격자·해안·모형·기간 검증. [최종 방법](docs/FINAL_METHODS_SUMMARY.md).'),
        ('Quick Start','Python 3.11 이상. cache가 있는 프로젝트 폴더에서:\n\n```bash\npython -m venv .venv\nsource .venv/bin/activate\n'
         'python -m pip install -r requirements.txt\npython scripts/build_final_integration.py\nstreamlit run streamlit_app.py\n```\n\n'
         '최종 통합과 UI는 API를 호출하지 않습니다. 공개 요약만 있으면 재생성 명령은 생략하고 HTML 또는 Home/Reports를 열람합니다. '
         '전체 분석·테스트에는 기존 cache가 필요합니다. [재현 가이드](docs/REPRODUCIBILITY.md).'),
        ('결과물','[최종 HTML](output/final/report/'+REPORT_STEM+'.html) · [Markdown](output/final/report/'+REPORT_STEM+'.md) · '
         '[Executive Summary](output/final/EXECUTIVE_SUMMARY.md) · [Fact layer](output/final/final_research_fact_layer.csv) · '
         '[증거표](output/final/final_evidence_matrix.csv).'),
        ('해석의 한계',CAUTION+' [전체 한계](docs/FINAL_LIMITATIONS.md).'),
        ('재현성과 공개 정책','[문서 색인](docs/INDEX.md) · [원래 CLI/단계 기록](docs/STAGE_HISTORY.md) · '
         '[공개 계획](docs/GITHUB_PUBLICATION_PLAN.md) · [데이터 정책](docs/GITHUB_DATA_POLICY.md). '
         'raw/processed와 이전 대용량 결과는 기본 공개 대상이 아닙니다. 코드 라이선스는 사용자 선택 전까지 미확정이며 '
         'VERSION은 기존 값을 유지합니다. Git 초기화나 push를 하지 않았습니다.'),
        ('포트폴리오','[전체 설명](docs/FINAL_PORTFOLIO.md) · [기술 요약](docs/TECHNICAL_PORTFOLIO_SUMMARY.md) · '
         '[이력서 bullet](docs/RESUME_BULLETS.md) · [면접 질문](docs/INTERVIEW_NOTES.md) · [짧은 pitch](docs/PROJECT_PITCH_60SEC.md).')])
    for path,text in docs.items():write_text(root/path,text)
    return sorted(docs)


def publication_documents(root: Path) -> list[str]:
    """Document actual local sizes, explicit data attribution and unresolved publication choices."""
    sizes={name:sum(p.stat().st_size for p in (root/name).rglob('*') if p.is_file()) for name in ('data','output')}
    links='\n\n'.join(f'- [{name}]({url})' for name,url in OFFICIAL_LINKS.items())
    policy=markdown_sections('GitHub Data Policy',[
        ('코드와 데이터의 권리 분리','코드 LICENSE는 아직 선택하지 않았습니다. MIT 또는 Apache-2.0 등을 사용자와 검토한 후 결정합니다. '
         '코드 라이선스는 NASA·KMA·KHOA 자료의 권리를 자동 변경하지 않습니다. 원자료 재배포는 별도 검토 대상입니다.'),
        ('공식 데이터 출처',ATTRIBUTION+'\n\n'+links),
        ('공식 조건 확인','NASA는 프로젝트와 데이터 출처, 서비스명·버전·접근일을 함께 표기하고 출판·재배포 알림을 요청합니다. '
         'KMA ASOS 포털 표시는 공공저작물 출처표시 제1유형입니다. KHOA 해당 해안선 포털 표시는 이용허락범위 제한 없음입니다. '
         '이 조건을 다른 데이터셋이나 코드에 일반화하지 않습니다. 공식 문서 확인은 자료 API 재호출이 아닙니다.'),
        ('취득 metadata','취득일·제품버전·좌표계·해안선 파일 해시는 기존 metadata와 coastline manifest에 있는 값만 사용합니다. '
         '최종 fact manifest의 mtime은 취득일이 아닙니다. 누락된 서비스 버전은 UNKNOWN으로 남기고 임의 채우지 않습니다. '
         '공개 전 상세 인용문은 사용하는 cache별 metadata와 대조해야 합니다.'),
        ('기본 제외와 보존',f'data/의 논리적 파일 크기 {sizes["data"]:,} bytes입니다. 이 수치는 디스크 할당 크기가 아니라 파일 size 합계입니다. '
         'raw·processed·공식 geometry는 .gitignore로 기본 제외하며 삭제하지 않습니다. 전체 output도 final package를 제외하면 기본 제외합니다.'),
        ('선택 공개','최종 fact/evidence/보고서와 선택 차트 사본만 공개 후보로 둡니다. 원자료 샘플은 이번에 추가하지 않았습니다. '
         '요약도 데이터 출처와 proxy·표본 한계를 함께 표시합니다. 내부 QA·실행 로그·환경별 snapshot은 공개 후보에서 제외합니다.'),
        ('라이선스 결정 전','[MIT](https://opensource.org/license/mit), [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)을 '
         '선택지로만 제시하며 법적 적합성을 확정하지 않습니다. LICENSE·저작권 주체·최종 공개 승인이 없으면 실제 release는 보류합니다.')])
    plan=markdown_sections('GitHub Publication Plan',[
        ('COMMIT','사용자 공개 승인 후: src/, dashboard/, scripts/, tests/, config/, requirements.txt, '
         'streamlit_app.py, main.py, README.md, AGENTS.md, VERSION, CHANGELOG.md, .gitignore, docs/. '
         '비밀·개인 경로 검사를 통과한 파일만 대상입니다. config의 실제 credential 파일은 포함하지 않습니다.'),
        ('OPTIONAL','output/final의 facts·evidence·registry·summary·HTML/Markdown 및 report/assets, '
         'output/manifests/final_integration_manifest.json. .gitignore는 이 작은 요약을 허용하지만 실제 commit은 사용자 결정입니다. '
         'Home/Reports 요약을 사용하려면 함께 제공해야 합니다. 이전 interactive map·전체 table은 공개 승인 후 별도 배포할 수 있습니다.'),
        ('DO_NOT_COMMIT','.env 및 그 변형, .streamlit/secrets*, data/, final 이외의 output/, output/final/qa/, '
         '.venv/, cache, 개인 경로·키가 포함된 로그. 원자료와 큰 해안선 geometry는 로컬에 보존합니다.'),
        ('로컬 용량 기준',f'data/: {sizes["data"]:,} bytes; output/ 전체: {sizes["output"]:,} bytes. '
         '시점은 문서 생성 시이며 output/final 재생성으로 전체 output 크기는 조금 달라질 수 있습니다. '
         '정확한 공개후보 경로·크기는 final_public_file_inventory.csv를 따릅니다. 대용량 원자료는 기본 Git 제외입니다.'),
        ('결정과 검증','새 저장소 URL은 아직 없습니다. git init·remote·push를 수행하지 않습니다. '
         '공개 전 license 선택, VERSION 결정, 자료 인용 검토, secret scan과 파일목록 검토를 사용자가 승인해야 합니다.')])
    docs={'docs/GITHUB_DATA_POLICY.md':policy,'docs/GITHUB_PUBLICATION_PLAN.md':plan}
    groups=[('Overview',['FINAL_RESULTS_SUMMARY','FINAL_PORTFOLIO','ARCHITECTURE','STAGE_HISTORY']),
            ('Data',['GITHUB_DATA_POLICY','DATA_PIPELINE','NATIONWIDE_ASOS_SCREENING']),
            ('Methods',['FINAL_METHODS_SUMMARY','FINAL_LIMITATIONS','METHODOLOGY']),
            ('Nationwide',['NATIONWIDE_TIER_A_ANALYSIS','TIER_B_1991_2025_ANALYSIS','COMMON_PERIOD_51_STATION_ANALYSIS']),
            ('Spatial',['NATIONWIDE_SPATIAL_ANALYSIS','COMMON_PERIOD_51_STATION_SPATIAL_REANALYSIS']),
            ('Robustness',['SPATIAL_ROBUSTNESS_AND_COASTAL_ANALYSIS','SPATIAL_DEPENDENCE_ADJUSTED_MODELING','SPATIAL_MODEL_NUMERICAL_ROBUSTNESS','TREND_PERIOD_SENSITIVITY_ANALYSIS']),
            ('Portfolio',['TECHNICAL_PORTFOLIO_SUMMARY','RESUME_BULLETS','INTERVIEW_NOTES','PROJECT_STORY_3MIN','PROJECT_PITCH_60SEC']),
            ('Release',['REPRODUCIBILITY','GITHUB_PUBLICATION_PLAN','RELEASE_CHECKLIST','V1_STATUS'])]
    docs['docs/INDEX.md']=markdown_sections('Documentation Index',[(g,'\n\n'.join(f'- [{name}]({name}.md)' for name in names)) for g,names in groups])
    for path,text in docs.items():write_text(root/path,text)
    return sorted(docs)
