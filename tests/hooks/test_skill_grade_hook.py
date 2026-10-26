"""Deterministic PIPE-PAGES-R023 skill-grade fixtures."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.docs import public_surface_links, skill_grade
from tests.hooks.conftest import Repo


VALID_SKILL = """---
name: demo
description: Inspect one demo record. Use when the agent must inspect a demo record.
skill_type: skill
---

# Demo

## Usage

Run the read-only lookup.

## Examples

`demo lookup`

See the [sibling guide](guide.md) and the [repository README](../../README.md).
"""


def _skill(root: Path, text: str = VALID_SKILL, *, rel: str = "skills/demo/SKILL.md") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _repo(root: Path, text: str = VALID_SKILL) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    skill = _skill(root, text)
    (skill.parent / "guide.md").write_text("# Guide\n", encoding="utf-8")
    return root


@pytest.mark.spec("PIPE-PAGES-R023.1")
def test_skill_grade_model(tmp_path: Path) -> None:
    policy = skill_grade.SkillGradePolicy()
    assert policy.schema_version == "skill-grade-v1"
    assert dict(policy.criterion_weights) == {
        "frontmatter": 20,
        "description": 20,
        "structure": 20,
        "links": 20,
        "file_metadata": 20,
    }
    assert policy.minimum_grade == 80

    root = _repo(tmp_path / "repo")
    document = root / "skills/demo/SKILL.md"
    report = skill_grade.grade_document(root, document)
    assert report.skill_path == "skills/demo/SKILL.md"
    assert report.document_path == report.skill_path
    assert report.criterion_scores == report.scores
    assert report.source_digest == "sha256:" + hashlib.sha256(document.read_bytes()).hexdigest()
    assert report.snapshot["identity"]
    assert report.policy_source_digest == policy.digest
    assert report.status == "pass"


@pytest.mark.spec("PIPE-PAGES-R023.2")
def test_skill_grade_criteria(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    good = skill_grade.grade(root)
    assert len(good) == 1
    assert good[0].scores == {criterion: 20 for criterion in skill_grade.CRITERIA}

    vague = _repo(
        tmp_path / "vague", VALID_SKILL.replace("Use when the agent must inspect a demo record.", "A useful helper.")
    )
    vague_report = skill_grade.grade(vague)[0]
    assert vague_report.scores["description"] == 0
    assert any(finding.code == "missing-use-condition" for finding in vague_report.findings)

    missing_sections = _repo(tmp_path / "sections", VALID_SKILL.replace("## Examples", "## Other"))
    section_report = skill_grade.grade(missing_sections)[0]
    assert section_report.scores["structure"] == 0
    assert any(finding.code == "missing-section" for finding in section_report.findings)

    broken = _repo(tmp_path / "broken", VALID_SKILL.replace("guide.md", "absent.md"))
    broken_report = skill_grade.grade(broken)[0]
    assert broken_report.scores["links"] == 0
    finding = next(finding for finding in broken_report.findings if finding.code == "missing-target")
    assert finding.source_document == "skills/demo/SKILL.md"
    assert finding.target == "skills/demo/absent.md"

    malformed = _repo(tmp_path / "malformed", VALID_SKILL.replace("name: demo", "name: [demo"))
    malformed_report = skill_grade.grade(malformed)[0]
    assert malformed_report.scores["frontmatter"] == 0
    assert malformed_report.hard_failure is True
    assert malformed_report.status == "fail"


@pytest.mark.spec("PIPE-PAGES-R023.3")
def test_skill_grade_registration() -> None:
    assert GATES["skill-grade"] == "pipelines_hooks.docs.skill_grade"
    assert callable(skill_grade.main)


@pytest.mark.spec("PIPE-PAGES-R023.4")
def test_skill_grade_refusals(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    policy_path = root / "policy.yaml"
    policy_path.write_text(
        "schema_version: skill-grade-v9\ncriterion_weights:\n"
        "  frontmatter: 20\n  description: 20\n  structure: 20\n  links: 20\n  file_metadata: 20\n"
        "minimum_grade: 80\n",
        encoding="utf-8",
    )
    with pytest.raises(CannotRun, match="unsupported policy schema"):
        skill_grade.load_policy(policy_path)

    malformed_policy = root / "malformed-policy.yaml"
    malformed_policy.write_text("criterion_weights: [oops\n", encoding="utf-8")
    with pytest.raises(CannotRun, match="malformed policy"):
        skill_grade.load_policy(malformed_policy)

    outside = tmp_path / "outside" / "SKILL.md"
    outside.parent.mkdir()
    outside.write_text(VALID_SKILL, encoding="utf-8")
    with pytest.raises(CannotRun, match="escapes repository"):
        skill_grade.grade_document(root, outside)

    escaped = _repo(tmp_path / "escaped", VALID_SKILL.replace("guide.md", "escape.md"))
    # Recreate the escaping link in the fixture, since _repo writes its own
    # sibling guide and the target is outside the repository.
    escape_path = escaped / "skills/demo/escape.md"
    escape_path.symlink_to(outside)
    report = skill_grade.grade(escaped)[0]
    assert report.status == "fail"
    assert report.hard_failure is True
    assert any(finding.refusal == "unsafe-path" for finding in report.findings)

    declared_escape = tmp_path / "declared-escape"
    declared_escape.mkdir()
    with pytest.raises(CannotRun, match="declared skills root escapes"):
        skill_grade.discover_skill_documents(root, (declared_escape,))


@pytest.mark.spec("PIPE-PAGES-R023.5")
def test_skill_grade_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path / "repo")
    policy = skill_grade.SkillGradePolicy()
    report = skill_grade.grade(root, policy)[0]
    encoded = json.loads(json.dumps(report.as_dict(), sort_keys=True))
    assert encoded["schema_version"] == "skill-grade-v1"
    assert encoded["policy_digest"] == policy.digest
    assert encoded["source_digest"] == report.source_digest
    assert encoded["criteria"]["links"]["score"] == 20

    broken = _repo(tmp_path / "broken", VALID_SKILL.replace("guide.md", "absent.md"))
    assert skill_grade.main(["--root", str(broken), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    link_finding = next(f for f in payload["reports"][0]["findings"] if f["code"] == "missing-target")
    assert link_finding["source_document"] == "skills/demo/SKILL.md"
    assert link_finding["target"] == "skills/demo/absent.md"


@pytest.mark.spec("PIPE-PAGES-R023.6")
def test_skill_grade_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path / "repo")
    assert skill_grade.main(["--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applicable"] is True
    assert payload["reports"][0]["status"] == "pass"

    malformed = _repo(tmp_path / "malformed", VALID_SKILL.replace("---\nname: demo", "---\nname: [demo"))
    assert skill_grade.main(["--root", str(malformed)]) == 1
    assert "malformed-frontmatter" in capsys.readouterr().out

    empty = tmp_path / "empty"
    empty.mkdir()
    assert skill_grade.main(["--root", str(empty)]) == 0
    assert "NOT APPLICABLE" in capsys.readouterr().out


@pytest.mark.spec("PIPE-PAGES-R023.6")
def test_nested_skill_links_cli(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    report = skill_grade.grade(root)[0]
    assert report.status == "pass"
    assert report.scores["links"] == 20

    root_link_findings = public_surface_links.local_link_findings(
        root,
        "See the [README](README.md).",
    )
    assert root_link_findings == []


@pytest.mark.spec("PIPE-PAGES-R023.1")
@pytest.mark.spec("PIPE-PAGES-R023.6")
def test_skill_grade_inventory_keeps_all_canonical_roots_and_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path / "repo")
    other = _skill(root, rel="components/skills/other/SKILL.md")
    (other.parent / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / "components/README.md").write_text("# components\n", encoding="utf-8")

    assert (
        skill_grade.main(
            [
                "--root",
                str(root),
                "--skills-root",
                "components/skills",
                "--skills-root",
                "skills",
                "--skills-root",
                "skills",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["inventory"] == {
        "roots": ["components/skills", "skills"],
        "documents": ["components/skills/other/SKILL.md", "skills/demo/SKILL.md"],
        "root_count": 2,
        "document_count": 2,
    }
    assert payload["snapshot"]["mode"] == "filesystem"

    assert skill_grade.main(["--root", str(root), "--json"]) == 0
    auto_payload = json.loads(capsys.readouterr().out)
    assert auto_payload["inventory"] == payload["inventory"]


@pytest.mark.spec("PIPE-PAGES-R023.4")
@pytest.mark.spec("PIPE-PAGES-R023.5")
def test_skill_grade_snapshot_reads_staged_index_when_worktree_is_dirty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path / "repo")
    fixture_repo = Repo(root)
    fixture_repo.git("init", "-q", "-b", "main")
    fixture_repo.git("add", "--", "README.md", "skills/demo/SKILL.md", "skills/demo/guide.md")
    fixture_repo.git("commit", "-q", "-m", "base")
    policy_text = (
        "schema_version: skill-grade-v1\ncriterion_weights:\n"
        "  frontmatter: 20\n  description: 20\n  structure: 20\n  links: 20\n  file_metadata: 20\n"
        "minimum_grade: 80\n"
    )
    (root / "policy.yaml").write_text(policy_text, encoding="utf-8")
    fixture_repo.git("add", "--", "policy.yaml")
    staged_skill = (root / "skills/demo/SKILL.md").read_bytes()
    (root / "skills/demo/SKILL.md").write_text("malformed working tree\n", encoding="utf-8")
    (root / "policy.yaml").write_text("schema_version: skill-grade-v9\n", encoding="utf-8")

    assert skill_grade.main(["--root", str(root), "--policy", "policy.yaml", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    report = payload["reports"][0]
    assert payload["snapshot"]["mode"] == "index"
    assert payload["snapshot"]["commit"]
    assert payload["snapshot"]["tree"]
    assert report["source_digest"] == "sha256:" + hashlib.sha256(staged_skill).hexdigest()
    assert report["policy_source_digest"] == "sha256:" + hashlib.sha256(policy_text.encode()).hexdigest()
    assert report["snapshot"] == payload["snapshot"]

    tree = subprocess.run(
        ["git", "write-tree"], cwd=root, env=sanitized_env(), check=True, capture_output=True, text=True
    ).stdout.strip()
    assert payload["snapshot"]["tree"] == tree

    fixture_repo.git("commit", "-q", "-m", "policy")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    assert skill_grade.main(["--root", str(root), "--json"]) == 0
    committed_payload = json.loads(capsys.readouterr().out)
    assert committed_payload["snapshot"]["mode"] == "commit"
    assert committed_payload["snapshot"]["commit"] == fixture_repo.git("rev-parse", "HEAD").strip()
    assert committed_payload["reports"][0]["source_digest"] == "sha256:" + hashlib.sha256(staged_skill).hexdigest()


@pytest.mark.spec("PIPE-PAGES-R023.2")
@pytest.mark.spec("PIPE-PAGES-R023.5")
def test_skill_grade_external_links_are_explicitly_unchecked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = VALID_SKILL.replace(
        "See the [sibling guide](guide.md) and the [repository README](../../README.md).",
        "See the [sibling guide](guide.md), [repository README](../../README.md), and [remote](https://example.invalid/guide).",
    )
    root = _repo(tmp_path / "repo", text)
    assert skill_grade.main(["--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    finding = next(item for item in payload["reports"][0]["findings"] if item["code"] == "external-unchecked")
    assert finding["target"] == "https://example.invalid/guide"
    assert finding["disposition"] == "unchecked"
    assert finding["blocking"] is False
    assert payload["reports"][0]["scores"]["links"] == 20
