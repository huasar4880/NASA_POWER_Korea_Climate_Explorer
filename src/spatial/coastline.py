"""Official KHOA coastline acquisition, immutable cache validation and metric distance."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile
from collections import Counter

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
import shapefile
from shapely.geometry import Point, MultiLineString, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.strtree import STRtree
from shapely import from_wkb

from src.config import PROJECT_ROOT
from src.spatial.robustness_audit import sha256

COAST_DIR = PROJECT_ROOT / 'data/geospatial/coastline'
SOURCE_URL = 'https://www.data.go.kr/data/15083948/fileData.do'
SOURCE = '해양수산부 국립해양조사원_해안선_20251231'


def download_official_archive(directory: Path = COAST_DIR) -> Path:
    """Follow official public portal download flow; never bypass CAPTCHA or replace raw."""
    import requests
    with requests.Session() as session:
        page = session.get(SOURCE_URL, timeout=30)
        page.raise_for_status()
        response = session.get('https://www.data.go.kr/tcs/dss/selectFileDataDownload.do', params={
            'publicDataPk':'15083948', 'publicDataDetailPk':'uddi:0ccd96a8-a234-412d-841e-81359f812202',
            'atchFileId':'', 'fileDetailSn':'1', 'publicDataTyCode':'PR0051'}, timeout=30)
        response.raise_for_status()
        metadata = response.json()
        if not metadata.get('status'):
            raise ValueError('Official coastline metadata unavailable')
        if metadata['dataSetFileDetailInfo']['dataNm'] != SOURCE:
            raise ValueError('coastline source changed: catalogue version needs explicit review')
        params = {'atchFileId': metadata['atchFileId'], 'fileDetailSn': metadata['fileDetailSn']}
        check = session.post('https://www.data.go.kr/cmm/cmm/check-limit.json', data=params, timeout=30)
        check.raise_for_status()
        if check.json().get('needCaptcha'):
            raise ValueError('Official download requires CAPTCHA; user download needed')
        params['dataNm'] = metadata['dataSetFileDetailInfo']['dataNm']
        filename = Path(metadata['fileDataRegistVO']['orginlFileNm']).name
        path = directory / 'raw' / filename
        if path.exists():
            return path
        directory.joinpath('raw').mkdir(parents=True, exist_ok=True)
        with session.get('https://www.data.go.kr/cmm/cmm/fileDownload.do', params=params, timeout=(30,120), stream=True) as result:
            result.raise_for_status()
            temp = path.with_suffix('.zip.partial')
            with temp.open('wb') as stream:
                for chunk in result.iter_content(1024 * 1024):
                    stream.write(chunk)
            if not zipfile.is_zipfile(temp):
                raise ValueError('Official response is not a ZIP archive; retained .partial for diagnosis')
            temp.replace(path)
        provenance = {'source_name':SOURCE, 'provider':'해양수산부 국립해양조사원', 'source_url':SOURCE_URL,
                      'reference_year':2025, 'retrieved_at':datetime.now(timezone.utc).isoformat(),
                      'license_note':'공공데이터포털 이용허락범위 제한 없음 (2026-09-08 확인)',
                      'archive_filename':filename, 'archive_sha256':sha256(path),
                      'archive_size_bytes':path.stat().st_size, 'download_url':result.url,
                      'archive_name_note':'Official catalogue reference is 20251231; attachment filename says 2026.'}
        directory.joinpath('acquisition.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
        return path


def validate_components(shp: Path) -> dict[str, Path]:
    """Require SHP, SHX, DBF and explicit PRJ with identical basename."""
    paths = {ext:shp.with_suffix(ext) for ext in ('.shp','.shx','.dbf','.prj')}
    if any(not p.is_file() for p in paths.values()):
        raise ValueError('Missing shapefile component (.shp/.shx/.dbf/.prj required)')
    return paths


def detect_crs(prj: Path) -> CRS:
    """Read declared CRS; never infer from coordinate magnitudes."""
    return CRS.from_wkt(prj.read_text(encoding='utf-8-sig'))


def validate_geometries(geometries: list) -> dict:
    """Fail closed on null/empty/invalid/non-line geometries; report exact duplicates."""
    empty = sum(g is None or g.is_empty for g in geometries)
    invalid = sum(g is not None and not g.is_valid for g in geometries)
    types = sorted({g.geom_type for g in geometries if g is not None})
    duplicates = len(geometries) - len({g.wkb for g in geometries if g is not None})
    if not geometries or empty or invalid or not set(types).issubset({'LineString','MultiLineString'}):
        raise ValueError(f'Coastline geometry rejected: empty={empty}, invalid={invalid}, types={types}')
    return {'feature_count':len(geometries), 'geometry_types':types,
            'empty_geometry_count':empty, 'duplicate_geometry_count':duplicates,
            'invalid_geometry_count_before':invalid, 'invalid_geometry_count_after':invalid,
            'repair_method':'none; invalid geometry fails closed; duplicates retained (distance invariant)'}


def include_official_coast(record: dict) -> bool:
    """Official specification: retain statistical Y natural/artificial coast; no bridges/river endpoints."""
    return int(record['GRP_CON']) in (1,2) and str(record['GRP_STA']).strip() == 'Y'


def repair_projected_line(geometry: BaseGeometry) -> BaseGeometry:
    """Remove only zero-length multipart fragments exactly covered by retained valid lines."""
    if geometry.is_valid:
        return geometry
    if geometry.geom_type != 'MultiLineString':
        raise ValueError('Unexpected projection invalidity; repair refused')
    valid=[part for part in geometry.geoms if part.is_valid]
    invalid=[part for part in geometry.geoms if not part.is_valid]
    if not valid:
        raise ValueError('No valid components remain; repair refused')
    repaired=MultiLineString(valid)
    for part in invalid:
        if part.length != 0 or any(repaired.distance(Point(p)) != 0 for p in part.coords):
            raise ValueError('Invalid fragment is not redundant; repair refused')
    return repaired


def prepare_coastline(archive: Path, directory: Path = COAST_DIR, analysis_crs: str = 'EPSG:5179') -> dict:
    """Validate official archive and persist provenance; preserve archive/source components."""
    acquisition = json.loads((directory / 'acquisition.json').read_text())
    if sha256(archive) != acquisition['archive_sha256']:
        raise ValueError('coastline source changed: archive checksum mismatch')
    extracted = directory / 'raw' / archive.stem
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            target = (extracted / member.filename).resolve()
            if not target.is_relative_to(extracted.resolve()):
                raise ValueError('Unsafe ZIP member path')
            if not target.exists():
                z.extract(member, extracted)
    candidates = list(extracted.rglob('*.shp'))
    if len(candidates) != 1:
        raise ValueError(f'Expected one unambiguous coastline SHP; found {len(candidates)}')
    shp = candidates[0]
    components = validate_components(shp)
    crs = detect_crs(components['.prj'])
    with shapefile.Reader(str(shp)) as reader:
        geometries = [shape(s.__geo_interface__) for s in reader.iterShapes()]
    summary = validate_geometries(geometries)
    bounds = np.array([g.bounds for g in geometries])
    manifest = {**acquisition, **summary, 'source_crs':crs.to_string(), 'source_crs_wkt':crs.to_wkt(),
                'analysis_crs':analysis_crs, 'geometry_filename':shp.relative_to(directory).as_posix(),
                'geometry_sha256':sha256(shp), 'component_hashes':{p.relative_to(directory).as_posix():sha256(p) for p in components.values()},
                'bounding_box':[float(bounds[:,0].min()),float(bounds[:,1].min()),float(bounds[:,2].max()),float(bounds[:,3].max())]}
    existing = directory / 'coastline_manifest.json'
    if existing.exists():
        previous=json.loads(existing.read_text())
        if previous['archive_sha256'] != manifest['archive_sha256'] or previous['component_hashes'] != manifest['component_hashes']:
            raise ValueError('coastline source changed: manifest differs; explicit review needed')
    directory.joinpath('processed').mkdir(exist_ok=True)
    with shapefile.Reader(str(shp)) as reader:
        records=list(reader.iterRecords())
    selected=[i for i,r in enumerate(records) if include_official_coast(r)]
    projection=Transformer.from_crs(crs,analysis_crs,always_xy=True)
    projected=[transform(projection.transform,geometries[i]) for i in selected]
    invalid_projected=sum(not g.is_valid for g in projected)
    repaired_ids=[selected[i] for i,g in enumerate(projected) if not g.is_valid]
    projected=[repair_projected_line(g) for g in projected]
    validate_geometries(projected)
    # Immutable processed full-resolution geometry: object-free hex WKB, official source IDs.
    cache=directory/'processed/coastline_epsg5179_wkb.json'
    payload={'analysis_crs':analysis_crs,'source_geometry_ids':selected,
             'geometry_wkb_hex':[g.wkb_hex for g in projected]}
    encoded=json.dumps(payload,separators=(',',':'))
    if cache.exists() and cache.read_text()!=encoded:
        raise ValueError('coastline source changed: processed geometry differs; review required')
    if not cache.exists():
        cache.write_text(encoded,encoding='utf-8')
    manifest.update({'analysis_feature_count':len(selected),'excluded_feature_count':len(records)-len(selected),
                     'selection_rule':'GRP_STA=Y AND GRP_CON in (1,2); official natural/artificial statistical coastline',
                     'island_groups_retained':dict(Counter(str(records[i]['GRP_ISL']) for i in selected)),
                     'survey_year_counts':dict(Counter(str(r['SOR_DAT']) for r in records)),
                     'processed_geometry_filename':cache.relative_to(directory).as_posix(),
                     'processed_geometry_sha256':sha256(cache), 'processed_size_bytes':cache.stat().st_size,
                     'attribute_specification':'해안선 속성테이블 명세서.pdf, pp.1,3',
                     'projected_invalid_before':invalid_projected,'projected_invalid_after':0,
                     'projection_repaired_source_ids':repaired_ids,
                     'projection_repair':'Remove only collapsed zero-length multipart fragments exactly covered by valid remaining line; geometric point set unchanged',
                     'processing_version':1})
    if not existing.exists() or json.loads(existing.read_text()) != manifest:
        existing.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


def load_coastline(analysis_crs: str, directory: Path = COAST_DIR) -> dict:
    """Read only validated cache; missing/corrupt geometry disables coastal analysis."""
    try:
        manifest = json.loads((directory / 'coastline_manifest.json').read_text())
        if manifest['source_url'] != SOURCE_URL or not manifest.get('license_note'):
            raise ValueError('Official source/license not verified')
        if sha256(directory/'raw'/manifest['archive_filename']) != manifest['archive_sha256']:
            raise ValueError('coastline source changed: archive checksum mismatch')
        for name, digest in manifest['component_hashes'].items():
            if sha256(directory/name) != digest:
                raise ValueError('coastline source changed: component checksum mismatch')
        shp = directory / manifest['geometry_filename']
        validate_components(shp)
        source_crs = detect_crs(shp.with_suffix('.prj'))
        target_crs = CRS.from_user_input(analysis_crs)
        if not target_crs.is_projected or any(a.unit_name != 'metre' for a in target_crs.axis_info):
            raise ValueError('Coastal distance requires projected metre CRS')
        cached=directory/manifest['processed_geometry_filename']
        if sha256(cached)!=manifest['processed_geometry_sha256']:
            raise ValueError('coastline source changed: processed checksum mismatch')
        payload=json.loads(cached.read_text())
        if payload['analysis_crs']!=analysis_crs or source_crs.to_string()!=manifest['source_crs']:
            raise ValueError('Cached CRS differs from requested/declared CRS')
        geometries=[from_wkb(g) for g in payload['geometry_wkb_hex']]
        summary=validate_geometries(geometries)
        if len(geometries)!=manifest['analysis_feature_count']:
            raise ValueError('Cached geometry count differs')
        if not np.isfinite([g.bounds for g in geometries]).all():
            raise ValueError('Nonfinite projected coastline')
        return {**manifest, 'analysis_geometry_validation':summary, 'analysis_crs':analysis_crs, 'available':True,
                'reason':'Official archive, components, CRS and line geometries validated',
                'geometries':geometries, 'tree':STRtree(geometries), 'source_geometry_ids':payload['source_geometry_ids']}
    except (OSError, ValueError, KeyError, shapefile.ShapefileException) as exc:
        return {'available':False, 'source_url':SOURCE_URL, 'source_name':SOURCE,
                'reason':f'공식 coastline geometry 미검증: {type(exc).__name__}: {str(exc).replace(str(PROJECT_ROOT), "PROJECT_ROOT")}'}


def station_distances(stations: pd.DataFrame, coast: dict) -> pd.DataFrame:
    """Shortest projected station-to-line distance in km; retain islands and all features."""
    projection = Transformer.from_crs('EPSG:4326', coast['analysis_crs'], always_xy=True)
    result = stations[['station_id','station_name','region_level1','latitude','longitude','elevation_m']].copy()
    distances, nearest = [], []
    for row in result.itertuples():
        if not np.isfinite([row.latitude,row.longitude]).all():
            raise ValueError('Missing station coordinates')
        point = Point(*projection.transform(row.longitude,row.latitude))
        index = int(coast['tree'].nearest(point))
        distances.append(point.distance(coast['geometries'][index]) / 1000)
        nearest.append(coast.get('source_geometry_ids',list(range(len(coast['geometries']))))[index])
    if not np.isfinite(distances).all() or np.any(np.array(distances) < 0):
        raise ValueError('Invalid coastal distance')
    result['distance_to_coast_km'] = distances
    result['nearest_coast_geometry_id'] = nearest
    result['coastline_source'] = coast['source_name']
    result['coastline_reference_year'] = coast['reference_year']
    result['analysis_crs'] = coast['analysis_crs']
    result['distance_method'] = 'shortest point-to-line projected Euclidean; metres / 1000'
    return result
