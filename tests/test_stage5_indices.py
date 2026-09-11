"""5단계 연속일수와 Busan·Jeju warm-night 검증 테스트."""

from pathlib import Path

import pandas as pd

from src.climate_analysis import CityClimateResult
from src.climate_indices import calculate_consecutive_climate_indices
from src.config import Location
from src.stage5_analysis import build_warm_night_validation


def test_consecutive_indices_break_at_year_boundary_and_missing_values() -> None:
    """네 연속일수 지표는 연도 경계와 결측일에서 sequence를 끊는다."""

    dates = pd.date_range("2020-12-28", "2021-01-05")
    daily = pd.DataFrame(
        {
            "DATE": dates,
            "YEAR": dates.year,
            "T2M_MAX": [30, 31, 33, 34, 30, 30, float("nan"), 33, 33],
            "T2M_MIN": [25] * 9,
            "PRECTOTCORR": [0.0] * 9,
        }
    )
    indices = calculate_consecutive_climate_indices(daily).set_index("YEAR")
    assert indices.loc[2020, "max_consecutive_tmax_ge_30"] == 4
    assert indices.loc[2021, "max_consecutive_tmax_ge_30"] == 2
    assert indices.loc[2020, "max_consecutive_tmax_ge_33"] == 2
    assert indices.loc[2021, "max_consecutive_tmax_ge_33"] == 2
    assert indices.loc[2020, "max_consecutive_tmin_ge_25"] == 4
    assert indices.loc[2021, "max_consecutive_tmin_ge_25"] == 5
    assert indices.loc[2020, "max_consecutive_precip_lt_1"] == 4
    assert indices.loc[2021, "max_consecutive_precip_lt_1"] == 5


def _warm_night_result(city: str, key: str, raw_path: Path) -> CityClimateResult:
    dates = pd.date_range("1981-01-01", "2025-12-31")
    tmin = pd.Series(24.0, index=range(len(dates)))
    tmin.loc[(dates.year >= 2016) & (dates.month == 7)] = 25.0
    processed = pd.DataFrame({"DATE": dates, "YEAR": dates.year, "T2M_MIN": tmin})
    raw = pd.DataFrame({"DATE": dates.strftime("%Y%m%d"), "T2M_MIN": tmin})
    raw.to_csv(raw_path, index=False)
    annual = (
        processed.groupby("YEAR")["T2M_MIN"]
        .apply(lambda values: float((values >= 25.0).sum()))
        .rename("days_tmin_ge_25")
        .reset_index()
    )
    return CityClimateResult(
        location=Location(key=key, name=city, latitude=0.0, longitude=0.0),
        raw_path=raw_path,
        processed_path=raw_path,
        processed_data=processed,
        annual_data=annual,
        monthly_climatology=pd.DataFrame(),
        trend_data=pd.DataFrame(),
        past_vs_recent=pd.DataFrame(),
        quality=None,  # type: ignore[arg-type]
        download_source="cache",
        status_code=None,
    )


def test_busan_jeju_warm_night_validation_recomputes_annual_counts(tmp_path: Path) -> None:
    """두 도시의 raw 일자료와 연도별 threshold count가 일치하는지 재검증한다."""

    results = [
        _warm_night_result("Busan", "busan", tmp_path / "busan.csv"),
        _warm_night_result("Jeju", "jeju", tmp_path / "jeju.csv"),
    ]
    statistical = pd.DataFrame(
        [
            {
                "city": city,
                "metric": "warm_night_25",
                "linear_slope_per_decade": 1.0,
                "mk_trend": "increasing",
                "mk_tau": 0.5,
                "mk_p_value": 0.01,
                "fdr_q_value": 0.02,
                "significant_fdr": True,
                "sen_slope_per_decade": 1.0,
                "sen_ci_lower": 0.5,
                "sen_ci_upper": 1.5,
            }
            for city in ("Busan", "Jeju")
        ]
    )
    validation = build_warm_night_validation(results, statistical)
    assert len(validation) == 90
    assert validation["count_matches_stage4"].all()
    assert validation["year_complete"].all()
    assert validation["raw_fill_value_count"].eq(0).all()
    assert validation["raw_out_of_range_count"].eq(0).all()
    assert validation["first_10yr_mean_days"].eq(0.0).all()
    assert validation["last_10yr_mean_days"].gt(0.0).all()
