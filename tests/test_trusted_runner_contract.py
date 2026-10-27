"""Contract tests for the opt-in trusted runner routing policy."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github/workflows"
POLICY = ROOT / "reference/trusted-runner-policy.yml"


def _on(document: dict) -> dict:
    return document.get("on", document.get(True))


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def test_policy_is_separate_from_recovery_and_restricts_compatible_workflows() -> None:
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    assert policy["runner_group"] == "arbora-ci-trusted"
    assert policy["runner_group"] != "eg-release-recovery"
    assert "group3" not in policy["runner_group"]
    assert policy["fork_pull_request_fallback"] == "ubuntu-latest"
    assert policy["compatible_workflows"] == ["gates_pipeline.yml", "main_pipeline.yml"]
    assert set(policy["compatible_workflows"]).isdisjoint(policy["excluded_workflows"])
    assert {"avx2", "rust-1.96"} <= set(policy["labels"])


def test_gates_trusted_routing_is_opt_in_and_fork_safe() -> None:
    workflow = _workflow("gates_pipeline.yml")
    inputs = _on(workflow)["workflow_call"]["inputs"]
    assert inputs["runner"]["default"] == '"ubuntu-latest"'
    assert "arbora-ci-trusted" in inputs["runner"]["description"]
    assert "runner-selection" not in workflow["jobs"]
    runs_on = workflow["jobs"]["gates"]["runs-on"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in runs_on
    assert "github.event_name == 'push'" in runs_on
    assert "refs/heads/{0}" in runs_on
    assert '"group":"arbora-ci-trusted"' in runs_on
    assert "inputs.runner != '\"arbora-ci-trusted\"'" in runs_on
    assert runs_on.rfind("inputs.runner") < runs_on.rfind("'\"ubuntu-latest\"'")


def test_main_trusted_routing_is_trusted_event_only() -> None:
    workflow = _workflow("main_pipeline.yml")
    assert "runner-selection" not in workflow["jobs"]
    for name in ("tests", "backward", "supply-chain"):
        runs_on = workflow["jobs"][name]["runs-on"]
        assert "github.event_name == 'push'" in runs_on
        assert "refs/heads/{0}" in runs_on
        assert "github.event.pull_request.head.repo.full_name == github.repository" in runs_on
        assert '"group":"arbora-ci-trusted"' in runs_on
        assert "inputs.runner != '\"arbora-ci-trusted\"'" in runs_on
        assert runs_on.rfind("inputs.runner") < runs_on.rfind("'\"ubuntu-latest\"'")


def _expected_runner(
    *, event: str, repository: str, head_repository: str | None, ref: str, default_branch: str, requested: str
) -> str:
    trusted_event = (event == "push" and ref == f"refs/heads/{default_branch}") or (
        event == "pull_request" and head_repository == repository
    )
    if not trusted_event:
        return '"ubuntu-latest"'
    if requested == '"arbora-ci-trusted"':
        return '{"group":"arbora-ci-trusted","labels":["self-hosted","linux","x64","homelab","avx2","rust-1.96"]}'
    return requested or '"ubuntu-latest"'


def test_fork_cannot_smuggle_a_custom_group_json_runner() -> None:
    trusted_group = '{"group":"arbora-ci-trusted","labels":["self-hosted"]}'
    assert (
        _expected_runner(
            event="pull_request",
            repository="Knuckles-Team/medulla",
            head_repository="attacker/medulla",
            ref="refs/pull/1/merge",
            default_branch="main",
            requested=trusted_group,
        )
        == '"ubuntu-latest"'
    )
    assert (
        _expected_runner(
            event="pull_request",
            repository="Knuckles-Team/medulla",
            head_repository="Knuckles-Team/medulla",
            ref="refs/pull/1/merge",
            default_branch="main",
            requested=trusted_group,
        )
        == trusted_group
    )
    assert (
        _expected_runner(
            event="push",
            repository="Knuckles-Team/medulla",
            head_repository=None,
            ref="refs/heads/feature",
            default_branch="main",
            requested=trusted_group,
        )
        == '"ubuntu-latest"'
    )
    assert (
        _expected_runner(
            event="workflow_dispatch",
            repository="Knuckles-Team/medulla",
            head_repository=None,
            ref="refs/heads/main",
            default_branch="main",
            requested=trusted_group,
        )
        == '"ubuntu-latest"'
    )


def test_pipelines_ci_is_the_explicit_opt_in_and_no_container_job_is_rerouted() -> None:
    workflow = _workflow("ci.yml")
    expected = "${{ vars.ARBORA_TRUSTED_CI_RUNNER == 'true' && '\"arbora-ci-trusted\"' || '\"ubuntu-latest\"' }}"
    assert workflow["jobs"]["gates"]["with"]["runner"] == expected
    assert workflow["jobs"]["main"]["with"]["runner"] == expected
    reviewed_sha = "b49b77468d0048f58a5876560f1767072b73c04d"
    assert workflow["jobs"]["gates"]["uses"] == (
        f"Knuckles-Team/pipelines/.github/workflows/gates_pipeline.yml@{reviewed_sha}"
    )
    assert workflow["jobs"]["main"]["uses"] == (
        f"Knuckles-Team/pipelines/.github/workflows/main_pipeline.yml@{reviewed_sha}"
    )
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    assert policy["enablement_variable"] == "ARBORA_TRUSTED_CI_RUNNER"
    assert policy["enablement_default"] is False
