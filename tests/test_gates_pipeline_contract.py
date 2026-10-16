"""Contracts for the shared gates workflow, require-tag and the fast-tests hook (PIPE-RELEASE-R007)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from pipelines_hooks.cli import GATES
from tests.hooks.conftest import HOOK_REPOSITORY

WORKFLOWS = Path(__file__).parents[1] / ".github/workflows"
GATES_WORKFLOW = WORKFLOWS / "gates_pipeline.yml"
PYTHON_WORKFLOW = WORKFLOWS / "python_pipeline.yml"
SKIP_TEMPLATE = Path(__file__).parents[1] / "templates/workflows/gates-skip.yml"

EXPECTED_INPUTS = {
    "config", "test-scope", "src-root", "runner", "rust", "all-files",
    "extra-manual-hooks", "skip-hooks", "setup-command", "timeout-minutes",
}  # fmt: skip


def _on(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document.get(True, document.get("on"))


def _require_tag_script() -> str:
    steps = yaml.safe_load(PYTHON_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["publish-pypi"]["steps"]
    return next(step for step in steps if step.get("name") == "Require a release tag")["run"]


def _run_guard(ref: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", _require_tag_script()], env={"REF": ref, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, check=False)


def test_gates_workflow_inputs_all_default() -> None:
    inputs = _on(GATES_WORKFLOW)["workflow_call"]["inputs"]
    assert set(inputs) == EXPECTED_INPUTS
    assert all(not spec["required"] and "default" in spec for spec in inputs.values())
    assert _on(GATES_WORKFLOW)["workflow_call"].get("secrets") is None


def test_gates_workflow_scopes_to_the_diff_and_caps_time() -> None:
    text = GATES_WORKFLOW.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    job = document["jobs"]["gates"]
    assert job["timeout-minutes"] == "${{ inputs.timeout-minutes }}"
    assert _on(GATES_WORKFLOW)["workflow_call"]["inputs"]["timeout-minutes"]["default"] == 15
    assert "--from-ref" in text and "--to-ref" in text and "--all-files" in text
    assert "for stage in pre-commit pre-push" in text and "--hook-stage \"$stage\"" in text
    assert "pr-test-scope" in text and "fetch-depth: 0" in text
    assert "pipelines-hook" in text and "job.workflow_sha" in text


def test_require_tag_defaults_off_and_guards_the_publish_step() -> None:
    document = yaml.safe_load(PYTHON_WORKFLOW.read_text(encoding="utf-8"))
    spec = _on(PYTHON_WORKFLOW)["workflow_call"]["inputs"]["require-tag"]
    assert spec["default"] is False and spec["required"] is False
    steps = document["jobs"]["publish-pypi"]["steps"]
    first = next(step for step in steps if step.get("name") == "Require a release tag")
    assert steps.index(first) < next(i for i, step in enumerate(steps) if "uses" in step and "publish-python-package" in step["uses"])
    assert first["name"] == "Require a release tag" and first["if"] == "inputs.require-tag"
    # existing inputs unchanged
    assert {"runtime-profiles", "web-assets"} <= set(_on(PYTHON_WORKFLOW)["workflow_call"]["inputs"])


def test_require_tag_refuses_a_branch_ref_and_names_it() -> None:
    refused = _run_guard("refs/heads/main")
    assert refused.returncode == 1
    assert "refs/heads/main" in refused.stdout
    assert _run_guard("refs/tags/v1.2.3").returncode == 0
    assert _run_guard("refs/tags/nightly").returncode == 1


def test_skip_template_is_the_inverse_of_the_documented_ignore_list() -> None:
    skip = yaml.safe_load(SKIP_TEMPLATE.read_text(encoding="utf-8"))
    paths = set(_on(SKIP_TEMPLATE)["pull_request"]["paths"])
    header = GATES_WORKFLOW.read_text(encoding="utf-8")
    assert all(path.strip("'") in header for path in paths)
    assert skip["jobs"]["gates"]["name"] == "gates / gates"


def test_fast_tests_is_a_pre_push_published_gate() -> None:
    assert GATES["fast-tests"] == "pipelines_hooks.ci_replica.fast_tests"
    hooks = {hook["id"]: hook for hook in yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))}
    assert hooks["fast-tests"]["stages"] == ["pre-push"]
    assert hooks["fast-tests"]["entry"] == "pipelines-hook fast-tests"


def test_spec_trailers_is_skipped_on_push_only() -> None:
    steps = yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gates"]["steps"]
    hooks = [step for step in steps if str(step.get("name", "")).startswith("pre-commit")]
    assert hooks
    for step in hooks:
        assert 'EVENT_NAME" == "push"' in step["run"]
        assert "spec-trailers" in step["run"]
