"""Unit tests for read-only dashboard data, filters, downloads, and charts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from dashboard.charts import (
    create_anomaly_chart,
    create_heatmap,
    create_sen_slope_ci_chart,
    create_timeseries_chart,
)
from dashboard.data_loader import DashboardDataError, load_annual_climate_data, load_csv
from dashboard.filters import (
    build_download_dataframe,
    dataframe_to_csv_bytes,
    filter_cities,
    filter_metric,
    filter_seasonal,
    filter_statistical_trends,
    filter_years,
    prepare_chart_dataframe,
)


@pytest.fixture
def annual_sample() -> pd.DataFrame:
    """Return a compact two-city annual table."""

    return pd.DataFrame(
        {
            "city": ["Seoul", "Seoul", "Busan", "Busan"],
            "YEAR": [1981, 1982, 1981, 1982],
            "T2M_mean_C": [10.0, 11.0, 15.0, 16.0],
            "solar_mean_kWh_m2_day": [float("nan"), float("nan"), float("nan"), 4.0],
        }
    )


def test_dashboard_csv_loader_validates_schema(tmp_path) -> None:
    """The cached loader reads valid CSVs and reports missing columns."""

    path = tmp_path / "sample.csv"
    path.write_text("city,YEAR\nSeoul,1981\n", encoding="utf-8")
    loaded = load_csv(path, ("city", "YEAR"))
    assert loaded.to_dict("records") == [{"city": "Seoul", "YEAR": 1981}]
    with pytest.raises(DashboardDataError, match="필요한 컬럼"):
        load_csv(path, ("T2M",))
    with pytest.raises(DashboardDataError, match="데이터 파일이 없습니다"):
        load_csv(tmp_path / "missing.csv")

    empty_path = tmp_path / "empty.csv"
    empty_path.write_text("city,YEAR\n", encoding="utf-8")
    with pytest.raises(DashboardDataError, match="CSV가 비어 있습니다"):
        load_csv(empty_path)


def test_city_metric_and_year_filters(annual_sample) -> None:
    """City and inclusive year filters retain only requested rows."""

    seoul = filter_cities(annual_sample, ["Seoul"])
    year = filter_years(seoul, 1982, 1982)
    assert year[["city", "YEAR"]].to_dict("records") == [{"city": "Seoul", "YEAR": 1982}]

    metrics = pd.DataFrame({"metric": ["temperature", "wind"], "value": [1, 2]})
    assert filter_metric(metrics, "wind")["value"].tolist() == [2]


def test_seasonal_filtering() -> None:
    """Seasonal filtering combines city, metric, and season selections."""

    data = pd.DataFrame(
        {
            "city": ["Seoul", "Seoul", "Busan"],
            "metric": ["temperature", "wind", "temperature"],
            "season": ["DJF", "JJA", "DJF"],
        }
    )
    result = filter_seasonal(data, ["Seoul"], "temperature", "DJF")
    assert result.to_dict("records") == [
        {"city": "Seoul", "metric": "temperature", "season": "DJF"}
    ]


def test_solar_nan_is_not_converted_to_zero(annual_sample) -> None:
    """Chart preparation removes missing solar rows instead of inventing zeroes."""

    prepared = prepare_chart_dataframe(
        annual_sample,
        ["city", "YEAR", "solar_mean_kWh_m2_day"],
        sort_by=["YEAR"],
    )
    assert prepared["solar_mean_kWh_m2_day"].tolist() == [4.0]
    assert 0.0 not in prepared["solar_mean_kWh_m2_day"].tolist()

    real_annual = load_annual_climate_data()
    early = real_annual.loc[real_annual["YEAR"].between(1981, 1983), "solar_mean_kWh_m2_day"]
    assert len(early) == 24
    assert early.isna().all()


def test_statistical_and_fdr_filtering() -> None:
    """Trend filters respect metric, direction, and FDR significance."""

    data = pd.DataFrame(
        {
            "city": ["Seoul", "Busan", "Jeju"],
            "metric": ["temperature", "temperature", "wind"],
            "significant_fdr": [True, False, True],
            "mk_trend": ["increasing", "no trend", "increasing"],
        }
    )
    result = filter_statistical_trends(
        data,
        cities=["Seoul", "Busan"],
        metrics="temperature",
        fdr_significance="유의",
        trend_direction="increasing",
    )
    assert result["city"].tolist() == ["Seoul"]


def test_chart_input_and_download_dataframe_are_copies(annual_sample) -> None:
    """Display preparation and CSV serialization do not mutate source values."""

    source = annual_sample.copy(deep=True)
    downloaded = build_download_dataframe(annual_sample, ["city", "YEAR"])
    payload = dataframe_to_csv_bytes(downloaded).decode("utf-8-sig")
    assert downloaded.columns.tolist() == ["city", "YEAR"]
    assert payload.startswith("city,YEAR")
    pd.testing.assert_frame_equal(annual_sample, source)


def test_plotly_chart_builders_return_figures(annual_sample) -> None:
    """Core dashboard chart builders return valid Plotly Figure objects."""

    series = create_timeseries_chart(
        annual_sample,
        "YEAR",
        "T2M_mean_C",
        title="Temperature",
        y_title="°C",
        color_column="city",
    )
    anomaly_data = annual_sample.rename(columns={"T2M_mean_C": "T2M_anomaly"})
    anomaly = create_anomaly_chart(anomaly_data, "T2M_anomaly", title="Anomaly", unit="°C")
    heatmap = create_heatmap(
        annual_sample,
        row_column="city",
        column_column="YEAR",
        value_column="T2M_mean_C",
        title="Heatmap",
        colorbar_title="°C",
    )
    ci = create_sen_slope_ci_chart(
        pd.DataFrame(
            {
                "city": ["Seoul"],
                "sen_slope_per_decade": [0.4],
                "sen_ci_lower": [0.2],
                "sen_ci_upper": [0.6],
            }
        ),
        title="Sen slope",
        unit="°C",
    )
    assert all(isinstance(figure, go.Figure) for figure in (series, anomaly, heatmap, ci))
    assert len(series.data) == 2
    assert all(trace.hovertemplate for trace in series.data)


def test_streamlit_default_page_smoke() -> None:
    """The multipage router renders its default page without an exception."""

    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    app = AppTest.from_file(app_path, default_timeout=20).run()
    assert not app.exception
    assert any("NASA POWER Korea Climate Explorer" in title.value for title in app.title)
