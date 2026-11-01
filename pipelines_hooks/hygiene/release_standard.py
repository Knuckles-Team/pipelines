"""release-standard: a connector release publishes both a PyPI package and a Docker image (PIPE-RELEASE-R013).

Warn level (exit 0): a connector repository (one that declares the
``scion_sdk.connector`` entry point or tracks a ``connector_sources.py``) must
track ``docker/Dockerfile`` or use the provider's canonical renderer, and must have a
workflow whose job calls the shared ``container_pipeline.yml`` with the Docker publish
enabled (the job is not switched off by a literal ``if: false``). An explicitly selected
custom Dockerfile must remain tracked. ``--strict`` makes the findings blocking.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

import yaml

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths

ENTRY_POINT_GROUP = "scion_sdk.connector"
CONTAINER = "Knuckles-Team/pipelines/.github/workflows/container_pipeline.yml"


def is_connector(root: Path, paths: list[str]) -> bool:
    """A connector declares the SDK connector entry point or tracks a generated ``connector_sources.py``."""
    if any(path.rsplit("/", 1)[-1] == "connector_sources.py" for path in paths):
        return True
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return False
    points = document.get("project", {}).get("entry-points", {}).get(ENTRY_POINT_GROUP, {})
    return isinstance(points, dict) and bool(points)


def _enabled(job: dict) -> bool:
    return str(job.get("if", "true")).strip().lower() not in {"false", "0"}


def publishes_docker(root: Path, paths: list[str]) -> bool:
    """True when a tracked workflow has an enabled job that calls the shared container pipeline."""
    return bool(_container_jobs(root, paths))


def _container_jobs(root: Path, paths: list[str]) -> list[dict]:
    """Enabled shared container jobs, retaining their input contract for recipe checks."""
    jobs: list[dict] = []
    for path in paths:
        if not (path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))):
            continue
        try:
            document = yaml.safe_load((root / path).read_text(encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError):
            continue
        workflow_jobs = document.get("jobs") if isinstance(document, dict) else None
        for job in (workflow_jobs or {}).values() if isinstance(workflow_jobs, dict) else ():
            if isinstance(job, dict) and str(job.get("uses", "")).startswith(CONTAINER) and _enabled(job):
                jobs.append(job)
    return jobs


def _canonical_renderer_identity(root: Path, paths: list[str]) -> bool:
    """Whether the current source can be recognized by the central renderer."""
    if "pyproject.toml" not in paths or not (root / "pyproject.toml").is_file():
        return False
    try:
        document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    points = document.get("project", {}).get("entry-points", {}).get(ENTRY_POINT_GROUP, {})
    return (isinstance(points, dict) and bool(points)) or any(
        path.rsplit("/", 1)[-1] == "connector_sources.py" for path in paths
    )


def _has_container_recipe(root: Path, paths: list[str], jobs: list[dict]) -> bool:
    """Accept a tracked recipe, an explicit render, or the central canonical auto-render path."""
    if not jobs:
        return False
    recipes: list[bool] = []
    for job in jobs:
        raw_inputs = job.get("with")
        inputs: dict = raw_inputs if isinstance(raw_inputs, dict) else {}
        dockerfile = inputs.get("dockerfile", "docker/Dockerfile")
        if not isinstance(dockerfile, str):
            recipes.append(False)
        elif dockerfile != "docker/Dockerfile":
            recipes.append(dockerfile in paths)
        else:
            recipes.append(
                "docker/Dockerfile" in paths
                or str(inputs.get("render_connector", "")).strip().lower() in {"true", "1", "yes"}
                or _canonical_renderer_identity(root, paths)
            )
    return all(recipes)


def inspect(root: Path, paths: list[str]) -> list[str]:
    """Every finding for one repository (empty means conformant or not a connector)."""
    if not is_connector(root, paths):
        return []
    findings: list[str] = []
    jobs = _container_jobs(root, paths)
    if not _has_container_recipe(root, paths, jobs):
        findings.append("docker/Dockerfile is not tracked (a release publishes the <version>-mcp image)")
    if not jobs:
        findings.append(f"no enabled workflow job calls {CONTAINER} (a release publishes PyPI and Docker)")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="release-standard", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--strict", action="store_true", help="fail on findings instead of warning")
    arguments = parser.parse_args(argv)
    root = repo_root(arguments.root)
    findings = inspect(root, tracked_paths(root))
    if not findings:
        print("release-standard: conformant (or not a connector)")
        return 0
    level = "FAIL" if arguments.strict else "WARN"
    print(f"{level}: release-standard (specs/ordered-digest-release, PIPE-RELEASE-R013):")
    for finding in findings:
        print(f"  {finding}")
    return 1 if arguments.strict else 0
