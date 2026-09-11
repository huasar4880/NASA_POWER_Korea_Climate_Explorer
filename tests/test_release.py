"""Small v1.0 release-contract tests; scientific workflows remain unchanged."""

from __future__ import annotations

from pathlib import Path
import re

from scripts.check_release_safety import scan_repository

ROOT = Path(__file__).resolve().parents[1]


def test_stable_version_file() -> None:
    """The public release exposes one simple semantic version."""

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == "1.1.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)


def test_release_safety_scanner_detects_secret_and_personal_path(tmp_path: Path) -> None:
    """Unsafe literals are reported by file name without entering project fixtures."""

    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    unsafe = "pass" + "word='not-a-real-password'\n" + "/Us" + "ers/example/private\n"
    (tmp_path / "unsafe.txt").write_text(unsafe, encoding="utf-8")
    result = scan_repository(tmp_path)
    assert result.secret_files == ("unsafe.txt",)
    assert result.personal_path_files == ("unsafe.txt",)
    assert result.personal_email_files == ()
    assert not result.safe


def test_project_release_candidates_pass_safety_scan() -> None:
    """Public-candidate text contains no key value or personal absolute path."""

    result = scan_repository(ROOT)
    assert result.secret_files == ()
    assert result.personal_path_files == ()
    assert result.personal_email_files == ()
    assert result.env_ignored
    assert result.env_tracked is not True
