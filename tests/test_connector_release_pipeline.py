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
    assert set(_on(document)["workflow_call"]["inputs"]) == {"runner", "test-scope", "sync-args", "skip-hooks"}
    assert document["permissions"] == {"contents": "read"}
    job = document["jobs"]["gates"]
    assert job["uses"] == "Knuckles-Team/pipelines/.github/workflows/gates_pipeline.yml@main"
    assert job["with"]["stages"] == "pre-commit"
    assert job["with"]["skip-hooks"] == "${{ inputs.skip-hooks }}"
    assert _on(document)["workflow_call"]["inputs"]["skip-hooks"]["default"] == "docker-compose-check"
    setup = job["with"]["setup-command"]
    assert "uv sync --frozen ${{ inputs.sync-args }}" in setup
    assert 'npm install --global --prefix "$HOME/.npm-global" bun' in setup
    assert "PYTHONPATH=" in setup and '>> "$GITHUB_ENV"' in setup
    assert "bump2version" not in setup and '.venv/bin" >> "$GITHUB_PATH"' in setup
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


@pytest.mark.spec("PIPE-GATES-R016.35")
def test_connector_pr_workflow_forwards_skip_hooks_and_the_webarchiver_patch_skips_the_scanner_hook() -> None:
    document = yaml.safe_load((WORKFLOWS / "connector_pr_pipeline.yml").read_text(encoding="utf-8"))
    assert _on(document)["workflow_call"]["inputs"]["skip-hooks"]["default"] == "docker-compose-check"
    assert document["jobs"]["gates"]["with"]["skip-hooks"] == "${{ inputs.skip-hooks }}"
    patch = (Path(__file__).parents[1] / "scripts/connector_migrate_patches/webarchiver.patch").read_text(
        encoding="utf-8"
    )
    assert "+      skip-hooks: docker-compose-check,scanner-versions" in patch


# spec: PIPE-RELEASE-R017
@pytest.mark.spec("PIPE-RELEASE-R017")
def test_connector_pr_builds_the_image_only_when_a_container_input_changes(tmp_path: Path) -> None:
    document = yaml.safe_load((WORKFLOWS / "connector_pr_pipeline.yml").read_text(encoding="utf-8"))
    assert document["jobs"]["container-build"]["needs"] == "container-inputs"
    assert document["jobs"]["container-build"]["if"] == "needs.container-inputs.outputs.build == 'true'"
    assert document["jobs"]["container-build"]["uses"].endswith("/container_build_check.yml@main")
    steps = document["jobs"]["container-inputs"]["steps"]
    script = next(step for step in steps if step.get("id") == "changed")["run"]
    for pattern in (
        "docker/*",
        "Dockerfile*",
        ".dockerignore",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "pnpm-lock.yaml",
        "patches/*",
    ):
        assert pattern in script

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    def run_detect(base: str = "main") -> str:
        output = tmp_path / "out"
        output.unlink(missing_ok=True)
        env = {"PATH": "/usr/bin:/bin", "BASE_REF": base, "GITHUB_OUTPUT": str(output)}
        subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, check=True, capture_output=True)
        return output.read_text().strip()

    git("init", "-b", "main")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    (tmp_path / "README.md").write_text("x")
    git("add", "README.md")
    git("commit", "-m", "base")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("checkout", "-b", "change")
    (tmp_path / "README.md").write_text("y")
    git("commit", "-am", "docs")
    assert run_detect() == "build=false"  # no Dockerfile: skips cleanly

    (tmp_path / "docker").mkdir()
    (tmp_path / "docker/Dockerfile").write_text("FROM scratch\n")
    git("add", "docker/Dockerfile")
    git("commit", "-m", "dockerfile")
    assert run_detect() == "build=true"

    git("update-ref", "refs/remotes/origin/main", "HEAD")
    (tmp_path / "README.md").write_text("z")
    git("commit", "-am", "docs only")
    assert run_detect() == "build=false"  # Dockerfile present, no container input changed

    (tmp_path / "patches").mkdir()
    (tmp_path / "patches/a.patch").write_text("p")
    git("add", "patches/a.patch")
    git("commit", "-m", "patch")
    assert run_detect() == "build=true"
