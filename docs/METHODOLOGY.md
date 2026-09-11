# Methodology

## Scope and Data

The analysis covers 1981-01-01–2025-12-31 (16,436 days) for Seoul, Busan, Daejeon,
Daegu, Gwangju, Gangneung, Jeju and Jeonju. NASA POWER Daily Point uses the city
coordinates, community `RE` and `LST`. KMA ASOS uses one mapped primary station per city.
NASA is a grid product and KMA is a station observation; agreement is not a claim that either is
an interchangeable representation of the other.

## Variable Mapping and Aggregation

| Analysis variable | NASA | KMA | Daily unit | Annual aggregation |
|---|---|---|---|---|
| mean temperature | T2M | avgTa | °C | mean |
| maximum temperature | T2M_MAX | maxTa | °C | mean; annual maximum also retained |
| minimum temperature | T2M_MIN | minTa | °C | mean; annual minimum also retained |
| precipitation | PRECTOTCORR | sumRn | mm/day | sum |
| relative humidity | RH2M | avgRhm | % | mean |
| wind speed | WS10M | avgWs | m/s | mean |
| solar radiation | ALLSKY_SFC_SW_DWN | sumGsr | kWh/m²/day | mean |

KMA solar is converted by

\[
G_{kWh/m^2/day}=\frac{G_{MJ/m^2/day}}{3.6}.
\]

Monthly climatology is the mean of like calendar months across the analysis period. DJF assigns
December to the following `season_year`. Rolling means use complete 5- or 10-year windows; incomplete
leading windows remain missing.

## Climate Normal and Anomaly

The WMO-style project baseline is 1991–2020. For year \(y\),

\[
A_y=T_y-\overline{T}_{1991:2020}.
\]

Anomaly is not a forecast and the latest-year anomaly is not a recent-ten-year mean.

## Linear Trend

For annual value \(y_t\), ordinary least squares fits

\[
y_t=\beta_0+\beta_1t+\epsilon_t.
\]

The stored slope is reported as \(10\beta_1\) per decade with p-value and fit diagnostics.
Linearity, residual assumptions and serial dependence must be considered.

## Mann–Kendall and Modified MK

The MK score is

\[
S=\sum_{i<j}\operatorname{sgn}(x_j-x_i).
\]

Its standardized statistic tests a monotonic trend without requiring normality. A lag-1
autocorrelation diagnostic controls whether the Hamed–Rao Modified MK sensitivity result is also
reported. It does not solve all dependence, change points or nonlinearity.

## Sen's Slope and Multiple Testing

Sen's slope is the median pairwise slope,

\[
\hat\beta_{Sen}=\operatorname{median}_{i<j}\frac{x_j-x_i}{j-i},
\]

with a 95% interval and per-decade conversion. Benjamini–Hochberg orders \(m\) p-values and compares
\(p_{(i)}\) with \(i\alpha/m\). The stored q-value/`significant_fdr` is used; the report does not
reclassify it. Statistical significance is not effect size, causality or future persistence.

## Threshold and Consecutive-day Proxies

Counts use daily NASA values: TMAX ≥30°C, TMAX ≥33°C, TMIN ≥25°C, precipitation ≥30/50 mm,
and precipitation <1 mm. Maximum consecutive runs are separately derived. They are analytical
proxies, not official KMA heatwave, tropical-night or drought statistics.

## Cross-source Validation

NASA and KMA are joined one-to-one on city/date. Each metric drops only pairs missing that variable.
Let \(d_i=N_i-K_i\):

\[
Bias=\frac{1}{n}\sum d_i,\quad
MAE=\frac{1}{n}\sum|d_i|,\quad
RMSE=\sqrt{\frac{1}{n}\sum d_i^2}.
\]

Pearson r describes linear association; Spearman ρ describes rank association. Neither is accuracy
percentage. Normalized RMSE is \(RMSE/|\overline K|\), undefined when the denominator is effectively zero.

For precipitation wet day ≥1 mm/day:

\[
POD=\frac{hit}{hit+miss},\quad
FAR=\frac{false\ alarm}{hit+false\ alarm},\quad
CSI=\frac{hit}{hit+miss+false\ alarm}.
\]

Zero denominators remain missing.

## Gangneung Continuity

Gangneung station 105 is the complete 1981–2025 primary record. Bukgangneung 104 is used only for
the 2008-07-28–2025-12-31 overlap comparison. Bias(104−105), MAE, RMSE and correlation are
reported separately. The records are not spliced, even though their correlation is high.

## Missing-data Caveats

- NASA solar `-999` during 1981–1983 becomes NaN; valid trend years are 1984–2025.
- KMA `sumRn` blank/null semantics do not publicly distinguish all zero, trace precipitation and
  uncomputed daily-total cases. Blanks therefore remain NaN.
- Precipitation metrics and POD/FAR/CSI use only dates with numerical values on both sides.
  `missing_precipitation` is a numerical-blank count, not a confirmed observation-outage count.
- No missing observation is synthesized, interpolated or converted to zero without an official rule.

## Interpretation Boundary

Grid–station distance, terrain, coast and urban setting may affect differences, but this pipeline
does not attribute causes. Rankings are one-metric ordering, not climate-risk scores. The analysis
is retrospective and contains no machine learning, prediction, future scenario or attribution model.

## Experimental Nationwide ASOS Screening

The v1.1 experimental extension first classifies official ASOS metadata, probes small daily-data
windows for every discovered station, and performs detailed screening only for metadata Tier A/B
candidates. Final eligibility uses the three temperature variables: each variable must have no more
than 5% missing cells, at least 90% of years must reach 90% complete days, and an unexplained
temperature gap of 90 days or longer fails the rule. A complete day requires avgTa, maxTa and minTa.
Precipitation blanks and solar availability are recorded but never used to reject a temperature
candidate. Station history and proximity are review evidence, not permission to splice records.
The full definitions and reason codes are in
[Nationwide ASOS Screening](NATIONWIDE_ASOS_SCREENING.md).
