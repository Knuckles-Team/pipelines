"""The connector PR workflow and the post-release verification (PIPE-RELEASE-R011, R012)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).parents[1] / ".github/workflows"


def _on(document: dict) -> dict:
    return document.get(True, document.get("on"))


# spec: PIPE-RELEASE-R011
@pytest.mark.spec("PIPE-RELEASE-R011")
def test_connector_pr_workflow_is_fast_commit_stage_and_never_publishes() -> None:
    document = yaml.safe_load((WORKFLOWS / "connector_pr_pipeline.yml").read_text(encoding="utf-8"))
    assert set(_on(document)["workflow_call"]["inputs"]) == {"runner", "test-scope", "sync-args"}
    assert document["permissions"] == {"contents": "read"}
    job = document["jobs"]["gates"]
    assert job["uses"] == "Knuckles-Team/pipelines/.github/workflows/gates_pipeline.yml@main"
    assert job["with"]["stages"] == "pre-commit"
    assert job["with"]["skip-hooks"] == "docker-compose-check"
    setup = job["with"]["setup-command"]
    assert "uv sync --frozen ${{ inputs.sync-args }}" in setup
    assert 'npm install --global --prefix "$HOME/.npm-global" bun' in setup
    assert "PYTHONPATH=" in setup and '>> "$GITHUB_ENV"' in setup
    assert "uv tool install bump2version" in setup and '.venv/bin" >> "$GITHUB_PATH"' in setup
    assert job["with"]["config"] == ".pre-commit-config.yaml"
    assert job["with"]["timeout-minutes"] <= 10
    text = (WORKFLOWS / "connector_pr_pipeline.yml").read_text(encoding="utf-8")
    assert "secrets" not in text and "pypi" not in text.lower()


# spec: PIPE-RELEASE-R011
@pytest.mark.spec("PIPE-RELEASE-R011")
def test_gates_stage_loop_reads_the_stages_input() -> None:
    document = yaml.safe_load((WORKFLOWS / "gates_pipeline.yml").read_text(encoding="utf-8"))
    inputs = _on(document)["workflow_call"]["inputs"]
    assert inputs["stages"]["default"] == "pre-commit pre-push"
    steps = document["jobs"]["gates"]["steps"]
    step = next(s for s in steps if s.get("name") == "pre-commit (commit and pre-push stages)")
    assert step["env"]["STAGES"] == "${{ inputs.stages }}"
    assert "for stage in $STAGES" in step["run"]


def _verify_script() -> str:
    steps = yaml.safe_load((WORKFLOWS / "container_pipeline.yml").read_text(encoding="utf-8"))["jobs"][
        "publish-docker"
    ]["steps"]
    step = next(s for s in steps if s.get("name") == "Verify the release artifacts")
    assert "refs/heads/main" in step["if"]
    return step["run"]


def _run_verify(tmp_path: Path, missing: str) -> subprocess.CompletedProcess[str]:
    """Run the step with a fake curl that fails for URLs containing ``missing``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        f'#!/bin/bash\nfor a in "$@"; do [[ -n "{missing}" && "$a" == *"{missing}"* ]] && exit 22; done\nexit 0\n'
    )
    curl.chmod(0o755)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo-mcp"\nversion = "1.2.3"\n')
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "VERSION": "1.2.3", "SUFFIX": "-mcp", "BUILD_CONTEXT": ".", "DOCKER_USER": "knucklessg1",
        "REPO_NAME": "demo-mcp", "VERIFY_ATTEMPTS": "1", "VERIFY_DELAY": "0",
    }  # fmt: skip
    return subprocess.run(
        ["bash", "-c", _verify_script()], cwd=tmp_path, env=env, capture_output=True, text=True, check=False
    )


# spec: PIPE-RELEASE-R012
@pytest.mark.spec("PIPE-RELEASE-R012")
def test_verification_passes_when_both_artifacts_exist(tmp_path: Path) -> None:
    assert _run_verify(tmp_path, "").returncode == 0


# spec: PIPE-RELEASE-R012
@pytest.mark.spec("PIPE-RELEASE-R012")
@pytest.mark.parametrize(
    ("missing", "message"),
    [("hub.docker.com", "knucklessg1/demo-mcp:1.2.3-mcp is missing"), ("pypi.org", "demo-mcp==1.2.3 is missing")],
)
def test_verification_fails_naming_the_missing_artifact(tmp_path: Path, missing: str, message: str) -> None:
    result = _run_verify(tmp_path, missing)
    assert result.returncode == 1
    assert message in result.stdout + result.stderr
