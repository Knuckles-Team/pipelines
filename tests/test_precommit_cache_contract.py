"""Every workflow job that runs pre-commit restores and installs its hook environments (reference/ci-standard.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).parents[1] / ".github/workflows").glob("*.yml"))


def _pre_commit_jobs():
    for path in WORKFLOWS:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, job in (document.get("jobs") or {}).items():
            if "uses" in job:  # reusable-workflow caller: the callee is checked on its own
                continue
            steps = job.get("steps") or []
            if any("pre-commit run" in str(step.get("run", "")) for step in steps):
                yield pytest.param(steps, id=f"{path.name}::{name}")


@pytest.mark.parametrize("steps", _pre_commit_jobs())
def test_job_restores_and_installs_hook_environments(steps):
    restores = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/cache") and "~/.cache/pre-commit" in str((step.get("with") or {}).get("path", ""))
    ]
    assert restores, "a job that runs pre-commit must restore ~/.cache/pre-commit"
    assert any("install-hooks" in str(step.get("run", "")) for step in steps), "a job that runs pre-commit needs its own install-hooks step"
    assert not any("PRE_COMMIT_HOME" in str(step.get("env", "")) for step in steps), "no per-run PRE_COMMIT_HOME"
