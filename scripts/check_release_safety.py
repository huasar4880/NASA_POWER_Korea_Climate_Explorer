"""Fail-closed scan for release-blocking secrets and personal absolute paths.

The scanner never prints matched text or credential values.  Expected credential
*names* in source and documentation are safe; only likely assigned literal values,
private-key headers, or a real local KMA key copied outside ignored env files fail.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from urllib.parse import quote, unquote


SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_FILES = {".env", ".env.local", ".DS_Store"}
PUBLIC_RELEASE_NAME = "huasar4880"
PUBLIC_RELEASE_EMAIL = "323835330+huasar4880@users.noreply.github.com"


def without_approved_public_identity(text: str) -> str:
    """Mask only the exact public identity explicitly approved for this release.

    Use only for account-name/email checks, never for path or actual-key checks.
    """
    text = re.sub(r'(?<![\w.%+@-])' + re.escape(PUBLIC_RELEASE_EMAIL) + r'(?![\w.%+@-])',
                  'APPROVED_PUBLIC_EMAIL', text)
    return re.sub(r'(?<![\w])' + re.escape(PUBLIC_RELEASE_NAME) + r'(?![\w])',
                  'APPROVED_PUBLIC_NAME', text)


TEXT_SUFFIXES = {"", ".py", ".md", ".txt", ".toml", ".json", ".yaml", ".yml", ".ini", ".cfg", ".sh", ".html", ".j2", ".css"}
GENERIC_SECRET_FIXTURES = {
    "tests/test_kma_asos.py",
    "tests/test_release.py",
    "tests/test_reporting.py",
}
PERSONAL_PATTERNS = (re.compile(r"/Users/[^/\s]+/"), re.compile(r"/home/[^/\s]+/"))
PERSONAL_EMAIL_PATTERNS = (
    re.compile(r"(?i)\b[a-z0-9._%+-]{1,128}@(?:gmail|naver|daum|hanmail|yahoo|outlook|icloud)\.[a-z]{2,}\b"),
)
LITERAL_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)[?&](?:servicekey|api[_-]?key|token|password|secret)=(?!REDACTED|PLACEHOLDER|YOUR[_-])[^&\s]{8,}"),
    re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*['\"](?!REDACTED|PLACEHOLDER|YOUR[_-]|발급받은)[^'\"]{8,}['\"]"),
)


@dataclass(frozen=True)
class SafetyResult:
    """Only file names and status flags; matched confidential content is omitted."""

    scanned_files: int
    secret_files: tuple[str, ...]
    personal_path_files: tuple[str, ...]
    personal_email_files: tuple[str, ...]
    env_present: bool
    env_ignored: bool
    git_repository: bool
    env_tracked: bool | None

    @property
    def safe(self) -> bool:
        """Return whether no release-blocking issue was found."""

        return (
            not self.secret_files
            and not self.personal_path_files
            and not self.personal_email_files
            and self.env_ignored
            and self.env_tracked is not True
        )


def _local_kma_variants(root: Path) -> set[str]:
    """Read the local key for equality checks without returning or logging it."""

    env = root / ".env"
    if not env.is_file():
        return set()
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("KMA_API_KEY="):
            value = line.split("=", 1)[1].strip().strip("'\"")
            if len(value) >= 8 and value.upper() not in {"REDACTED", "PLACEHOLDER", "YOUR_KEY"}:
                decoded = unquote(value)
                return {value, decoded, quote(decoded, safe="")}
    return set()


def _git_state(root: Path) -> tuple[bool, bool | None]:
    """Check repository and tracked-env state without printing Git output."""

    probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        return False, None
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", ".env"], capture_output=True, text=True, check=False)
    return True, tracked.returncode == 0


def scan_repository(root: Path) -> SafetyResult:
    """Scan public-candidate text while excluding local/derived ignored content."""

    root = Path(root).resolve()
    variants = _local_kma_variants(root)
    secrets: set[str] = set()
    personal: set[str] = set()
    personal_emails: set[str] = set()
    scanned = 0
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in SKIP_DIRS for part in relative.parts) or path.name in SKIP_FILES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        scanned += 1
        name = relative.as_posix()
        # These tests intentionally contain obvious non-production sentinel values.
        # Exact matches to the real local KMA key are still checked for every file.
        fixture_or_scanner = name in GENERIC_SECRET_FIXTURES or name == "scripts/check_release_safety.py"
        if any(value and value in text for value in variants) or (
            not fixture_or_scanner and any(pattern.search(text) for pattern in LITERAL_SECRET_PATTERNS)
        ):
            secrets.add(name)
        if name != "scripts/check_release_safety.py" and any(pattern.search(text) for pattern in PERSONAL_PATTERNS):
            personal.add(name)
        if name != "scripts/check_release_safety.py" and any(pattern.search(text) for pattern in PERSONAL_EMAIL_PATTERNS):
            personal_emails.add(name)
    ignore = root / ".gitignore"
    ignored_lines = {line.strip() for line in ignore.read_text(encoding="utf-8").splitlines()} if ignore.is_file() else set()
    git_repository, env_tracked = _git_state(root)
    return SafetyResult(
        scanned,
        tuple(sorted(secrets)),
        tuple(sorted(personal)),
        tuple(sorted(personal_emails)),
        (root / ".env").exists(),
        ".env" in ignored_lines,
        git_repository,
        env_tracked,
    )


def main() -> int:
    """Print status only; never echo matches or secret material."""

    parser = argparse.ArgumentParser(description="GitHub 공개 전 secret·개인 절대경로 안전성 검사")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="검사할 프로젝트 루트")
    result = scan_repository(parser.parse_args().root)
    print(f"scanned files: {result.scanned_files}")
    print(f"secret found: {'no' if not result.secret_files else 'yes'}")
    print(f"personal absolute path: {'no' if not result.personal_path_files else 'yes'}")
    print(f"personal email: {'no' if not result.personal_email_files else 'yes'}")
    print(f".env present: {'yes' if result.env_present else 'no'}")
    print(f".env ignored: {'yes' if result.env_ignored else 'no'}")
    print(f"git repository: {'yes' if result.git_repository else 'no'}")
    tracked = "not applicable (no repository)" if result.env_tracked is None else "yes" if result.env_tracked else "no"
    print(f".env tracked: {tracked}")
    for category, files in (
        ("secret risk files", result.secret_files),
        ("personal-path risk files", result.personal_path_files),
        ("personal-email risk files", result.personal_email_files),
    ):
        if files:
            print(f"{category}: {', '.join(files)}")
    return 0 if result.safe else 1


if __name__ == "__main__":
    raise SystemExit(main())
