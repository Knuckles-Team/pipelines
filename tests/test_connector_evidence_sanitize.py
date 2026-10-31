"""Captured connector evidence carries no personal identity (PIPE-GATES-R016.118)."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import connector_evidence_sanitize as sanitizer  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "connector_spec_delivery"


@pytest.mark.spec("PIPE-GATES-R016.118")
def test_author_identity_becomes_the_neutral_maintainer() -> None:
    skill = "---\nname: demo\nmetadata:\n  author: Example Person\n---\n\n# Demo\nauthor: kept in the body\n"
    clean = sanitizer.sanitize_text(skill)
    assert "  author: Repository Maintainers\n" in clean and "author: kept in the body" in clean
    toml = '[[project.authors]]\nname = "Example Person"\nemail = "person@example.org"\n\n[project.urls]\n'
    assert sanitizer.sanitize_text(toml) == (
        '[[project.authors]]\nname = "Repository Maintainers"\nemail = "maintainers@example.invalid"\n\n[project.urls]\n'
    )


@pytest.mark.spec("PIPE-GATES-R016.118")
def test_a_rewritten_file_carries_its_digests_through_every_fixture(tmp_path: Path) -> None:
    content = "---\nmetadata:\n  author: Example Person\n---\n"
    digest = hashlib.sha256(content.encode()).hexdigest()
    record = {"content": content, "bytes": len(content), "sha256": digest}
    (tmp_path / "a.json").write_text(json.dumps({"file": record}, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "b.json").write_text(
        json.dumps({"pin": {"source_sha256": digest, "bytes": len(content)}}, indent=2) + "\n", encoding="utf-8"
    )
    sanitizer.sanitize_paths([tmp_path / "a.json", tmp_path / "b.json"], [])
    new = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["file"]
    pin = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))["pin"]
    assert new["sha256"] == hashlib.sha256(new["content"].encode()).hexdigest() == pin["source_sha256"]
    assert new["bytes"] == len(new["content"].encode()) == pin["bytes"]


@pytest.mark.spec("PIPE-GATES-R016.118")
def test_every_committed_evidence_fixture_is_already_sanitized(tmp_path: Path) -> None:
    copies = []
    for source in sorted(FIXTURES.glob("*.json")):
        copies.append(tmp_path / source.name)
        shutil.copy(source, copies[-1])
    assert sanitizer.sanitize_paths(copies, []) == []
