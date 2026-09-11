"""Conservative Korean text from explicit facts; no model, inference or network service."""

from __future__ import annotations

from reporting.data_provider import ReportFacts
from reporting.formatters import finite, format_value

PRECIPITATION_CAVEAT = (
    "KMA ASOS 일강수량 API의 공란 의미가 무강수와 실제 미산출을 완전히 구분할 수 없어, "
    "NASA–KMA 강수 검증은 양쪽 자료에 유효한 강수 수치가 존재하는 날짜에 한정하였다."
)
CONTINUITY_CAVEAT = (
    "강릉 본 분석은 Gangneung 105, 중첩기간 비교는 Bukgangneung 104이다. "
    "높은 상관을 근거로 두 관측소를 하나의 연속자료로 간주하거나 임의로 이어 붙이지 않는다."
)
LIMITATIONS = [
    "NASA POWER는 격자자료이고 KMA ASOS는 지점관측자료다. 두 위치는 동일하지 않다.",
    "지형·해안·도시환경이 차이에 영향을 줄 가능성은 있으나 이 보고서는 원인을 자동 추론하지 않는다.",
    "통계적 유의성은 인과관계를 증명하지 않으며 과거 추세를 미래 예측으로 해석하지 않는다.",
    "threshold와 연속일수는 분석용 proxy이며 기상청 공식 폭염일수·열대야 통계와 동일하지 않다.",
    "KMA 강수 공란 의미 미확정: 무강수·미량강수·일합계 미산출·실제 missing을 완전히 구분하지 못한다.",
    "일부 변수에는 결측기간이 있다. 유효 pair 수와 변수별 유효 분석기간을 함께 확인한다.",
    "도시별 비교와 순위는 특정 지표의 비교이며 종합 위험도 평가가 아니다.",
    "높은 correlation은 정확도 백분율이 아니며 절대오차와 systematic bias를 따로 확인한다.",
]


def trend_sentence(label: str, slope: object, significant: object, unit: str = "°C/10년") -> str:
    """Distinguish direction, significance and missing values without claiming causality."""

    if not finite(slope):
        return f"{label}: 유효한 추세 자료가 없어 방향과 유의성을 판단하지 않았다."
    direction = "증가" if slope > 0 else "감소" if slope < 0 else "0"
    if slope == 0:
        statement = "Sen 기울기의 저장값은 0이다. 이는 기후변화가 없다는 결론을 뜻하지 않는다."
        if significant is True:
            statement += " 별도로 저장된 MK 기반 FDR 검정은 유의하다. 기울기 추정과 검정 결과를 구분한다."
        elif significant is False:
            statement += " FDR 보정 후 통계적 유의성은 확인되지 않았다."
        else:
            statement += " FDR 자료가 없어 유의성을 판단하지 않았다."
    elif significant is True:
        statement = f"{direction} 추세가 관찰되었으며 FDR 보정 후 통계적 유의성이 확인되었다."
    elif significant is False:
        statement = f"{direction} 방향을 보였으나 FDR 보정 후 통계적 유의성은 확인되지 않았다."
    else:
        statement = f"{direction} 방향을 보였으나 FDR 유의성 자료가 없어 유의성을 판단하지 않았다."
    return f"{label}: {statement} Sen's slope {format_value(slope, 'sen_slope')} {unit}."


def bias_sentence(bias: object, rmse: object, correlation: object, unit: str = "°C") -> str:
    """Keep temporal association separate from absolute and systematic differences."""

    if not all(finite(v) for v in (bias, rmse, correlation)):
        return "NASA–KMA agreement: 일부 지표의 자료가 없어 종합적인 해석을 보류한다."
    pattern = "시간적 변화 패턴의 일치도는 높지만 절대값 차이는 존재한다." if correlation >= 0.9 and rmse > 0 else "상관과 절대오차를 구분해서 해석해야 한다."
    return f"{pattern} Bias(NASA − KMA) {format_value(bias)} {unit}, RMSE {format_value(rmse)} {unit}, Pearson r {format_value(correlation, 'pearson')}."


def executive_summary(facts: ReportFacts) -> list[str]:
    """Produce eight stable summary statements using only the report fact layer."""

    value = facts.value
    return [
        f"{value('analysis_start_year')}–{value('analysis_end_year')} NASA 장기 평균기온은 {format_value(value('temperature_mean'))} °C이다.",
        trend_sentence("연평균기온", value("temperature_sen_slope"), value("temperature_fdr_significant")),
        f"{value('analysis_end_year')}년 T2M anomaly는 {format_value(value('recent_anomaly'))} °C이며 기준은 {value('normal_start_year')}–{value('normal_end_year')} normal이다.",
        trend_sentence("33°C 분석용 proxy", value("days_tmax_ge_33_sen_slope"), value("days_tmax_ge_33_fdr_significant"), "일/년/10년"),
        trend_sentence("Tmin ≥25°C 분석용 warm-night proxy", value("days_tmin_ge_25_sen_slope"), value("days_tmin_ge_25_fdr_significant"), "일/년/10년"),
        bias_sentence(value("kma_t2m_bias"), value("kma_t2m_rmse"), value("kma_t2m_pearson")),
        f"NASA 일사 추세의 유효기간: {format_value(value('solar_valid_start_year'), 'valid_start_year')}–{format_value(value('solar_valid_end_year'), 'valid_end_year')}. 결측은 0으로 채우지 않았다.",
        PRECIPITATION_CAVEAT,
    ]


def threshold_findings(facts: ReportFacts, large_difference_days: int = 10) -> list[str]:
    """Flag the largest stored annual count gap per threshold; do not calculate new trends."""

    rows = facts.tables["threshold"].rows
    sentences = []
    for threshold in dict.fromkeys(row["threshold"] for row in rows):
        candidates = [r for r in rows if r["threshold"] == threshold and finite(r["difference"])]
        if not candidates:
            sentences.append(f"{threshold}: 유효한 비교 자료가 없다.")
            continue
        row = max(candidates, key=lambda r: abs(r["difference"]))
        direction = "많았다" if row["difference"] > 0 else "적었다" if row["difference"] < 0 else "같았다"
        flag = f" 큰 차이 표시 기준(|차이| ≥{large_difference_days}일)에 해당한다." if abs(row["difference"]) >= large_difference_days else ""
        sentences.append(
            f"{threshold}: 저장된 연도별 결과 중 절대 차이가 가장 큰 {row['year']}년에는 NASA count "
            f"{format_value(row['nasa_count'], 'nasa_count')}, KMA count {format_value(row['kma_count'], 'kma_count')}로 "
            f"NASA가 {direction}. 차이(NASA−KMA) {format_value(row['difference'])}일.{flag} 원인은 추정하지 않는다."
        )
    return sentences
