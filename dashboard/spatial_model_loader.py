"""Read-only Stage-14 loader with explicit mtime invalidation."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from src.config import PROJECT_ROOT


@st.cache_data(show_spinner=False)
def _read(path: str, mtime_ns: int) -> pd.DataFrame:
    """Cache by file modification time; station IDs remain strings."""
    return pd.read_csv(path, dtype={'station_id':str, 'excluded_station_id':str})


def load_manifest(root: Path = PROJECT_ROOT) -> dict:
    """Return an empty state if Stage 14 has not been generated."""
    try:
        return json.loads((root/'output/manifests/spatial_modeling_manifest.json').read_text())
    except (OSError, ValueError):
        return {}


def load_table(name: str, root: Path = PROJECT_ROOT) -> pd.DataFrame:
    """Read only manifested Stage-14 table paths; prohibit path traversal."""
    relative = load_manifest(root).get('generated_tables', {}).get(name)
    if not relative:
        return pd.DataFrame()
    path = (root/relative).resolve()
    namespace = (root/'output/tables/spatial_models').resolve()
    if not path.is_relative_to(namespace) or not path.is_file():
        return pd.DataFrame()
    try:
        return _read(str(path), path.stat().st_mtime_ns)
    except (OSError, ValueError):
        return pd.DataFrame()
