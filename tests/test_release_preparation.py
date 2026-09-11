"""Local archive release checks; intentionally separate from public-clone tests."""
from __future__ import annotations

import json

from scripts.prepare_public_release import ROOT, RELEASE, MANIFEST, check_protected, digest


def test_actual_research_artifacts_unchanged() -> None:
    """Every pre-release research file retains both its bytes and its filesystem timestamp."""
    baseline = json.loads((ROOT / RELEASE / 'qa/protected_baseline.json').read_text())
    result = check_protected(ROOT, baseline)
    assert result['file_count'] == baseline['file_count'] > 0
    assert result['content_changed'] == result['mtime_changed'] == []
    assert result['content_digest_before'] == result['content_digest_after']
    assert result['mtime_digest_before'] == result['mtime_digest_after']


def test_historical_release_manifest_unchanged() -> None:
    """Stage19 retains its original 1.0.0 metadata and exact completed manifest."""
    path = 'output/manifests/final_integration_manifest.json'
    baseline = json.loads((ROOT / RELEASE / 'qa/protected_baseline.json').read_text())
    old = json.loads((ROOT / path).read_text())
    assert old['VERSION'] == '1.0.0' and old['completed']
    assert digest(ROOT / path) == baseline['files'][path]['sha256']


def test_release_manifest_no_publication_claim() -> None:
    """The new local manifest cannot imply that a GitHub push or code-license choice occurred."""
    manifest = json.loads((ROOT / MANIFEST).read_text())
    assert manifest['release_version'] == '1.1.0' and manifest['previous_version'] == '1.0.0'
    assert not manifest['push_performed'] and not manifest['release_tag_created']
    assert manifest['license_status'] == 'pending'
