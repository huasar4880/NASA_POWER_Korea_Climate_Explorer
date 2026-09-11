"""Stage14.5 real-data reproducibility/UI audit; never reruns previous-stage pipelines."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def verify(baseline_path: Path | None=None) -> dict:
    """Recheck new review products and all existing dashboard pages while blocking HTTP."""
    from streamlit.testing.v1 import AppTest
    from src.spatial_numerical.data import snapshot
    from src.spatial_numerical.workflow import MANIFEST,run_review,report_from_saved
    from src.spatial.robustness_audit import check_snapshot,sha256
    before=json.loads((ROOT/MANIFEST).read_text())
    protected=json.loads(baseline_path.read_text()) if baseline_path else snapshot(ROOT)
    with patch('requests.sessions.Session.request',side_effect=AssertionError('API forbidden during verification')):
        after=run_review(root=ROOT)
        changes=[name for name,digest in before['output_hashes'].items() if sha256(ROOT/name)!=digest]
        reports={name:sha256(ROOT/name) for name in after['generated_reports']}
        report_from_saved(ROOT)
        same_report=all(sha256(ROOT/name)==digest for name,digest in reports.items())
        pages={}
        for path in sorted((ROOT/'dashboard/pages').glob('*.py')):
            if path.stem.startswith('_'):
                continue
            app=AppTest.from_string(f'from dashboard.pages.{path.stem} import render\nrender()').run(timeout=60)
            errors=[str(item.value) for item in app.exception]
            pages[path.stem]={'passed':not errors,'exceptions':errors}
            if path.stem=='spatial_models' and not errors:
                for outcome in after['model_configs']['outcomes']:
                    app.selectbox[0].set_value(outcome).run(timeout=60)
                    if app.exception:
                        pages[path.stem]['passed']=False
                        pages[path.stem]['exceptions'].extend(str(item.value) for item in app.exception)
            print(f'{path.stem}: {"PASS" if pages[path.stem]["passed"] else "FAIL"}',flush=True)
        router=AppTest.from_file(str(ROOT/'streamlit_app.py')).run(timeout=60)
    protected_changed=check_snapshot(ROOT,protected)
    result={'compared_artifacts':len(before['output_hashes']),'reproducible_artifacts':len(before['output_hashes'])-len(changes),
            'changed_artifacts':changes,'report_regeneration_identical':same_report,
            'dashboard_pages':pages,'page_count':len(pages),'default_router_passed':not bool(router.exception),
            'protected_files_count':len(protected),'protected_files_changed':protected_changed,
            'NASA_API_calls':0,'KMA_API_calls':0,'http_requests_blocked':True,
            'review_completed':not changes and same_report and not protected_changed
                and all(p['passed'] for p in pages.values()) and not bool(router.exception)}
    path=ROOT/'output/reports/spatial_models_numerical/numerical_review_verification.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main() -> int:
    """Exit nonzero for software/protection failures, not diagnosed unsupported specifications."""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline',type=Path)
    result=verify(parser.parse_args().baseline)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['review_completed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
