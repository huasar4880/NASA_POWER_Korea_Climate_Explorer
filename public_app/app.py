"""Seven public views built exclusively from saved facts, figures and a portable report."""
from __future__ import annotations

import json
import re

import pandas as pd
import streamlit as st

from public_app.data import (ROOT, DEMO, FIGURES, REPORT, REPOSITORY, RELEASE, LIMITATIONS,
    UNAVAILABLE, asset_path, load_bundle, fact_table, fact_values)

VIEWS = ('Home', 'Nationwide Trends', 'NASA × KMA Validation', 'Spatial Patterns',
         'Period Sensitivity', 'Methods / Limitations', 'Research Report')


def display_markdown(name: str) -> str:
    """Hide internal fact anchors on screen while preserving every source/download byte."""
    text = asset_path(name).read_text(encoding='utf-8')
    return re.sub(r'<!--\s*fact:[A-Za-z0-9_]+\s*-->', '', text)


@st.cache_data(show_spinner=False)
def saved_bundle() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cache immutable public CSV records between navigation events."""
    return load_bundle()


def figure(key: str, caption: str) -> None:
    """Show a selected existing PNG; never generate maps or charts at runtime."""
    path = asset_path(FIGURES[key])
    if path.is_file(): st.image(str(path), caption=caption, width='stretch')
    else: st.info(UNAVAILABLE)


def provenance(facts: pd.DataFrame, ids: list[str]) -> None:
    """Expose the saved values, units and original archive source paths for each displayed fact."""
    with st.expander('Values & provenance / 원본 근거'):
        st.dataframe(fact_table(facts, ids), hide_index=True, width='stretch')


def render(view: str) -> None:
    """Render one public view, gracefully handling a missing or damaged selected package."""
    st.title('NASA POWER Korea Climate Explorer' if view == 'Home' else view)
    try:
        facts, evidence = saved_bundle()
        v = fact_values(facts)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        st.warning('The selected public result package is unavailable or failed integrity checks.')
        st.info(UNAVAILABLE)
        return
    st.caption('PUBLIC DEMO · Validated precomputed results · No API keys or raw cache required')
    if view == 'Home':
        st.markdown('**대한민국 기온변화에서 반복되는 결과와 분석 조건에 민감한 결과를 구분합니다.**')
        st.write('KMA ASOS + NASA POWER · Long-term 1981–2025 · Common period 1991–2025')
        columns = st.columns(4)
        for col, label, fid in zip(columns, ('ASOS screened', 'Long-term stations', 'Common-period stations', 'NASA grids'),
                                  ('inventory_n', 'tier_a', 'common_n', 'grid_n')):
            col.metric(label, str(v[fid]))
        st.subheader('Key findings / 반복 확인된 결과')
        for row in evidence.loc[evidence.final_evidence_class.eq('ROBUST')].itertuples():
            st.markdown('- ' + row.statement)
        st.info('KMA의 공간군집과 기울기 크기는 기간·가중치에 민감합니다. 상관이나 공간적 연관을 인과관계로 해석하지 않습니다.')
        st.caption('Data acquisition → Quality control → Nationwide screening → Trend analysis → NASA validation → Spatial robustness → Period sensitivity')
        st.markdown(f'[GitHub]({REPOSITORY}) · [v1.1.0 Release]({RELEASE}) · '
                    f'[Methods]({REPOSITORY}/blob/main/docs/FINAL_METHODS_SUMMARY.md) · '
                    f'[Limitations]({REPOSITORY}/blob/main/docs/FINAL_LIMITATIONS.md)')
        report_download()
        figure('comparison', 'Saved common-period NASA–KMA TAVG trend comparison; °C/decade.')
    elif view == 'Nationwide Trends':
        variable = st.selectbox('Temperature variable', ('TAVG', 'TMAX', 'TMIN'))
        ids = [f'common_KMA_{variable}_{x}' for x in ('median', 'positive', 'fdr')]
        columns = st.columns(3)
        for col, label, fid in zip(columns, ('Median Sen slope (°C/decade)', 'Increasing stations', 'BH-FDR significant'), ids):
            col.metric(label, f'{v[fid]:.4f}' if fid.endswith('median') else str(v[fid]))
        st.caption('1991–2025 · KMA ASOS common-period cohort · Station median, not a national area-weighted mean.')
        figure('trends', 'Saved TMAX/TMIN trends for the common-period cohort; °C/decade.')
        provenance(facts, ids)
    elif view == 'NASA × KMA Validation':
        ids = [f'validation_TAVG_{x}' for x in ('bias', 'mae', 'rmse', 'pearson_r', 'spearman_rho')]
        st.write('공통기간 TAVG 일별 유효 관측쌍으로 계산한 지점별 검증 통계의 중앙값입니다. 전국 pooled 통계가 아닙니다.')
        st.dataframe(pd.DataFrame({'Metric': ['Bias (°C)', 'MAE (°C)', 'RMSE (°C)', 'Pearson r', 'Spearman rho'],
                                  'Saved station median': [v[x] for x in ids]}), hide_index=True)
        figure('errors', 'Saved station-level NASA–KMA Bias and RMSE; °C.')
        provenance(facts, ids)
    elif view == 'Spatial Patterns':
        for row in evidence.loc[evidence.conclusion_id.isin(['D', 'E', 'F', 'G'])].itertuples():
            st.markdown(f'**{row.final_evidence_class}** — {row.statement}')
        figure('spatial', 'Saved station-linked versus unique-grid Moran I. Unequal sample sizes; not independent station grids.')
        st.info('전체 관측소 지도·해안선 geometry·공간모형 상세 표는 연구용 환경에서 제공합니다. ' + UNAVAILABLE)
    elif view == 'Period Sensitivity':
        variable = st.selectbox('Temperature variable', ('TAVG', 'TMAX', 'TMIN'))
        years = (1981, 1986, 1991, 1996, 2001)
        ids = [f'window_{year}_KMA_{variable}_median' for year in years]
        st.dataframe(pd.DataFrame({'Start year': years, 'End year': [2025] * len(years),
            'Stored median Sen slope (°C/decade)': [v[x] for x in ids]}), hide_index=True)
        st.warning('고정 Tier A 표본의 중첩기간 비교입니다. 기울기 차이를 온난화 가속도의 증거로 단정하지 않습니다.')
        figure('period', 'Saved TAVG start-year sensitivity; °C/decade. This figure always shows TAVG.')
        provenance(facts, ids)
    elif view == 'Methods / Limitations':
        for line in LIMITATIONS: st.markdown('- ' + line)
        with st.expander('Methods / 방법', expanded=True):
            st.markdown(display_markdown('docs/FINAL_METHODS_SUMMARY.md'))
        with st.expander('Full limitations / 상세 한계'):
            st.markdown(display_markdown('docs/FINAL_LIMITATIONS.md'))
        st.caption('Code: MIT. KMA ASOS / NASA POWER / KHOA data retain provider terms and attribution requirements.')
    elif view == 'Research Report':
        st.markdown(display_markdown(DEMO + 'EXECUTIVE_SUMMARY.md'))
        report_download()
        st.download_button('Download Executive Summary', asset_path(DEMO + 'EXECUTIVE_SUMMARY.md').read_bytes(),
                           file_name='EXECUTIVE_SUMMARY.md', mime='text/markdown')
        st.caption('HTML report contains its figures and can be opened offline. No new analysis is performed.')
    else:
        st.info(UNAVAILABLE)


def report_download() -> None:
    """Offer the existing portable report as a download, not an unverified external URL."""
    path = asset_path(REPORT)
    if path.is_file():
        st.download_button('Download Final Research Report', path.read_bytes(),
            file_name=path.name, mime='text/html', key='public_final_report')
    else: st.info(UNAVAILABLE)


def run() -> None:
    """Start the public-only interface without importing any research or data acquisition module."""
    st.set_page_config(page_title='NASA POWER Korea Climate Explorer', page_icon='🌏', layout='wide')
    st.sidebar.title('Korea Climate Explorer')
    view = st.sidebar.radio('Explore research', VIEWS)
    st.sidebar.caption('PUBLIC · v1.1.0 research results · MIT code')
    st.sidebar.caption('Selected outputs only. Full research environment: APP_MODE=full.')
    render(view)
