"""Focused public spec contract checks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.check_public_specs import problems

ROOT = Path(__file__).resolve().parents[1]


def test_public_specs_validate() -> None:
    assert problems(ROOT) == []


def test_private_reference_and_duplicate_owner_fail(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "specs", tmp_path / "specs")
    document = tmp_path / "specs/ecosystem-pages-parity/spec.md"
    document.write_text(document.read_text() + "\nSee plans/refactor draft.\n")
    status = tmp_path / "specs/ordered-digest-release/status.json"
    data = json.loads(status.read_text())
    data["requirement_ids"] = ["PIPE-PAGES-R001"]
    status.write_text(json.dumps(data))
    errors = problems(tmp_path)
    assert any("private or local reference" in error for error in errors)
    assert any("duplicate requirement owner" in error for error in errors)
