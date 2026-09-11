"""Deterministic, independently replayable facts from existing scientific artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.spatial.robustness_audit import sha256

FINAL = Path('output/final')
COMMON = Path('output/tables/common_period')
SPATIAL = Path('output/tables/common_period_spatial')
PERIOD = Path('output/tables/period_sensitivity')
COMMON_MANIFEST = Path('output/manifests/common_period_51station_manifest.json')


def scalar(value: Any) -> str:
    """Serialize scalars without rounding; JSON preserves lists and booleans."""
    if hasattr(value, 'item'):
        value = value.item()
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def select(frame: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply exact equality filters, preserving original zero-based CSV row numbers."""
    for column, value in filters.items():
        frame = frame.loc[frame[column].eq(value)]
    return frame


def evaluate(frame: pd.DataFrame, column: str, operation: str) -> Any:
    """Only descriptive operations on saved values are permitted, never new inference."""
    if operation == 'count_rows':
        return len(frame)
    if frame.empty:
        raise ValueError('Empty fact selection')
    values = frame[column]
    if values.isna().any():
        raise ValueError(f'Missing source value: {column}')
    if operation == 'cell':
        if len(values) != 1:
            raise ValueError('Scalar fact selection is not unique')
        return values.iloc[0]
    if operation == 'median':
        return values.median()
    if operation == 'positive_count':
        return int(values.gt(0).sum())
    if operation == 'negative_count':
        return int(values.lt(0).sum())
    if operation == 'true_count':
        if not values.isin([True, False]).all():
            raise ValueError('Nonboolean count source')
        return int(values.sum())
    raise ValueError(f'Unsupported fact operation: {operation}')


class FactBook:
    """Build a small scalar layer with explicit file, row, column and operation provenance."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.rows: list[dict] = []
        self.frames: dict[str, pd.DataFrame] = {}

    def add(self, fact_id: str, topic: str, file: Path, column: str,
            filters: dict | None = None, operation: str = 'cell', unit: str = '1',
            period: str = '1991–2025') -> None:
        """Read a saved CSV selection and record reproducible descriptive provenance."""
        name = file.as_posix()
        if name not in self.frames:
            self.frames[name] = pd.read_csv(self.root / file)
        subset = select(self.frames[name], filters or {})
        value = evaluate(subset, column, operation)
        self.rows.append(dict(fact_id=fact_id, topic=topic, metric=column, value=scalar(value),
            unit=unit, source_file=name, **{'source_row/key': json.dumps(subset.index.tolist())},
            source_column=column, analysis_period=period,
            notes=json.dumps({'operation': operation, 'filters': filters or {},
                'scope': 'saved estimates; unweighted station summary, not national area mean'}, ensure_ascii=False)))

    def manifest(self, fact_id: str, key: str, file: Path = COMMON_MANIFEST,
                 unit: str = '1') -> None:
        """Copy one manifest field without interpreting or reconstructing it."""
        data = json.loads((self.root / file).read_text())
        self.rows.append(dict(fact_id=fact_id, topic='scale', metric=key, value=scalar(data[key]),
            unit=unit, source_file=file.as_posix(), **{'source_row/key': key}, source_column=key,
            analysis_period='metadata', notes=json.dumps({'operation': 'json_key'})))

    def frame(self) -> pd.DataFrame:
        """Return a stable, unique fact inventory."""
        result = pd.DataFrame(self.rows).sort_values('fact_id').reset_index(drop=True)
        if result.fact_id.duplicated().any():
            raise ValueError('Duplicate fact ID')
        return result


def build_facts(root: Path) -> pd.DataFrame:
    """Collect approved scale, temperature, validation and robustness facts without refitting."""
    b = FactBook(root)
    for fid, key in [('tier_a','tier_a_count'),('tier_b','tier_b_count'),('common_n','station_count'),
                     ('grid_n','unique_NASA_grid_count'),('common_period','analysis_period'),('normal','normal_period')]:
        b.manifest(fid, key,unit='grids' if fid=='grid_n' else ('date/year range' if fid in ('common_period','normal') else 'stations'))
    b.manifest('long_period','analysis_period',Path('output/manifests/nationwide_analysis_manifest.json'),unit='date range')
    b.manifest('windows','windows',Path('output/manifests/period_sensitivity_manifest.json'))
    b.manifest('long_grid_n','unique_NASA_grid_count',Path('output/manifests/period_sensitivity_manifest.json'),unit='grids')
    b.add('inventory_n','scale',Path('data/station_metadata/processed/kma_asos_station_inventory.csv'),
          'station_id',operation='count_rows',unit='stations',period='metadata snapshot')
    for source in ('KMA','NASA'):
        for metric in ('TAVG','TMAX','TMIN'):
            filt={'source':source,'metric':metric}
            for label,op,col,unit in [('median','median','sen_slope_per_decade','°C/decade'),
                                      ('positive','positive_count','sen_slope_per_decade','stations'),
                                      ('fdr','true_count','significant_fdr','stations')]:
                b.add(f'common_{source}_{metric}_{label}','temperature',COMMON/'common_period_temperature_trends.csv',col,filt,op,unit)
        for season in ('DJF','MAM','JJA','SON'):
            b.add(f'common_{source}_{season}','seasonal',COMMON/'common_period_seasonal_temperature_trends.csv',
                  'sen_slope_per_decade',{'source':source,'metric':'TAVG','season':season},'median','°C/decade')
        b.add(f'common_{source}_dtr','dtr',SPATIAL/'common_period_dtr_trends.csv','sen_slope_per_decade',
              {'source':source},'median','°C/decade')
        b.add(f'common_{source}_dtr_negative','dtr',SPATIAL/'common_period_dtr_trends.csv','sen_slope_per_decade',
              {'source':source},'negative_count','stations')
    b.add('contrast_median','contrast',SPATIAL/'common_period_tmax_tmin_warming_contrast.csv','tmin_minus_tmax',operation='median',unit='°C/decade')
    b.add('contrast_positive','contrast',SPATIAL/'common_period_tmax_tmin_warming_contrast.csv','tmin_minus_tmax',operation='positive_count',unit='stations')
    for metric in ('TAVG','TMAX','TMIN'):
        for col,unit in [('bias','°C'),('mae','°C'),('rmse','°C'),('pearson_r','1'),('spearman_rho','1'),('n_pairs','days')]:
            b.add(f'validation_{metric}_{col}','validation',COMMON/'common_period_nasa_kma_temperature_validation.csv',col,{'metric':metric},'median',unit)
        b.add(f'agreement_{metric}','agreement',COMMON/'common_period_nasa_kma_trend_consistency.csv',
              'same_direction',{'metric':metric},'true_count','stations')
    for row in pd.read_csv(root/SPATIAL/'common_period_global_morans_i.csv').to_dict('records'):
        if row['weight_variant']!='directed_knn_k4':
            continue
        for col in ('Moran_I','permutation_p','n_spatial_units'):
            b.add(f"spatial_{row['variable']}_{row['representation']}_{col}",'spatial',SPATIAL/'common_period_global_morans_i.csv',col,
                  {k:row[k] for k in ('variable','representation','weight_variant')},unit='spatial units' if col=='n_spatial_units' else '1')
    for row in pd.read_csv(root/SPATIAL/'common_period_spatial_robustness_summary.csv').to_dict('records'):
        for col in ('robustness_class','n_configurations','n_significant'):
            b.add(f"weights_{row['variable']}_{row['representation']}_{col}",'weights',SPATIAL/'common_period_spatial_robustness_summary.csv',col,
                  {k:row[k] for k in ('variable','representation')})
    for variable in ('kma_tavg_sen_slope','tavg_bias','tavg_rmse'):
        for col in ('spearman_rho','spearman_p'):
            b.add(f'coast_{variable}_{col}','coastal',SPATIAL/'common_period_coastal_distance_associations.csv',col,{'variable':variable})
        for col in ('median_difference','fdr_q','coastal_n','inland_n'):
            b.add(f'coast_group_{variable}_{col}','coastal',SPATIAL/'common_period_coastal_threshold_sensitivity.csv',col,
                  {'variable':variable,'threshold_km':30},unit='stations' if col.endswith('_n') else ('1' if col=='fdr_q' else ('°C/decade' if variable=='kma_tavg_sen_slope' else '°C')))
    for row in pd.read_csv(root/PERIOD/'period_sensitivity_window_summary.csv').to_dict('records'):
        y=int(row['start_year']);src=row['source'];metric=row['metric']
        for col in ('median','positive_count','fdr_increasing_count'):
            b.add(f'window_{y}_{src}_{metric}_{col}','period',PERIOD/'period_sensitivity_window_summary.csv',col,
                  {'start_year':y,'source':src,'metric':metric},unit='°C/decade' if col=='median' else 'stations',period=f'{y}–2025')
    for metric in ('TAVG','TMAX','TMIN'):
        for col in ('positive_all_count','significant_all_count','median'):
            b.add(f'stability_{metric}_{col}','stability',PERIOD/'period_sensitivity_national_stability_summary.csv',col,
                  {'source':'KMA','metric':metric},unit='°C/decade' if col=='median' else 'stations',period='fixed Tier A; all stored windows')
    for row in pd.read_csv(root/PERIOD/'period_sensitivity_moran_trajectory.csv').to_dict('records'):
        if row['weight_variant']!='directed_knn_k4':continue
        for col in ('period_robustness','significant_window_count','I_1981','I_1991','I_2001','p_1981','p_1991','p_2001'):
            b.add(f"trajectory_{row['variable']}_{row['representation']}_{col}",'period_spatial',PERIOD/'period_sensitivity_moran_trajectory.csv',col,
                  {k:row[k] for k in ('variable','representation','weight_variant')},period='fixed Tier A; stored windows')
    for variable,representation in [('nasa_tavg_sen_slope','STATION_LINKED'),('nasa_tavg_sen_slope','UNIQUE_GRID'),
                                    ('tavg_bias','STATION_LINKED'),('tavg_rmse','STATION_LINKED')]:
        filters={'variable':variable,'representation':representation}
        for label,extra in [('total',{}),('stable',{'period_robustness':'SPATIALLY_STABLE_POSITIVE'})]:
            b.add(f'allweights_{variable}_{representation}_{label}','period_weights',
                  PERIOD/'period_sensitivity_spatial_robustness_summary.csv','period_robustness',
                  {**filters,**extra},'count_rows','weight configurations',period='all stored windows')
    for name,dimensions,columns,topic,unit in [
        ('seasonal_summary',['start_year','source','season'],['median'],'period_season','°C/decade'),
        ('threshold_window_summary',['start_year','source','threshold'],['median','positive_count'],'threshold','days/decade'),
        ('validation_window_summary',['start_year','metric'],['bias_median','rmse_median'],'period_validation','°C'),
        ('dtr_summary',['start_year','source'],['median','negative_count'],'period_dtr','°C/decade'),
        ('contrast_summary',['start_year','source'],['median','positive_count'],'period_contrast','°C/decade'),
        ('coastal_association_stability',['variable'],['period_interpretation','minimum','maximum','significant_window_count'],'period_coast','1'),
        ('coastal_group_period_stability',['variable'],['period_interpretation','minimum','maximum','significant_window_count'],'period_coast_group','outcome unit'),
        ('trend_consistency_window_summary',['start_year','metric'],['same_direction_count','both_significant_count'],'period_agreement','stations'),
    ]:
        path=PERIOD/f'period_sensitivity_{name}.csv'
        for row in pd.read_csv(root/path).to_dict('records'):
            if topic=='threshold' and row['threshold'] not in ('TMAX_GE_33','TMIN_GE_25'):continue
            filters={k:row[k] for k in dimensions}; suffix='_'.join(str(row[k]) for k in dimensions)
            for col in columns:
                actual_unit=unit
                if topic=='period_coast_group':
                    actual_unit='°C' if row['variable'] in ('tavg_bias','tavg_rmse') else ('days/decade' if row['variable'].startswith('days_') else '°C/decade')
                if col=='period_interpretation':actual_unit='classification'
                b.add(f'{topic}_{suffix}_{col}',topic,path,col,filters,
                      unit='stations' if col in ('positive_count','negative_count') else ('windows' if col=='significant_window_count' else actual_unit),
                      period=f"{row.get('start_year','multiple')}–2025")
    path=Path('output/tables/spatial_models_numerical/stage14_model_interpretation_status.csv')
    for row in pd.read_csv(root/path).to_dict('records'):
        for col in ('classical_p','hc3_p','interpretation_status'):
            b.add(f"model_{row['outcome']}_{col}",'model_review',path,col,{'outcome':row['outcome']},period='1981–2025')
    path=Path('output/tables/spatial_models_numerical/spatial_model_numerical_stability.csv')
    for label in sorted(pd.read_csv(root/path).numerical_class.unique()):
        b.add(f'model_count_{label}','model_review',path,'numerical_class',{'numerical_class':label},'count_rows','model combinations',period='1981–2025')
    return b.frame()


def verify_facts(root: Path, facts: pd.DataFrame) -> dict:
    """Replay every fact and require agreement with preserved upstream manifest checksums."""
    errors=[]; cache={}; hashes={}
    for path in (root/'output/manifests').glob('*.json'):
        if path.name.startswith('final_'):continue
        manifest=json.loads(path.read_text())
        if isinstance(manifest.get('output_hashes'),dict):
            hashes.update(manifest['output_hashes'])
    sources={}
    for row in facts.to_dict('records'):
        name=row['source_file']; path=root/name
        if name not in sources:
            digest=sha256(path)
            if name in hashes and digest!=hashes[name]:errors.append(f'Upstream hash mismatch: {name}')
            sources[name]={'sha256':digest,'mtime_ns':path.stat().st_mtime_ns,
                           'upstream_manifest_hash_verified':name in hashes}
        op=json.loads(row['notes'])['operation']
        if op=='json_key':value=json.loads(path.read_text())[row['source_row/key']]
        else:
            if name not in cache:cache[name]=pd.read_csv(path)
            subset=select(cache[name],json.loads(row['notes'])['filters'])
            if json.dumps(subset.index.tolist())!=row['source_row/key']:errors.append(f"Row mismatch: {row['fact_id']}")
            value=evaluate(subset,row['source_column'],op)
        if scalar(value)!=row['value']:errors.append(f"Value mismatch: {row['fact_id']}")
    if errors:raise ValueError('; '.join(errors))
    return {'verified':True,'fact_count':len(facts),'sources':sources}


def values(facts: pd.DataFrame) -> dict:
    """Decode a saved fact layer into a convenient ID-indexed mapping."""
    return {row.fact_id:json.loads(row.value) for row in facts.itertuples()}
