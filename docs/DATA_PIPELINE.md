# Data Pipeline

## End-to-end Flow

```text
NASA API → NASA raw cache → NASA processed → annual/monthly/seasonal analysis
                                             → statistics/normal/anomaly/indices
KMA API  → KMA raw cache  → KMA processed ──┐
NASA processed ──────────────────────────────┴→ date/city match → validation
analysis + validation tables → charts → dashboard / deterministic reports
```

| Stage | Input | Output | Core modules | Main files |
|---|---|---|---|---|
| Configuration | JSON settings | typed settings/locations | `src/config.py`, `src/station_metadata.py` | `config/locations.json`, `config/kma_stations.json` |
| NASA ingestion | Daily Point API | immutable city raw cache | `src/nasa_power.py`, `src/city_analysis.py` | `data/raw/*_power_daily*.csv` |
| KMA ingestion | ASOS Daily API | immutable station raw cache | `src/kma_asos.py`, `src/kma_workflow.py` | `data/kma_raw/*_asos_daily*.csv` |
| NASA processing | NASA raw | tidy daily city data | `src/preprocess.py`, `src/climate_analysis.py` | `data/processed/*.csv` |
| KMA processing | KMA raw | typed ASOS fields, null preserved | `src/kma_preprocess.py` | `data/kma_processed/*.csv` |
| Aggregation | NASA processed | annual/monthly/past-vs-recent | `src/analysis.py`, `src/climatology.py` | `output/tables/city_climate_*.csv` |
| Statistical analysis | annual/monthly data | trends, normal, anomaly, FDR | `src/statistical_analysis.py`, `src/stage5_analysis.py` | `city_climate_statistical_trends.csv`, normals/anomalies |
| Climate indices | NASA daily/annual | threshold and consecutive proxies | `src/climate_indices.py` | `city_consecutive_climate_indices_1981_2025.csv` |
| Matching | NASA/KMA processed | one row per common city/date | `src/validation.py` | `output/validation/matched/*.csv` |
| Validation | matched valid pairs | overall/month/season/year metrics | `src/validation.py`, `src/kma_workflow.py` | `output/tables/nasa_kma_*.csv` |
| Visualization | output tables/matched | static charts | `src/visualization.py`, `src/validation_visualization.py` | `output/charts/**/*.png` |
| Dashboard | existing result CSV | interactive read-only views | `dashboard/data_loader.py`, `dashboard/pages/*` | no source mutation |
| Reports | existing result CSV | HTML, Markdown, manifest, report PNG | `reporting/*` | `output/reports/**` |

## Invariants

1. Raw files are never modified by downstream processing.
2. Processed files do not overwrite raw files.
3. NASA fill value `-999` and KMA null remain missing unless an official, testable rule exists.
4. Every city uses the same code path; city names and coordinates come from config.
5. Existing complete caches prevent unnecessary API calls.
6. Validation uses variable-specific valid pairs; it does not convert missing data to zero.
7. Dashboard/report are terminal consumers and cannot start ingestion.

## Operational Commands

```bash
# Single/all NASA workflows
python main.py --city Seoul
python main.py --all

# KMA cache / validation
python main.py --download-kma --all
python main.py --validate-kma --all

# Consumers of saved results
streamlit run streamlit_app.py
python main.py --report --all
```

## Refresh and Recovery

Normal execution reuses raw cache. A failed API request leaves successful city files intact. Check the
reported city and cause, then rerun; use `--force-download` only when replacement is intentional.
KMA code 22 means the daily allowance is exhausted and must not be bypassed. Code 23/HTTP 429 uses
delay/backoff. After upstream data changes, rerun the relevant analysis before restarting Dashboard or reports.

## Provenance

NASA response metadata, location settings, KMA station mapping and source URLs are retained in result
tables/config. Report manifests add exact scalar cells, table CSV line numbers, source hashes and mtimes.
The analysis period and file-generation time are different concepts and are displayed separately.
