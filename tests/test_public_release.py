"""Offline lightweight-clone tests: no private archive, credentials or API calls required."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest

from scripts.prepare_public_release import (DEMO, FIGURES, ROOT, candidates, check_links,
    check_protected, classify, digest, inventory, scan, snapshot)
from src.final_integration.workflow import load_final
from scripts.check_release_safety import PUBLIC_RELEASE_NAME, PUBLIC_RELEASE_EMAIL


def test_release_version() -> None:
    """The approved public software version is fixed explicitly."""
    assert (ROOT / 'VERSION').read_text().strip() == '1.1.0'


def test_readme_release_entrypoint() -> None:
    """Version, approved code license and distinct lightweight instructions are discoverable."""
    text = (ROOT / 'README.md').read_text()
    assert all(s in text for s in ('v1.1.0', 'Code License:', '[MIT License](LICENSE)', 'test_public_release.py', 'public_demo/'))


def test_changelog_sections() -> None:
    """Release notes preserve historic v1.0 and include four required v1.1 sections."""
    text = (ROOT / 'CHANGELOG.md').read_text()
    assert all(s in text for s in ('## [1.1.0]', '## [1.0.0]', '### Added', '### Changed',
                                  '### Validated', '### Known Limitations'))


@pytest.mark.parametrize('name', ['.env', '.env.production', 'data/raw/private.csv',
    'data/processed/private.csv', 'data/geospatial/coastline/source.zip',
    'output/final/qa/audit.json', 'output/final/release/qa/baseline.json', 'logs/run.log'])
def test_private_files_ignored(tmp_path: Path, name: str) -> None:
    """Real Git ignore evaluation excludes private files, including absent future caches."""
    shutil.copyfile(ROOT / '.gitignore', tmp_path / '.gitignore')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, capture_output=True)
    result = subprocess.run(['git', '-C', str(tmp_path), 'check-ignore', '-q', name])
    assert result.returncode == 0 and classify(name) == 'DO_NOT_COMMIT'


def test_env_example_is_blank() -> None:
    """The example exposes the actual environment variable name without a credential."""
    lines = (ROOT / '.env.example').read_text().splitlines()
    name = 'KMA_' + 'API_KEY' + '='
    assert [x for x in lines if x.startswith(name)] == [name]


def test_public_candidate_scan() -> None:
    """Source, docs, tests and CSV payloads have no secret or personal-path findings."""
    assert scan(ROOT, candidates(ROOT))['safe']


def test_scanner_reports_only_paths(tmp_path: Path) -> None:
    """Synthetic sensitive literals are detected without returning matched values."""
    payload = 'fake-only-' + '0123456789abcdef'
    path = tmp_path / 'sample.csv'
    path.write_text('Authorization: Bear' + 'er ' + payload + '\n/Us' + 'ers/example/private\n')
    result = scan(tmp_path, [path])
    assert not result['safe'] and result['risks'][0]['personal_path']
    assert result['risks'][0]['secret'] and payload not in json.dumps(result)
    source = tmp_path / 'matrix.py'
    source.write_text('result = matrix' + '@' + 'np.linalg\n')
    assert scan(tmp_path, [source])['safe']
    source.write_text('contact = ' + repr('private' + '@' + 'example.org'))
    assert scan(tmp_path, [source])['risks'][0]['email']


def test_exact_key_never_fixture_exempt(tmp_path: Path) -> None:
    """Even test fixtures cannot publish an exact match of a locally configured key."""
    path = tmp_path / 'tests/test_kma_asos.py'
    path.parent.mkdir()
    value = 'only-in-temporary-' + 'fixture-0123456789'
    path.write_text(value)
    with patch('scripts.check_release_safety._local_kma_variants', return_value={value}):
        assert scan(tmp_path, [path])['risks'][0]['secret']


@pytest.mark.parametrize('key', ['serviceKey', 'api_key'])
def test_quoted_dictionary_key_scan(tmp_path: Path, key: str) -> None:
    """Quoted dictionary/JSON credential fields are checked, not only query strings."""
    path = tmp_path / 'sample.json'
    value = 'temporary-test-' + '0123456789abcdef'
    path.write_text(json.dumps({key: value}))
    result = scan(tmp_path, [path])
    assert not result['safe'] and result['risks'][0]['secret']
    assert value not in json.dumps(result)


def test_public_relative_links() -> None:
    """Published Markdown links resolve inside the lightweight set, not just on this machine."""
    assert check_links(ROOT, candidates(ROOT)) == []


def test_demo_assets() -> None:
    """Only three registry-selected existing PNGs and checksummed summary copies are shipped."""
    manifest = json.loads((ROOT / DEMO / 'public_demo_manifest.json').read_text())
    assert len(manifest['figures']) == len(FIGURES) == 3
    for name, expected in manifest['payload_hashes'].items():
        assert digest(ROOT / DEMO / name) == expected
    for name, expected in manifest['figures'].items():
        assert digest(ROOT / name) == expected
        assert (ROOT / name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_public_categories() -> None:
    """Public selection is explicit, with historic reports optional and caches forbidden."""
    assert classify('reporting/templates/city_report.html.j2') == 'COMMIT'
    assert classify('output/public_demo/final_evidence_matrix.csv') == 'COMMIT'
    assert classify('output/final/report/full.html') == 'OPTIONAL'
    assert classify('data/raw.csv') == 'DO_NOT_COMMIT'
    assert classify('../outside.py') == 'DO_NOT_COMMIT'


def test_no_large_candidates_or_forbidden_index() -> None:
    """No public candidate exceeds the hard size limit; any present Git index stays allowlisted."""
    result = inventory(ROOT)
    assert not result['over_50_MB'] and not result['over_100_MB']
    probe = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z'], capture_output=True, text=True)
    if probe.returncode == 0:
        assert all(classify(p) == 'COMMIT' for p in probe.stdout.split('\0') if p)


def test_approved_mit_license() -> None:
    """The user's approved license is present; its completion is recorded separately from push."""
    assert (ROOT / 'LICENSE').read_text().startswith('MIT License\n')
    assert digest(ROOT / 'LICENSE') == '541e79c362c186b3052495525ee6c8e086ca575ff961828f73cf689392667308'
    assert '- [x] Choose code license before public GitHub push' in (ROOT / 'docs/RELEASE_CHECKLIST.md').read_text()


def test_demo_manifest_versions() -> None:
    """New release metadata distinguishes current version from historical research provenance."""
    manifest = json.loads((ROOT / DEMO / 'public_demo_manifest.json').read_text())
    assert manifest['release_version'] == '1.1.0' and manifest['previous_version'] == '1.0.0'


def test_protection_detects_changes(tmp_path: Path) -> None:
    """Content and timestamp changes cannot silently pass the release protection gate."""
    folder = tmp_path / 'data'; folder.mkdir()
    path = folder / 'fixture.txt'; path.write_text('original')
    before = snapshot(tmp_path)
    assert not check_protected(tmp_path, before)['content_changed']
    path.write_text('changed')
    result = check_protected(tmp_path, before)
    assert result['content_changed'] == ['data/fixture.txt']
    assert result['mtime_changed'] == ['data/fixture.txt']


def test_demo_load_without_archive_or_network(tmp_path: Path) -> None:
    """The normal loader reads the public-only checksum bundle without raw data or HTTP."""
    shutil.copytree(ROOT / DEMO, tmp_path / DEMO)
    with patch('requests.sessions.Session.request', side_effect=AssertionError('No HTTP')) as request:
        facts, evidence = load_final(tmp_path)
    assert len(facts) > 0 and len(evidence) > 0 and request.call_count == 0
    assert not (tmp_path / 'data').exists() and not (tmp_path / 'output/final').exists()


def test_demo_tampering_fails_closed(tmp_path: Path) -> None:
    """A corrupted public CSV cannot silently be presented as verified results."""
    shutil.copytree(ROOT / DEMO, tmp_path / DEMO)
    (tmp_path / DEMO / 'final_evidence_matrix.csv').write_text('tampered')
    with pytest.raises(ValueError, match='checksum'):
        load_final(tmp_path)


def test_approved_identity_allowed(tmp_path: Path) -> None:
    """Only the explicitly approved public identity is exempt from personal-identity findings."""
    path = tmp_path / 'identity.txt'
    path.write_text(PUBLIC_RELEASE_NAME + '\n' + PUBLIC_RELEASE_EMAIL)
    assert scan(tmp_path, [path])['safe']


def test_approved_identity_does_not_hide_paths(tmp_path: Path) -> None:
    """A private absolute path remains forbidden even when it contains the approved author name."""
    path = tmp_path / 'private.txt'
    path.write_text('/Us' + 'ers/' + PUBLIC_RELEASE_NAME + '/Desktop/private')
    result = scan(tmp_path, [path])
    assert not result['safe'] and result['risks'][0]['personal_path']


def test_other_emails_still_forbidden(tmp_path: Path) -> None:
    """Private mail and unapproved noreply variants are not covered by the exact allowlist."""
    path = tmp_path / 'private.txt'
    for value in ('not-public' + '@' + 'naver.com', 'other-' + PUBLIC_RELEASE_EMAIL):
        path.write_text(value)
        assert scan(tmp_path, [path])['risks'][0]['email']
