"""The shared PR gate refuses a head branch that an earlier pull request already merged (PIPE-GATES-R063)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
GATES_WORKFLOW = ROOT / ".github/workflows/gates_pipeline.yml"
CI_TEMPLATE = ROOT / "templates/workflows/ci.yml"
FAKE_GH = """#!/usr/bin/env bash
# a recorded API answer: the merged pull request numbers of the head branch, one per line
printf '%s' "$FAKE_MERGED"
echo "$@" >> "$FAKE_LOG"
"""


def _job() -> dict:
    return yaml.safe_load(GATES_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["branch-reuse"]


def _run(tmp_path: Path, merged: str, number: str = "12") -> subprocess.CompletedProcess[str]:
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir(exist_ok=True)
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    script = _job()["steps"][0]["run"]
    env = {
        **os.environ,
        "PATH": f"{gh.parent}{os.pathsep}{os.environ['PATH']}",
        "FAKE_MERGED": merged,
        "FAKE_LOG": str(tmp_path / "gh.log"),
        "REPOSITORY": "Org/demo",
        "HEAD_OWNER": "Org",
        "HEAD_REF": "feature-x",
        "PR_NUMBER": number,
    }
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)


@pytest.mark.spec("PIPE-GATES-R063")
def test_a_head_branch_with_a_merged_pull_request_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, "7\n")
    assert result.returncode == 1
    assert "#7" in result.stdout
    assert "new branch from the default branch" in result.stdout
    assert "head=Org:feature-x" in (tmp_path / "gh.log").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R063")
def test_a_new_head_branch_passes(tmp_path: Path) -> None:
    assert _run(tmp_path, "").returncode == 0


@pytest.mark.spec("PIPE-GATES-R063")
def test_the_pull_request_itself_is_not_an_earlier_merge(tmp_path: Path) -> None:
    assert _run(tmp_path, "12\n", number="12").returncode == 0


@pytest.mark.spec("PIPE-GATES-R063")
def test_the_job_runs_inside_the_shared_gates_workflow() -> None:
    job = _job()
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job["permissions"] == {"contents": "read"}
    template = yaml.safe_load(CI_TEMPLATE.read_text(encoding="utf-8"))["jobs"]
    assert template["gates"]["uses"].endswith("/gates_pipeline.yml@main")
    assert "gates" in template["ci-required"]["needs"]
