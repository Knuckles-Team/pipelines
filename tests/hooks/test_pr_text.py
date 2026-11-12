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
        ("built on GR1080", "hostname or local path"),
        ("see keycloak.heavenhomestead.com", "hostname or local path"),
        ("ran local-release", "internal tool or script name"),
        ("ran trunk-gate and localgate.sh", "internal tool or script name"),
        ("held a medulla-cargo-slot", "internal tool or script name"),
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
def test_a_short_row_number_is_not_a_hostname() -> None:
    assert not any("hostname" in item for item in findings("body", "rows R001 and R1080 land"))


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


@pytest.mark.spec("PIPE-GATES-R099")
def test_a_comment_is_linted_like_a_body() -> None:
    assert main(["--comment", "queued on the train", "--strict"]) == 1
    assert main(["--comment", "The importer now skips empty rows; unit tests pass.", "--strict"]) == 0


COMMENT_WORKFLOW = Path(__file__).parents[2] / ".github/workflows/comment_text_pipeline.yml"
COMMENT_TEMPLATE = Path(__file__).parents[2] / "templates/workflows/comment-text.yml"


@pytest.mark.spec("PIPE-GATES-R099")
def test_the_comment_workflow_lints_comment_events_staged_by_default() -> None:
    workflow = yaml.safe_load(COMMENT_WORKFLOW.read_text(encoding="utf-8"))
    assert workflow[True]["workflow_call"]["inputs"]["pr-text-strict"]["default"] is False
    job = workflow["jobs"]["comment-text"]
    assert "issue_comment" in job["if"]
    assert "pull_request_review_comment" in job["if"]
    last = job["steps"][-1]
    # The comment text travels in the environment, never interpolated into the script.
    assert last["env"]["COMMENT_BODY"] == "${{ github.event.comment.body }}"
    assert "github.event" not in last["run"]
    assert 'pipelines-hook pr-text --comment "$COMMENT_BODY"' in last["run"]
    caller = yaml.safe_load(COMMENT_TEMPLATE.read_text(encoding="utf-8"))
    assert set(caller[True]) == {"issue_comment", "pull_request_review_comment"}
    assert caller["jobs"]["comment-text"]["uses"].endswith("comment_text_pipeline.yml@main")
