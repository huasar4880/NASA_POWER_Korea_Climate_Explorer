"""Pure dataframe filtering and download helpers for the dashboard."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def filter_cities(dataframe: pd.DataFrame, cities: Sequence[str] | None) -> pd.DataFrame:
    """Return rows for selected city names."""

    if not cities:
        return dataframe.copy()
    return dataframe.loc[dataframe["city"].isin(cities)].copy()


def filter_metric(dataframe: pd.DataFrame, metrics: str | Sequence[str] | None) -> pd.DataFrame:
    """Return rows for one or more stage-5 metric keys."""

    if metrics is None or metrics == []:
        return dataframe.copy()
    selected = [metrics] if isinstance(metrics, str) else list(metrics)
    return dataframe.loc[dataframe["metric"].isin(selected)].copy()


def filter_years(
    dataframe: pd.DataFrame,
    start_year: int,
    end_year: int,
    year_column: str = "YEAR",
) -> pd.DataFrame:
    """Filter an inclusive exploratory year range."""

    years = pd.to_numeric(dataframe[year_column], errors="coerce")
    return dataframe.loc[years.between(start_year, end_year, inclusive="both")].copy()


def filter_seasonal(
    dataframe: pd.DataFrame,
    cities: Sequence[str] | None = None,
    metrics: str | Sequence[str] | None = None,
    seasons: str | Sequence[str] | None = None,
) -> pd.DataFrame:
    """Filter the stored seasonal trend table."""

    filtered = filter_metric(filter_cities(dataframe, cities), metrics)
    if seasons is None or seasons == []:
        return filtered
    selected = [seasons] if isinstance(seasons, str) else list(seasons)
    return filtered.loc[filtered["season"].isin(selected)].copy()


def _as_bool(series: pd.Series) -> pd.Series:
    """Normalize CSV boolean values without treating arbitrary strings as true."""

    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def filter_statistical_trends(
    dataframe: pd.DataFrame,
    cities: Sequence[str] | None = None,
    metrics: str | Sequence[str] | None = None,
    fdr_significance: str = "전체",
    trend_direction: str = "전체",
) -> pd.DataFrame:
    """Apply city, metric, FDR, and trend-direction filters."""

    filtered = filter_metric(filter_cities(dataframe, cities), metrics)
    if fdr_significance == "유의":
        filtered = filtered.loc[_as_bool(filtered["significant_fdr"])]
    elif fdr_significance == "비유의":
        filtered = filtered.loc[~_as_bool(filtered["significant_fdr"])]
    if trend_direction != "전체":
        filtered = filtered.loc[filtered["mk_trend"] == trend_direction]
    return filtered.copy()


def prepare_chart_dataframe(
    dataframe: pd.DataFrame,
    required_columns: Sequence[str],
    sort_by: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Select chart columns, coerce values as stored, and remove incomplete rows."""

    missing = sorted(set(required_columns) - set(dataframe.columns))
    if missing:
        raise KeyError(f"차트 입력에 필요한 컬럼이 없습니다: {', '.join(missing)}")
    prepared = dataframe.loc[:, list(required_columns)].dropna().copy()
    if sort_by:
        prepared = prepared.sort_values(list(sort_by))
    return prepared.reset_index(drop=True)


def build_download_dataframe(
    dataframe: pd.DataFrame,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Return a filtered, index-free copy suitable for CSV download."""

    selected = dataframe.loc[:, list(columns)].copy() if columns else dataframe.copy()
    return selected.reset_index(drop=True)


def dataframe_to_csv_bytes(dataframe: pd.DataFrame) -> bytes:
    """Serialize the current filtered table as UTF-8 with BOM."""

    return build_download_dataframe(dataframe).to_csv(index=False).encode("utf-8-sig")

