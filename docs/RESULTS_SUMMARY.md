# v1.0 Results Summary

이 문서는 2026-09-04에 현재 저장된 결과 CSV를 읽어 작성한 release snapshot이다.
값은 표시 반올림했으며 원본 정밀도와 행은 source CSV에 있다. 인과관계·미래예측·종합
위험도 판단을 하지 않는다.

## 1–3. T2M, Tmax and Tmin Long-term Change

| City | T2M mean (°C) | T2M Sen (°C/decade) | Tmax-mean Sen | Tmin-mean Sen |
|---|---:|---:|---:|---:|
| Seoul | 11.215 | 0.387 | 0.394 | 0.381 |
| Busan | 16.139 | 0.343 | 0.320 | 0.367 |
| Daejeon | 11.045 | 0.407 | 0.436 | 0.388 |
| Daegu | 11.141 | 0.415 | 0.422 | 0.397 |
| Gwangju | 12.364 | 0.286 | 0.330 | 0.262 |
| Gangneung | 11.737 | 0.410 | 0.406 | 0.424 |
| Jeju | 16.184 | 0.279 | 0.277 | 0.277 |
| Jeonju | 12.507 | 0.334 | 0.396 | 0.293 |

세 열의 Sen slope는 모든 도시에서 양수이고 BH-FDR 이후 유의하다. slope의 크기는
도시 전체 기후위험 순위가 아니며 원인을 설명하지 않는다.

Source: `output/tables/city_climate_statistical_trends.csv`

## 4. Warm-night Proxy

| City | NASA TMIN ≥25°C mean (days/year) | Sen slope (days/year/decade) | FDR significant |
|---|---:|---:|---|
| Seoul | 1.67 | 0.263 | yes |
| Busan | 32.07 | 6.376 | yes |
| Daejeon | 0.24 | 0.000 | yes¹ |
| Daegu | 0.16 | 0.000 | yes¹ |
| Gwangju | 0.96 | 0.000 | yes¹ |
| Gangneung | 2.51 | 0.000 | yes¹ |
| Jeju | 35.87 | 6.172 | yes |
| Jeonju | 2.64 | 0.000 | yes¹ |

¹ 저장 정밀도에서 Sen median slope가 음의 0으로 표시되는 경우다. MK 기반 FDR 검정
판정과 slope 추정치를 구분해야 하며 “변화 없음”이라는 결론이 아니다. 이 count는
NASA 분석용 proxy이며 KMA 공식 열대야 통계가 아니다.

Source: `output/tables/city_climate_statistical_trends.csv`

## 5–8. Precipitation, Humidity, Wind and Solar

| City | Precip Sen ((mm/year)/decade) | Humidity Sen (pp/decade) | Wind Sen ((m/s)/decade) | Solar Sen ((kWh/m²/day)/decade) |
|---|---:|---:|---:|---:|
| Seoul | 26.617 | 0.038 | −0.005 | −0.024 |
| Busan | 5.219 | −0.033 | 0.045 | 0.015 |
| Daejeon | 19.252 | −0.450 | 0.005 | −0.031 |
| Daegu | 10.113 | −0.367 | 0.015 | 0.002 |
| Gwangju | 46.581 | −0.082 | −0.024 | −0.001 |
| Gangneung | 67.562* | −0.334 | 0.001 | 0.002 |
| Jeju | 29.144 | −0.105 | −0.034 | 0.057* |
| Jeonju | 23.167 | −0.197 | −0.005 | −0.036 |

`*`는 해당 열의 BH-FDR 유의를 뜻한다. 강수는 강릉, 일사는 제주만 유의했고,
습도·풍속은 8개 도시 모두 유의하지 않았다. 일사 trend의 공통 유효기간은
1984–2025이며 1981–1983을 0으로 채우지 않았다.

Source: `output/tables/city_climate_statistical_trends.csv`

## 9. NASA–KMA T2M Validation

| City | Bias NASA−KMA (°C) | MAE (°C) | RMSE (°C) | Pearson r | n_pairs |
|---|---:|---:|---:|---:|---:|
| Seoul | −1.625 | 1.740 | 2.067 | 0.993 | 16,436 |
| Busan | 1.179 | 1.893 | 2.276 | 0.981 | 16,436 |
| Daejeon | −2.066 | 2.120 | 2.395 | 0.994 | 16,436 |
| Daegu | −3.211 | 3.247 | 3.589 | 0.990 | 16,435 |
| Gwangju | −1.779 | 1.866 | 2.118 | 0.993 | 16,436 |
| Gangneung | −1.776 | 1.985 | 2.577 | 0.979 | 16,435 |
| Jeju | 0.008 | 1.242 | 1.585 | 0.983 | 16,436 |
| Jeonju | −1.145 | 1.320 | 1.603 | 0.994 | 16,436 |

상관은 모두 높지만 절대오차와 systematic bias가 동시에 존재한다. 상관을 정확도
백분율로 읽지 않는다. Tmax/Tmin과 다른 변수의 전체 지표는 자동보고서 및 source CSV에 있다.

Source: `output/tables/nasa_kma_validation_metrics.csv`

## 10. Gangneung Continuity

| Primary/overlap comparison | Period | n_pairs | Bias 104−105 (°C) | MAE | RMSE | Pearson r |
|---|---|---:|---:|---:|---:|---:|
| Bukgangneung 104 − Gangneung 105 | 2008-07-28–2025-12-31 | 6,365 | −1.070 | 1.089 | 1.248 | 0.998 |

높은 상관에도 평균차가 있다. v1.0 primary는 105이며 104를 연결하거나 대체하지 않는다.

Source: `output/tables/gangneung_station_continuity_validation.csv`

## 11. Data Quality

- NASA와 KMA의 도시별 일자료는 16,436행, 1981-01-01–2025-12-31이다.
- KMA 도시별 중복 날짜와 누락 날짜는 모두 0이다.
- NASA solar missing은 각 도시 1,095일이며 1981–1983 fill-value 기간이다.
- KMA 강수 수치 공란은 도시별 8,916–10,888행이다. **관측누락률로 확정할 수 없다.**
- KMA 일사 missing은 37–1,125행, 기타 변수에도 소수 결측이 있어 metric별
  `n_pairs`가 다르다. 결측은 0으로 변환하지 않는다.

Sources: `output/tables/data_quality_summary.csv`,
`output/tables/kma_data_quality_summary.csv`

## 12. Limitations

NASA grid와 ASOS station의 차이, station distance, 지형·해안·도시환경을 고려해야 한다.
KMA precipitation blank 의미는 미확정이므로 강수 지표는 유효 수치 pair subset의 결과다.
Proxy는 공식 KMA 지표가 아니며, 통계적 유의성은 인과관계가 아니다. 순위는 한 지표의
상대 순서이고 종합 기후위험을 뜻하지 않는다. 이 결과는 과거자료 분석이며 예측이 아니다.

## Reproduce the Source Tables

```bash
python main.py --all
python main.py --validate-kma --all
python main.py --report --all
```

두 API workflow는 cache를 재사용한다. 공개 결과 재현 시 사용한 NASA 서비스 버전과
access date도 함께 기록한다.
