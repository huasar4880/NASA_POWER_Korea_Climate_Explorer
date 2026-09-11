"""Read-only Stage-13 loaders with mtime-based cache invalidation."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from src.config import PROJECT_ROOT


@st.cache_data(show_spinner=False)
def _read(path: str, mtime_ns: int) -> pd.DataFrame:
    """Read a selected CSV; mtime is an explicit cache key."""
    return pd.read_csv(path, dtype={'station_id':str})


def load_robustness_manifest(root: Path = PROJECT_ROOT) -> dict:
    """Return a saved manifest, or an empty state if not yet generated."""
    try:
        return json.loads((root/'output/manifests/spatial_robustness_manifest.json').read_text())
    except (OSError,ValueError):
        return {}


def load_robustness_table(key: str, root: Path = PROJECT_ROOT) -> pd.DataFrame:
    """Load only tables named by Stage-13 manifest; reject paths outside project."""
    manifest=load_robustness_manifest(root)
    name=manifest.get('generated_tables',{}).get(key)
    if not name:
        return pd.DataFrame()
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return pd.DataFrame()
    try:
        return _read(str(path),path.stat().st_mtime_ns)
    except (ValueError,OSError):
        return pd.DataFrame()
