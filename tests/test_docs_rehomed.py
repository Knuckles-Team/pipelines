"""The legacy docs/ directory is gone; its content lives at reference/.

PIPE-PAGES-R006: every generated or gate-checked artifact previously stored
under the legacy docs directory is moved to its new canonical tracked
location, every quality gate that referenced the old location is repointed,
and the legacy docs directory is then removed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATED = ("pages-readiness.md", "publication-identity.md", "python-release-readiness.md")


def test_the_legacy_docs_directory_no_longer_exists() -> None:
    assert not (ROOT / "docs").exists()


def test_every_migrated_artifact_exists_at_its_new_tracked_location() -> None:
    for name in MIGRATED:
        destination = ROOT / "reference" / name
        assert destination.is_file(), destination


def test_reference_directory_is_declared_in_the_root_hygiene_allowlist() -> None:
    import tomllib

    layout = tomllib.loads((ROOT / ".config/repo-layout.toml").read_text(encoding="utf-8"))
    assert "reference" in layout["dirs"]
    assert "docs" not in layout["dirs"]


def test_no_tracked_source_reads_from_the_removed_docs_directory() -> None:
    import subprocess

    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    needles = ("docs/pages-readiness.md", "docs/publication-identity.md", "docs/python-release-readiness.md")
    for relative in tracked:
        if relative.startswith("reference/") or relative == "tests/test_docs_rehomed.py":
            continue
        text = (ROOT / relative).read_text(encoding="utf-8", errors="ignore")
        for needle in needles:
            assert needle not in text, f"{relative} still references the removed {needle}"


def test_readme_links_point_at_the_new_reference_location() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in MIGRATED:
        assert f"reference/{name}" in readme
