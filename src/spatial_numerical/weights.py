"""Weight geometry, spectral intervals and canonical-order diagnostics."""
from __future__ import annotations

import hashlib
import numpy as np
import pandas as pd
from src.spatial.distances import calculate_distance_matrix
from src.spatial.robustness import build_weight, row_standardize, distance_band_limits
from src.spatial_models.models import ordering_hash


def canonical(data: pd.DataFrame) -> pd.DataFrame:
    """Canonical numeric station-ID order; fail on duplicates, never drop a station."""
    result = data.copy()
    result['station_id'] = result.station_id.astype(str)
    if result.station_id.duplicated().any() or result.empty:
        raise ValueError('Duplicate or empty station set')
    return result.sort_values('station_id', key=lambda x: pd.to_numeric(x, errors='raise')).reset_index(drop=True)


def matrix_hash(matrix: np.ndarray) -> str:
    """Canonical float64 little-endian matrix fingerprint."""
    return hashlib.sha256(np.asarray(matrix, dtype='<f8').tobytes()).hexdigest()


def weight_settings(distances: pd.DataFrame) -> list[dict]:
    """Nine predeclared configurations, one data-derived cutoff; no grid search."""
    _, cutoff = distance_band_limits(distances)
    cutoff = float(np.nextafter(cutoff, np.inf))
    settings = [
        dict(weight_type='directed_knn_k4',family='directed_knn',k=4,row_standardized=True),
        dict(weight_type='symmetric_knn_k4',family='symmetric_knn',k=4,row_standardized=True),
        dict(weight_type='distance_band_x1',family='distance_band',cutoff_km=cutoff,row_standardized=True)]
    for power in (1,2):
        for variant, standardized, radius in [('row',True,None), ('raw',False,None), ('cutoff_row',True,cutoff)]:
            settings.append(dict(weight_type=f'inverse_distance_p{power}_{variant}',family='inverse_distance',
                                 power=power,row_standardized=standardized,cutoff_km=radius))
    return settings


def build_matrix(distances: pd.DataFrame, setting: dict) -> tuple[np.ndarray,np.ndarray]:
    """Return genuine pre-standardization and selected matrices with no zero-distance pairs."""
    d = distances.to_numpy(float)
    n = len(d)
    if not np.isfinite(d).all() or np.any(d[~np.eye(n,dtype=bool)] <= 0):
        raise ValueError('Nonfinite or zero-distance distinct stations')
    if setting['family'] == 'inverse_distance':
        raw = np.zeros_like(d)
        np.power(d, -float(setting['power']), out=raw, where=d>0)
        if setting.get('cutoff_km') is not None:
            raw[d>setting['cutoff_km']] = 0
    elif setting['family'] == 'distance_band':
        raw = ((d>0)&(d<=setting['cutoff_km'])).astype(float)
    else:
        old = {'weight_family':setting['family'],'k':setting['k']}
        raw = (build_weight(distances,old).matrix > 0).astype(float)
    if not np.isfinite(raw).all() or (raw.sum(axis=1)==0).any():
        raise ValueError('Invalid weights or isolated station')
    return raw, row_standardize(raw) if setting['row_standardized'] else raw.copy()


def spectral_properties(matrix: np.ndarray) -> tuple[dict,np.ndarray]:
    """Zero-connected nonsingularity interval, distinct from Neumann convergence interval."""
    w = np.asarray(matrix,float)
    if w.ndim!=2 or w.shape[0]!=w.shape[1] or not np.isfinite(w).all():
        raise ValueError('Invalid weight matrix')
    eigen = np.linalg.eigvals(w)
    if not np.isfinite(eigen).all():
        raise ValueError('Nonfinite spectrum')
    radius = float(np.abs(eigen).max())
    if radius <= 0:
        raise ValueError('Positive spectral radius required')
    tolerance = 1e-9 * max(1.,radius)
    real = eigen.real[np.abs(eigen.imag) <= tolerance]
    positive, negative = real[real>tolerance], real[real < -tolerance]
    upper = float(1/positive.max()) if len(positive) else np.inf
    lower = float(1/negative.min()) if len(negative) else -np.inf
    return dict(eigenvalue_min_real_part=float(eigen.real.min()),eigenvalue_max_real_part=float(eigen.real.max()),
                max_eigenvalue_imaginary=float(np.abs(eigen.imag).max()),spectral_radius=radius,
                lower_admissible_bound=lower,upper_admissible_bound=upper,
                neumann_lower=-1/radius,neumann_upper=1/radius,
                solver_lower=-1.,solver_upper=1.,real_eigenvalue_tolerance=tolerance,
                matrix_rank=int(np.linalg.matrix_rank(w)),condition_number=float(np.linalg.cond(w))),eigen


def boundary_distance(estimate: float, lower: float, upper: float, threshold: float=.01) -> dict:
    """Signed boundary distances; 1% operational near-boundary flag, not a model estimate."""
    if lower>=upper:
        raise ValueError('Invalid interval')
    if not np.isfinite(estimate):
        return dict(distance_to_lower_bound=np.nan,distance_to_upper_bound=np.nan,
                    relative_boundary_distance=np.nan,near_boundary=False,outside_interval=False)
    left, right = estimate-lower, upper-estimate
    fraction = min(left,right)/(upper-lower) if np.isfinite(upper-lower) else np.nan
    return dict(distance_to_lower_bound=left,distance_to_upper_bound=right,relative_boundary_distance=fraction,
                near_boundary=bool(np.isfinite(fraction) and fraction<=threshold),outside_interval=bool(left<0 or right<0))


def diagnose_weights(master: pd.DataFrame) -> tuple[dict,dict[str,pd.DataFrame]]:
    """Build a fixed weight inventory with row and full eigen-spectrum diagnostics."""
    master=canonical(master)
    distances=calculate_distance_matrix(master)
    inventory, diagnostics, spectra, rows = {},[],[],[]
    for setting in weight_settings(distances):
        raw,w=build_matrix(distances,setting)
        spectral,eigen=spectral_properties(w)
        n=len(w); nonzero=w[w>0]; normalized=row_standardize(w)
        row={'weight_type':setting['weight_type'],**setting,**spectral,'n_stations':n,
             'nonzero_count':len(nonzero),'density':len(nonzero)/(n*(n-1)),
             'min_nonzero_weight':float(nonzero.min()),'median_nonzero_weight':float(np.median(nonzero)),
             'max_weight':float(nonzero.max()),'row_sum_before_min':float(raw.sum(axis=1).min()),
             'row_sum_before_median':float(np.median(raw.sum(axis=1))),'row_sum_before_max':float(raw.sum(axis=1).max()),
             'row_sum_after_min':float(w.sum(axis=1).min()),'row_sum_after_max':float(w.sum(axis=1).max()),
             'mean_neighbor_effective_count':float(np.mean(1/np.sum(normalized**2,axis=1))),
             'adjacency_symmetric':bool(np.array_equal(w>0,w.T>0)),
             'raw_symmetric':bool(np.allclose(raw,raw.T)), 'numeric_symmetric':bool(np.allclose(w,w.T)),
             'isolates':int(np.sum(w.sum(axis=1)==0)), 'ordering_hash':ordering_hash(tuple(master.station_id)),
             'weight_hash':matrix_hash(w)}
        diagnostics.append(row)
        for i,value in enumerate(sorted(eigen,key=lambda z:(z.real,z.imag))):
            spectra.append(dict(weight_type=setting['weight_type'],eigen_index=i,real=float(value.real),imaginary=float(value.imag),absolute=float(abs(value))))
        for i,station_id in enumerate(master.station_id):
            rows.append(dict(weight_type=setting['weight_type'],station_id=station_id,
                             row_sum_before_standardization=raw[i].sum(),row_sum_after_standardization=w[i].sum()))
        inventory[setting['weight_type']]={'matrix':w,'raw':raw,'setting':setting,'spectral':spectral}
    return inventory,{'inverse_distance_weight_diagnostics':pd.DataFrame(diagnostics),
                      'spatial_weight_eigenvalues':pd.DataFrame(spectra),'spatial_weight_row_sums':pd.DataFrame(rows)}
