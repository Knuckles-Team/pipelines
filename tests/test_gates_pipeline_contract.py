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
    "python-version", "config", "ci-config", "test-scope", "src-root", "runner", "rust", "all-files",
    "extra-manual-hooks", "stages", "skip-hooks", "setup-command", "uv-cache-local-path", "spec-hooks", "timeout-minutes", "scanners",
}  # fmt: skip


def _on(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document.get(True, document.get("on"))


def _require_tag_script() -> str:
    steps = yaml.safe_load(PYTHON_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["publish-pypi"]["steps"]
    return next(step for step in steps if step.get("name") == "Require a release tag")["run"]


def _run_guard(ref: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", _require_tag_script()],
        env={"REF": ref, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


# spec: PIPE-RELEASE-R007.1
def test_gates_workflow_inputs_all_default() -> None:
    inputs = _on(GATES_WORKFLOW)["workflow_call"]["inputs"]
    assert set(inputs) == EXPECTED_INPUTS
    assert all(not spec["required"] and "default" in spec for spec in inputs.values())
    assert _on(GATES_WORKFLOW)["workflow_call"].get("secrets") is None


# spec: PIPE-RELEASE-R007.1
def test_gates_workflow_forwards_optional_uv_cache_path() -> None:
    inputs = _on(GATES_WORKFLOW)["workflow_call"]["inputs"]
    cache_input = inputs["uv-cache-local-path"]
    assert cache_input["required"] is False
    assert cache_input["type"] == "string" and cache_input["default"] == ""
    steps = yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gates"]["steps"]
    install = next(step for step in steps if step.get("name") == "Install uv")
    assert install["with"]["cache-local-path"] == "${{ inputs.uv-cache-local-path }}"
    assert install["with"]["enable-cache"] is True
    assert "uv.lock" in install["with"]["cache-dependency-glob"]


# spec: PIPE-RELEASE-R007.2
def test_gates_workflow_scopes_to_the_diff_and_caps_time() -> None:
    text = GATES_WORKFLOW.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    job = document["jobs"]["gates"]
    assert job["timeout-minutes"] == "${{ inputs.timeout-minutes }}"
    assert _on(GATES_WORKFLOW)["workflow_call"]["inputs"]["timeout-minutes"]["default"] == 15
    assert "--from-ref" in text and "--to-ref" in text and "--all-files" in text
    assert "for stage in $STAGES" in text and '--hook-stage "$stage"' in text
    assert "pr-test-scope" in text and "fetch-depth: 0" in text
    assert "pipelines-hook" in text and "job.workflow_sha" in text
    # The copyable caller block cancels only superseded pull request runs; a
    # main run is never cancelled mid-build, so every landed train gets a verdict.
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in text
    assert "cancel-in-progress: true" not in text


# spec: PIPE-RELEASE-R007.3
def test_require_tag_defaults_off_and_guards_the_publish_step() -> None:
    document = yaml.safe_load(PYTHON_WORKFLOW.read_text(encoding="utf-8"))
    spec = _on(PYTHON_WORKFLOW)["workflow_call"]["inputs"]["require-tag"]
    assert spec["default"] is False and spec["required"] is False
    steps = document["jobs"]["publish-pypi"]["steps"]
    first = next(step for step in steps if step.get("name") == "Require a release tag")
    assert steps.index(first) < next(
        i for i, step in enumerate(steps) if "uses" in step and "publish-python-package" in step["uses"]
    )
    assert first["name"] == "Require a release tag" and first["if"] == "inputs.require-tag"
    # existing inputs unchanged
    assert {"runtime-profiles", "web-assets"} <= set(_on(PYTHON_WORKFLOW)["workflow_call"]["inputs"])


# spec: PIPE-RELEASE-R007.4
def test_require_tag_refuses_a_branch_ref_and_names_it() -> None:
    refused = _run_guard("refs/heads/main")
    assert refused.returncode == 1
    assert "refs/heads/main" in refused.stdout
    assert _run_guard("refs/tags/v1.2.3").returncode == 0
    nightly = _run_guard("refs/tags/nightly")
    assert nightly.returncode == 1
    assert "refs/tags/nightly" in nightly.stdout


# spec: PIPE-RELEASE-R007.5
def test_gates_logs_scope_before_running_tests() -> None:
    text = GATES_WORKFLOW.read_text(encoding="utf-8")
    scope = text.index('scope="$(uvx')
    evidence = text.index('echo "pr-test-scope: $scope"', scope)
    dispatch = text.index('case "$scope"', evidence)
    assert scope < evidence < dispatch


def test_skip_template_is_the_inverse_of_the_documented_ignore_list() -> None:
    skip = yaml.safe_load(SKIP_TEMPLATE.read_text(encoding="utf-8"))
    paths = set(_on(SKIP_TEMPLATE)["pull_request"]["paths"])
    header = GATES_WORKFLOW.read_text(encoding="utf-8")
    assert all(path.strip("'") in header for path in paths)
    assert skip["jobs"]["gates"]["name"] == "gates / gates"


def test_fast_tests_is_a_pre_push_published_gate() -> None:
    assert GATES["fast-tests"] == "pipelines_hooks.ci_replica.fast_tests"
    hooks = {
        hook["id"]: hook
        for hook in yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    }
    assert hooks["fast-tests"]["stages"] == ["pre-push"]
    assert hooks["fast-tests"]["entry"] == "pipelines-hook fast-tests"


def test_spec_trailers_is_skipped_on_push_only() -> None:
    steps = yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gates"]["steps"]
    hooks = [step for step in steps if str(step.get("name", "")).startswith("pre-commit")]
    assert hooks
    for step in hooks:
        assert 'EVENT_NAME" == "push"' in step["run"]
        assert "spec-trailers" in step["run"]


def _gates_steps() -> list[dict]:
    return yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gates"]["steps"]


#: Steps that build, test or scan code: a spec or docs only change never runs them.
_CODE_ONLY_STEPS = (
    "Fetch the scanner recipes", "Restore the scanner toolchain", "Build the pinned scanners and put them on PATH",
    "Caller setup", "pre-commit (extra manual hooks)", "Affected tests",
)  # fmt: skip


# spec: PIPE-RELEASE-R007.9
def test_gates_workflow_routes_each_change_scope_to_its_gates() -> None:
    steps = _gates_steps()
    names = [step.get("name") for step in steps]
    scope = next(step for step in steps if step.get("id") == "scope")
    assert names.index("Install uv") < names.index("Classify the change") < names.index("Install Rust toolchain")
    assert "pipelines-hook change-scope" in scope["run"] and "--force-full" in scope["run"]
    assert 'EVENT_NAME" != "pull_request"' in scope["run"] and 'ALL_FILES" == "true"' in scope["run"]
    by_name = {step.get("name"): step for step in steps}
    for name in _CODE_ONLY_STEPS:
        assert "steps.scope.outputs.scope != 'spec'" in by_name[name]["if"], name
    rust = by_name["Install Rust toolchain"]["if"]
    assert "steps.scope.outputs.scope == 'full'" in rust and "steps.scope.outputs.rust == 'true'" in rust
    for name in ("pre-commit (commit and pre-push stages)", "CI-only gates"):
        step = by_name[name]
        assert "if" not in step, name
        assert step["env"]["SCOPE_SKIP"] == "${{ steps.scope.outputs.skip-hooks }}"
        assert 'SKIP="${SKIP:+$SKIP,}$SCOPE_SKIP"' in step["run"]


# spec: PIPE-RELEASE-R007.11
def test_docs_only_paths_is_removed_for_the_default_scope() -> None:
    inputs = _on(GATES_WORKFLOW)["workflow_call"]["inputs"]
    assert "docs-only-paths" not in inputs
    assert inputs["spec-hooks"]["default"] == ""
    assert "docs-only-paths" not in GATES_WORKFLOW.read_text(encoding="utf-8")
    template = (Path(__file__).parents[1] / "templates/workflows/ci.yml").read_text(encoding="utf-8")
    assert "docs-only-paths" not in template and "change_scope.yml@main" in template
    assert 'case "$r" in failure|cancelled)' in template
    outputs = _on(WORKFLOWS / "change_scope.yml")["workflow_call"]["outputs"]
    assert set(outputs) == {"scope", "code", "spec", "docs", "python", "rust", "frontend", "ci", "deps"}


# spec: PIPE-RELEASE-R007.12
def test_gates_workflow_names_each_not_applicable_gate() -> None:
    report = next(step for step in _gates_steps() if step.get("name") == "Report gates not applicable to this change")
    assert report["if"] == "steps.scope.outputs.scope == 'spec'"
    for gate in ("build", "tests", "scanners"):
        assert f"{gate}: not applicable: spec/docs-only change" in report["run"]


def test_ci_only_gates_run_from_their_own_file_and_skip_when_absent() -> None:
    inputs = _on(GATES_WORKFLOW)["workflow_call"]["inputs"]
    assert inputs["ci-config"]["default"] == ".config/ci-gates.yaml"
    steps = yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gates"]["steps"]
    step = next(step for step in steps if step.get("name") == "CI-only gates")
    assert '--config "$CI_CONFIG" $PRE_COMMIT_RANGE' in step["run"]
    assert 'if [[ ! -f "$CI_CONFIG" ]]' in step["run"]


def test_no_workflow_grants_write_all() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            assert line.split("#")[0].strip() != "permissions: write-all", path.name


def test_reusable_workflows_default_to_the_environment_python() -> None:
    workflows = GATES_WORKFLOW.parent
    for name in ("gates_pipeline.yml", "main_pipeline.yml", "desktop_release_pipeline.yml"):
        inputs = _on(workflows / name)["workflow_call"]["inputs"]
        assert inputs["python-version"]["default"] == "3.14", name
    main = _on(workflows / "main_pipeline.yml")["workflow_call"]["inputs"]
    assert main["backward-python"]["default"] == ""
