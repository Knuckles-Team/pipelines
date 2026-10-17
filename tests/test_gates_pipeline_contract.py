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
    "config", "ci-config", "test-scope", "src-root", "runner", "rust", "all-files",
    "extra-manual-hooks", "skip-hooks", "setup-command", "docs-only-paths", "timeout-minutes",
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
    assert "for stage in pre-commit pre-push" in text and '--hook-stage "$stage"' in text
    assert "pr-test-scope" in text and "fetch-depth: 0" in text
    assert "pipelines-hook" in text and "job.workflow_sha" in text


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


def _docs_only_step() -> dict:
    steps = yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gates"]["steps"]
    return next(step for step in steps if step.get("id") == "scope")


def _detect(tmp_path: Path, changed: list[str], patterns: str, event: str = "pull_request") -> str:
    # A git hook exports GIT_DIR/GIT_INDEX_FILE; without this the fixture writes to the real repository.
    clean = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path.parent)}

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            env=clean,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    tmp_path.mkdir()
    git("init", "-q")
    (tmp_path / "seed").write_text("seed", encoding="utf-8")
    git("add", "seed")
    git("commit", "-qm", "seed")
    base = git("rev-parse", "HEAD")
    for name in changed:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(name, encoding="utf-8")
        git("add", name)
    git("commit", "-qm", "change")
    output = tmp_path.parent / f"{tmp_path.name}.out"
    output.write_text("", encoding="utf-8")
    env = {
        "DOCS_ONLY_PATHS": patterns,
        "EVENT_NAME": event,
        "PR_BASE": base,
        "BASE_REF": "main",
        "ALL_FILES": "false",
        "GITHUB_OUTPUT": str(output),
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(
        ["bash", "-c", _docs_only_step()["run"]], cwd=tmp_path, env=env, check=True, capture_output=True, text=True
    )
    return output.read_text(encoding="utf-8").strip()


DOCS = "specs/* docs/* *.md plans/* LICENSE"


def test_docs_only_detection_passes_a_docs_diff_and_gates_a_mixed_one(tmp_path: Path) -> None:
    assert _detect(tmp_path / "docs", ["docs/a/b.md", "README.md", "specs/x/requirements.md"], DOCS) == "docs-only=true"
    assert _detect(tmp_path / "mixed", ["docs/a.md", "pkg/module.py"], DOCS) == "docs-only=false"
    assert _detect(tmp_path / "off", ["docs/a.md"], "") == "docs-only=false"
    assert _detect(tmp_path / "push", ["docs/a.md"], DOCS, event="push") == "docs-only=false"


def test_docs_only_guard_covers_every_later_step() -> None:
    steps = yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gates"]["steps"]
    position = steps.index(_docs_only_step())
    assert position == 1
    assert all("steps.scope.outputs.docs-only != 'true'" in step["if"] for step in steps[position + 1 :])


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
