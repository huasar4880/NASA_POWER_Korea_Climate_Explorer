"""Read-only research regression, with all new QA confined to the local release namespace."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_public_release import (MANIFEST, RELEASE, candidates, check_protected, classify,
    git_state, inventory, save_json)


def metadata(root: Path) -> dict:
    """Assemble observed local release state; never assert unexecuted gates as successful."""
    folder = root / RELEASE
    baseline = json.loads((folder / 'qa/protected_baseline.json').read_text())
    public = inventory(root)
    protected = check_protected(root, baseline)
    git = git_state(root)
    files = baseline['files']
    excluded = {key: sum(v['bytes'] for p, v in files.items() if p.startswith(prefix))
        for key, prefix in {'data_bytes': 'data/', 'historic_output_bytes': 'output/',
                            'coastline_bytes': 'data/geospatial/coastline/',
                            'stage19_qa_bytes': 'output/final/qa/'}.items()}
    excluded['total_excluded_research_bytes'] = sum(v['bytes'] for v in files.values())
    tests = {'status': 'not_run', 'collected': 0, 'passed': 0, 'failed': 0, 'errors': 0,
             'skipped': 0, 'existing': 0, 'new': 0}
    junit = folder / 'qa/pytest.xml'
    if junit.exists():
        cases = list(ET.parse(junit).iter('testcase'))
        tests.update(collected=len(cases), failed=sum(c.find('failure') is not None for c in cases),
            errors=sum(c.find('error') is not None for c in cases),
            skipped=sum(c.find('skipped') is not None for c in cases),
            new=sum(c.get('classname', '').endswith(('test_public_release', 'test_release_preparation')) for c in cases))
        tests['passed'] = len(cases) - tests['failed'] - tests['errors'] - tests['skipped']
        tests['existing'] = len(cases) - tests['new']
        tests['status'] = 'passed' if tests['passed'] == len(cases) and len(cases) > 0 else 'failed'
    qa = {}
    for name in ('pytest_runtime', 'pip', 'dashboard', 'report', 'public_clone'):
        path = folder / 'qa' / f'{name}.json'
        qa[name] = json.loads(path.read_text()) if path.exists() else {'passed': False, 'status': 'not_run'}
    forbidden = [p for p in set(git['staged_paths'] + git['tracked_paths']) if classify(p) != 'COMMIT']
    expected_index = set(public['paths'])
    index_matches = git['initialized'] and set(git['tracked_paths']) == expected_index
    gates = {'pytest': tests['status'] == 'passed' and qa['pytest_runtime'].get('passed', False),
        'pip': qa['pip'].get('passed', False), 'dashboard': qa['dashboard'].get('passed', False),
        'report': qa['report'].get('passed', False), 'public_clone': qa['public_clone'].get('passed', False),
        'protected': not protected['content_changed'] and not protected['mtime_changed'],
        'public_scan': public['scan']['safe'], 'links': not public['broken_links'],
        'large_files': not public['over_50_MB'], 'index': not forbidden and index_matches,
        'version': (root / 'VERSION').read_text().strip() == '1.1.0',
        'license_pending': not (root / 'LICENSE').exists(),
        'no_remote_or_tag': not git['remote_configured'] and git['tag_count'] == 0}
    result = {'release_version': '1.1.0', 'previous_version': baseline['previous_version'],
        'technical_preparation_complete': all(gates.values()), 'publication_approval': 'pending',
        'gates': gates, 'pytest': tests, 'pip_check': qa['pip'], 'qa': qa,
        'NASA_API_calls': 0, 'KMA_API_calls': 0,
        'network_rule': 'Release operations are offline; runtime network blockers recorded in QA',
        'protected_research_artifacts': protected, 'excluded_size': excluded,
        'public_candidates': public, 'git_repository_already_existed': False,
        'git': git, 'forbidden_files_staged': forbidden,
        'local_commit_created': bool(git['commit_hash']), 'local_commit_hash': git['commit_hash'],
        'intended_commit_message': 'Release v1.1.0 nationwide climate analysis platform',
        'identity_blocker': not (git['identity_name_present'] and git['identity_email_present']),
        'remote_configured': git['remote_configured'], 'push_performed': False,
        'release_tag_created': False, 'license_status': 'pending',
        'license_blocker': 'Choose code license before public GitHub push',
        'baseline_stage19_completed': baseline['stage19_completed'],
        'baseline_stage19_artifact_hashes_verified': baseline['stage19_artifact_hashes_verified'],
        'metadata_scope': 'Local untracked release evidence; excluded from commit to avoid commit-hash recursion'}
    save_json(root / MANIFEST, result)
    return result


def run_tests(root: Path) -> int:
    """Execute the full suite with external HTTP blocked; preserve the original Stage19 QA."""
    import pytest
    metadata(root)  # Pending manifest exists for contract tests, not a claim of completed QA.
    with ExitStack() as stack:
        blockers = [stack.enter_context(patch(target, side_effect=AssertionError('Release QA prohibits HTTP')))
            for target in ('requests.sessions.Session.request', 'urllib.request.urlopen', 'http.client.HTTPConnection.connect')]
        code = pytest.main(['-q', f'--junitxml={RELEASE}/qa/pytest.xml'])
        attempts = sum(b.call_count for b in blockers)
    save_json(root / RELEASE / 'qa/pytest_runtime.json',
              {'passed': code == 0 and attempts == 0, 'exit_code': int(code), 'network_attempts': attempts})
    return int(code)


def check_ui_and_report(root: Path) -> dict:
    """Exercise existing pages and parse the existing report without regenerating research files."""
    from scripts.verify_final_integration import dashboard_qa
    from src.final_integration.audit import report_qa
    from src.final_integration.workflow import load_final
    facts, _ = load_final(root)
    report = report_qa(root, facts)
    save_json(root / RELEASE / 'qa/report.json', report)
    ui = dashboard_qa()
    save_json(root / RELEASE / 'qa/dashboard.json', ui)
    return {'report': report['passed'], 'dashboard': ui['passed'], 'pages': ui['page_count']}


def public_clone_qa(root: Path) -> dict:
    """Test a temporary allowlist-only checkout; no raw cache, environment file or hidden archive."""
    env = dict(os.environ)
    env.pop('KMA_API_KEY', None)
    env.pop('PYTHONPATH', None)
    with tempfile.TemporaryDirectory(prefix='nasa-public-release-') as directory:
        export = Path(directory)
        for source in candidates(root):
            target = export / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        test_code = """from unittest.mock import patch
import pytest
with patch('requests.sessions.Session.request', side_effect=AssertionError('No HTTP')), patch('urllib.request.urlopen', side_effect=AssertionError('No HTTP')), patch('http.client.HTTPConnection.connect', side_effect=AssertionError('No HTTP')):
    raise SystemExit(pytest.main(['tests/test_public_release.py','-q']))
"""
        test = subprocess.run([sys.executable, '-c', test_code], cwd=export, env=env,
                              capture_output=True, text=True)
        app_code = """from contextlib import ExitStack
from unittest.mock import patch
from pathlib import Path
from streamlit.testing.v1 import AppTest
with ExitStack() as stack:
    blocks=[stack.enter_context(patch(t, side_effect=AssertionError('No HTTP'))) for t in ('requests.sessions.Session.request','urllib.request.urlopen','http.client.HTTPConnection.connect')]
    app=AppTest.from_file('streamlit_app.py').run(timeout=60)
    assert not app.exception
    assert len(app.metric)>=4
    assert not Path('data').exists() and not Path('.env').exists()
    assert not Path('output/final').exists()
    assert sum(b.call_count for b in blocks)==0
print('Public Home PASS; network attempts 0')
"""
        app = subprocess.run([sys.executable, '-c', app_code], cwd=export, env=env,
                             capture_output=True, text=True)
        # Preserve failure evidence privately; never print logs or matched values in status output.
        for name, process in (('public_clone_tests', test), ('public_clone_home', app)):
            path = root / RELEASE / 'qa' / f'{name}.log'
            path.write_text(process.stdout + process.stderr, encoding='utf-8')
        result = {'passed': test.returncode == app.returncode == 0, 'pytest_exit_code': test.returncode,
                  'home_exit_code': app.returncode, 'research_archive_included': False,
                  'credentials_included': False, 'network_blocked': True}
    save_json(root / RELEASE / 'qa/public_clone.json', result)
    return result


def main() -> int:
    """Select an offline verification action; never initialize, stage, commit or push Git."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('tests', 'ui', 'demo', 'finish'))
    action = parser.parse_args().action
    if action == 'tests': return run_tests(ROOT)
    if action == 'ui': print(json.dumps(check_ui_and_report(ROOT))); return 0
    if action == 'demo': print(json.dumps(public_clone_qa(ROOT))); return 0
    pip = subprocess.run([sys.executable, '-m', 'pip', 'check'], capture_output=True, text=True)
    save_json(ROOT / RELEASE / 'qa/pip.json', {'passed': pip.returncode == 0,
        'result': 'No broken requirements found.' if pip.returncode == 0 else 'Dependency conflict'})
    result = metadata(ROOT)
    print(json.dumps({key: result[key] for key in ('technical_preparation_complete', 'gates', 'pytest',
        'protected_research_artifacts', 'excluded_size', 'identity_blocker')}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
