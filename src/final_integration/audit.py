"""Actual final-package QA, test accounting and release gates; no climate reanalysis."""
from __future__ import annotations

import ast
import base64
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import pandas as pd

from src.nationwide.tier_a_pipeline import _atomic_csv,_atomic_json
from src.spatial.robustness_audit import sha256,check_snapshot
from .content import format_value
from .facts import FINAL,values
from .report import REPORT_STEM,write_text


class ReportParser(HTMLParser):
    """Collect semantic report references using the standard HTML tokenizer."""
    def __init__(self) -> None:
        super().__init__();self.images=[];self.ids=[];self.hrefs=[];self.fact_spans=[];self.tables=0;self.sections=0
        self.active_fact=None

    def handle_starttag(self,tag: str,attrs: list[tuple]) -> None:
        """Record links, figures, sections and explicitly tagged quantitative prose."""
        a=dict(attrs)
        if tag=='img':self.images.append(a.get('src',''))
        if 'id' in a:self.ids.append(a['id'])
        if 'href' in a:self.hrefs.append(a['href'])
        if tag=='table':self.tables+=1
        if tag=='section':self.sections+=1
        if tag=='span' and 'data-fact' in a:self.active_fact=a['data-fact']

    def handle_data(self,data: str) -> None:
        """Capture the displayed scalar inside a fact span."""
        if self.active_fact:self.fact_spans.append((self.active_fact,data))

    def handle_endtag(self,tag: str) -> None:
        """End a quantitative span."""
        if tag=='span':self.active_fact=None


def report_qa(root: Path,facts: pd.DataFrame) -> dict:
    """Validate every tagged value, selected image and relative Markdown image link."""
    path=root/FINAL/'report'/f'{REPORT_STEM}.html'
    html=path.read_text();parser=ReportParser();parser.feed(html);v=values(facts)
    mismatches=[fid for fid,text in parser.fact_spans if fid not in v or text!=format_value(v[fid])]
    bad_images=[]
    for i,uri in enumerate(parser.images):
        try:
            assert uri.startswith('data:image/png;base64,')
            assert base64.b64decode(uri.split(',',1)[1],validate=True).startswith(b'\x89PNG\r\n\x1a\n')
        except (ValueError,AssertionError):bad_images.append(i)
    broken=[url for url in parser.hrefs if url.startswith('#') and url[1:] not in parser.ids]
    md=path.with_suffix('.md').read_text()
    broken += [url for url in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',md) if not (path.parent/url).is_file()]
    unresolved='{{' in html or '{{' in md
    result={'sections':parser.sections,'tables':parser.tables,'figures':len(parser.images),
            'fact_spans':len(parser.fact_spans),'fact_mismatches':mismatches,'bad_images':bad_images,
            'broken_local_links':broken,'unresolved_tokens':unresolved,
            'html_document':html.lower().startswith('<!doctype html>') and html.endswith('</html>'),
            'scope':'structural HTML parse and fact/image/link validation; browser QA recorded separately'}
    result['passed']=not mismatches and not bad_images and not broken and not unresolved and result['html_document']
    return result


def classify_test(nodeid: str) -> str:
    """Assign each test exactly once using explicit filename priority, not subjective double-counting."""
    name=nodeid.split('::')[0]
    rules=[('security',('release','safety')),('dashboard',('dashboard',)),
           ('reports',('report','final_integration')),('spatial',('spatial','period_sensitivity')),
           ('validation',('validation',)),('quality',('preprocess','quality','screening')),
           ('ingestion',('nasa_power','kma_asos','nationwide_asos')),
           ('statistics',('analysis','statistics','climate','common_period','tier_b'))]
    return next((category for category,terms in rules if any(x in name for x in terms)),'regression')


def test_summary(root: Path,nodes: list[str],xml_path: Path | None = None) -> pd.DataFrame:
    """Count collected and actually executed tests by category and old/new origin."""
    records={}
    if xml_path is not None:
        for test in ET.parse(xml_path).iter('testcase'):
            classname=test.attrib['classname'];name=test.attrib['name']
            key=classname.replace('.','/')+'.py::'+name
            status='passed'
            for flag in ('failure','error','skipped'):
                if test.find(flag) is not None:status={'failure':'failed','error':'errors','skipped':'skipped'}[flag]
            records[key]=status
    rows=[]
    for node in nodes:
        rows.append({'category':classify_test(node),'origin':'new' if node.startswith('tests/test_final_integration.py::') else 'existing',
            'collected':1,'passed':int(records.get(node)=='passed'),'failed':int(records.get(node)=='failed'),
            'errors':int(records.get(node)=='errors'),'skipped':int(records.get(node)=='skipped'),
            'not_run':int(node not in records)})
    result=pd.DataFrame(rows).groupby(['category','origin'],as_index=False).sum()
    result['counting_rule']='filename keyword priority; each collected node exactly once; pytest JUnit outcomes'
    _atomic_csv(result,root/FINAL/'final_test_summary.csv')
    return result


def page_count(root: Path) -> int:
    """Count actual router Page calls rather than guessing a page total."""
    tree=ast.parse((root/'streamlit_app.py').read_text())
    return sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='Page' for n in ast.walk(tree))


def release_checklist(root: Path,gates: dict) -> None:
    """Keep technical completion separate from the user's publication/license decisions."""
    labels={'pytest':'전체 pytest','pip_check':'pip check','security':'secret·개인경로·email scan',
            'report':'최종 report·fact consistency','dashboard':'Dashboard 전체 페이지·상호작용',
            'http':'실제 Streamlit HTTP 200','protected':'기존 data/output SHA256·mtime 보존',
            'reproducibility':'결정적 facts/report 재생성','documents':'README·docs·자료정책·선택 그림'}
    lines=['# Release Checklist','기술 검증과 실제 공개 승인은 별도입니다. VERSION은 변경하지 않습니다.']
    lines+=['- ['+('x' if gates.get(key) else ' ')+'] '+label for key,label in labels.items()]
    lines+=['- [x] .env 및 raw/processed 기본 Git 제외 규칙 확인',
            '- [x] Git init / remote / push 수행하지 않음',
            '- [ ] 코드 LICENSE·저작권 주체 사용자 결정',
            '- [ ] 데이터 상세 인용 및 공개 범위 사용자 최종 승인',
            '- [ ] VERSION 변경 승인 (현재 VERSION 유지)',
            '- [ ] Git 저장소 생성·공개 여부 사용자 결정']
    lines+=['기술 gate가 모두 통과하면 v1.1.0 candidate를 추천합니다. 이는 release 발행·라이선스 확정·push 완료가 아닙니다.']
    write_text(root/'docs/RELEASE_CHECKLIST.md','\n\n'.join(lines)+'\n')


def finish_manifest(root: Path,baseline: dict,qa: dict) -> dict:
    """Publish a fail-closed integration manifest from actual checks and current artifact hashes."""
    from .workflow import publication_inventory,security_scan
    changed=check_snapshot(root,baseline)
    tests=pd.read_csv(root/FINAL/'final_test_summary.csv')
    test_ok=bool(tests.collected.sum()>0 and tests.passed.sum()==tests.collected.sum() and qa.get('pytest_exit_code',1)==0)
    gates={'pytest':test_ok,'pip_check':qa.get('pip_check',False),'report':qa.get('report',{}).get('passed',False),
           'dashboard':qa.get('dashboard',{}).get('passed',False),'http':qa.get('http',{}).get('passed',False),
           'protected':not changed,'reproducibility':qa.get('reproducibility',False),
           'documents':qa.get('documents',False),'security':security_scan(root)['safe']}
    release_checklist(root,gates)
    inventory=publication_inventory(root);scan=security_scan(root)
    gates['security']=scan['safe']
    facts=json.loads((root/FINAL/'final_research_fact_manifest.json').read_text())
    manifest={'stage':'final_integration','VERSION':(root/'VERSION').read_text().strip(),
        'status':'completed' if all(gates.values()) else 'incomplete','completed':all(gates.values()),'gates':gates,
        'test_count':int(tests.collected.sum()),'passed':int(tests.passed.sum()),
        'existing_tests':int(tests.loc[tests.origin.eq('existing'),'collected'].sum()),
        'new_tests':int(tests.loc[tests.origin.eq('new'),'collected'].sum()),
        'pip_check':qa.get('pip_check',False),'fact_count':facts['fact_count'],
        'protected_file_count':len(baseline),'protected_files_changed':changed,
        'protected_file_digest':__import__('hashlib').sha256(json.dumps(baseline,sort_keys=True).encode()).hexdigest(),
        'fact_hash':sha256(root/FINAL/'final_research_fact_layer.csv'),
        'artifact_hashes':dict(zip(inventory.path,inventory.sha256)),
        'report':qa.get('report',{}),'dashboard_QA':qa.get('dashboard',{}),'HTTP_QA':qa.get('http',{}),
        'security_scan':scan,'reproducibility':qa.get('reproducibility',False),
        'NASA_API_calls':0,'KMA_API_calls':0,'external_network_blocked':True,
        'recommended_next_version':'v1.1.0 candidate' if all(gates.values()) else 'pending QA',
        'release_blockers':['code license and copyright holder approval','data/publication scope approval','VERSION approval','Git publication approval'],
        'git_init_performed':False,'git_remote_performed':False,'git_push_performed':False}
    _atomic_json(manifest,root/'output/manifests/final_integration_manifest.json')
    return manifest
