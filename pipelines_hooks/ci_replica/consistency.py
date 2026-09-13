"""The anti-drift check and the build-affecting-diff (skip-safe) query."""

from __future__ import annotations

import fnmatch
import posixpath
from pathlib import Path

from pipelines_hooks.ci_replica.cargo import build_tool_problems
from pipelines_hooks.ci_replica.plan import build_plan, discover_workflow_files, load_workflow
from pipelines_hooks.ci_replica.registry import WorkflowSpec
from pipelines_hooks.core.gitenv import git_text


def _workflow_problems(workflows_dir: Path, spec: WorkflowSpec) -> tuple[list[str], int]:
    path = workflows_dir / spec.filename
    if not path.is_file():
        return [], 0
    plan, unclassified, stale = build_plan(spec, load_workflow(path))
    problems = [f"{spec.filename}: job {job!r} is neither executable nor skip-reasoned" for job in unclassified]
    problems += [f"{spec.filename}: registry names job {job!r} that no longer exists" for job in stale]
    return problems, len(plan)


def consistency_problems(root: Path, *, workflows_dir: Path, registry: dict[str, WorkflowSpec]) -> list[str]:
    """Every registration, classification and build-tool drift (empty means consistent)."""
    found = {path.name for path in discover_workflow_files(workflows_dir)}
    problems = [f"workflow {name!r} is not registered in [tool.pipelines_hooks.ci_replica]" for name in sorted(found - set(registry))]
    problems += [f"registry names workflow {name!r} that no longer exists" for name in sorted(set(registry) - found)]
    steps = 0
    for spec in registry.values():
        workflow_problems, count = _workflow_problems(workflows_dir, spec)
        problems += workflow_problems
        steps += count
    texts = {name: (workflows_dir / name).read_text(encoding="utf-8") for name in registry if (workflows_dir / name).is_file()}
    problems += build_tool_problems(root / ".cargo" / "config.toml", texts)
    print(f"ci-gate-replica consistency: {len(registry)} workflow(s), {steps} step row(s) across matrix legs")
    return problems


def pattern_matches(path: str, pattern: str) -> bool:
    """``DIR/**`` prefix, ``**/X`` at any depth, otherwise fnmatch on the path or its basename."""
    if pattern.endswith("/**"):
        return path == pattern[:-3] or path.startswith(pattern[:-3] + "/")
    pattern = pattern.removeprefix("**/")
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(posixpath.basename(path), pattern)


def build_affecting_changes(root: Path, *, base_ref: str, patterns: tuple[str, ...]) -> list[str]:
    """Changed paths (working tree vs ``base_ref``) matching a build-affecting pattern."""
    changed = [line.strip() for line in git_text(root, ("diff", "--name-only", base_ref)).splitlines() if line.strip()]
    return [path for path in changed if any(pattern_matches(path, pattern) for pattern in patterns)]
