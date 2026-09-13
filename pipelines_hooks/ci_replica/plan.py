"""Parse workflow files and build the per-step execution plan."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipelines_hooks.ci_replica.matrix import apply_matrix, combo_label, matrix_combinations
from pipelines_hooks.ci_replica.registry import ARTIFACT_IO_ACTIONS, ENV_SETUP_ACTIONS, WorkflowSpec
from pipelines_hooks.core.errors import CannotRun


def discover_workflow_files(workflows_dir: Path) -> list[Path]:
    return sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")) if workflows_dir.is_dir() else []


def load_workflow(path: Path) -> dict:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CannotRun(f"cannot parse workflow {path.name}: {exc}") from exc
    if not isinstance(document, dict) or "jobs" not in document:
        raise CannotRun(f"{path.name} did not parse into a workflow with a top-level 'jobs:' map")
    return document


def step_label(step: dict) -> str:
    for key in ("name", "id", "uses"):
        if step.get(key):
            return str(step[key])
    lines = (step.get("run") or "").strip().splitlines()
    return lines[0][:60] if lines else "<empty step>"


def job_steps(job: dict) -> list[dict]:
    """A job's steps; a reusable-workflow job becomes one synthetic step so it is still reported."""
    if "steps" in job:
        return job.get("steps") or []
    return [{"uses": job["uses"], "name": job.get("name") or f"(reusable workflow: {job['uses']})"}] if job.get("uses") else []


def classify_step(step: dict) -> tuple[str, str]:
    """``(mode, detail)`` with mode RUN, ENV_SETUP, ARTIFACT_IO or SKIP_LOUD."""
    if step.get("run") is not None:
        return "RUN", step["run"]
    uses = step.get("uses") or ""
    action = uses.split("@", 1)[0]
    if action in ENV_SETUP_ACTIONS:
        return "ENV_SETUP", uses
    if action in ARTIFACT_IO_ACTIONS:
        return "ARTIFACT_IO", uses
    kind = "reusable workflow" if ".github/workflows/" in uses else "marketplace action"
    return "SKIP_LOUD", f"{kind} '{uses}' has no local equivalent -- not executed here"


def _job_rows(spec: WorkflowSpec, job_id: str, job: dict) -> list[dict]:
    rows = []
    for combo in matrix_combinations((job.get("strategy") or {}).get("matrix")):
        for step in job_steps(job):
            leg = apply_matrix(step, combo)
            mode, detail = ("SKIP_LOUD", spec.skip_reasons[job_id]) if job_id in spec.skip_reasons else classify_step(leg)
            rows.append({"workflow": spec.filename, "blocking": spec.blocking, "job": job_id + combo_label(combo),
                         "name": step_label(leg), "mode": mode, "detail": detail})
    return rows


def build_plan(spec: WorkflowSpec, document: dict) -> tuple[list[dict], list[str], list[str]]:
    """``(plan rows, unclassified jobs, stale registry job ids)`` for one workflow."""
    jobs = document.get("jobs") or {}
    known = spec.executable_jobs | set(spec.skip_reasons)
    unclassified = sorted(job_id for job_id in jobs if job_id not in known)
    plan = [row for job_id, job in jobs.items() if job_id in known for row in _job_rows(spec, job_id, job or {})]
    return plan, unclassified, sorted(job_id for job_id in known if job_id not in jobs)
