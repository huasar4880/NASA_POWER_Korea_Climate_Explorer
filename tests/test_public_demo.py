"""Deployment contracts that also run in a fresh public-only Python environment."""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from public_app.data import ALLOWED, ROOT, MANIFEST, FIGURES, asset_path, load_bundle, verify_bundle
from public_app.mode import app_mode
from public_app.app import VIEWS


@pytest.mark.parametrize('value,expected', [(None, 'public'), ('public', 'public'),
    ('invalid', 'public'), ('full', 'full')])
def test_safe_mode_default(monkeypatch, value: str | None, expected: str) -> None:
    """Missing or misspelled mode settings never expose the research router."""
    monkeypatch.delenv('APP_MODE', raising=False)
    if value is not None: monkeypatch.setenv('APP_MODE', value)
    assert app_mode() == expected


def test_public_payload_and_size() -> None:
    """The selected package is intact and remains small, with no raw cache content."""
    result = verify_bundle()
    assert set(result['files']) == ALLOWED and len(FIGURES) == 5
    assert sum(asset_path(name).stat().st_size for name in ALLOWED) < 10_000_000
    assert all(not name.startswith('data/') for name in ALLOWED)


@pytest.mark.parametrize('name', ['.env', 'data/raw/file.csv', '../private.csv'])
def test_reject_private_paths(name: str) -> None:
    """Public loaders cannot be redirected to a secret or raw cache."""
    with pytest.raises(ValueError, match='allowlist'): asset_path(name)


def test_no_raw_env_fallback(tmp_path: Path) -> None:
    """Only selected public files are sufficient to load the entire public package."""
    for name in (*ALLOWED, MANIFEST):
        target = tmp_path / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    facts, evidence = load_bundle(tmp_path)
    assert len(facts) > 0 and len(evidence) > 0
    assert not (tmp_path / 'data').exists() and not (tmp_path / '.env').exists()
    (tmp_path / next(iter(FIGURES.values()))).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum'): load_bundle(tmp_path)


@pytest.mark.parametrize('view', VIEWS)
def test_public_views_without_api(view: str) -> None:
    """Each public view renders with every external HTTP entry point blocked."""
    with ExitStack() as stack:
        blocked = [stack.enter_context(patch(target, side_effect=AssertionError('No public HTTP')))
            for target in ('requests.sessions.Session.request', 'urllib.request.urlopen', 'http.client.HTTPConnection.connect')]
        app = AppTest.from_string(f'from public_app.app import render\nrender({view!r})').run(timeout=30)
        assert not app.exception and len(app.title) == 1
        if app.selectbox:
            app.selectbox[0].select('TMIN').run(timeout=30)
            assert not app.exception
        assert sum(b.call_count for b in blocked) == 0


def test_missing_bundle_guidance() -> None:
    """Missing cache is an explicit guidance message, not a crash or a download attempt."""
    code = '''from unittest.mock import patch
from public_app.app import render
with patch('public_app.app.saved_bundle', side_effect=FileNotFoundError('missing')):
    render('Home')
'''
    app = AppTest.from_string(code).run(timeout=30)
    assert not app.exception and app.info and app.warning


def test_public_router_navigation() -> None:
    """The public-only Cloud entrypoint exposes exactly seven usable navigation choices."""
    app = AppTest.from_file(str(ROOT / 'public_app/streamlit_app.py')).run(timeout=30)
    assert not app.exception and tuple(app.radio[0].options) == VIEWS
    for view in VIEWS:
        app.radio[0].set_value(view).run(timeout=30)
        assert not app.exception


def test_public_import_avoids_research_dependencies() -> None:
    """No geospatial/statistical or acquisition module is imported by public startup."""
    code = """import sys
from public_app.app import run
blocked=('src.nasa_power','src.kma_asos','geopandas','shapely','libpysal','spreg','scipy','matplotlib','statsmodels')
assert not any(name in sys.modules for name in blocked)
"""
    process = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr


def test_report_is_self_contained() -> None:
    """The public HTML copy embeds its figures rather than requiring excluded assets."""
    from public_app.data import REPORT
    text = asset_path(REPORT).read_text()
    assert '<!doctype html>' in text.lower() and 'data:image/png;base64,' in text
    assert 'src="assets/' not in text


def test_display_hides_fact_anchors_without_editing_source() -> None:
    """Provenance markers remain in the downloadable source, not in the public prose."""
    from public_app.app import display_markdown
    from public_app.data import DEMO
    path = asset_path(DEMO + 'EXECUTIVE_SUMMARY.md')
    before = path.read_bytes()
    text = display_markdown(DEMO + 'EXECUTIVE_SUMMARY.md')
    assert '<!-- fact:' in before.decode() and '<!-- fact:' not in text
    assert '105' in text and path.read_bytes() == before
