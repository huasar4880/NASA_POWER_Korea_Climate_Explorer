"""NASA POWER 원본 일별 데이터를 분석 가능한 형태로 정제한다."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import SETTINGS


def preprocess_daily_data(
    raw_data: pd.DataFrame,
    parameters: tuple[str, ...] = SETTINGS.parameters,
    missing_values: Iterable[float] = SETTINGS.missing_values,
) -> pd.DataFrame:
    """날짜와 기온 변수를 변환해 tidy 일별 DataFrame을 만든다.

    NASA POWER의 결측치 표식은 NaN으로 바꾸되 보간하거나 임의 값을 채우지 않는다.
    """

    required_columns = {"DATE", *parameters}
    missing_columns = required_columns.difference(raw_data.columns)
    if missing_columns:
        raise ValueError(f"원본 데이터에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    tidy = raw_data.loc[:, ["DATE", *parameters]].copy()
    date_text = tidy["DATE"].astype("string").str.zfill(8)
    tidy["DATE"] = pd.to_datetime(date_text, format="%Y%m%d", errors="coerce")
    invalid_date_count = int(tidy["DATE"].isna().sum())
    if invalid_date_count:
        raise ValueError(f"변환할 수 없는 날짜가 {invalid_date_count}개 있습니다.")

    for parameter in parameters:
        tidy[parameter] = pd.to_numeric(tidy[parameter], errors="coerce")
        tidy[parameter] = tidy[parameter].mask(tidy[parameter].isin(missing_values))

    if tidy["DATE"].duplicated().any():
        duplicates = tidy.loc[tidy["DATE"].duplicated(), "DATE"].dt.strftime("%Y-%m-%d")
        raise ValueError(f"중복 날짜가 있습니다: {duplicates.iloc[0]}")

    tidy = tidy.sort_values("DATE").reset_index(drop=True)
    tidy.insert(1, "YEAR", tidy["DATE"].dt.year.astype("int64"))
    return tidy


def save_processed_data(dataframe: pd.DataFrame, output_path: Path) -> None:
    """정제 데이터를 별도 CSV에 저장한다."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_path, index=False, date_format="%Y-%m-%d")


def load_processed_data(input_path: Path) -> pd.DataFrame:
    """기존 정제 CSV를 변경하지 않고 분석용 DataFrame으로 읽는다."""

    if not input_path.exists():
        raise FileNotFoundError(f"정제 CSV가 없습니다: {input_path}")
    dataframe = pd.read_csv(input_path, parse_dates=["DATE"])
    required_columns = {"DATE", "YEAR", *SETTINGS.parameters}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(f"정제 데이터에 필수 컬럼이 없습니다: {sorted(missing_columns)}")
    if dataframe.empty:
        raise ValueError(f"정제 CSV가 비어 있습니다: {input_path}")
    return dataframe
