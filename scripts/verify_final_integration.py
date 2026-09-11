"""Verify final saved-result integration, preserving all pre-stage data and outputs."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def dashboard_qa() -> dict:
    """Exercise every original page plus nondefault selections and empty filters without HTTP."""
    from streamlit.testing.v1 import AppTest
    pages={}
    with ExitStack() as stack:
        blockers=[stack.enter_context(patch(target,side_effect=AssertionError('Dashboard QA prohibits external HTTP')))
                  for target in ('requests.sessions.Session.request','urllib.request.urlopen','http.client.HTTPConnection.connect')]
        for path in sorted((ROOT/'dashboard/pages').glob('*.py')):
            if path.stem.startswith('_'):continue
            app=AppTest.from_string(f'from dashboard.pages.{path.stem} import render\nrender()').run(timeout=60)
            errors=[type(e).__name__+': '+str(e.value) for e in app.exception];interactions=[]
            if not errors and len(app.selectbox):
                widget=app.selectbox[0]
                if len(widget.options)>1:
                    # AppTest.select_index re-formats display labels in this Streamlit version.
                    # Send the same serialized display option that a browser sends instead.
                    states=app._tree.get_widget_states()
                    next(state for state in states.widgets if state.id==widget.id).string_value=widget.options[-1]
                    app._run(widget_state=states,timeout=60)
                    errors += [str(e.value) for e in app.exception];interactions.append('first selectbox: last option')
            if not errors and len(app.multiselect):
                app.multiselect[0].set_value([]).run(timeout=60)
                errors += [str(e.value) for e in app.exception];interactions.append('first multiselect: empty')
            pages[path.stem]={'passed':not errors,'exceptions':errors,'interactions':interactions,
                              'empty_filter':'tested' if any('empty' in x for x in interactions) else 'not applicable to this page'}
            print(f'{path.stem}: {"PASS" if not errors else "FAIL"}',flush=True)
        router=AppTest.from_file(str(ROOT/'streamlit_app.py')).run(timeout=60)
        attempts=sum(b.call_count for b in blockers)
    return {'page_count':len(pages),'pages':pages,'router_passed':not bool(router.exception),
            'network_attempts':attempts,'passed':all(p['passed'] for p in pages.values()) and not bool(router.exception) and attempts==0}


def verify(baseline_path: Path,run_tests: bool=True) -> dict:
    """Run cache-only builds, UI/report QA and regression; produce an honest release gate."""
    from src.final_integration.audit import report_qa,test_summary,finish_manifest,release_checklist
    from src.final_integration.workflow import build,load_final
    from src.final_integration.documents import generate_documents,publication_documents
    from src.final_integration.content import figures
    from src.final_integration.facts import FINAL
    from src.nationwide.tier_a_pipeline import _atomic_json
    from src.spatial.robustness_audit import sha256,check_snapshot
    baseline=json.loads(baseline_path.read_text());changed=check_snapshot(ROOT,baseline)
    if changed:raise ValueError('Protected files already changed; do not reset baseline')
    target=ROOT/FINAL/'qa';target.mkdir(parents=True,exist_ok=True)
    _atomic_json(baseline,target/'protected_baseline.json')
    env={'python':platform.python_version(),'platform':platform.system(),
         'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata['Name']}}
    _atomic_json(env,target/'environment.json')
    release_checklist(ROOT,{})
    before=build(ROOT)
    paths=['final_research_fact_layer.csv','final_evidence_matrix.csv','final_figure_registry.csv',
           'EXECUTIVE_SUMMARY.md',before['report']['html'].removeprefix('output/final/'),before['report']['markdown'].removeprefix('output/final/')]
    hashes={p:sha256(ROOT/FINAL/p) for p in paths}
    build(ROOT);reproduced=all(sha256(ROOT/FINAL/p)==h for p,h in hashes.items())
    facts,ev=load_final(ROOT);rqa=report_qa(ROOT,facts)
    ui=dashboard_qa();_atomic_json(ui,target/'dashboard.json')
    collected=subprocess.run([sys.executable,'-m','pytest','--collect-only','-q'],cwd=ROOT,capture_output=True,text=True,check=False)
    nodes=[line.strip() for line in collected.stdout.splitlines() if line.startswith('tests/') and '::' in line]
    if collected.returncode or not nodes:raise ValueError('pytest collection failed')
    test_summary(ROOT,nodes)
    http=json.loads((target/'http.json').read_text()) if (target/'http.json').is_file() else {'passed':False,'status':'not run'}
    qa={'report':rqa,'dashboard':ui,'http':http,'reproducibility':reproduced,
        'documents':all((ROOT/p).is_file() for p in before['documents']),'pip_check':False}
    finish_manifest(ROOT,baseline,qa)
    if run_tests:
        process=subprocess.run([sys.executable,'-m','pytest','-q','--junitxml=output/final/qa/pytest.xml'],cwd=ROOT,check=False)
        if (target/'pytest.xml').is_file():test_summary(ROOT,nodes,target/'pytest.xml')
        qa['pytest_exit_code']=process.returncode
    pip=subprocess.run([sys.executable,'-m','pip','check','--disable-pip-version-check'],cwd=ROOT,capture_output=True,text=True,check=False)
    qa['pip_check']=pip.returncode==0
    qa['pip_result']='No broken requirements found.' if qa['pip_check'] else 'Dependency conflict; inspect local pip check'
    generate_documents(ROOT,facts,ev,figures(facts));publication_documents(ROOT)
    _atomic_json(qa,target/'verification.json')
    final=finish_manifest(ROOT,baseline,qa)
    print(json.dumps({'completed':final['completed'],'gates':final['gates'],'tests':final['test_count'],
                      'passed':final['passed'],'protected_changes':final['protected_files_changed']},ensure_ascii=False,indent=2))
    return final


def main() -> int:
    """Require an explicit pre-work snapshot; never silently accept a changed baseline."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    result=verify(parser.parse_args().baseline)
    return 0 if result['completed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
