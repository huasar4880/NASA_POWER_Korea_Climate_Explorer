"""NASA POWER 대한민국 주요 도시 종합 기후분석 workflow 실행 진입점."""

from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from src.analysis import (
    build_annual_trend_table,
    calculate_annual_means,
    calculate_monthly_climatology,
    calculate_year_month_means,
    save_analysis_table,
    save_trend_report,
)
from src.city_analysis import (
    CityAnalysisResult,
    analyze_cities,
    analyze_city,
    build_city_annual_table,
    build_city_comparison_table,
    build_city_validation_table,
)
from src.climate_analysis import (
    CityClimateResult,
    analyze_city_climate,
    analyze_climate_cities,
    build_city_climate_summary,
    build_data_quality_summary,
    combine_city_climate_annual,
    combine_city_monthly_climatology,
    combine_city_past_vs_recent,
    parameter_metadata_table,
)
from src.config import (
    ANNUAL_CHART_PATH,
    ANNUAL_TRENDS_DATA_PATH,
    CITY_ANNUAL_COMPARISON_CHART_PATH,
    CITY_RECENT_VS_PAST_CHART_PATH,
    CITY_TEMPERATURE_HEATMAP_PATH,
    CITY_TREND_PER_DECADE_CHART_PATH,
    CITY_TRENDS_TABLE_PATH,
    CITY_VALIDATION_TABLE_PATH,
    CITY_CLIMATE_ANNUAL_PATH,
    CITY_CLIMATE_PAST_VS_RECENT_PATH,
    CITY_CLIMATE_SUMMARY_PATH,
    CITY_CLIMATE_TEMPERATURE_CHART_PATH,
    CITY_CLIMATE_TREND_HEATMAP_PATH,
    CITY_CLIMATE_ANOMALIES_PATH,
    CITY_CLIMATE_CHANGE_RANKINGS_PATH,
    CITY_CLIMATE_NORMALS_PATH,
    CITY_CLIMATE_SIGNIFICANCE_HEATMAP_PATH,
    CITY_CLIMATE_STATISTICAL_TRENDS_PATH,
    CITY_CONSECUTIVE_INDICES_PATH,
    CITY_EXTREME_HEAT_SEN_SLOPE_CHART_PATH,
    CITY_HOT_DAYS_33_CHART_PATH,
    CITY_HUMIDITY_CHART_PATH,
    CITY_MONTHLY_CLIMATOLOGY_PATH,
    CITY_PRECIPITATION_CHART_PATH,
    CITY_SOLAR_CHART_PATH,
    CITY_SEN_SLOPE_TEMPERATURE_CHART_PATH,
    CITY_SEASONAL_CLIMATE_TRENDS_PATH,
    CITY_SEASONAL_TEMPERATURE_TRENDS_CHART_PATH,
    CITY_SEASONAL_TREND_HEATMAP_PATH,
    CITY_TEMPERATURE_ANOMALY_CHART_PATH,
    CITY_TEMPERATURE_ANOMALY_HEATMAP_PATH,
    CITY_WARM_NIGHTS_25_CHART_PATH,
    CITY_WARM_NIGHT_SEN_SLOPE_CHART_PATH,
    CITY_WIND_CHART_PATH,
    BUSAN_JEJU_WARM_NIGHT_VALIDATION_PATH,
    CLIMATE_PARAMETER_METADATA_PATH,
    DATA_QUALITY_SUMMARY_PATH,
    LONG_TERM_TRENDS_CHART_PATH,
    MONTHLY_CLIMATOLOGY_CHART_PATH,
    MONTHLY_CLIMATOLOGY_PATH,
    PROCESSED_DATA_PATH,
    SETTINGS,
    TREND_REPORT_PATH,
    TREND_SUMMARY_PATH,
    YEAR_MONTH_DATA_PATH,
    YEAR_MONTH_HEATMAP_PATH,
    city_annual_data_path,
    city_annual_trends_data_path,
    city_processed_data_path,
    city_raw_data_path,
    city_trend_summary_path,
    city_climate_annual_data_path,
    city_climate_monthly_data_path,
    city_climate_processed_data_path,
    city_climate_raw_data_path,
    city_climate_summary_path,
    ensure_directories,
    load_location,
    load_locations,
)
from src.nasa_power import NasaPowerError, fetch_daily_data
from src.preprocess import load_processed_data
from src.stage5_analysis import Stage5AnalysisResult, build_stage5_analysis
from src.visualization import (
    plot_annual_mean_temperature,
    plot_city_annual_temperature_comparison,
    plot_city_recent_vs_past_temperature,
    plot_city_temperature_heatmap,
    plot_city_trend_per_decade,
    plot_city_climate_metric,
    plot_city_climate_trend_heatmap,
    plot_city_climate_significance_heatmap,
    plot_city_sen_slopes,
    plot_city_seasonal_temperature_trends,
    plot_city_seasonal_trend_heatmap,
    plot_city_temperature_anomalies,
    plot_city_temperature_anomaly_heatmap,
    plot_long_term_trends,
    plot_monthly_climatology,
    plot_year_month_heatmap,
)


def _date_range_summary(dataframe: pd.DataFrame) -> tuple[str, str]:
    """정제 DataFrame의 시작일과 종료일 문자열을 반환한다."""

    return (
        dataframe["DATE"].min().strftime("%Y-%m-%d"),
        dataframe["DATE"].max().strftime("%Y-%m-%d"),
    )


def _validate_period(dataframe: pd.DataFrame, start: date, end: date) -> None:
    """행 수와 날짜 범위가 요청 기간과 일치하는지 검증한다."""

    expected_rows = (end - start).days + 1
    actual_start = dataframe["DATE"].min().date()
    actual_end = dataframe["DATE"].max().date()
    if len(dataframe) != expected_rows:
        raise ValueError(
            f"데이터 행 수가 예상과 다릅니다: expected={expected_rows}, actual={len(dataframe)}"
        )
    if actual_start != start or actual_end != end:
        raise ValueError(
            "날짜 범위가 요청과 다릅니다: "
            f"expected={start}~{end}, actual={actual_start}~{actual_end}"
        )


def run_stage2_analysis(processed_data: pd.DataFrame | None = None) -> int:
    """기존 서울 정제 데이터를 읽어 2단계 장기추세 결과를 생성한다."""

    ensure_directories()
    daily_data = (
        processed_data.copy()
        if processed_data is not None
        else load_processed_data(PROCESSED_DATA_PATH)
    )
    _validate_period(daily_data, SETTINGS.analysis_start, SETTINGS.analysis_end)

    annual_data = calculate_annual_means(daily_data)
    annual_trends, trend_summary = build_annual_trend_table(annual_data)
    monthly_climatology = calculate_monthly_climatology(daily_data)
    year_month_data = calculate_year_month_means(daily_data)

    save_analysis_table(annual_trends, ANNUAL_TRENDS_DATA_PATH)
    save_analysis_table(trend_summary, TREND_SUMMARY_PATH)
    save_analysis_table(monthly_climatology, MONTHLY_CLIMATOLOGY_PATH)
    save_analysis_table(year_month_data, YEAR_MONTH_DATA_PATH)
    save_trend_report(trend_summary, TREND_REPORT_PATH)

    plot_long_term_trends(annual_trends, LONG_TERM_TRENDS_CHART_PATH, "Seoul")
    plot_monthly_climatology(
        monthly_climatology,
        MONTHLY_CLIMATOLOGY_CHART_PATH,
        "Seoul",
    )
    plot_year_month_heatmap(year_month_data, YEAR_MONTH_HEATMAP_PATH, "Seoul")
    return 0


def _print_city_validation(result: CityAnalysisResult) -> None:
    """도시 분석 결과의 데이터 품질 검증값을 출력한다."""

    validation = result.validation
    print(f"\n[{result.location.name}] 데이터 검증")
    print(f"- 날짜 범위: {validation.start_date} ~ {validation.end_date}")
    print(f"- 행 수: {validation.row_count:,}")
    print(
        "- 필수 컬럼: "
        f"T2M={validation.has_t2m}, "
        f"T2M_MAX={validation.has_t2m_max}, "
        f"T2M_MIN={validation.has_t2m_min}"
    )
    print(
        "- 결측치: "
        f"T2M={validation.missing_t2m}, "
        f"T2M_MAX={validation.missing_t2m_max}, "
        f"T2M_MIN={validation.missing_t2m_min}"
    )
    print(
        "- 비정상 값: "
        f"T2M={validation.abnormal_t2m}, "
        f"T2M_MAX={validation.abnormal_t2m_max}, "
        f"T2M_MIN={validation.abnormal_t2m_min}"
    )
    print(f"- 중복 날짜: {validation.duplicate_dates}")


def _create_seoul_legacy_outputs(result: CityAnalysisResult) -> None:
    """1·2단계에서 약속한 서울 전용 결과 파일을 계속 생성한다."""

    plot_annual_mean_temperature(result.annual_data, ANNUAL_CHART_PATH, "Seoul")
    run_stage2_analysis(result.processed_data)


def _print_climate_quality(result: CityClimateResult) -> None:
    """도시별 7변수 품질검사 결과를 간결하게 출력한다."""

    quality = result.quality
    print(f"\n[{result.location.name}] 4단계 데이터 품질")
    print(f"- 기간: {quality.start_date} ~ {quality.end_date}, {quality.row_count:,}행")
    print(f"- 중복 날짜: {quality.duplicate_dates}")
    print(f"- 결측치: {quality.missing_counts}")
    print(f"- fill value: {quality.fill_value_counts}")
    print(f"- 분석 제외 이상값: {quality.abnormal_counts}")


def run_city_climate_workflow(
    city_name: str,
    force_download: bool = False,
) -> int:
    """특정 도시의 4단계 7변수 종합 기후분석을 실행한다."""

    location = load_location(city_name)
    result = analyze_city_climate(location, force_download=force_download)
    _print_climate_quality(result)
    source = "NASA POWER API" if result.download_source == "api" else "climate raw 캐시"
    temperature_trend = result.trend_data.loc[
        result.trend_data["metric"] == "temperature", "trend_per_decade"
    ].iloc[0]
    print(f"- 4단계 데이터 출처: {source}")
    print(f"- T2M 장기추세: {temperature_trend:+.4f} °C/10년")
    print(f"- climate raw: {city_climate_raw_data_path(location.key)}")
    print(f"- climate processed: {city_climate_processed_data_path(location.key)}")
    print(f"- climate 연간표: {city_climate_annual_data_path(location.key)}")
    print(f"- climate 월표: {city_climate_monthly_data_path(location.key)}")
    print(f"- climate 추세표: {city_climate_summary_path(location.key)}")
    return 0


def _save_all_climate_outputs(results: list[CityClimateResult]) -> None:
    """8개 도시 종합표, 품질표와 8종 비교 그래프를 저장한다."""

    annual = combine_city_climate_annual(results)
    monthly = combine_city_monthly_climatology(results)
    past_vs_recent = combine_city_past_vs_recent(results)
    summary = build_city_climate_summary(results)
    quality = build_data_quality_summary(results)

    save_analysis_table(annual, CITY_CLIMATE_ANNUAL_PATH)
    save_analysis_table(monthly, CITY_MONTHLY_CLIMATOLOGY_PATH)
    save_analysis_table(past_vs_recent, CITY_CLIMATE_PAST_VS_RECENT_PATH)
    save_analysis_table(summary, CITY_CLIMATE_SUMMARY_PATH)
    save_analysis_table(quality, DATA_QUALITY_SUMMARY_PATH)
    save_analysis_table(parameter_metadata_table(), CLIMATE_PARAMETER_METADATA_PATH)

    plot_city_climate_metric(
        annual,
        "T2M_mean_C",
        CITY_CLIMATE_TEMPERATURE_CHART_PATH,
        "Korean Cities Annual Mean Temperature (1981-2025)",
        "Annual mean T2M (deg C)",
    )
    plot_city_climate_metric(
        annual,
        "precipitation_total_mm",
        CITY_PRECIPITATION_CHART_PATH,
        "Korean Cities Annual Precipitation (1981-2025)",
        "Annual precipitation total (mm/year)",
    )
    plot_city_climate_metric(
        annual,
        "RH2M_mean_pct",
        CITY_HUMIDITY_CHART_PATH,
        "Korean Cities Annual Mean Relative Humidity (1981-2025)",
        "Annual mean RH2M (%)",
    )
    plot_city_climate_metric(
        annual,
        "WS10M_mean_m_s",
        CITY_WIND_CHART_PATH,
        "Korean Cities Annual Mean Wind Speed (1981-2025)",
        "Annual mean WS10M (m/s)",
    )
    plot_city_climate_metric(
        annual,
        "solar_mean_kWh_m2_day",
        CITY_SOLAR_CHART_PATH,
        "Korean Cities Annual Mean Solar Irradiation (1981-2025)",
        "Mean ALLSKY_SFC_SW_DWN (kW-hr/m^2/day)",
    )
    plot_city_climate_metric(
        annual,
        "days_tmax_ge_33",
        CITY_HOT_DAYS_33_CHART_PATH,
        "33 deg C Threshold Heat-Day Proxy (NASA POWER)",
        "Days with T2M_MAX >= 33 deg C (days/year)",
    )
    plot_city_climate_metric(
        annual,
        "days_tmin_ge_25",
        CITY_WARM_NIGHTS_25_CHART_PATH,
        "25 deg C Minimum-Temperature Warm-Night Proxy (NASA POWER)",
        "Days with T2M_MIN >= 25 deg C (days/year)",
    )
    plot_city_climate_trend_heatmap(summary, CITY_CLIMATE_TREND_HEATMAP_PATH)


def _save_stage5_outputs(results: list[CityClimateResult]) -> Stage5AnalysisResult:
    """기존 processed 자료로 5단계 통계표와 8종 그래프를 생성한다."""

    stage5 = build_stage5_analysis(results)
    save_analysis_table(
        stage5.statistical_trends,
        CITY_CLIMATE_STATISTICAL_TRENDS_PATH,
        float_format="%.8g",
    )
    save_analysis_table(stage5.climate_normals, CITY_CLIMATE_NORMALS_PATH, "%.8g")
    save_analysis_table(stage5.climate_anomalies, CITY_CLIMATE_ANOMALIES_PATH, "%.8g")
    save_analysis_table(stage5.seasonal_trends, CITY_SEASONAL_CLIMATE_TRENDS_PATH, "%.8g")
    save_analysis_table(stage5.consecutive_indices, CITY_CONSECUTIVE_INDICES_PATH, "%.8g")
    save_analysis_table(stage5.rankings, CITY_CLIMATE_CHANGE_RANKINGS_PATH, "%.8g")
    save_analysis_table(
        stage5.warm_night_validation,
        BUSAN_JEJU_WARM_NIGHT_VALIDATION_PATH,
        float_format="%.8g",
    )

    plot_city_temperature_anomalies(
        stage5.climate_anomalies,
        CITY_TEMPERATURE_ANOMALY_CHART_PATH,
    )
    plot_city_temperature_anomaly_heatmap(
        stage5.climate_anomalies,
        CITY_TEMPERATURE_ANOMALY_HEATMAP_PATH,
    )
    plot_city_sen_slopes(
        stage5.statistical_trends,
        "temperature",
        CITY_SEN_SLOPE_TEMPERATURE_CHART_PATH,
        "City T2M Sen Slopes with 95% Confidence Intervals",
        "T2M Sen slope (deg C / decade)",
    )
    plot_city_sen_slopes(
        stage5.statistical_trends,
        "hot_day_33",
        CITY_EXTREME_HEAT_SEN_SLOPE_CHART_PATH,
        "33 deg C Threshold-Day Proxy Sen Slopes",
        "Sen slope (days / decade)",
    )
    plot_city_sen_slopes(
        stage5.statistical_trends,
        "warm_night_25",
        CITY_WARM_NIGHT_SEN_SLOPE_CHART_PATH,
        "25 deg C Minimum-Temperature Proxy Sen Slopes",
        "Sen slope (days / decade)",
    )
    plot_city_seasonal_temperature_trends(
        stage5.seasonal_trends,
        CITY_SEASONAL_TEMPERATURE_TRENDS_CHART_PATH,
    )
    plot_city_seasonal_trend_heatmap(
        stage5.seasonal_trends,
        CITY_SEASONAL_TREND_HEATMAP_PATH,
    )
    plot_city_climate_significance_heatmap(
        stage5.statistical_trends,
        CITY_CLIMATE_SIGNIFICANCE_HEATMAP_PATH,
    )
    return stage5


def run_all_climate_workflow(
    force_download: bool = False,
    request_interval_seconds: float = 1.0,
) -> int:
    """등록된 8개 도시의 4단계 종합 기후분석을 실행한다."""

    locations = list(load_locations().values())
    results, errors = analyze_climate_cities(
        locations,
        force_download=force_download,
        request_interval_seconds=request_interval_seconds,
    )
    if errors:
        details = "; ".join(f"{city}: {message}" for city, message in errors.items())
        raise RuntimeError(
            "일부 도시 4단계 분석에 실패했습니다. 성공한 도시 climate raw는 유지됩니다. "
            f"실패 내용: {details}"
        )
    if len(results) != len(locations):
        raise RuntimeError(f"4단계 도시 분석 수 불일치: {len(results)}/{len(locations)}")

    _save_all_climate_outputs(results)
    stage5 = _save_stage5_outputs(results)
    summary = build_city_climate_summary(results)
    print("\n4단계 도시 종합 기후요약")
    print(
        summary.loc[
            :,
            [
                "city",
                "temperature_mean",
                "temperature_trend_per_decade",
                "precipitation_annual_mean",
                "humidity_mean",
                "wind_speed_mean",
                "solar_mean",
            ],
        ].to_string(index=False)
    )
    print(f"- 종합 연간표: {CITY_CLIMATE_ANNUAL_PATH}")
    print(f"- 장기 기후요약: {CITY_CLIMATE_SUMMARY_PATH}")
    print(f"- 월 climatology: {CITY_MONTHLY_CLIMATOLOGY_PATH}")
    print(f"- 과거·최근 비교: {CITY_CLIMATE_PAST_VS_RECENT_PATH}")
    print(f"- 데이터 품질표: {DATA_QUALITY_SUMMARY_PATH}")
    significant_raw = int(stage5.statistical_trends["significant_raw"].sum())
    significant_fdr = int(stage5.statistical_trends["significant_fdr"].sum())
    print("\n5단계 기후통계 고도화 완료")
    print(
        f"- 연간 Mann-Kendall 검정: {len(stage5.statistical_trends)}개, "
        f"raw 유의={significant_raw}, FDR 유의={significant_fdr}"
    )
    print(f"- 통계 종합표: {CITY_CLIMATE_STATISTICAL_TRENDS_PATH}")
    print(f"- 1991-2020 climate normal: {CITY_CLIMATE_NORMALS_PATH}")
    print(f"- climate anomaly: {CITY_CLIMATE_ANOMALIES_PATH}")
    print(f"- 계절 추세: {CITY_SEASONAL_CLIMATE_TRENDS_PATH}")
    print(f"- 연속일수 proxy: {CITY_CONSECUTIVE_INDICES_PATH}")
    print(f"- 변수별 도시 순위: {CITY_CLIMATE_CHANGE_RANKINGS_PATH}")
    print(f"- Busan·Jeju warm-night 검증: {BUSAN_JEJU_WARM_NIGHT_VALIDATION_PATH}")
    return 0


def run_city_workflow(
    city_name: str,
    force_download: bool = False,
    connection_test: bool = False,
) -> int:
    """지정한 도시 한 곳을 다운로드·정제·분석한다."""

    ensure_directories()
    location = load_location(city_name)
    raw_path = city_raw_data_path(location.key)
    print(f"분석 위치: {location.name} ({location.latitude}, {location.longitude})")

    if connection_test and (force_download or not raw_path.exists()):
        print("NASA POWER API 연결 테스트: 2020-01-01 ~ 2025-12-31")
        connection = fetch_daily_data(
            location.latitude,
            location.longitude,
            SETTINGS.test_start,
            SETTINGS.test_end,
        )
        print(f"연결 테스트 성공: HTTP {connection.status_code}, {len(connection.dataframe):,}행")

    result = analyze_city(location, force_download=force_download)
    source_text = "NASA POWER API" if result.download_source == "api" else "기존 raw 캐시"
    print(f"데이터 출처: {source_text}")
    _print_city_validation(result)

    if location.key == "seoul":
        _create_seoul_legacy_outputs(result)

    t2m_trend = result.trend_summary.loc[result.trend_summary["PARAMETER"] == "T2M"].iloc[0]
    print(f"- T2M 추세: {t2m_trend['CHANGE_C_PER_DECADE']:+.4f} °C/10년")
    print(f"- raw CSV: {city_raw_data_path(location.key)}")
    print(f"- processed CSV: {city_processed_data_path(location.key)}")
    print(f"- 연평균 CSV: {city_annual_data_path(location.key)}")
    print(f"- 연간 추세 CSV: {city_annual_trends_data_path(location.key)}")
    print(f"- 회귀 요약 CSV: {city_trend_summary_path(location.key)}")
    run_city_climate_workflow(location.name, force_download)
    return 0


def run_all_city_workflow(
    force_download: bool = False,
    request_interval_seconds: float = 1.0,
) -> int:
    """locations.json의 모든 도시를 분석하고 전국 비교 결과를 생성한다."""

    ensure_directories()
    locations = list(load_locations().values())
    print(f"전체 도시 분석: {', '.join(location.name for location in locations)}")
    results, errors = analyze_cities(
        locations,
        force_download=force_download,
        request_interval_seconds=request_interval_seconds,
    )

    if results:
        validation_table = build_city_validation_table(results)
        save_analysis_table(validation_table, CITY_VALIDATION_TABLE_PATH)
    if errors:
        details = "; ".join(f"{city}: {message}" for city, message in errors.items())
        raise RuntimeError(
            "일부 도시 분석에 실패했습니다. 성공한 도시 파일은 유지되며 재실행 시 raw 캐시를 "
            f"재사용합니다. 실패 내용: {details}"
        )
    if len(results) != len(locations):
        raise RuntimeError(f"도시 분석 수가 예상과 다릅니다: {len(results)}/{len(locations)}")

    comparison = build_city_comparison_table(results)
    city_annual = build_city_annual_table(results)
    save_analysis_table(comparison, CITY_TRENDS_TABLE_PATH)
    plot_city_annual_temperature_comparison(city_annual, CITY_ANNUAL_COMPARISON_CHART_PATH)
    plot_city_trend_per_decade(comparison, CITY_TREND_PER_DECADE_CHART_PATH)
    plot_city_recent_vs_past_temperature(comparison, CITY_RECENT_VS_PAST_CHART_PATH)
    plot_city_temperature_heatmap(city_annual, CITY_TEMPERATURE_HEATMAP_PATH)

    seoul_result = next(result for result in results if result.location.key == "seoul")
    _create_seoul_legacy_outputs(seoul_result)

    print("\n도시 비교 분석 결과")
    print(
        comparison.loc[
            :, ["city", "mean_temperature", "temperature_difference", "trend_per_decade"]
        ].to_string(index=False)
    )
    print(f"- 도시 비교표: {CITY_TRENDS_TABLE_PATH}")
    print(f"- 데이터 검증표: {CITY_VALIDATION_TABLE_PATH}")
    print(f"- 연평균 비교 그래프: {CITY_ANNUAL_COMPARISON_CHART_PATH}")
    print(f"- 10년당 추세 그래프: {CITY_TREND_PER_DECADE_CHART_PATH}")
    print(f"- 과거·최근 비교 그래프: {CITY_RECENT_VS_PAST_CHART_PATH}")
    print(f"- 도시×연도 heatmap: {CITY_TEMPERATURE_HEATMAP_PATH}")
    run_all_climate_workflow(force_download, request_interval_seconds)
    return 0


def run_workflow(force_download: bool = False) -> int:
    """기존 기본 실행과 호환되는 서울 전체 workflow를 실행한다."""

    return run_city_workflow("Seoul", force_download, connection_test=True)


def parse_args() -> argparse.Namespace:
    """단일 도시, 전체 도시 및 기존 2단계 실행 인수를 파싱한다."""

    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--city", help="locations.json의 특정 도시 이름을 분석합니다.")
    mode.add_argument("--all", action="store_true", help="등록된 모든 도시를 분석합니다.")
    mode.add_argument(
        "--stage2-only",
        action="store_true",
        help="기존 서울 processed CSV로 2단계 output만 생성합니다.",
    )
    mode.add_argument(
        "--nationwide-stations",
        action="store_true",
        help="KMA 공식 metadata에서 전국 ASOS station inventory를 생성합니다.",
    )
    mode.add_argument(
        "--screen-nationwide-asos",
        action="store_true",
        help="전국 ASOS availability·기온 completeness를 screening합니다.",
    )
    mode.add_argument(
        "--analyze-nationwide-tier-a",
        action="store_true",
        help="10단계 Final Tier A station의 1981~2025 전국 기온분석을 실행합니다.",
    )
    mode.add_argument(
        "--analyze-nationwide-station",
        metavar="STATION_ID",
        help="debugging 목적으로 Final Tier A station 한 곳을 분석합니다.",
    )
    mode.add_argument(
        "--report-nationwide",
        action="store_true",
        help="저장된 전국 Tier A 결과표만 읽어 종합보고서를 생성합니다.",
    )
    mode.add_argument(
        "--analyze-spatial",
        action="store_true",
        help="저장된 Final Tier A 결과로 전국 공간 기후패턴을 분석합니다.",
    )
    mode.add_argument(
        "--report-spatial",
        action="store_true",
        help="저장된 공간분석 결과표만 읽어 Stage-12 보고서를 생성합니다.",
    )
    mode.add_argument('--analyze-spatial-robustness', action='store_true', help='Stage-13 공간 강건성·해안성 분석 (저장자료만 사용)')
    mode.add_argument('--report-spatial-robustness', action='store_true', help='저장된 Stage-13 보고서 생성')
    mode.add_argument('--analyze-spatial-models', action='store_true', help='Stage-14 공간보정 모델 분석 (저장자료만 사용)')
    mode.add_argument('--report-spatial-models', action='store_true', help='저장된 Stage-14 보고서 생성')
    mode.add_argument('--analyze-tier-b', action='store_true', help='독립 Tier B 1991–2025 기온분석')
    mode.add_argument('--report-tier-b', action='store_true', help='저장된 Tier B 결과만으로 보고서 생성')
    mode.add_argument('--analyze-common-period', action='store_true', help='Tier A+B 1991–2025 공통기간 재분석')
    mode.add_argument('--report-common-period', action='store_true', help='저장된 공통기간 결과 보고서 생성')
    mode.add_argument('--analyze-period-sensitivity', action='store_true', help='Stage18 고정 Tier A 시작연도 민감성 (저장자료만 사용)')
    mode.add_argument('--report-period-sensitivity', action='store_true', help='저장된 Stage18 기간 민감성 보고서 생성')
    mode.add_argument('--analyze-common-period-spatial', action='store_true', help='Stage17 공통기간 공간 재분석 (저장자료만 사용)')
    mode.add_argument('--report-common-period-spatial', action='store_true', help='저장된 Stage17 공간 재분석 보고서 생성')
    kma_action = parser.add_mutually_exclusive_group()
    kma_action.add_argument(
        "--validate-kma",
        action="store_true",
        help="기존 NASA processed와 KMA ASOS 일자료를 교차검증합니다.",
    )
    kma_action.add_argument(
        "--download-kma",
        action="store_true",
        help="KMA ASOS raw 데이터만 다운로드하거나 캐시를 확인합니다.",
    )
    kma_action.add_argument(
        "--report", action="store_true",
        help="저장된 결과 CSV만 읽어 HTML/Markdown 보고서를 생성합니다(--city 또는 --all).",
    )
    kma_action.add_argument(
        "--report-comparison", action="store_true",
        help="저장된 결과 CSV만 읽어 8개 도시 비교보고서를 생성합니다.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="기존 raw 파일이 있어도 API에서 다시 다운로드합니다.",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=1.0,
        help="전체 도시 NASA/KMA 신규 API 요청 사이의 대기시간(초, 기본 1.0)입니다.",
    )
    parser.add_argument(
        "--refresh-stations",
        action="store_true",
        help="--nationwide-stations/--screen-nationwide-asos에서 공식 metadata cache를 갱신합니다.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="전국 screening의 후보·예상 요청량만 계산하고 ASOS daily API는 호출하지 않습니다.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="이번 실행에서 상세 screening할 미완료 Tier A/B station 최대 수입니다.",
    )
    parser.add_argument(
        "--sample-stations",
        action="store_true",
        help="서울과 metadata 유형별 외부 station 표본만 screening합니다.",
    )
    return parser.parse_args()


def main() -> int:
    """명령행 실행 오류를 이해하기 쉬운 메시지로 보고한다."""

    args = parse_args()
    try:
        if args.refresh_stations and not (args.nationwide_stations or args.screen_nationwide_asos):
            raise ValueError("--refresh-stations는 전국 ASOS 명령과 함께 사용하세요.")
        if args.dry_run and not (
            args.screen_nationwide_asos
            or args.analyze_nationwide_tier_a
            or args.analyze_nationwide_station
            or args.analyze_spatial
            or args.analyze_spatial_robustness
            or args.analyze_spatial_models
            or args.analyze_tier_b
            or args.analyze_common_period
            or args.analyze_common_period_spatial
            or args.analyze_period_sensitivity
        ):
            raise ValueError("--dry-run은 전국 screening, Tier A 또는 공간분석 명령과 함께 사용하세요.")
        if (args.batch_size or args.sample_stations) and not args.screen_nationwide_asos:
            raise ValueError("--batch-size/--sample-stations는 --screen-nationwide-asos 전용입니다.")
        if args.batch_size is not None and args.batch_size < 1:
            raise ValueError("--batch-size는 1 이상이어야 합니다.")
        if args.analyze_period_sensitivity or args.report_period_sensitivity:
            if any((args.validate_kma, args.download_kma, args.report, args.report_comparison, args.force_download)):
                raise ValueError('Stage18은 기존 도시/KMA/force/report 옵션과 결합할 수 없습니다.')
            from src.period_sensitivity.workflow import run_analysis
            from src.period_sensitivity.artifacts import report_from_saved
            import json
            if args.report_period_sensitivity:
                print('\n'.join(report_from_saved()))
            else:
                result = run_analysis(dry_run=args.dry_run)
                keys = ('status', 'station_count', 'unique_NASA_grid_count', 'total_trend_fits',
                        'NASA_API_calls', 'KMA_API_calls', 'protected_files_changed', 'output_files')
                print(json.dumps(result if args.dry_run else {k: result[k] for k in keys}, ensure_ascii=False, indent=2))
            return 0
        if args.analyze_common_period_spatial or args.report_common_period_spatial:
            if any((args.validate_kma, args.download_kma, args.report, args.report_comparison, args.force_download)):
                raise ValueError('Stage17은 기존 도시/KMA/force/report 옵션과 결합할 수 없습니다.')
            from src.common_period_spatial.workflow import run_analysis
            from src.common_period_spatial.artifacts import report_from_saved
            import json
            if args.report_common_period_spatial:
                print('\n'.join(report_from_saved()))
            else:
                result = run_analysis(dry_run=args.dry_run)
                keys = ('status', 'station_count', 'unique_NASA_grid_count', 'NASA_API_calls', 'KMA_API_calls',
                        'shared_grid_groups', 'protected_files_changed', 'output_files')
                print(json.dumps(result if args.dry_run else {k: result[k] for k in keys}, ensure_ascii=False, indent=2))
            return 0
        if args.analyze_common_period or args.report_common_period:
            if any((args.validate_kma, args.download_kma, args.report, args.report_comparison, args.force_download)):
                raise ValueError('공통기간 분석은 기존 도시/KMA/force/report 옵션과 결합할 수 없습니다.')
            from src.common_period.workflow import run_analysis
            from src.common_period.artifacts import report_from_saved
            import json
            if args.report_common_period:
                print('\n'.join(report_from_saved()))
            else:
                result = run_analysis(dry_run=args.dry_run)
                print(json.dumps(result if args.dry_run else {k: result[k] for k in (
                    'status', 'tier_a_count', 'tier_b_count', 'station_count', 'NASA_API_calls', 'KMA_API_calls',
                    'unique_NASA_grid_count', 'shared_grid_groups', 'tier_b_reproduction_passed',
                    'protected_files_changed', 'output_files')}, ensure_ascii=False, indent=2))
            return 0
        if args.analyze_tier_b or args.report_tier_b:
            if any((args.validate_kma, args.download_kma, args.report, args.report_comparison, args.force_download)):
                raise ValueError('Tier B는 기존 도시/KMA/force/report 옵션과 결합할 수 없습니다.')
            from src.tier_b.workflow import run_analysis
            from src.tier_b.artifacts import report_from_saved
            import json
            if args.report_tier_b:
                print('\n'.join(report_from_saved()))
            else:
                result = run_analysis(dry_run=args.dry_run, interval=args.request_interval)
                print(json.dumps(result if args.dry_run else {k: result[k] for k in (
                    'status', 'station_count', 'NASA_API_calls', 'KMA_API_calls', 'protected_files_changed', 'output_files')},
                    ensure_ascii=False, indent=2))
            return 0
        if args.analyze_spatial_models or args.report_spatial_models:
            if any((args.validate_kma, args.download_kma, args.report, args.report_comparison, args.force_download)):
                raise ValueError('Stage-14는 다운로드·KMA·다른 보고서 옵션과 결합할 수 없습니다.')
            from src.spatial_models.workflow import run_modeling, report_from_saved
            if args.report_spatial_models:
                print('\n'.join(report_from_saved()))
            else:
                import json
                result = run_modeling(dry_run=args.dry_run)
                visible = result if args.dry_run else {key: result[key] for key in (
                    'station_count','main_unique_fits','longitude_sensitivity_fits','loo_fits',
                    'NASA_API_calls','KMA_API_calls','failed_models','protected_files_changed',
                    'generated_tables','generated_charts','generated_reports')}
                print(json.dumps(visible, ensure_ascii=False, indent=2))
                if not args.dry_run and result['failed_models']:
                    print('일부 공간모형 실패/불안정: spatial_model_failures.csv를 확인하세요.')
                    return 1
            return 0
        if args.analyze_spatial_robustness or args.report_spatial_robustness:
            if any((args.validate_kma, args.download_kma, args.report, args.report_comparison, args.force_download)):
                raise ValueError('Stage-13는 다운로드·KMA·다른 보고서 옵션과 결합할 수 없습니다.')
            from src.spatial.robustness_workflow import run_robustness, report_from_saved
            if args.report_spatial_robustness:
                print('\n'.join(report_from_saved()))
            else:
                result = run_robustness(dry_run=args.dry_run)
                print(f"Stage-13 {'dry-run' if args.dry_run else '분석'} 완료: {result['station_count']} stations, {len(result['weight_configurations'])} weights")
                print('NASA API: 0 / KMA API: 0')
                if not args.dry_run:
                    print(f"Coastal available: {result['coastline']['available']}")
                    print('Manifest: output/manifests/spatial_robustness_manifest.json')
            return 0
        if args.report_nationwide:
            if any((
                args.validate_kma, args.download_kma, args.report, args.report_comparison,
                args.force_download, args.dry_run,
            )):
                raise ValueError("--report-nationwide는 저장 결과만 사용하는 독립 명령입니다.")
            from src.nationwide.tier_a_workflow import generate_report_from_saved_tables

            html_path, markdown_path = generate_report_from_saved_tables()
            print("전국 Tier A 종합보고서 생성 완료 (API 호출 없음)")
            print(f"- HTML: {html_path}")
            print(f"- Markdown: {markdown_path}")
            return 0
        if args.report_spatial:
            if any((
                args.validate_kma, args.download_kma, args.report, args.report_comparison,
                args.force_download, args.dry_run,
            )):
                raise ValueError("--report-spatial은 저장 결과만 사용하는 독립 명령입니다.")
            from src.spatial.spatial_workflow import generate_spatial_report_from_saved_tables

            html_path, markdown_path = generate_spatial_report_from_saved_tables()
            print("전국 공간 기후패턴 보고서 생성 완료 (API 호출 없음)")
            print(f"- HTML: {html_path}")
            print(f"- Markdown: {markdown_path}")
            return 0
        if args.analyze_spatial:
            if any((
                args.validate_kma, args.download_kma, args.report, args.report_comparison,
                args.force_download,
            )):
                raise ValueError("공간분석은 다운로드·KMA·기존 보고서 옵션과 함께 실행할 수 없습니다.")
            from src.spatial.spatial_data import INPUT_PATHS
            from src.spatial.spatial_workflow import expected_spatial_outputs, run_spatial_analysis

            result = run_spatial_analysis(dry_run=args.dry_run)
            print("전국 공간 기후패턴 분석 실행계획" if result.dry_run else "전국 공간 기후패턴 분석 완료")
            print(f"- input station 수: {result.station_count}")
            print(f"- input tables: {', '.join(path.name for path in INPUT_PATHS.values())}")
            print(
                f"- spatial weight: {result.config['spatial_weights_method']}, "
                f"k={result.config['knn_k']}"
            )
            print(f"- coastline analysis available: {result.coastline.available}")
            print(f"- coastline status: {result.coastline.reason}")
            print("- NASA/KMA API calls: 0")
            if result.dry_run:
                print("- expected outputs:")
                for path in expected_spatial_outputs():
                    print(f"  - {path}")
                print("dry-run 완료: 분석파일을 수정하지 않았습니다.")
                return 0
            assert result.products is not None
            tavg = result.products.global_morans.loc[
                result.products.global_morans["variable"].eq("kma_tavg_sen_slope")
            ].iloc[0]
            print(
                f"- KMA TAVG Global Moran: I={tavg['moran_i']:.6f}, "
                f"permutation p={tavg['permutation_p']:.4f}"
            )
            print(f"- tables: {len(result.table_paths)}개")
            print(f"- maps/charts: {len(result.chart_paths)}개")
            if result.report_paths:
                print(f"- report HTML: {result.report_paths[0]}")
                print(f"- report Markdown: {result.report_paths[1]}")
            print(f"- manifest: {result.manifest_path}")
            return 0
        if args.analyze_nationwide_tier_a or args.analyze_nationwide_station:
            if any((args.validate_kma, args.download_kma, args.report, args.report_comparison)):
                raise ValueError("전국 Tier A 분석과 기존 KMA·보고서 작업을 함께 실행할 수 없습니다.")
            from src.nationwide.tier_a_pipeline import build_download_plan, load_tier_a_stations
            from src.nationwide.tier_a_workflow import run_nationwide_tier_a

            station_id = args.analyze_nationwide_station
            selected = load_tier_a_stations()
            if station_id is not None:
                selected = selected.loc[selected["station_id"].astype(str).eq(str(station_id))]
                if selected.empty:
                    raise KeyError(f"Final Tier A에 없는 station ID입니다: {station_id}")
            plan = build_download_plan(selected)
            print("전국 Tier A 기온분석 실행계획")
            print(f"- station 수: {plan.station_count}")
            print(f"- NASA cache hit: {plan.cache_hits}")
            print(f"- 신규 download 필요: {plan.downloads_needed}")
            print(f"- 예상 NASA API 요청: {plan.estimated_api_requests}")
            if args.dry_run:
                print("dry-run 완료: NASA/KMA API를 호출하지 않았습니다.")
                return 0
            result = run_nationwide_tier_a(
                force_nasa=args.force_download,
                request_interval_seconds=args.request_interval,
                station_id=station_id,
                publish=station_id is None,
            )
            print("전국 Tier A 기온분석 완료")
            print(f"- prepared station: {result.prepared_count}")
            print(f"- NASA cache hit: {result.cache_hits}")
            print(f"- 실제 NASA API 요청: {result.api_calls}")
            if result.products is not None:
                tavg = result.products.summary["kma_tavg_sen_slope_decade"]
                print(f"- KMA TAVG Sen slope median: {tavg.median():+.4f} °C/10년")
            for name, path in result.table_paths.items():
                print(f"- table {name}: {path}")
            for name, path in result.map_paths.items():
                print(f"- map {name}: {path}")
            if result.report_paths:
                print(f"- report HTML: {result.report_paths[0]}")
                print(f"- report Markdown: {result.report_paths[1]}")
            return 0
        if args.nationwide_stations or args.screen_nationwide_asos:
            if any((args.validate_kma, args.download_kma, args.report, args.report_comparison, args.force_download)):
                raise ValueError("전국 station screening과 기존 다운로드·validation·보고서 옵션을 함께 사용할 수 없습니다.")
            from src.nationwide.nationwide_workflow import (
                CONTINUITY_REVIEW_PATH,
                HISTORY_FLAGS_PATH,
                INVENTORY_MAP_PATH,
                MASTER_PATH,
                REGIONAL_COVERAGE_PATH,
                SCREENING_SUMMARY_PATH,
                SHORTLIST_PATH,
                build_nationwide_inventory,
                run_nationwide_screening,
            )

            if args.nationwide_stations:
                result = build_nationwide_inventory(refresh=args.refresh_stations)
                inventory = result.inventory
                print(f"공식 ASOS station inventory 완료: {len(inventory):,}개 고유 station")
                print(f"- metadata source: {result.metadata.source}")
                print(f"- official history segments: {len(result.metadata.segments):,}")
                print(f"- active: {int(inventory['is_active'].sum()):,}")
                print(f"- historical/inactive: {int((~inventory['is_active']).sum()):,}")
                print(f"- inventory: {result.metadata.inventory.shape[0]:,}행")
                print(f"- history flags: {HISTORY_FLAGS_PATH}")
                print(f"- continuity review: {CONTINUITY_REVIEW_PATH}")
                return 0

            from src.kma_asos import KmaApiKeyError, get_kma_api_key

            api_key: str | None
            try:
                api_key = get_kma_api_key()
            except KmaApiKeyError:
                api_key = None
            result = run_nationwide_screening(
                api_key=api_key,
                refresh_stations=args.refresh_stations,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                sample_only=args.sample_stations,
                request_interval_seconds=args.request_interval,
            )
            estimates = result.estimates
            print(f"ASOS stations discovered: {estimates['asos_stations']}")
            print(f"Preliminary Tier A/B candidates: {estimates['preliminary_tier_ab']}")
            print(f"Detailed screening stations: {estimates['detailed_screening_stations']}")
            print(f"Estimated API requests: {estimates['estimated_api_requests']}")
            print("Detailed periods: Tier A=1981-01-01~2025-12-31; Tier B=1991-01-01~2025-12-31 또는 종료 station은 2020-12-31")
            if result.dry_run:
                print("dry-run 완료: ASOS daily API를 호출하지 않았습니다.")
                return 0
            if result.daily_screening_skipped:
                print("KMA_API_KEY가 없어 실제 daily availability screening은 수행하지 않았습니다.")
                return 0
            summary = result.summary.iloc[0]
            print(f"전국 ASOS screening 완료: Tier A={summary['final_tier_a']}, Tier B={summary['final_tier_b']}")
            print(f"- actual daily API requests: {result.actual_api_requests}")
            if args.sample_stations:
                print("- 표본 결과는 진단 전용이며 기존 전국 master/shortlist를 변경하지 않았습니다.")
                return 0
            print(f"- master: {MASTER_PATH}")
            print(f"- shortlist: {SHORTLIST_PATH}")
            print(f"- summary: {SCREENING_SUMMARY_PATH}")
            print(f"- regional coverage: {REGIONAL_COVERAGE_PATH}")
            print(f"- station map: {INVENTORY_MAP_PATH}")
            return 0
        if args.report or args.report_comparison:
            if args.force_download or args.stage2_only:
                raise ValueError("보고서 생성은 다운로드·분석 실행과 분리되어 있습니다.")
            if args.report_comparison and args.city:
                raise ValueError("--report-comparison에는 --city를 지정하지 마세요.")
            if args.report and not (args.city or args.all):
                raise ValueError("--report에는 --city CITY 또는 --all을 지정하세요.")
            from reporting.report_builder import generate_reports
            from src.config import PROJECT_ROOT

            reports = generate_reports(
                PROJECT_ROOT, city=args.city, all_cities=args.all,
                comparison_only=args.report_comparison,
            )
            print(f"기후분석 보고서 생성 완료: {len(reports)}종 (API 호출 없음)")
            for report in reports:
                print(f"- HTML: {report.html_path}")
                print(f"- Markdown: {report.markdown_path}")
                print(f"- Manifest: {report.manifest_path}")
            return 0
        if (args.validate_kma or args.download_kma) and args.stage2_only:
            raise ValueError("KMA 작업과 --stage2-only는 함께 사용할 수 없습니다.")
        if args.validate_kma or args.download_kma:
            from src.kma_asos import KmaApiKeyError, KmaAsosClient, get_kma_api_key

            if not (args.city or args.all):
                raise ValueError("KMA 작업에는 --city CITY 또는 --all을 지정하세요.")
            try:
                api_key = get_kma_api_key()
            except KmaApiKeyError as exc:
                skipped_action = "validation" if args.validate_kma else "download"
                print(
                    f"{exc}\nKMA API key가 없어 ASOS {skipped_action}을 실행하지 않았습니다.",
                    file=sys.stderr,
                )
                return 0
            from src.kma_workflow import (
                all_kma_city_names,
                run_kma_downloads,
                run_kma_validation,
            )

            client = KmaAsosClient(api_key)
            city_names = all_kma_city_names() if args.all else [args.city]
            if args.download_kma:
                downloads = run_kma_downloads(
                    city_names,
                    client=client,
                    force_download=args.force_download,
                    request_interval_seconds=args.request_interval,
                )
                print("KMA ASOS raw 다운로드/캐시 확인 완료")
                for result in downloads:
                    print(f"- {result.path} ({result.source}, {len(result.dataframe):,}행)")
                return 0
            results, outputs = run_kma_validation(
                city_names,
                client=client,
                force_download=args.force_download,
                request_interval_seconds=args.request_interval,
            )
            print(f"NASA POWER × KMA ASOS validation 완료: {len(results)}개 도시")
            for result in results:
                print(
                    f"- {result.station.city}: matched={len(result.matched):,}, "
                    f"missing_dates={result.quality.missing_dates}"
                )
            for name, path in outputs.items():
                print(f"- {name}: {path}")
            return 0
        if args.stage2_only and args.force_download:
            raise ValueError("--stage2-only와 --force-download는 함께 사용할 수 없습니다.")
        if args.stage2_only:
            return run_stage2_analysis()
        if args.all:
            return run_all_city_workflow(args.force_download, args.request_interval)
        if args.city:
            return run_city_workflow(args.city, args.force_download)
        return run_workflow(args.force_download)
    except (NasaPowerError, OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
