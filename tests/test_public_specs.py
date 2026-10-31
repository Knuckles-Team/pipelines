"""Focused public spec contract checks."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scripts.check_public_specs import problems

ROOT = Path(__file__).resolve().parents[1]


def test_public_specs_validate() -> None:
    assert problems(ROOT) == []


def test_private_reference_and_duplicate_owner_fail(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "specs", tmp_path / "specs")
    document = tmp_path / "specs/ecosystem-pages-parity/spec.md"
    document.write_text(document.read_text() + "\nSee plans/refactor draft.\n")
    for status in (tmp_path / "specs").glob("*/status.json"):
        status.unlink()
    requirements = tmp_path / "specs/ordered-digest-release/requirements.md"
    requirements.write_text(requirements.read_text() + "| `PIPE-PAGES-R001` | **Duplicate owner.** |\n")
    for args in (
        ("init", "-q"),
        ("add", "-A"),
        ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "fixture"),
    ):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    errors = problems(tmp_path)
    assert any("private or local reference" in error for error in errors)
    assert any("duplicate requirement owner" in error for error in errors)
