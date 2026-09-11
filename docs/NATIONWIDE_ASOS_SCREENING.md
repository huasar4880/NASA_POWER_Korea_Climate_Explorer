# Nationwide ASOS Station Screening

## 1. 목적과 범위

이 문서는 stable v1.0의 8개 도시 결과를 변경하지 않고 추가한 **v1.1 experimental**
전국 ASOS 관측소 inventory 및 장기 기온분석 적합성 선별 절차를 설명한다. 이번 단계의
결과는 전국 기후추세 자체가 아니라, 다음 단계에서 사용할 관측소 후보와 제외·검토 근거다.

## 2. 공식 metadata source

관측소 이력은 기상청 기상자료개방포털의
[지상관측 지점정보](https://data.kma.go.kr/tmeta/stn/selectStnList.do?pgmNo=123)를 사용한다.
웹 화면을 해석해 목록을 만들지 않고, 동일 서비스의 공식 CSV 다운로드를 세션 기반으로
호출한다. 공식 분류코드 `SFC01`(종관기상관측), 서비스 구분 `F00101`을 요청해 AWS나
다른 관측망을 제외한다. 관측소 수는 코드에 고정하지 않고 응답에서 계산한다.

원본 CSV는 MS949로 보존하고, station ID, 기간, 명칭, 주소, 관리관서, 위·경도,
노장 해발고도를 정규화한다. 주소의 첫 두 토큰만 `region_level1/2`로 사용하며 관측소명으로
행정구역을 추측하지 않는다. source URL과 수집시각을 inventory에 기록한다.

## 3. Station inventory와 cache

- 원본: `data/station_metadata/raw/kma_station_metadata_raw.csv`
- 수집 manifest: `data/station_metadata/raw/metadata_manifest.json`
- 정규화: `data/station_metadata/processed/kma_asos_station_inventory.csv`
- 공개 inventory: `data/station_metadata/kma_asos_station_inventory.csv`

기본 실행은 정상 cache를 재사용한다. `--refresh-stations`를 명시한 경우에만 공식
metadata를 다시 받는다. 원본 이력 segment는 삭제·병합하지 않으며, station별 대표 행은
현재 운영 segment를 우선해 별도로 만든다.

## 4. Metadata Tier 정의

이 Tier는 **프로젝트의 선별 규칙**이며 기상청 공식 품질등급이 아니다.

| Tier | Metadata 예비 기준 |
|---|---|
| A | 시작일 ≤ 1981-01-01, active 또는 종료일 ≥ 2025-12-31 |
| B | 시작일 ≤ 1991-01-01, 종료일 ≥ 2020-12-31 |
| C | 위 기준은 아니지만 목표기간과 겹치는 관측기간이 20년 이상 |
| D | 20년 미만의 단기 기록 |
| X | 날짜·좌표 등 metadata 검증 필요 |

Metadata A/B는 후보일 뿐이다. 실제 ASOS 일자료 검사와 continuity 검토를 통과해야
final A/B가 된다.

## 5. Daily availability와 completeness

모든 station은 시작부, 1991년, 2000년, 2020년, 2025년 및 필요한 종료부의 최대 31일
구간을 probe한다. 상세 다운로드는 metadata A/B 후보로 제한한다. A는 1981–2025,
B는 1991–2025 또는 종료된 관측소의 경우 1991–2020을 검사한다.

분석 달력의 윤년을 포함한 기대일수와 고유 관측일수를 비교한다. 연도별
`completeness_ratio`는 같은 날 평균·최고·최저기온 세 값이 모두 유효한 일수 /
그해 기대일수다. 전체 `core_temperature_missing_rate`는 3 × 기대일수 행렬에서 세 기온
변수의 결측 cell 수가 차지하는 비율이다. 변수별 결측률도 따로 유지한다.

Final A/B의 기온 품질 기준은 다음과 같다.

- 평균·최고·최저기온 각각의 결측률 ≤ 5%
- 대상 연도의 90% 이상에서 연 completeness ≥ 90%
- 기온 세 변수 중 하나라도 없는 연속 구간이 90일 이상이면 탈락
- 실제 자료의 시작·종료가 metadata 목표범위와 31일 넘게 다르면 수동 검토

## 6. Gap 기준

각 기온변수의 최장 연속결측과, 세 기온 중 하나 이상이 결측인 연속 구간을 계산한다.
7·30·90일 이상 gap의 개수를 보존한다. 정확히 90일인 gap도 `LONG_TEMP_GAP`이다.
전체 결측률이 낮아도 특정 시기 장기 공백이 있으면 장기추세 후보에서 제외한다.

## 7. Station continuity risk

공식 metadata의 다중 segment, 동일 명칭의 다른 ID, 가까운 관련 명칭, 좌표 이동을 review
flag로 만든다. Haversine 거리는 5 km와 20 km 탐색범위, 1 km segment 이동 기준에
사용하지만 거리만으로 두 station을 연결하지 않는다.

- `low`: 명시적 위험 없음
- `medium`: 이력·인접 후보가 있으나 자동 제외 사유는 아님
- `high`: 1 km 이상 segment 좌표 이동 등, 수동 검토 필요
- `manual_review`: 동일/관련 명칭의 다른 ID 또는 metadata 이상

`high/manual_review` station은 해결 전 final A/B에 넣지 않는다. 원자료를 station 간
splice하거나 이름이 비슷하다는 이유로 계보를 확정하지 않는다.

## 8. 강수 caveat

KMA `sumRn` 공란은 이 단계에서 0으로 바꾸지 않는다. 강수의 장기 공란 문제는 stable
validation과 같은 caveat를 유지하며, 강수 결측률은 station의 기온 Tier 탈락 기준이
아니다. 강수 현상 유무를 공식 규칙으로 확정하지 않은 값은 관측 누락과 무강수를 임의로
구분하지 않는다.

## 9. 일사 caveat

`sumGsr`는 MJ/m²/day를 3.6으로 나눠 kWh/m²/day로 표시하되 원본은 변경하지 않는다.
관측 시작시점과 장기 결측이 station마다 다를 수 있어 일사 결측률도 final 기온 Tier의
탈락 기준으로 사용하지 않는다.

## 10. Eligibility logic와 reason code

Final Tier A는 metadata A와 A기간 일자료 기준을 통과하고 continuity/mismatch 문제가
없어야 한다. A기간을 통과하지 못한 metadata A station은 continuity 문제가 없을 때만
1991–2025 품질을 다시 평가해 Tier B가 될 수 있다. Metadata B도 같은 B 품질 기준을
통과해야 한다.

| Code | 의미 |
|---|---|
| `ELIGIBLE_FULL_PERIOD` | 1981–2025 final A 기준 통과 |
| `ELIGIBLE_1991_PLUS` | 1991+ final B 기준 통과 |
| `STARTED_AFTER_1981` | metadata C |
| `SHORT_RECORD` | metadata D |
| `HIGH_TEMP_MISSING` | 기온 변수별 결측률 기준 초과 |
| `LONG_TEMP_GAP` | 90일 이상 연속 기온 공백 |
| `LOW_ANNUAL_COMPLETENESS` | 연 completeness 기준 미달 |
| `CONTINUITY_REVIEW` | unresolved high/manual continuity |
| `NO_ASOS_DATA` | probe에서 일자료 미확인 |
| `METADATA_DATA_MISMATCH` | metadata와 실제 범위 불일치 |
| `METADATA_INVALID` | metadata 날짜·좌표 검증 필요 |
| `NOT_DETAILED_SCREENED` | 아직 상세검사를 완료하지 않음 |

## 11. API 호출 전략

일자료는 공공데이터포털의
[ASOS 일자료 API](https://www.data.go.kr/data/15059093/openapi.do)를 사용한다.
기존 `KmaAsosClient`의 ServiceKey 단일 인코딩, 최대 10년 기간분할, pagination,
HTTP 429 및 공식 코드 23 backoff를 재사용한다. 서버가 `numOfRows=1000`을 오류로
거부하는 실제 동작 때문에 안전한 999건을 사용한다. `--dry-run`은 API를 호출하지 않고
현재 cache를 고려한 하한 요청량을 계산한다. 공식 일일 한도 오류(code 22)는 우회하지 않는다.

## 12. Cache와 resume

- Probe: `data/nationwide_asos_raw/probes/<id>_<start>_<end>.csv`
- 상세 chunk: `data/nationwide_asos_raw/stations/<id>/chunks/`
- station 결과: `data/nationwide_asos_raw/stations/<id>/`
- 상태: `data/nationwide_asos_raw/screening_state.json`

완료한 probe·chunk·station cache는 다음 실행에서 재사용한다. 기존 8개 도시 raw가 대상
기간을 완전히 덮으면 읽기 전용으로 복사해 전국 namespace에 재사용하지만, 기존 파일은
수정하지 않는다. 상태파일에는 완료 여부, 기간, 행 수, source와 오류 유형만 저장하며 API
key·요청 URL은 저장하지 않는다.

## 13. 실행과 shortlist 사용법

```bash
python main.py --nationwide-stations
python main.py --nationwide-stations --refresh-stations
python main.py --screen-nationwide-asos --dry-run
python main.py --screen-nationwide-asos --sample-stations
python main.py --screen-nationwide-asos
```

`nationwide_asos_station_master.csv`는 전체 판단 근거, `longterm_shortlist.csv`는 final
A/B만 담는다. 제외·보류 station은 `excluded_or_review.csv`에서 reason code로 확인한다.
shortlist의 `nasa_query_latitude/longitude`는 11단계의 NASA POWER point 요청 후보 좌표이며,
이번 단계에서는 전국 NASA 자료나 추세값을 생성하지 않는다.

## 14. 11단계와의 연결

11단계에서는 final A와 B를 분석기간별로 분리하고, manual review가 남은 station을 자동
포함하지 않은 채 NASA POWER point와 ASOS를 station 좌표 기준으로 비교해야 한다.
관측소 밀도 차이, 고도, 해안·도서 대표성, 같은 station ID 내부 이전 이력은 별도의 공간·
연속성 불확실성으로 유지한다. 이번 shortlist는 분석 가능성 screening이지 전국 대표성을
보장하는 표본 설계가 아니다.

## 15. 2026-09-05 실행 스냅샷

공식 CSV의 148개 이력 segment에서 105개 고유 ASOS ID를 확인했다. active 97개,
historical/inactive 8개이며 metadata Tier A 61개, B 6개였다. 105개 모두 최소 한 probe
구간에서 실제 일자료가 확인됐고 A/B 67개를 상세검사했다. 최종 결과는 Tier A 45개,
Tier B 6개, manual review 25개, 그 밖의 제외 29개다. 따라서 현재 shortlist는 51개다.

상세검사 station의 core temperature missing rate는 0–0.000750, 최장 기온 gap은 모두
90일 미만이었고 metadata–daily 범위 mismatch는 없었다. 최종 A/B에서 제외된 주요 원인은
기온 결측이 아니라 해결되지 않은 station continuity였다. 이 수치는 metadata refresh나
screening config가 바뀌면 다시 계산해야 한다.
