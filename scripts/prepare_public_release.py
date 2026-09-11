"""Offline release packaging and audits; never download data, fit models or run Git writes."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tokenize
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RELEASE = Path('output/final/release')
MANIFEST = RELEASE / 'v1.1.0_release_preparation_manifest.json'
PREVIEW = 'docs/GITHUB_STAGED_FILE_PREVIEW.txt'
DEMO = Path('output/public_demo')
FIGURES = (
    'common_period_kma_nasa_tavg_scatter.png',
    'kma_tavg_median_slope_by_start_year.png',
    'nasa_station_vs_grid_moran.png',
)
ROOT_FILES = {'.gitignore', '.env.example', 'VERSION', 'LICENSE', 'README.md', 'CHANGELOG.md',
              'AGENTS.md', 'requirements.txt', 'main.py', 'streamlit_app.py'}
SOURCE_DIRS = {'src', 'dashboard', 'reporting', 'scripts', 'tests', 'config'}
DEMO_FILES = {'EXECUTIVE_SUMMARY.md', 'final_research_fact_layer.csv',
              'final_evidence_matrix.csv', 'public_demo_manifest.json'}
SKIP = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache',
        '.ruff_cache', '.DS_Store'}


def digest(path: Path) -> str:
    """Hash bytes in a streaming, read-only operation."""
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_json(path: Path, value: dict) -> None:
    """Write newly generated release metadata, never a historic research artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def classify(name: str) -> str:
    """Apply the small public repository allowlist independently of Git state."""
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or any(x in SKIP for x in path.parts):
        return 'DO_NOT_COMMIT'
    if path.name.startswith('.env') and name != '.env.example':
        return 'DO_NOT_COMMIT'
    if name in ROOT_FILES:
        return 'COMMIT'
    if path.parts[0] in SOURCE_DIRS and path.suffix in {'.py', '.json', '.css', '.j2'}:
        return 'COMMIT'
    if name.startswith('docs/') and (path.suffix == '.md' or name == PREVIEW):
        return 'COMMIT'
    if name in {f'docs/assets/final/{f}' for f in FIGURES}:
        return 'COMMIT'
    if name in {f'{DEMO}/{f}' for f in DEMO_FILES}:
        return 'COMMIT'
    if name.startswith('output/final/') and not name.startswith(('output/final/qa/', f'{RELEASE}/')):
        return 'OPTIONAL'
    if name.startswith('docs/assets/'):
        return 'OPTIONAL'
    return 'DO_NOT_COMMIT'


def candidates(root: Path) -> list[Path]:
    """Enumerate only allowlisted public files, without traversing private data trees."""
    paths = [root / name for name in ROOT_FILES]
    for folder in (*sorted(SOURCE_DIRS), 'docs', str(DEMO)):
        paths.extend((root / folder).rglob('*'))
    return sorted({p for p in paths if p.is_file() and not p.is_symlink()
                   and classify(p.relative_to(root).as_posix()) == 'COMMIT'})


def combined(files: dict, field: str) -> str:
    """Hash sorted relative path/value pairs for an unambiguous combined fingerprint."""
    payload = json.dumps([(p, files[p][field]) for p in sorted(files)], separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def snapshot(root: Path) -> dict:
    """Freeze every currently existing data/output file, before creating release outputs."""
    files = {}
    for folder in ('data', 'output'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file():
                files[path.relative_to(root).as_posix()] = {
                    'sha256': digest(path), 'mtime_ns': path.stat().st_mtime_ns,
                    'bytes': path.stat().st_size}
    return {'files': files, 'file_count': len(files),
            'content_digest': combined(files, 'sha256'), 'mtime_digest': combined(files, 'mtime_ns')}


def check_protected(root: Path, baseline: dict) -> dict:
    """Compare all baseline paths; new release files do not redefine the protected set."""
    content, mtime, current = [], [], {}
    for name, before in baseline['files'].items():
        path = root / name
        if not path.is_file():
            content.append(name); mtime.append(name)
            current[name] = {'sha256': 'MISSING', 'mtime_ns': None}
            continue
        current[name] = {'sha256': digest(path), 'mtime_ns': path.stat().st_mtime_ns}
        if current[name]['sha256'] != before['sha256']: content.append(name)
        if current[name]['mtime_ns'] != before['mtime_ns']: mtime.append(name)
    return {'file_count': len(current), 'content_changed': content, 'mtime_changed': mtime,
            'content_digest_before': baseline['content_digest'],
            'content_digest_after': combined(current, 'sha256'),
            'mtime_digest_before': baseline['mtime_digest'],
            'mtime_digest_after': combined(current, 'mtime_ns')}


def initialize_baseline(root: Path) -> dict:
    """Require the completed Stage19 manifest and freeze it before any release edits."""
    target = root / RELEASE / 'qa/protected_baseline.json'
    if target.exists(): raise ValueError('Existing baseline must never be reset')
    previous = (root / 'VERSION').read_text().strip()
    manifest = json.loads((root / 'output/manifests/final_integration_manifest.json').read_text())
    bad = [p for p, h in manifest['artifact_hashes'].items() if digest(root / p) != h]
    if previous != '1.0.0' or not manifest['completed'] or bad:
        raise ValueError('Baseline gate failed: ' + ', '.join(bad))
    baseline = snapshot(root)
    baseline.update(previous_version=previous, stage19_completed=True,
                    stage19_artifact_hashes_verified=len(manifest['artifact_hashes']))
    save_json(target, baseline)
    return {key: value for key, value in baseline.items() if key != 'files'}


def copy_demo(root: Path) -> dict:
    """Copy a minimal saved-result demo; never edit original summaries or regenerate charts."""
    source = root / 'output/final'
    manifest = json.loads((source / 'final_research_fact_manifest.json').read_text())
    if not manifest['verified']: raise ValueError('Source fact verification is not complete')
    for name, expected in manifest['payload_hashes'].items():
        if Path(name).name != name or digest(source / name) != expected:
            raise ValueError('Source fact payload mismatch')
    folder = root / DEMO
    folder.mkdir(parents=True, exist_ok=True)
    payload = {}
    for name in sorted(DEMO_FILES - {'public_demo_manifest.json'}):
        dest = folder / name
        if dest.exists() and digest(dest) != digest(source / name):
            raise ValueError('Refusing to overwrite a different demo file: ' + name)
        if not dest.exists(): shutil.copy2(source / name, dest)
        payload[name] = digest(dest)
    result = {'release_version': '1.1.0', 'previous_version': '1.0.0', 'verified': True,
              'scope': 'Saved facts and evidence only; full research archive is not included',
              'source_manifest': 'output/final/final_research_fact_manifest.json',
              'source_manifest_sha256': digest(source / 'final_research_fact_manifest.json'),
              'payload_hashes': payload, 'NASA_API_calls': 0, 'KMA_API_calls': 0,
              'figures': {f'docs/assets/final/{f}': digest(root / 'docs/assets/final' / f) for f in FIGURES}}
    save_json(folder / 'public_demo_manifest.json', result)
    return result


def scan(root: Path, paths: list[Path]) -> dict:
    """Report paths/status only, never matched credentials, emails or personal strings."""
    from scripts.check_release_safety import (GENERIC_SECRET_FIXTURES, LITERAL_SECRET_PATTERNS,
        PERSONAL_PATTERNS, PERSONAL_EMAIL_PATTERNS, _local_kma_variants,
        without_approved_public_identity)
    variants = _local_kma_variants(root)
    risks, scanned = [], 0
    user = Path.home().name
    bearer = re.compile(r'(?i)\bBearer\s+(?!REDACTED|PLACEHOLDER|YOUR[_-])[A-Za-z0-9._~+/=-]{16,}')
    service = re.compile(r'''(?i)(?:servicekey|api[_-]?key|token|secret|password)['"]?\s*[:=]\s*['"](?!REDACTED|PLACEHOLDER|YOUR[_-])[^'"\s]{8,}['"]''')
    email_pattern = re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')
    for path in paths:
        try: text = path.read_text(encoding='utf-8')
        except UnicodeError: continue
        scanned += 1
        name = path.relative_to(root).as_posix()
        fixture = name in GENERIC_SECRET_FIXTURES or name == 'scripts/check_release_safety.py'
        secret = any(v in text for v in variants) or (not fixture and any(
            p.search(text) for p in (*LITERAL_SECRET_PATTERNS, bearer, service)))
        personal = (name != 'scripts/check_release_safety.py' and any(p.search(text) for p in PERSONAL_PATTERNS)) or (
            len(user) >= 5 and user.casefold() in without_approved_public_identity(text).casefold())
        # Python's matrix @ operator is not an email; only literals/comments can contain one.
        email_text = text
        if path.suffix == '.py':
            try:
                email_text = '\n'.join(t.string for t in tokenize.generate_tokens(io.StringIO(text).readline)
                                       if t.type in (tokenize.STRING, tokenize.COMMENT))
            except (tokenize.TokenError, IndentationError):
                pass  # Invalid source is scanned conservatively in full.
        email = any(p.search(without_approved_public_identity(email_text))
                    for p in (*PERSONAL_EMAIL_PATTERNS, email_pattern))
        if secret or personal or email:
            risks.append({'path': name, 'secret': secret, 'personal_path': personal, 'email': email})
    return {'safe': not risks, 'scanned_text_files': scanned, 'risks': risks,
            'matched_values_disclosed': False,
            'fixture_exemptions': sorted(GENERIC_SECRET_FIXTURES),
            'exemption_rule': 'Obvious mock-only literals; real key matches are never exempt'}


def check_links(root: Path, paths: list[Path]) -> list[dict]:
    """Check Markdown relative links against the actual lightweight publication set."""
    public = {p.resolve() for p in paths}
    failures = []
    for path in paths:
        if path.suffix != '.md': continue
        text = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
        links = re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', text)
        links += re.findall(r'^\[[^\]]+\]:\s*(\S+)', text, re.M)
        for raw in links:
            url = urlsplit(raw.strip('<>'))
            if url.scheme in {'http', 'https', 'mailto'} or not url.path: continue
            dest = (path.parent / unquote(url.path)).resolve()
            if url.scheme or url.path.startswith('/') or dest not in public:
                failures.append({'path': path.relative_to(root).as_posix(), 'target': raw})
    return failures


def git_state(root: Path) -> dict:
    """Inspect branch/index and identity presence without revealing identity or remote URLs."""
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    initialized = run('rev-parse', '--is-inside-work-tree').returncode == 0
    staged = run('diff', '--cached', '--name-only', '-z').stdout.split('\0') if initialized else []
    tracked = run('ls-files', '-z').stdout.split('\0') if initialized else []
    commit = run('rev-parse', '--verify', 'HEAD') if initialized else None
    return {'initialized': initialized, 'branch': run('symbolic-ref', '--short', 'HEAD').stdout.strip() if initialized else None,
            'staged_paths': [p for p in staged if p], 'tracked_paths': [p for p in tracked if p],
            'remote_configured': bool(run('remote').stdout.strip()) if initialized else False,
            'tag_count': len(run('tag', '--list').stdout.splitlines()) if initialized else 0,
            'identity_name_present': bool(run('config', '--get', 'user.name').stdout.strip()),
            'identity_email_present': bool(run('config', '--get', 'user.email').stdout.strip()),
            'commit_hash': commit.stdout.strip() if commit and commit.returncode == 0 else None}


def inventory(root: Path, write_preview: bool = False) -> dict:
    """Preview sizes and scan every public candidate; account for preview self-size explicitly."""
    paths = candidates(root)
    if write_preview:
        target = root / PREVIEW
        if target not in paths: paths = sorted([*paths, target])
        body = ''
        for _ in range(10):
            sizes = {p: len(body.encode()) if p == target else p.stat().st_size for p in paths}
            next_body = ('# Selective staging preview — COMMIT candidates only\n'
                '# Includes this preview; size solved to a fixed point. No private file values.\n'
                f'file_count: {len(paths)}\ntotal_bytes: {sum(sizes.values())}\n'
                'category\tbytes\tpath\n' + ''.join(f'COMMIT\t{sizes[p]}\t{p.relative_to(root).as_posix()}\n' for p in paths))
            if next_body == body: break
            body = next_body
        else: raise ValueError('Preview size did not converge')
        target.write_text(body, encoding='utf-8')
    return {'file_count': len(paths), 'total_bytes': sum(p.stat().st_size for p in paths),
            'paths': [p.relative_to(root).as_posix() for p in paths],
            'over_50_MB': [p.relative_to(root).as_posix() for p in paths if p.stat().st_size > 50_000_000],
            'over_100_MB': [p.relative_to(root).as_posix() for p in paths if p.stat().st_size > 100_000_000],
            'scan': scan(root, paths), 'broken_links': check_links(root, paths)}


def main() -> int:
    """Run one explicit local release operation; Git mutations require separate user authority."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('baseline', 'demo', 'audit', 'preview', 'protected', 'git'))
    args = parser.parse_args()
    if args.action == 'baseline': result = initialize_baseline(ROOT)
    elif args.action == 'demo': result = copy_demo(ROOT)
    elif args.action == 'git': result = git_state(ROOT)
    elif args.action == 'protected':
        result = check_protected(ROOT, json.loads((ROOT / RELEASE / 'qa/protected_baseline.json').read_text()))
    else:
        result = inventory(ROOT, write_preview=args.action == 'preview')
        save_json(ROOT / RELEASE / 'qa/public_candidate_audit.json', result)
        result = {key: value for key, value in result.items() if key != 'paths'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
