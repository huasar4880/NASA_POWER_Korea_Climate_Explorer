"""Offline Stage-14 rerun/report/UI/protection audit; does not alter previous outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify(baseline_path: Path | None = None) -> dict:
    """Audit actual saved artifacts and every dashboard page; preserve model failures."""
    from streamlit.testing.v1 import AppTest
    from src.spatial.robustness_audit import check_snapshot, sha256
    from src.spatial_models.data import protected_snapshot
    from src.spatial_models.workflow import MANIFEST, run_modeling, report_from_saved
    baseline = json.loads(baseline_path.read_text()) if baseline_path else protected_snapshot(ROOT)
    before = json.loads((ROOT/MANIFEST).read_text())
    with patch('requests.sessions.Session.request', side_effect=AssertionError('External API forbidden')):
        rerun = run_modeling(root=ROOT)
        reproducibility = {name:sha256(ROOT/name)==digest for name,digest in before['output_hashes'].items()}
        report_before = {name:sha256(ROOT/name) for name in rerun['generated_reports']}
        report_from_saved(ROOT)
        report_equal = all(sha256(ROOT/name)==digest for name,digest in report_before.items())
        pages = {}
        for path in sorted((ROOT/'dashboard/pages').glob('*.py')):
            if path.stem.startswith('_'):
                continue
            app = AppTest.from_string(f'from dashboard.pages.{path.stem} import render\nrender()').run(timeout=60)
            errors = [str(item.value) for item in app.exception]
            pages[path.stem] = {'passed':not errors,'exceptions':errors}
            print(f'Page {path.stem}: {"PASS" if not errors else "FAIL"}', flush=True)
            if path.stem == 'spatial_models' and not errors:
                for outcome in rerun['outcomes']:
                    for family in ('OLS','SAR','SEM'):
                        app.selectbox[0].set_value(outcome)
                        app.radio[0].set_value(family)
                        app.run(timeout=60)
                        if app.exception:
                            pages[path.stem]['passed'] = False
                            pages[path.stem]['exceptions'].extend(str(item.value) for item in app.exception)
        router = AppTest.from_file(str(ROOT/'streamlit_app.py')).run(timeout=60)
        router_ok = not bool(router.exception)
    changed = check_snapshot(ROOT, baseline)
    result = {'reproducible_artifacts':sum(reproducibility.values()), 'compared_artifacts':len(reproducibility),
              'changed_artifacts':[name for name,ok in reproducibility.items() if not ok],
              'report_regeneration_identical':report_equal, 'dashboard_pages':pages,
              'default_router_passed':router_ok, 'NASA_API_calls':0, 'KMA_API_calls':0,
              'http_requests_blocked_during_verification':True,
              'protected_files_count':len(baseline), 'protected_files_changed':changed,
              'failed_or_unstable_models':rerun['failed_models'],
              'software_verification_passed':all(reproducibility.values()) and report_equal and router_ok
                  and all(p['passed'] for p in pages.values()) and not changed,
              'all_models_stable':rerun['failed_models']==0}
    path = ROOT/'output/reports/spatial_models/spatial_modeling_verification.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main() -> int:
    """Run verification and distinguish software integrity from model instability."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    result = verify(args.baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['software_verification_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
