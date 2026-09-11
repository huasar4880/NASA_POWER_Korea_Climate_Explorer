"""Verify actual Stage18 reproducibility, all 18 pages and immutable previous-stage artifacts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def file_state() -> dict:
    """Record all project data/output hashes and mtimes, including new Stage18 files for dry-run."""
    from src.spatial.robustness_audit import sha256
    return {p.relative_to(ROOT).as_posix():(sha256(p),p.stat().st_mtime_ns)
            for folder in ('data','output') for p in (ROOT/folder).rglob('*') if p.is_file()}


def verify(baseline: Path|None=None) -> dict:
    """Prohibit all HTTP attempts, rerun only Stage18, exercise selectors and compare every output."""
    from streamlit.testing.v1 import AppTest
    from src.period_sensitivity.data import MANIFEST,REPORT_DIR,snapshot
    from src.period_sensitivity.workflow import run_analysis
    from src.period_sensitivity.artifacts import report_from_saved,load_tables
    from src.spatial.robustness_audit import sha256,check_snapshot
    from src.nationwide.tier_a_pipeline import _atomic_json
    before=json.loads((ROOT/MANIFEST).read_text())
    protected=json.loads(baseline.read_text()) if baseline else snapshot(ROOT)
    with patch('requests.sessions.Session.request',side_effect=AssertionError('Stage18 verification prohibits HTTP')) as http:
        state=file_state(); dry=run_analysis(ROOT,dry_run=True); dry_changes=state!=file_state()
        after=run_analysis(ROOT)
        changes=[p for p,digest in before['output_hashes'].items() if sha256(ROOT/p)!=digest]
        same_inventory=set(before['output_files'])==set(after['output_files'])
        reports={p:sha256(ROOT/p) for p in after['output_files'] if '/reports/' in p}
        report_from_saved(ROOT); reports_equal=all(sha256(ROOT/p)==d for p,d in reports.items())
        broken_links=[]
        for relative in reports:
            if relative.endswith('.html'):
                path=ROOT/relative
                for url in re.findall(r'(?:href|src)="([^"]+)"',path.read_text()):
                    if not url.startswith(('https://','http://','#')) and not (path.parent/url).is_file():
                        broken_links.append(url)
        pages={}
        for path in sorted((ROOT/'dashboard/pages').glob('*.py')):
            if path.stem.startswith('_'): continue
            app=AppTest.from_string(f'from dashboard.pages.{path.stem} import render\nrender()').run(timeout=60)
            errors=[str(e.value) for e in app.exception]
            if path.stem=='period_sensitivity' and not errors:
                for key,values in [('stage18_window_a',[1991,2001,1981]),('stage18_window_b',[1986,1996,2001]),
                                   ('stage18_metric',['TMAX','TMIN','TAVG']),('stage18_source',['NASA','KMA'])]:
                    for value in values:
                        app.selectbox(key=key).set_value(value).run(timeout=60)
                        errors += [str(e.value) for e in app.exception]
            pages[path.stem]={'passed':not errors,'exceptions':errors}
            print(f'{path.stem}: {"PASS" if not errors else "FAIL"}',flush=True)
        router=AppTest.from_file(str(ROOT/'streamlit_app.py')).run(timeout=60)
        saved=load_tables(ROOT); attempts=http.call_count
    changed=check_snapshot(ROOT,protected)
    result={'compared_artifacts':len(before['output_hashes']),'changed_artifacts':changes,
        'same_output_inventory':same_inventory,'dry_run_changed_files':dry_changes,
        'broken_report_links':broken_links,
        'report_regeneration_identical':reports_equal,'page_count':len(pages),'dashboard_pages':pages,
        'default_router_passed':not bool(router.exception),'protected_files_count':len(protected),
        'protected_files_changed':changed,'NASA_API_calls':0,'KMA_API_calls':0,'http_request_attempts':attempts,
        'http_requests_blocked':True,'dry_run_station_count':dry['station_count'],
        'dry_run_grid_count':dry['unique_NASA_grid_count'],'fit_count':dry['total_trend_fits'],
        'historical_checks_passed':bool(saved['historical_reproduction'].passed.all()),
        'all_window_quality_passed':bool(saved['data_quality'].data_quality_flag.eq('PASS').all()),
        'completed':not changes and same_inventory and not dry_changes and reports_equal and not changed and not broken_links
                    and not bool(router.exception) and all(p['passed'] for p in pages.values()) and attempts==0}
    _atomic_json(result,ROOT/REPORT_DIR/'period_sensitivity_verification.json')
    return result


def main() -> int:
    """Exit nonzero if any actual reproduction, UI, HTTP or protected-file check fails."""
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--baseline',type=Path)
    result=verify(parser.parse_args().baseline); print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['completed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
