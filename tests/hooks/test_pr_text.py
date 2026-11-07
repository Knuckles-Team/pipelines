"""PIPE-GATES-R099: pull request, comment and commit text is self-evident."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipelines_hooks.hygiene.pr_text import findings, main

WORKFLOW = Path(__file__).parents[2] / ".github/workflows/gates_pipeline.yml"
CLEAN = (
    "Make the importer skip empty rows.\n\n"
    "Why: an empty row crashed the import. Impact: such rows are now ignored. "
    "Verified: the importer unit tests pass.\n\n"
    "PIPE-GATES-R099 (pull request text is self-evident) is the rule.\n"
    "Spec: PIPE-GATES-R099\n"
)


@pytest.mark.spec("PIPE-GATES-R099")
@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("see host.example." + "arpa", "private reference"),
        ("saved to /home/user/x", "private reference"),
        ("run on R820", "hostname or local path"),
        ("ran local-ci", "internal tool or script name"),
        ("the merge train", "internal workflow jargon"),
        ("see the HANDOFF note", "private handoff document"),
        ("done per PIPE-GATES-R099 today", "bare row ID"),
    ],
)
def test_internal_references_jargon_and_bare_row_ids_are_findings(text: str, kind: str) -> None:
    assert any(kind in item for item in findings("body", text))


@pytest.mark.spec("PIPE-GATES-R099")
def test_a_private_repository_name_is_a_finding_only_when_given() -> None:
    assert not findings("body", "touches secret-repo")
    assert findings("body", "touches secret-repo", ("secret-repo",))


@pytest.mark.spec("PIPE-GATES-R099")
def test_self_evident_text_passes() -> None:
    assert findings("body", CLEAN) == []
    assert findings("body", "PIPE-GATES-R099: pull request text is self-evident") == []


@pytest.mark.spec("PIPE-GATES-R099")
def test_staged_mode_warns_and_strict_mode_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fix: thing\n\nlanded on the train\n", encoding="utf-8")
    assert main([str(message)]) == 0
    assert "WARN" in capsys.readouterr().out
    assert main([str(message), "--strict"]) == 1
    assert main(["--title", "fix: a thing", "--body", CLEAN, "--strict"]) == 0


@pytest.mark.spec("PIPE-GATES-R099")
def test_the_workflow_job_is_staged_by_default() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    option = workflow[True]["workflow_call"]["inputs"]["pr-text-strict"]
    assert option["default"] is False
    job = workflow["jobs"]["pr-text"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert "pipelines-hook pr-text" in job["steps"][-1]["run"]
