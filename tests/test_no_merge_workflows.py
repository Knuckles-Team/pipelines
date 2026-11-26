"""Auto-merge is GitHub's native setting, enabled per PR by its author; no workflow merges (PIPE-GATES-R016.116)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
WORKFLOWS = [*(ROOT / ".github/workflows").glob("*.y*ml"), *(ROOT / "templates/workflows").glob("*.y*ml")]


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_no_auto_merge_workflow_or_merge_token() -> None:
    names = {path.name for path in WORKFLOWS}
    assert not {name for name in names if name.startswith("auto_merge")}
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert "GIT_TOKEN" not in text, path
        assert "pull_request_target" not in text.split("#")[0], path


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_ci_template_has_the_single_required_check() -> None:
    text = (ROOT / "templates/workflows/ci.yml").read_text(encoding="utf-8")
    assert "name: CI required" in text


def _jobs(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs") or {}


@pytest.mark.spec("PIPE-GATES-R016.116.1")
def test_no_workflow_or_template_arms_or_merges() -> None:
    forbidden = ("gh pr merge", "enablePullRequestAutoMerge", "merge_when_pipeline_succeeds", "merge-when-pipeline")
    offenders = [
        f"{path.name}: {token}"
        for path in WORKFLOWS
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"these files merge or arm a merge: {offenders}"


@pytest.mark.spec("PIPE-GATES-R016.116.1")
def test_ci_standard_states_owner_only_merge_for_platform_pull_requests() -> None:
    text = (ROOT / "reference/ci-standard.md").read_text(encoding="utf-8")
    section = text.split("## Auto-merge and releases", 1)[1].split("\n## ", 1)[0]
    assert "platform" in section and "owner" in section
    assert "ARBORA-OPS-R896.10" in section and "MEDULLA-SDLC-R019.10" in section


ACTOR_CONDITION = re.compile(r"github\.(?:triggering_)?actor|pull_request\.user\.login|pull_request\.user\.id")


@pytest.mark.spec("PIPE-GATES-R016.116.2")
def test_no_gate_job_is_conditioned_on_actor_or_author() -> None:
    offenders = []
    for path in WORKFLOWS:
        for name, job in _jobs(path).items():
            conditions = [job.get("if"), *(step.get("if") for step in job.get("steps", []) if isinstance(step, dict))]
            offenders += [
                f"{path.name}: {name}" for c in conditions if isinstance(c, str) and ACTOR_CONDITION.search(c)
            ]
    assert not offenders, f"these jobs are conditioned on the actor or author: {offenders}"


@pytest.mark.spec("PIPE-GATES-R016.116.2")
def test_main_ruleset_has_no_bypass_actors() -> None:
    script = (ROOT / "scripts/apply_repo_ci_settings.sh").read_text(encoding="utf-8")
    assert "bypass_actors" not in script, "the main ruleset script names a bypass entry"
    assert "CI required" in script
