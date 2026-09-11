"""Fact-bound landing section; small published summaries work without raw data."""
from __future__ import annotations

import json

import streamlit as st

from src.config import PROJECT_ROOT
from src.final_integration.content import CAUTION,HIGHLIGHTS,TITLE,plain
from src.final_integration.facts import FINAL,values
from src.final_integration.workflow import load_final


def render_final_home() -> None:
    """Display verified saved facts, interpretation limits and navigation guidance only."""
    st.title(TITLE)
    st.caption('FINAL RESEARCH · 저장 결과 읽기 전용 · 새 분석·NASA/KMA API 호출 없음')
    try:facts,evidence=load_final(PROJECT_ROOT)
    except (OSError,ValueError,KeyError,json.JSONDecodeError):
        st.info('최종 요약이 없거나 검증되지 않았습니다. 원래 분석 페이지는 그대로 이용할 수 있습니다.')
        return
    v=values(facts)
    columns=st.columns(4)
    for col,(label,fid) in zip(columns,[('공식 ASOS inventory','inventory_n'),('장기 Tier A','tier_a'),
                                      ('공통기간 관측소','common_n'),('공통기간 NASA 고유 격자','grid_n')]):
        col.metric(label,str(v[fid]))
    st.caption(plain('장기 {{long_period}} · 공통기간 {{common_period}} · Climate Normal {{normal}}',facts,False))
    st.warning(CAUTION)
    st.subheader('무엇이 유지되고, 무엇이 달라지는가?')
    for text in HIGHLIGHTS:st.markdown('- '+plain(text,facts,False))
    with st.expander('검증 축과 증거 등급'):
        st.dataframe(evidence[['conclusion_id','statement','final_evidence_class']],hide_index=True)
    st.subheader('탐색 안내')
    st.markdown('**CORE ANALYSIS**에서 관측망·기온추세 → **VALIDATION**에서 NASA–KMA 비교 → '
                '**SPATIAL**에서 공간구조 → **ROBUSTNESS**에서 기간·격자·모형 한계 → '
                '**METHODS / REPORTS**에서 근거와 보고서를 확인하세요.')
    st.caption('연구 흐름: 원본 cache → 품질 screening → 추세·validation → 공간·기간 검증 → fact·evidence → 최종 보고서')
    path=PROJECT_ROOT/FINAL/'EXECUTIVE_SUMMARY.md'
    if not path.is_file():path=PROJECT_ROOT/'output/public_demo/EXECUTIVE_SUMMARY.md'
    if path.is_file():st.download_button('Executive Summary 다운로드',path.read_bytes(),file_name=path.name,mime='text/markdown',key='final_home_executive')
