"""Contracts for the reusable Maturin release workflow."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/maturin_pipeline.yml"
WHEEL_ACTION = ROOT / ".github/actions/maturin-build-wheels/action.yml"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _determine_version_script() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["publish"]["steps"]
    return next(step["run"] for step in steps if step.get("name") == "Determine version")


def test_maturin_release_consumes_exact_head_without_tag_history() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("ref: ${{ github.sha }}") == 3
    assert text.count("SOURCE_COMMIT=$(git rev-parse --verify HEAD)") == 3
    assert 'COMMIT_MESSAGE=$(git log -1 --format=%B "$LATEST_COMMIT"' in text
    assert "TAG=$(git tag" not in text
    assert "CURRENT_COMMIT" not in text
    assert "COMMIT_DIFFERENCE" not in text


def test_maturin_wheel_action_checks_head_before_and_after_build() -> None:
    text = WHEEL_ACTION.read_text(encoding="utf-8")

    assert "ref: ${{ github.sha }}" in text
    assert "Verify source commit before build" in text
    assert "Verify source commit after build" in text
    assert 'SOURCE_COMMIT=$(git rev-parse --verify HEAD)' in text
    assert '$(git rev-parse --verify HEAD)" != "$SOURCE_COMMIT"' in text


def test_determine_version_script_works_with_a_shallow_checkout(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q", "-b", "main")
    _git(source, "config", "user.name", "pipeline-test")
    _git(source, "config", "user.email", "pipeline-test@example.invalid")
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(source, "add", "--", "README.md")
    _git(source, "commit", "-q", "-m", "shallow package commit")
    expected = _git(source, "rev-parse", "HEAD")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "--depth", "1", source.as_uri(), str(clone))
    dist = clone / "dist"
    dist.mkdir()
    (dist / "fixture-1.2.3-py3-none-any.whl").write_bytes(b"wheel")
    github_env = tmp_path / "github-env"
    environment = os.environ.copy()
    environment.update(
        {
            "EXPECTED_COMMIT": expected,
            "GITHUB_ENV": str(github_env),
        }
    )

    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", _determine_version_script()],
        cwd=clone,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    metadata = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in github_env.read_text(encoding="utf-8").splitlines()
    }
    assert metadata["BUILD_VERSION"] == "1.2.3"
    assert metadata["LATEST_COMMIT"] == expected
    assert metadata["COMMIT_MESSAGE"].strip() == "shallow package commit"
