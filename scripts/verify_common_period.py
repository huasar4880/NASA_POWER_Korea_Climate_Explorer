"""Real cache-only Stage16 rerun, all-page Streamlit checks and immutable-stage audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify(baseline: Path | None = None) -> dict:
    """Block HTTP and verify reproducibility, UI filters, reports, prior hash/mtime."""
    from streamlit.testing.v1 import AppTest
    from src.common_period.data import MANIFEST, REPORT_DIR, snapshot
    from src.common_period.workflow import run_analysis
    from src.common_period.artifacts import report_from_saved
    from src.spatial.robustness_audit import sha256, check_snapshot
    before = json.loads((ROOT/MANIFEST).read_text())
    protected = json.loads(baseline.read_text()) if baseline else snapshot(ROOT)
    with patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP forbidden in common-period verification')):
        after = run_analysis(ROOT)
        changes = [name for name, digest in before['output_hashes'].items() if sha256(ROOT/name) != digest]
        reports = {name: sha256(ROOT/name) for name in after['output_files'] if '/reports/' in name}
        report_from_saved(ROOT)
        reports_equal = all(sha256(ROOT/name) == digest for name, digest in reports.items())
        pages = {}
        for path in sorted((ROOT/'dashboard/pages').glob('*.py')):
            if path.stem.startswith('_'):
                continue
            app = AppTest.from_string(f'from dashboard.pages.{path.stem} import render\nrender()').run(timeout=60)
            errors = [str(e.value) for e in app.exception]
            if path.stem == 'common_period' and not errors:
                for shared in ['공유 grid', '단독 grid', '전체']:
                    app.selectbox[0].set_value(shared).run(timeout=60)
                    errors += [str(e.value) for e in app.exception]
                app.multiselect[0].set_value(['TIER_B']).run(timeout=60)
                errors += [str(e.value) for e in app.exception]
                app.multiselect[2].set_value([]).run(timeout=60)
                errors += [str(e.value) for e in app.exception]
            pages[path.stem] = {'passed': not errors, 'exceptions': errors}
            print(f'{path.stem}: {"PASS" if not errors else "FAIL"}', flush=True)
        router = AppTest.from_file(str(ROOT/'streamlit_app.py')).run(timeout=60)
    changed = check_snapshot(ROOT, protected)
    result = {'compared_artifacts': len(before['output_hashes']), 'changed_artifacts': changes,
              'report_regeneration_identical': reports_equal, 'page_count': len(pages), 'dashboard_pages': pages,
              'default_router_passed': not bool(router.exception), 'protected_files_count': len(protected),
              'protected_files_changed': changed, 'NASA_API_calls': after['NASA_API_calls'], 'KMA_API_calls': after['KMA_API_calls'],
              'http_requests_blocked': True, 'tier_b_reproduction_passed': after['tier_b_reproduction_passed'],
              'completed': not changes and reports_equal and not changed and not bool(router.exception)
              and all(p['passed'] for p in pages.values()) and after['NASA_API_calls'] == after['KMA_API_calls'] == 0}
    (ROOT/REPORT_DIR/'common_period_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


def main() -> int:
    """Return nonzero for any reproducibility, protection or UI failure."""
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--baseline', type=Path)
    result = verify(parser.parse_args().baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
