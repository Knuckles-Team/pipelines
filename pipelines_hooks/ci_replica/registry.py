"""The repository's workflow registry: ``[tool.pipelines_hooks.ci_replica]``.

    [tool.pipelines_hooks.ci_replica]
    build_affecting = ["pyproject.toml", "uv.lock", ".github/workflows/**"]

    [tool.pipelines_hooks.ci_replica.workflows."release.yml"]
    blocking = true
    executable_jobs = ["gates", "build"]

    [tool.pipelines_hooks.ci_replica.workflows."release.yml".skip_reasons]
    publish-pypi = "requires a release tag and trusted publishing"
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun

ENV_SETUP_ACTIONS = ("actions/checkout", "actions/setup-python", "actions/setup-node", "astral-sh/setup-uv")
ARTIFACT_IO_ACTIONS = ("actions/upload-artifact", "actions/download-artifact")
_SPEC_KEYS = frozenset({"blocking", "executable_jobs", "skip_reasons"})


@dataclass(frozen=True)
class WorkflowSpec:
    filename: str
    blocking: bool
    executable_jobs: frozenset[str]
    skip_reasons: Mapping[str, str]


def _spec(filename: str, raw: object) -> WorkflowSpec:
    if not isinstance(raw, Mapping) or set(raw) - _SPEC_KEYS or not isinstance(raw.get("blocking"), bool):
        raise CannotRun(f"ci_replica.workflows.{filename!r} needs a boolean `blocking` and only {sorted(_SPEC_KEYS)}")
    reasons = raw.get("skip_reasons", {})
    if not isinstance(reasons, Mapping) or any(not isinstance(v, str) or not v.strip() for v in reasons.values()):
        raise CannotRun(f"ci_replica.workflows.{filename!r}.skip_reasons must map job ids to non-empty reasons")
    executable = frozenset(string_tuple(raw.get("executable_jobs", []), f"ci_replica.workflows.{filename}.executable_jobs"))
    if executable & set(reasons):
        raise CannotRun(f"ci_replica.workflows.{filename!r} classifies a job as both executable and skipped")
    return WorkflowSpec(filename, raw["blocking"], executable, dict(reasons))


def load_registry(root: Path) -> tuple[dict[str, WorkflowSpec], tuple[str, ...]]:
    """``(registry by filename, build-affecting patterns)``."""
    section = load_config(root).section("ci_replica")
    workflows = section.get("workflows", {})
    if not isinstance(workflows, Mapping):
        raise CannotRun("ci_replica.workflows must be a table")
    registry = {name: _spec(name, raw) for name, raw in workflows.items()}
    return registry, string_tuple(section.get("build_affecting", []), "ci_replica.build_affecting")
