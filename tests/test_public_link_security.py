"""Exact-path publication and approved development-container security contracts."""
from __future__ import annotations

import json
import re

import pytest

from scripts.prepare_public_release import ROOT, ROOT_FILES, classify, scan

DEPLOYMENT_MANIFEST = 'output/final/release/v1.1.0_public_demo_deployment_manifest.json'


@pytest.mark.parametrize('name', ['.devcontainer/devcontainer.json', DEPLOYMENT_MANIFEST])
def test_approved_literal_public_paths(name: str) -> None:
    """Only the exact requested additions are explicitly selectable for publication."""
    assert name in ROOT_FILES and classify(name) == 'COMMIT'


@pytest.mark.parametrize('name', [
    '.devcontainer/other.json', '.devcontainer/sub/devcontainer.json', '.devcontainer/**',
    'output/**', 'output/final/release/private.json',
    'output/final/release/qa/internal.json', DEPLOYMENT_MANIFEST + '.bak', '.env',
])
def test_neighbor_and_wildcard_paths_stay_forbidden(name: str) -> None:
    """The two additions cannot admit sibling files, wildcard names, QA or credentials."""
    assert classify(name) == 'DO_NOT_COMMIT'


def test_devcontainer_security_contract() -> None:
    """Inspect configuration without executing any lifecycle or dependency-install command."""
    path = ROOT / '.devcontainer/devcontainer.json'
    text = path.read_text()
    config = json.loads(re.sub(r'^\s*//.*$', '', text, flags=re.M))
    assert not config.get('privileged')
    assert not any(key in config for key in ('mounts', 'workspaceMount', 'runArgs',
        'initializeCommand', 'postCreateCommand', 'postStartCommand', 'remoteEnv', 'containerEnv'))
    assert config['postAttachCommand'] == {'server': 'streamlit run public_app/streamlit_app.py'}
    assert config['updateContentCommand'] == (
        '[ -f packages.txt ] && sudo apt update && sudo xargs apt install -y <packages.txt; '
        '[ -f requirements.txt ] && pip3 install --user -r requirements.txt; '
        "pip3 install --user streamlit; echo '✅ Packages installed and Requirements met'")
    assert all(term not in text for term in ('docker.sock', 'sudo apt upgrade',
        '--server.enableCORS', '--server.enableXsrfProtection', 'localEnv:'))
    assert scan(ROOT, [path])['safe']


def test_public_deployment_metadata_security() -> None:
    """The deployment record contains public metadata, not private runtime credentials."""
    path = ROOT / DEPLOYMENT_MANIFEST
    manifest = json.loads(path.read_text())
    assert manifest['version'] == '1.1.0'
    assert manifest['live_demo'] == 'https://korea-climate-explorer.streamlit.app/'
    assert manifest['API_required'] is False and manifest['raw_cache_required'] is False
    assert manifest['public_mode_views'] == 7 and manifest['full_research_views'] == 18
    assert scan(ROOT, [path])['safe']
