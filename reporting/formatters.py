"""Presentation-only formatting; source CSV precision is never changed."""

from __future__ import annotations

import html
import math
from numbers import Real

MISSING = "자료 없음"


def finite(value: object) -> bool:
    """Return whether a value is a finite, non-boolean numeric scalar."""

    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def format_value(value: object, column: str = "") -> str:
    """Format counts, probabilities, correlations and quantities without exposing NaN."""

    if value is None or (isinstance(value, Real) and not math.isfinite(value)):
        return MISSING
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if finite(value):
        # IEEE negative zero has no direction; normalize display only, not the fact.
        value = 0.0 if value == 0 else value
        if column in {"YEAR", "year", "MONTH", "month", "rank", "kma_station_id"} or any(
            word in column for word in ("n_pairs", "n_years", "row_count", "missing_", "duplicate", "fill_value", "abnormal", "suspicious", "_count", "valid_start", "valid_end", "baseline_start", "baseline_end", "n_overlap", "analysis_start", "analysis_end")
        ):
            return str(int(value))
        if column in {"hit", "miss", "false_alarm", "correct_negative"}:
            return str(int(value))
        if any(word in column for word in ("p_value", "q_value", "pearson_p", "spearman_p")):
            return "0 (저장 정밀도)" if value == 0 else f"{value:.3g}"
        digits = 3 if any(word in column for word in ("sen_", "slope", "pearson", "spearman", "correlation", "pod", "far", "csi")) else 2
        if "latitude" in column or "longitude" in column:
            digits = 4
        return f"{value:.{digits}f}"
    return str(value)


def markdown_escape(value: object) -> str:
    """Escape table delimiters and HTML in Markdown text."""

    return html.escape(str(value), quote=False).replace("|", "\\|").replace("\n", " ")
