"""Read only explicitly selected, checksummed public assets; no research pipeline imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEMO = 'output/public_demo/'
DEPLOYMENT = DEMO + 'deployment/'
MANIFEST = DEPLOYMENT + 'manifest.json'
REPOSITORY = 'https://github.com/huasar4880/NASA_POWER_Korea_Climate_Explorer'
RELEASE = REPOSITORY + '/releases/tag/v1.1.0'
FIGURES = {
    'trends': DEPLOYMENT + 'common_period_tmax_tmin_trends.png',
    'comparison': 'docs/assets/final/common_period_kma_nasa_tavg_scatter.png',
    'errors': DEPLOYMENT + 'common_period_bias_rmse.png',
    'spatial': 'docs/assets/final/nasa_station_vs_grid_moran.png',
    'period': 'docs/assets/final/kma_tavg_median_slope_by_start_year.png',
}
REPORT = DEPLOYMENT + 'Final_Research_Report.html'
ALLOWED = frozenset({DEMO + 'final_research_fact_layer.csv', DEMO + 'final_evidence_matrix.csv',
    DEMO + 'EXECUTIVE_SUMMARY.md', REPORT, 'docs/FINAL_METHODS_SUMMARY.md',
    'docs/FINAL_LIMITATIONS.md', *FIGURES.values()})
UNAVAILABLE = 'This analysis is available in the full reproducible research environment.'
LIMITATIONS = (
    'Demo uses validated precomputed outputs.',
    'Full raw datasets and caches are not distributed in the public repository.',
    'Threshold metrics are analytical proxies.',
    'Station sample is not an area-weighted national mean.',
    'Spatial associations are not causal estimates.',
    'Trend magnitude is sensitive to the selected analysis period.',
)


def checksum(path: Path) -> str:
    """Hash an existing asset without mutating it."""
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def asset_path(name: str, root: Path = ROOT) -> Path:
    """Reject paths outside the selected public package, including symlinks to private caches."""
    if name not in ALLOWED:
        raise ValueError('Asset is outside the public allowlist')
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Unsafe asset path')
    return path


def verify_bundle(root: Path = ROOT) -> dict:
    """Validate exact bundle membership and hashes before showing research values."""
    manifest = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    if set(manifest['files']) != ALLOWED:
        raise ValueError('Public bundle membership mismatch')
    for name, expected in manifest['files'].items():
        if checksum(asset_path(name, root)) != expected:
            raise ValueError('Public asset checksum mismatch: ' + name)
    return manifest


def load_bundle(root: Path = ROOT) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load public facts and evidence only, with no environment keys or raw-data fallback."""
    verify_bundle(root)
    facts = pd.read_csv(asset_path(DEMO + 'final_research_fact_layer.csv', root), dtype=str)
    evidence = pd.read_csv(asset_path(DEMO + 'final_evidence_matrix.csv', root))
    if facts.fact_id.duplicated().any():
        raise ValueError('Duplicate public fact identifiers')
    return facts, evidence


def fact_values(facts: pd.DataFrame) -> dict[str, Any]:
    """Decode saved scalar values, without aggregating or fitting research data."""
    return {row.fact_id: json.loads(row.value) for row in facts.itertuples()}


def fact_table(facts: pd.DataFrame, identifiers: list[str]) -> pd.DataFrame:
    """Select original fact records with provenance; this is not a new analysis."""
    return facts.set_index('fact_id').loc[identifiers, ['value', 'unit', 'analysis_period',
        'source_file', 'source_column']].reset_index()
