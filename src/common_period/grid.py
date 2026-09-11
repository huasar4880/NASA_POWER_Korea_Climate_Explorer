"""Native MERRA-2 grid inference with independent full daily-series verification."""
from __future__ import annotations

import hashlib
import numpy as np
import pandas as pd

from src.nationwide.tier_a_pipeline import PreparedStation

GRID_SOURCE = 'https://power.larc.nasa.gov/docs/methodology/data/sources/'
GRID_ORIGIN_SOURCE = 'https://gmao.gsfc.nasa.gov/media/publications/zbly36ziNFDFbmYmvhQeVqPhUo/Collow1341.pdf'
GRID_METHOD = 'native MERRA-2 nearest centre inferred from official origin/resolution; not API-returned metadata'


def grid_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """Nearest native cell centre (origin -90/-180, step .5/.625); fail on exact ties."""
    if not np.isfinite([latitude, longitude]).all() or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Invalid grid query coordinate')
    indices = np.array([(latitude+90)/.5, (longitude+180)/.625])
    if np.isclose(indices % 1, .5, atol=1e-10, rtol=0).any():
        raise ValueError('Grid boundary tie: returned metadata required')
    lat = np.floor(indices[0]+.5)*.5-90
    lon = (np.floor(indices[1]+.5)*.625) % 360-180
    return float(lat), float(lon)


def grid_id(latitude: float, longitude: float) -> str:
    """Canonical ID uses grid coordinates, never station identity."""
    return f'merra2_{latitude:.3f}_{longitude:.3f}'


def series_fingerprint(frame: pd.DataFrame) -> str:
    """Hash sorted dates and all three temperatures; NaN positions are retained."""
    selected = frame[['date', 'T2M', 'T2M_MAX', 'T2M_MIN']].sort_values('date').copy()
    selected['date'] = pd.to_datetime(selected.date).dt.strftime('%Y-%m-%d')
    return hashlib.sha256(selected.to_csv(index=False, float_format='%.12g', na_rep='NaN').encode()).hexdigest()


def build_grid_mapping(stations: pd.DataFrame, prepared: list[PreparedStation]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Detect shared grid groups and full-series mismatches without deleting stations."""
    result = stations.copy()
    coordinates = [grid_coordinates(r.latitude, r.longitude) for r in result.itertuples()]
    result['nasa_grid_latitude'] = [c[0] for c in coordinates]
    result['nasa_grid_longitude'] = [c[1] for c in coordinates]
    result['nasa_grid_id'] = [grid_id(*c) for c in coordinates]
    result['nasa_grid_coordinate_method'] = GRID_METHOD
    result['nasa_grid_returned_metadata_available'] = False
    frames = {item.station_id: item.nasa for item in prepared}
    result['nasa_series_sha256'] = result.station_id.map({sid: series_fingerprint(f) for sid, f in frames.items()})
    if result.nasa_series_sha256.isna().any():
        raise ValueError('NASA station missing for grid validation')
    mapping = []
    for gid, group in result.groupby('nasa_grid_id', sort=True):
        ids = group.station_id.tolist()
        identical = all(np.array_equal(frames[ids[0]][['T2M', 'T2M_MAX', 'T2M_MIN']].to_numpy(dtype=float),
                                       frames[sid][['T2M', 'T2M_MAX', 'T2M_MIN']].to_numpy(dtype=float), equal_nan=True)
                        and pd.to_datetime(frames[ids[0]].date).reset_index(drop=True).equals(
                            pd.to_datetime(frames[sid].date).reset_index(drop=True)) for sid in ids)
        mapping.append({'nasa_grid_id': gid, 'nasa_grid_latitude': group.nasa_grid_latitude.iloc[0],
                        'nasa_grid_longitude': group.nasa_grid_longitude.iloc[0], 'station_count': len(group),
                        'station_ids': '|'.join(ids), 'station_names': '|'.join(group.station_name),
                        'cohort_origins': '|'.join(sorted(group.cohort_origin.unique())),
                        'grid_series_identical': identical, 'grid_mapping_mismatch': not identical,
                        'grid_coordinate_method': GRID_METHOD, 'grid_source': GRID_SOURCE})
    mapping = pd.DataFrame(mapping)
    result = result.merge(mapping[['nasa_grid_id', 'station_count', 'grid_series_identical', 'grid_mapping_mismatch']]
                          .rename(columns={'station_count': 'nasa_grid_group_size'}), on='nasa_grid_id', validate='many_to_one')
    result['nasa_grid_shared'] = result.nasa_grid_group_size.gt(1)
    # Equal series in different inferred cells also need investigation; do not silently merge cells.
    cross = result.groupby('nasa_series_sha256').nasa_grid_id.transform('nunique').gt(1)
    result['identical_series_across_different_grids'] = cross
    return result, mapping
