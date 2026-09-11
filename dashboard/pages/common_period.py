"""Sixteenth read-only dashboard page: common period and NASA grid representation."""
from __future__ import annotations

import streamlit as st
import pandas as pd
from src.common_period.artifacts import load_tables, point_map, trend_scatter
from src.common_period.data import WARNING, GRID_WARNING


def filter_summary(frame: pd.DataFrame, origins: list, regions: list, stations: list,
                   elevations: list, coastal: list, shared: str) -> pd.DataFrame:
    """Apply metadata filters without mutating saved statistics or recalculating FDR."""
    result = frame.loc[frame.cohort_origin.isin(origins) & frame.region_level1.isin(regions)
                       & frame.station_id.isin(stations) & frame.elevation_band.isin(elevations)
                       & frame.coastal_class.isin(coastal)].copy()
    if shared != '전체':
        flags = result.nasa_grid_shared.astype(str).str.lower().eq('true')
        result = result.loc[flags if shared == '공유 grid' else ~flags]
    return result


def render() -> None:
    """Render all requested sections solely from checksum-verified saved outputs."""
    st.title('51개 공통기간 분석')
    st.info(WARNING); st.warning(GRID_WARNING)
    try:
        tables = load_tables()
    except (OSError, ValueError, KeyError):
        st.info('먼저 python main.py --analyze-common-period를 완료하세요. 읽기 전용 페이지입니다.')
        return
    summary = tables['common_period_station_temperature_summary']
    master = tables['common_period_1991_2025_station_master']
    grid = tables['common_period_nasa_grid_mapping']
    for column, label, value in zip(st.columns(6), ['Stations', 'Analysis', 'Normal', 'Tier A-origin', 'Tier B-origin', 'Unique NASA grids'],
                                   [len(master), '1991–2025', '1991–2020', int(master.cohort_origin.eq('TIER_A').sum()),
                                    int(master.cohort_origin.eq('TIER_B').sum()), len(grid)]):
        column.metric(label, value)
    st.caption('NASA grid 좌표는 공식 native 격자 규격에서 추정했으며 API 반환 좌표가 아닙니다. 공유 그룹의 일별 시계열 일치를 검증했습니다.')
    filters = {}
    with st.expander('필터', expanded=True):
        for col, label in [('cohort_origin', 'Cohort origin'), ('region_level1', 'Region'), ('station_id', 'Station'),
                           ('elevation_band', 'Elevation band'), ('coastal_class', 'Coastal/Inland')]:
            options = sorted(summary[col].dropna().unique())
            filters[col] = st.multiselect(label, options, default=options)
        sharing = st.selectbox('Shared NASA grid', ['전체', '공유 grid', '단독 grid'])
    filtered = filter_summary(summary, *[filters[c] for c in ('cohort_origin', 'region_level1', 'station_id', 'elevation_band', 'coastal_class')], sharing)
    st.caption(f'필터 결과 {len(filtered)}개 station · 표시만 변경하며 common FDR family는 재계산하지 않습니다.')
    if filtered.empty:
        st.info('선택 조건에 해당하는 station이 없습니다.'); return
    st.subheader('Common-period overview'); st.dataframe(filtered, hide_index=True)
    st.subheader('KMA TAVG map'); st.plotly_chart(point_map(filtered, 'kma_tavg_sen_slope', master), key='common_tavg')
    st.subheader('KMA/NASA trend comparison'); st.plotly_chart(trend_scatter(filtered), key='common_scatter')
    with st.expander('TMAX/TMIN'):
        for metric in ('tmax', 'tmin'):
            st.plotly_chart(point_map(filtered, f'kma_{metric}_sen_slope', master), key=f'common_{metric}')
    for title, name in [('Seasonal', 'seasonal_temperature_trends'), ('Threshold proxy', 'threshold_trends'),
                        ('NASA–KMA validation', 'nasa_kma_temperature_validation'), ('Data quality', 'data_quality'),
                        ('Cohort provenance', '1991_2025_station_master')]:
        with st.expander(title):
            frame = tables[f'common_period_{name}']
            st.dataframe(frame.loc[frame.station_id.isin(filtered.station_id)], hide_index=True)
    with st.expander('NASA grid sharing'):
        st.plotly_chart(point_map(filtered, 'nasa_grid_id', master), key='common_grid')
        st.dataframe(grid.loc[grid.nasa_grid_id.isin(filtered.nasa_grid_id)], hide_index=True)
        st.dataframe(tables['common_period_nasa_station_vs_grid_summary'], hide_index=True)
    with st.expander('Anomaly heatmap'):
        from dashboard.charts import create_heatmap
        frame = tables['common_period_temperature_anomalies_1991_2025']
        frame = frame.loc[frame.station_id.isin(filtered.station_id) & frame.source.eq('KMA') & frame.metric.eq('TAVG')]
        st.plotly_chart(create_heatmap(frame, row_column='station_id', column_column='year', value_column='anomaly',
                                       title='KMA TAVG anomaly · 1991–2020 normal', colorbar_title='°C'), key='common_anomaly')
    st.subheader('Limitations')
    st.write('Origin은 품질 우열·기후학적 집단이 아닙니다. 작은 Tier B 표본, grid 공유, 점/격자 차이를 고려하세요. '
             'Threshold는 공식 폭염/열대야 통계가 아니며 correlation은 정확도와 다릅니다. '
             '이번 단계는 공간모형·예측·보간·기후위험 종합순위를 제공하지 않습니다.')
