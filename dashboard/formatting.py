"""Dashboard labels, units, and display metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSpec:
    """Describe how one dashboard metric maps to stored analysis columns."""

    key: str
    label: str
    annual_column: str
    stats_metric: str
    unit: str
    monthly_column: str | None = None
    anomaly_prefix: str | None = None


CITY_LABELS = {
    "Seoul": "서울",
    "Busan": "부산",
    "Daejeon": "대전",
    "Daegu": "대구",
    "Gwangju": "광주",
    "Gangneung": "강릉",
    "Jeju": "제주",
    "Jeonju": "전주",
}

SEASON_LABELS = {
    "DJF": "겨울 (DJF)",
    "MAM": "봄 (MAM)",
    "JJA": "여름 (JJA)",
    "SON": "가을 (SON)",
}

METRICS: dict[str, MetricSpec] = {
    "temperature": MetricSpec(
        "temperature", "평균기온 (T2M)", "T2M_mean_C", "temperature", "°C",
        "T2M_mean_C", "T2M",
    ),
    "temperature_max_mean": MetricSpec(
        "temperature_max_mean", "평균 최고기온 (T2M_MAX)", "T2M_MAX_mean_C",
        "temperature_max_mean", "°C", anomaly_prefix="T2M_MAX",
    ),
    "temperature_min_mean": MetricSpec(
        "temperature_min_mean", "평균 최저기온 (T2M_MIN)", "T2M_MIN_mean_C",
        "temperature_min_mean", "°C", anomaly_prefix="T2M_MIN",
    ),
    "precipitation": MetricSpec(
        "precipitation", "연강수량 (PRECTOTCORR)", "precipitation_total_mm",
        "precipitation", "mm/year", "precipitation_monthly_total_mean_mm",
        "precipitation",
    ),
    "humidity": MetricSpec(
        "humidity", "평균 상대습도 (RH2M)", "RH2M_mean_pct", "humidity",
        "%", "RH2M_mean_pct", "RH2M",
    ),
    "wind": MetricSpec(
        "wind", "평균 10m 풍속 (WS10M)", "WS10M_mean_m_s", "wind",
        "m/s", "WS10M_mean_m_s", "WS10M",
    ),
    "solar": MetricSpec(
        "solar", "평균 일사량 (ALLSKY_SFC_SW_DWN)", "solar_mean_kWh_m2_day",
        "solar", "kW-hr/m²/day", "solar_mean_kWh_m2_day", "solar",
    ),
    "hot_day_30": MetricSpec(
        "hot_day_30", "30°C 이상 최고기온 proxy", "days_tmax_ge_30",
        "hot_day_30", "days/year",
    ),
    "hot_day_33": MetricSpec(
        "hot_day_33", "33°C 이상 최고기온 proxy", "days_tmax_ge_33",
        "hot_day_33", "days/year",
    ),
    "warm_night_25": MetricSpec(
        "warm_night_25", "25°C 이상 최저기온 proxy", "days_tmin_ge_25",
        "warm_night_25", "days/year",
    ),
    "heavy_precip_30": MetricSpec(
        "heavy_precip_30", "30 mm 이상 강수일 proxy", "days_precip_ge_30",
        "heavy_precip_30", "days/year",
    ),
    "heavy_precip_50": MetricSpec(
        "heavy_precip_50", "50 mm 이상 강수일 proxy", "days_precip_ge_50",
        "heavy_precip_50", "days/year",
    ),
    "dry_day_lt_1": MetricSpec(
        "dry_day_lt_1", "1 mm 미만 건조일 proxy", "days_precip_lt_1",
        "dry_day_lt_1", "days/year",
    ),
    "consecutive_hot_days_30": MetricSpec(
        "consecutive_hot_days_30", "최대 연속 30°C 이상 일수",
        "max_consecutive_tmax_ge_30", "consecutive_hot_days_30", "days",
    ),
    "consecutive_extreme_heat_33": MetricSpec(
        "consecutive_extreme_heat_33", "최대 연속 33°C 이상 일수",
        "max_consecutive_tmax_ge_33", "consecutive_extreme_heat_33", "days",
    ),
    "consecutive_warm_nights_25": MetricSpec(
        "consecutive_warm_nights_25", "최대 연속 25°C 이상 최저기온 일수",
        "max_consecutive_tmin_ge_25", "consecutive_warm_nights_25", "days",
    ),
    "consecutive_dry_days": MetricSpec(
        "consecutive_dry_days", "최대 연속 건조일 proxy",
        "max_consecutive_precip_lt_1", "consecutive_dry_days", "days",
    ),
}

SEASONAL_METRICS = {
    key: METRICS[key]
    for key in ("temperature", "precipitation", "humidity", "wind", "solar")
}


def city_display_name(city: str) -> str:
    """Return a Korean label while preserving the English analysis key."""

    return f"{CITY_LABELS.get(city, city)} ({city})"


def metric_label(metric: str) -> str:
    """Return a readable label for a stored metric key."""

    return METRICS.get(metric, MetricSpec(metric, metric, metric, metric, "")).label


def format_number(value: object, decimals: int = 3, suffix: str = "") -> str:
    """Format a dashboard number without changing its stored value."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "자료 없음"
    if numeric != numeric:
        return "자료 없음"
    return f"{numeric:,.{decimals}f}{suffix}"

