"""Cache-only final integration, publication inventory and read-only final artifact loader."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.nationwide.tier_a_pipeline import _atomic_csv, _atomic_json
from src.spatial.robustness_audit import sha256

from .content import evidence, figures
from .documents import generate_documents, publication_documents
from .facts import FINAL, build_facts, verify_facts
from .report import render_report


def build(root: Path) -> dict:
    """Regenerate only final artifacts and authored presentation documents with external I/O blocked."""
    root=root.resolve()
    version=(root/'VERSION').read_text().strip()
    if version not in {'1.0.0','1.1.0'}:raise ValueError('Unsupported final integration release')
    for name in ('common_period_51station_manifest','period_sensitivity_manifest','common_period_spatial_reanalysis_manifest'):
        if json.loads((root/'output/manifests'/f'{name}.json').read_text()).get('status')!='completed':
            raise ValueError('Incomplete source stage: '+name)
    with ExitStack() as stack:
        blockers=[stack.enter_context(patch(target,side_effect=AssertionError('Final integration prohibits network')))
                  for target in ('requests.sessions.Session.request','urllib.request.urlopen','http.client.HTTPConnection.connect')]
        facts=build_facts(root); provenance=verify_facts(root,facts)
        ev=evidence(facts); registry=figures(facts)
        _atomic_csv(facts,root/FINAL/'final_research_fact_layer.csv')
        _atomic_csv(ev,root/FINAL/'final_evidence_matrix.csv')
        _atomic_csv(registry,root/FINAL/'final_figure_registry.csv')
        report=render_report(root,facts,ev,registry)
        # Stage20 release documents must not be reverted by the historic Stage19 generator.
        docs=generate_documents(root,facts,ev,registry)+publication_documents(root) if version=='1.0.0' else []
        payload_hashes={name:sha256(root/FINAL/name) for name in
                        ('final_research_fact_layer.csv','final_evidence_matrix.csv','final_figure_registry.csv')}
        manifest={**provenance,'project_VERSION':(root/'VERSION').read_text().strip(),
            'generation_time':datetime.now(timezone.utc).isoformat(),'payload_hashes':payload_hashes,
            'source_rule':'exact stored cell or declared count/median of saved estimates; no new fitting',
            'source_mtime_rule':'filesystem change detector, not observation/access date',
            'NASA_API_calls':0,'KMA_API_calls':0,'network_attempts':sum(b.call_count for b in blockers),
            'report':report,'documents':docs}
        _atomic_json(manifest,root/FINAL/'final_research_fact_manifest.json')
    return manifest


def load_final(root: Path) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Load checksummed small summaries without requiring raw caches or generating output."""
    folder=root/FINAL
    manifest_path=folder/'final_research_fact_manifest.json'
    if not manifest_path.is_file():
        folder=root/'output/public_demo'
        manifest_path=folder/'public_demo_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    if not manifest.get('verified'):raise ValueError('Final facts are not verified')
    for name,digest in manifest['payload_hashes'].items():
        if Path(name).name!=name or sha256(folder/name)!=digest:raise ValueError('Final payload checksum mismatch')
    return pd.read_csv(folder/'final_research_fact_layer.csv',dtype=str),pd.read_csv(folder/'final_evidence_matrix.csv')


def public_candidates(root: Path) -> list[Path]:
    """Explicit publication allowlist; never inspect raw caches, ignored QA or credential files."""
    from scripts.check_release_safety import SKIP_DIRS
    folders=('src','dashboard','scripts','tests','config','docs','output/final')
    files=[p for folder in folders for p in (root/folder).rglob('*')
           if p.is_file() and not p.is_symlink() and not any(x in SKIP_DIRS or x=='qa' for x in p.relative_to(root).parts)
           and p.name!='.DS_Store' and not p.name.startswith('.env')]
    files += [p for p in root.iterdir() if p.is_file() and not p.name.startswith('.')
              and p.suffix in ('.py','.md','.txt','')]
    files += [root/'.gitignore']
    final=root/'output/manifests/final_integration_manifest.json'
    if final.is_file():files.append(final)
    return sorted(set(files))


def security_scan(root: Path, *, write: bool = True) -> dict:
    """Scan actual publication candidates including CSV; record paths only, never matched values."""
    from scripts.check_release_safety import (GENERIC_SECRET_FIXTURES,LITERAL_SECRET_PATTERNS,
        PERSONAL_EMAIL_PATTERNS,PERSONAL_PATTERNS,_local_kma_variants,without_approved_public_identity)
    candidates=public_candidates(root);variants=_local_kma_variants(root)
    risks=[]; scanned=0; user=Path.home().name
    for path in candidates:
        try:text=path.read_text(encoding='utf-8')
        except UnicodeError:continue
        scanned+=1;name=path.relative_to(root).as_posix()
        fixture=name in GENERIC_SECRET_FIXTURES or name=='scripts/check_release_safety.py'
        secret=any(value in text for value in variants) or (not fixture and any(p.search(text) for p in LITERAL_SECRET_PATTERNS))
        personal=any(p.search(text) for p in PERSONAL_PATTERNS) if name!='scripts/check_release_safety.py' else False
        # Runtime account name is checked without hardcoding it into public source.
        personal=personal or (len(user)>=5 and user.casefold() in without_approved_public_identity(text).casefold())
        email=any(p.search(text) for p in PERSONAL_EMAIL_PATTERNS) if name!='scripts/check_release_safety.py' else False
        if secret or personal or email:risks.append({'path':name,'secret':secret,'personal':personal,'email':email})
    result={'safe':not risks,'scanned_text_files':scanned,'candidate_files':len(candidates),
            'risks':risks,'matched_values_disclosed':False,'raw_and_credentials_excluded':True,
            'scope':'explicit public allowlist, including CSV; intentional credential fixtures exempt only generic patterns'}
    if write:_atomic_json(result,root/FINAL/'final_security_scan.json')
    return result


def publication_inventory(root: Path) -> pd.DataFrame:
    """Inventory public candidate paths and sizes; omit self-referential inventory and audit hashes."""
    mutable={'final_public_file_inventory.csv','final_security_scan.json','final_integration_manifest.json'}
    rows=[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha256(p),
           'publication_group':'OPTIONAL' if p.relative_to(root).parts[0]=='output' else 'COMMIT'}
          for p in public_candidates(root) if p.name not in mutable]
    frame=pd.DataFrame(rows)
    _atomic_csv(frame,root/FINAL/'final_public_file_inventory.csv')
    return frame
