"""Read-only protected artifact snapshots for Stage 13."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    """Hash a file without changing it."""
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(root: Path) -> dict[str, dict[str, object]]:
    """Record all existing data/output files and stable VERSION, excluding Stage 13."""
    paths = [root / 'VERSION']
    for directory in ('data', 'output'):
        paths.extend(p for p in (root / directory).rglob('*') if p.is_file())
    excluded = ('data/geospatial/coastline/', 'output/tables/robustness/',
                'output/tables/coastal/', 'output/charts/robustness/',
                'output/charts/coastal/', 'output/reports/robustness/')
    result = {}
    for path in sorted(paths):
        name = path.relative_to(root).as_posix()
        if name.startswith(excluded) or name in {
            'output/manifests/spatial_robustness_manifest.json',
            'output/tables/spatial_robustness_and_coastal_summary.csv',
        }:
            continue
        result[name] = {'sha256': sha256(path), 'mtime_ns': path.stat().st_mtime_ns}
    return result


def check_snapshot(root: Path, before: dict) -> list[str]:
    """Return names of changed/deleted protected baseline files."""
    return [name for name, info in before.items() if not (root / name).is_file()
            or sha256(root / name) != info['sha256']
            or (root / name).stat().st_mtime_ns != info['mtime_ns']]
