"""Stage19 fact, reporting, publication and read-only UI contracts; no live API tests."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import shutil
from unittest.mock import patch

import pandas as pd
import pytest

from src.config import PROJECT_ROOT as ROOT
from src.final_integration.audit import classify_test,page_count,report_qa,test_summary as summarize_tests
from src.final_integration.content import (HIGHLIGHTS,LIMITATIONS,METHODS,OFFICIAL_LINKS,RULES,
    evidence,figures,format_value,plain,references)
from src.final_integration.facts import FINAL,FactBook,build_facts,evaluate,scalar,values,verify_facts
from src.final_integration.report import REPORT_STEM,research_tables,sections
from src.final_integration.workflow import load_final,public_candidates,security_scan
from src.spatial.robustness_audit import sha256,check_snapshot


@pytest.fixture(scope='module')
def saved() -> pd.DataFrame:
    """Read immutable final facts once per module."""
    return load_final(ROOT)[0]


def test_final_fact_schema(saved) -> None:
    """Facts expose all requested provenance columns and unique IDs."""
    assert {'fact_id','topic','metric','value','unit','source_file','source_row/key','source_column','analysis_period','notes'}<=set(saved)
    assert saved.fact_id.is_unique and len(saved)>0 and not saved.isna().any().any()


def test_fact_topics(saved) -> None:
    """All research domains have actual saved evidence."""
    assert {'scale','temperature','dtr','contrast','seasonal','threshold','validation','spatial','coastal','period','model_review'}<=set(saved.topic)


def test_all_fact_provenance(saved) -> None:
    """Replay every selected value/aggregate and upstream checksum."""
    result=verify_facts(ROOT,saved)
    assert result['verified'] and result['fact_count']==len(saved)
    assert all(p['mtime_ns']>0 and len(p['sha256'])==64 for p in result['sources'].values())


def test_fact_tamper_detected(saved) -> None:
    """Changing a final value cannot silently pass provenance verification."""
    frame=saved.copy();frame.loc[frame.fact_id.eq('tier_a'),'value']='9999'
    with pytest.raises(ValueError,match='Value mismatch'):verify_facts(ROOT,frame)


def test_row_tamper_detected(saved) -> None:
    """Even a correct scalar fails if its recorded source rows are wrong."""
    frame=saved.copy();frame.loc[frame.fact_id.eq('inventory_n'),'source_row/key']='[]'
    with pytest.raises(ValueError,match='Row mismatch'):verify_facts(ROOT,frame)


@pytest.mark.parametrize('operation,expected',[('median',3.0),('positive_count',2),('negative_count',1),('count_rows',3)])
def test_descriptive_operations(operation,expected) -> None:
    """Allowed operations describe stored values and do not fit a model."""
    assert evaluate(pd.DataFrame({'v':[-1,3,7]}),'v',operation)==expected


def test_missing_not_zero() -> None:
    """A missing numeric source is not treated as a zero observation."""
    with pytest.raises(ValueError,match='Missing'):evaluate(pd.DataFrame({'v':[None]}),'v','median')


def test_empty_count_is_zero_but_empty_scalar_fails() -> None:
    """Zero matching rows is a legitimate count but never an invented data value."""
    frame=pd.DataFrame({'v':[]})
    assert evaluate(frame,'v','count_rows')==0
    with pytest.raises(ValueError,match='Empty'):evaluate(frame,'v','cell')


def test_unsupported_fit_fails() -> None:
    """Final integration explicitly rejects fitting operations."""
    with pytest.raises(ValueError,match='Unsupported'):evaluate(pd.DataFrame({'v':[1]}),'v','linear_regression')


def test_nonunique_cell_fails() -> None:
    """Scalar selection must not arbitrarily choose a row."""
    with pytest.raises(ValueError,match='not unique'):evaluate(pd.DataFrame({'v':[1,2]}),'v','cell')


def test_evidence_axes_and_classes(saved) -> None:
    """The matrix separates applicability, model sensitivity and project-defined classes."""
    ev=evidence(saved)
    assert len(ev)==8 and ev.conclusion_id.is_unique
    assert {'period_robustness','weight_robustness','grid_duplication_robustness','HC3/model_robustness'}<=set(ev)
    assert set(ev.final_evidence_class)<={'ROBUST','MODERATELY_ROBUST','SENSITIVE','DESCRIPTIVE_ONLY'}
    assert '운영규칙' in RULES


def test_robust_claims_have_sources(saved) -> None:
    """Every robust conclusion links real fact IDs, not unreferenced prose."""
    ev=evidence(saved);ids=set(saved.fact_id)
    assert set(ev.loc[ev.final_evidence_class.eq('ROBUST'),'conclusion_id'])=={'A','C','E','F'}
    assert all(set(row.main_metrics.split(';'))<=ids for row in ev.itertuples())


def test_sensitive_results_not_upgraded(saved) -> None:
    """Spatial/period sensitivity and conditional coastal inference stay visible."""
    ev=evidence(saved).set_index('conclusion_id')
    assert ev.loc['D','final_evidence_class']=='SENSITIVE'
    assert ev.loc['H','final_evidence_class']=='SENSITIVE'
    assert ev.loc['G','final_evidence_class']=='MODERATELY_ROBUST'
    assert 'RMSE model-sensitive' in ev.loc['G','HC3/model_robustness']


def test_classification_responds_to_evidence(saved) -> None:
    """Robust is not an unconditional string assigned regardless of the stored data."""
    modified=saved.copy()
    modified.loc[modified.fact_id.eq('allweights_tavg_bias_STATION_LINKED_stable'),'value']='0'
    assert evidence(modified).set_index('conclusion_id').loc['F','final_evidence_class']=='SENSITIVE'


def test_report_structure_and_consistency(saved) -> None:
    """Actual HTML contains the expected report structure and correct displayed values."""
    qa=report_qa(ROOT,saved)
    assert qa['passed'] and qa['sections']==15 and qa['figures']==10 and qa['tables']==9
    assert qa['fact_spans']>50


def test_all_authored_fact_tokens_exist(saved) -> None:
    """Narrative templates have no silently unresolved fact reference."""
    texts=HIGHLIGHTS+[p for _,paragraphs in sections() for p in paragraphs]
    assert all(set(references(t))<=set(saved.fact_id) for t in texts)


def test_unknown_fact_fails_closed(saved) -> None:
    """Missing facts cause an error instead of a guessed/default number."""
    with pytest.raises(KeyError):plain('{{not_a_fact}}',saved)


def test_no_hardcoded_research_estimates() -> None:
    """Core authored conclusion templates contain no copied decimal research estimates."""
    assert not re.search(r'(?<![\w_])[-+]?\d+\.\d+', '\n'.join(HIGHLIGHTS))
    assert all(references(t) for t in HIGHLIGHTS if 'Bias·RMSE의 공간구조' not in t)


def test_small_p_not_rounded_to_zero() -> None:
    """Presentation preserves the distinction between a tiny p and literal zero."""
    assert float(format_value(0.00000034))>0


def test_figure_registry_and_originals(saved) -> None:
    """Each selected figure is a real original PNG with a matching copied asset."""
    registry=figures(saved)
    assert registry.figure_id.is_unique and {'caption','why_selected','report_section'}<=set(registry)
    for row in registry.itertuples():
        source=ROOT/row.source_path;copy=ROOT/FINAL/'report/assets'/source.name
        assert source.read_bytes().startswith(b'\x89PNG') and sha256(source)==sha256(copy)
        assert '단위' in row.caption and 'N=' in row.caption


def test_tables_have_real_fact_references(saved) -> None:
    """All scalar report tables point to the same fact layer."""
    for _,table in research_tables(saved,evidence(saved)):
        if 'fact_id' in table:assert set(table.fact_id)<=set(saved.fact_id)


def test_executive_summary(saved) -> None:
    """The short research summary contains fact references and limits."""
    text=(ROOT/FINAL/'EXECUTIVE_SUMMARY.md').read_text()
    assert '목적과 범위' in text and '한계와 활용' in text and '<!-- fact:' in text
    assert all(fid in set(saved.fact_id) for fid in re.findall(r'<!-- fact:(.*?) -->',text))


@pytest.mark.parametrize('name,required',[
    ('FINAL_PORTFOLIO','STAR'),('TECHNICAL_PORTFOLIO_SUMMARY','statsmodels'),('FINAL_RESULTS_SUMMARY','기온추세'),
    ('FINAL_METHODS_SUMMARY','HC3'),('FINAL_LIMITATIONS','인과'),('REPRODUCIBILITY','cache'),
    ('RESUME_BULLETS','English'),('INTERVIEW_NOTES','90초'),('PROJECT_STORY_3MIN','예상 밖'),
    ('PROJECT_PITCH_60SEC','English'),('GITHUB_PUBLICATION_PLAN','DO_NOT_COMMIT'),
    ('GITHUB_DATA_POLICY','KHOA'),('INDEX','Robustness'),('RELEASE_CHECKLIST','LICENSE'),
])
def test_required_documents(name,required) -> None:
    """Each required publication artifact is substantive and contains its contract topic."""
    text=(ROOT/'docs'/f'{name}.md').read_text()
    assert len(text)>500 and required in text and '{{' not in text


def test_portfolio_and_interview_structure() -> None:
    """Preserve the requested long-form portfolio and interview coverage."""
    assert len(re.findall(r'^## ',(ROOT/'docs/FINAL_PORTFOLIO.md').read_text(),re.M))==15
    assert len(re.findall(r'^## ',(ROOT/'docs/INTERVIEW_NOTES.md').read_text(),re.M))==14
    assert (ROOT/'docs/RESUME_BULLETS.md').read_text().count('\n- ')==12


def test_readme_fact_preview_and_history() -> None:
    """The new entry point retains old instructions by linking the preserved stage history."""
    text=(ROOT/'README.md').read_text()
    assert '<!-- fact:' in text and text.count('docs/assets/final/')==3
    assert 'STAGE_HISTORY.md' in text and (ROOT/'docs/STAGE_HISTORY.md').is_file()
    assert 'API를 호출하지 않습니다' in text


def test_publication_excludes_caches_and_env() -> None:
    """The explicit candidate set cannot accidentally publish raw cache or credential files."""
    files=[p.relative_to(ROOT).as_posix() for p in public_candidates(ROOT)]
    assert not any(x.startswith(('data/','.env','.venv/','output/final/qa/')) for x in files)
    assert any(x.endswith('.csv') for x in files)


def test_gitignore_protection() -> None:
    """Secrets and large result namespaces are excluded, selected final data are allowlisted."""
    text=(ROOT/'.gitignore').read_text().splitlines()
    assert {'.env','.env.*','/data/','/output/*','!/output/public_demo/','/output/final/qa/'}<=set(text)


def test_security_scan_actual_public_files() -> None:
    """Scan candidate CSV, docs and source without displaying secret matches."""
    scan=security_scan(ROOT,write=False)
    assert scan['safe'] and not scan['risks'] and not scan['matched_values_disclosed']


def test_security_scan_includes_csv(tmp_path) -> None:
    """A secret-like literal in a public CSV must not evade suffix-based scanning."""
    folder=tmp_path/'output/final';folder.mkdir(parents=True)
    (tmp_path/'.gitignore').write_text('.env\n')
    (folder/'bad.csv').write_text('x\n'+"pass"+"word='not-a-real-key'\n")
    scan=security_scan(tmp_path)
    assert not scan['safe'] and scan['risks'][0]['path']=='output/final/bad.csv'


def test_personal_paths_not_in_final_docs() -> None:
    """Publication docs contain no personal filesystem prefix."""
    pattern='/Us'+'ers/'
    assert all(pattern not in p.read_text() for p in (ROOT/'docs').glob('*.md'))


def test_attribution_consistent() -> None:
    """All source institutions and official references appear in the final report."""
    text=(ROOT/FINAL/'report'/f'{REPORT_STEM}.html').read_text()
    assert all(x in text for x in ['NASA POWER','KMA ASOS','KHOA coastline'])
    assert all(url in text for url in OFFICIAL_LINKS.values())


def test_changelog_and_version() -> None:
    """Only the approved release version changes; historical manifests retain their versions."""
    assert (ROOT/'VERSION').read_text().strip()=='1.1.0'
    assert 'final research package' in (ROOT/'CHANGELOG.md').read_text()
    assert (ROOT/'LICENSE').read_text().startswith('MIT License\n')


def test_no_model_or_downloader_imports() -> None:
    """The final package must not import any fitting or download entry point."""
    for path in (ROOT/'src/final_integration').glob('*.py'):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert node.module not in ('src.nasa_power','src.kma_asos','scipy.stats','statsmodels.api')


def test_fact_build_has_zero_http(saved) -> None:
    """Rebuilding real final facts is entirely cache-only."""
    with patch('requests.sessions.Session.request',side_effect=AssertionError('HTTP forbidden')) as http:
        generated=build_facts(ROOT)
    assert http.call_count==0
    pd.testing.assert_frame_equal(generated,saved,check_dtype=False)


def test_read_only_public_summary(tmp_path,saved) -> None:
    """A verified small final bundle can load without any raw/processed folders."""
    folder=tmp_path/FINAL;folder.mkdir(parents=True)
    for name in ('final_research_fact_layer.csv','final_evidence_matrix.csv','final_figure_registry.csv','final_research_fact_manifest.json'):
        shutil.copyfile(ROOT/FINAL/name,folder/name)
    loaded,_=load_final(tmp_path)
    assert len(loaded)==len(saved) and not (tmp_path/'data').exists()


def test_final_payload_tamper_rejected(tmp_path) -> None:
    """The public loader fails closed when a summary is edited independently."""
    folder=tmp_path/FINAL;folder.mkdir(parents=True)
    for name in ('final_research_fact_layer.csv','final_evidence_matrix.csv','final_figure_registry.csv','final_research_fact_manifest.json'):
        shutil.copyfile(ROOT/FINAL/name,folder/name)
    with (folder/'final_evidence_matrix.csv').open('a') as stream:stream.write('\nchanged')
    with pytest.raises(ValueError,match='checksum'):load_final(tmp_path)


def test_dashboard_router_preserved() -> None:
    """All original routes remain while the information architecture is regrouped."""
    assert page_count(ROOT)==18
    text=(ROOT/'streamlit_app.py').read_text()
    assert all(x in text for x in ['HOME','CORE ANALYSIS','VALIDATION','SPATIAL','ROBUSTNESS','METHODS / REPORTS'])


def test_final_home_and_reports_no_network() -> None:
    """Changed landing/download surfaces render with saved outputs only."""
    from streamlit.testing.v1 import AppTest
    with patch('requests.sessions.Session.request',side_effect=AssertionError('HTTP forbidden')) as http:
        for module in ('overview','reports'):
            app=AppTest.from_string(f'from dashboard.pages.{module} import render\nrender()').run(timeout=60)
            assert not app.exception
    assert http.call_count==0


def test_missing_final_home_is_safe(tmp_path) -> None:
    """A missing optional final bundle gives a clear empty state rather than a download."""
    from streamlit.testing.v1 import AppTest
    with patch('dashboard.final_home.PROJECT_ROOT',tmp_path):
        app=AppTest.from_string('from dashboard.final_home import render_final_home\nrender_final_home()').run(timeout=30)
    assert not app.exception and len(app.info)==1


def test_test_summary_accounting(tmp_path) -> None:
    """Only executed JUnit cases count as passed; unrun tests stay explicitly unrun."""
    nodes=['tests/test_example.py::test_one','tests/test_final_integration.py::test_two']
    xml=tmp_path/'results.xml';xml.write_text('<testsuites><testsuite><testcase classname="tests.test_example" name="test_one"/></testsuite></testsuites>')
    summary=summarize_tests(tmp_path,nodes,xml)
    assert summary.collected.sum()==2 and summary.passed.sum()==1 and summary.not_run.sum()==1


def test_final_test_summary_shape() -> None:
    """The summary includes old and new tests with mutually exclusive categories."""
    frame=pd.read_csv(ROOT/FINAL/'final_test_summary.csv')
    assert {'category','origin','collected','passed','failed','errors','skipped','not_run'}<=set(frame)
    assert frame.loc[frame.origin.eq('existing'),'collected'].sum()==653
    assert not frame[['category','origin']].duplicated().any()


def test_final_manifest_and_protected_outputs() -> None:
    """Actual baseline comparison is required, not just a statement that data were preserved."""
    manifest=json.loads((ROOT/'output/manifests/final_integration_manifest.json').read_text())
    assert manifest['VERSION']=='1.0.0' and manifest['protected_file_count']>0
    baseline=json.loads((ROOT/FINAL/'qa/protected_baseline.json').read_text())
    # Stage20 explicitly authorizes the release VERSION bump, not research artifact edits.
    assert check_snapshot(ROOT,{p:v for p,v in baseline.items() if p!='VERSION'})==[]
    assert manifest['NASA_API_calls']==manifest['KMA_API_calls']==0
    assert not manifest['git_push_performed'] and not manifest['git_init_performed']
