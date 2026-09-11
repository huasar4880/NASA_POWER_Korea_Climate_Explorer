"""Static validation chart smoke tests using only synthetic known-shape fixtures."""

from __future__ import annotations

import pandas as pd

from src.validation import calculate_validation_metrics
from src.validation_visualization import create_validation_charts


def test_validation_chart_suite_writes_png_files(tmp_path) -> None:
    """All requested chart builders run without requiring KMA network data."""

    matched = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-07-01", "2021-01-01", "2021-07-01"]),
            "city": ["Seoul"] * 4,
            "nasa_T2M": [1.0, 21.0, 2.0, 22.0],
            "kma_T2M": [0.0, 20.0, 1.0, 21.0],
            "nasa_T2M_MAX": [4.0, 25.0, 5.0, 26.0],
            "kma_T2M_MAX": [3.0, 24.0, 4.0, 25.0],
            "nasa_T2M_MIN": [-2.0, 17.0, -1.0, 18.0],
            "kma_T2M_MIN": [-3.0, 16.0, -2.0, 17.0],
            "nasa_precipitation": [0.0, 5.0, 1.0, 8.0],
            "kma_precipitation": [1.0, 4.0, 2.0, 7.0],
            "nasa_RH2M": [50.0, 70.0, 55.0, 75.0],
            "kma_RH2M": [52.0, 68.0, 57.0, 73.0],
            "nasa_WS10M": [2.0, 3.0, 2.5, 3.5],
            "kma_WS10M": [1.8, 2.8, 2.3, 3.3],
            "nasa_solar": [2.0, 5.0, 2.2, 5.2],
            "kma_solar": [1.9, 4.9, 2.1, 5.1],
        }
    )
    metrics = calculate_validation_metrics(matched)
    outputs = create_validation_charts(matched, metrics, tmp_path)
    assert len(outputs) == 8
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs)

