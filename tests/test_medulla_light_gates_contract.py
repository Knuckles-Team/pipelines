"""Contract tests for the reusable Medulla lightweight-gates workflow."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/medulla_light_gates.yml"


def _on(document: dict) -> dict:
    return document.get("on", document.get(True))


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_is_a_three_job_reusable_caller_contract() -> None:
    document = _workflow()
    trigger = _on(document)
    assert set(trigger) == {"workflow_call"}
    call = trigger["workflow_call"]
    assert set(call["inputs"]) == {"runner"}
    assert call["inputs"]["runner"]["default"] == '"ubuntu-latest"'
    assert call["outputs"]["code"]["value"] == "${{ jobs.changes.outputs.code }}"
    assert set(document["jobs"]) == {"changes", "lint-and-architecture", "spec-gates"}


def test_change_scope_output_is_preserved_for_native_caller_jobs() -> None:
    document = _workflow()
    changes = document["jobs"]["changes"]
    assert changes["outputs"] == {"code": "${{ steps.scope.outputs.code }}"}
    scope = next(step for step in changes["steps"] if step.get("id") == "scope")
    assert "scripts/ci_change_scope.py" in scope["run"]
    assert '--event "$EVENT"' in scope["run"]
    assert '--base "$BASE"' in scope["run"]
    assert '--head "$HEAD"' in scope["run"]


def test_each_job_uses_full_caller_checkout_and_central_fork_safe_runner() -> None:
    document = _workflow()
    for job in document["jobs"].values():
        checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
        assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}
        runs_on = job["runs-on"]
        assert "github.event_name == 'push'" in runs_on
        assert "refs/heads/{0}" in runs_on
        assert "github.event.pull_request.head.repo.full_name == github.repository" in runs_on
        assert '"group":"arbora-ci-trusted"' in runs_on
        assert "inputs.runner != '\"arbora-ci-trusted\"'" in runs_on
        assert runs_on.rfind("inputs.runner") < runs_on.rfind("'\"ubuntu-latest\"'")


def test_light_jobs_preserve_medulla_commands_without_native_execution() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for command in (
        "pre-commit run --config .config/pre-commit.yaml --from-ref",
        "pre-commit run --config .config/pre-commit.yaml --all-files",
        "cargo fmt --all -- --check",
        "tests/test_ci_change_scope.py",
        "packaging/epistemic-graph-server",
        "pipelines-hook spec-status",
        "pipelines-hook spec-decomposition",
        "pipelines-hook spec-trailers",
    ):
        assert command in text
    assert "cargo test" not in text
    assert "cargo build" not in text
    assert "maturin" not in text


def test_spec_trailers_stays_pull_request_only_and_jobs_remain_independent() -> None:
    document = _workflow()
    spec_steps = document["jobs"]["spec-gates"]["steps"]
    trailers = next(step for step in spec_steps if step.get("name") == "spec-trailers")
    assert trailers["if"] == "github.event_name == 'pull_request'"
    for job in document["jobs"].values():
        assert "needs" not in job


def test_trusted_runner_uses_image_python_and_hosted_runner_uses_setup_python() -> None:
    document = _workflow()
    trusted = "inputs.runner == '\"arbora-ci-trusted\"'"
    hosted = "inputs.runner != '\"arbora-ci-trusted\"'"
    for name in ("lint-and-architecture", "spec-gates"):
        steps = document["jobs"][name]["steps"]
        portable = next(
            step for step in steps if step.get("name", "").startswith("Use the runner-provided portable Python")
        )
        assert portable["if"] == trusted
        assert "command -v python3" in portable["run"]
        assert "python3" in portable["run"]
        assert "-m venv" in portable["run"]
        assert ".python-version" in portable["run"]
        setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
        assert setup["if"] == hosted
