"""release-standard: a connector release publishes both a PyPI package and a Docker image (PIPE-RELEASE-R013).

Warn level (exit 0): a connector repository (one that tracks ``connector_manifest.yml`` or
depends on ``agent-connector-sdk``) must track ``docker/Dockerfile`` and a workflow whose
job calls the shared ``container_pipeline.yml`` with the Docker publish enabled (the job is
not switched off by a literal ``if: false``). ``--strict`` makes the findings blocking.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths

CONTAINER = "Knuckles-Team/pipelines/.github/workflows/container_pipeline.yml"


def is_connector(root: Path, paths: list[str]) -> bool:
    """A connector tracks the generated manifest or depends on the SDK."""
    if "connector_manifest.yml" in paths:
        return True
    pyproject = root / "pyproject.toml"
    return pyproject.is_file() and "agent-connector-sdk" in pyproject.read_text(encoding="utf-8", errors="replace")


def _enabled(job: dict) -> bool:
    return str(job.get("if", "true")).strip().lower() not in {"false", "0"}


def publishes_docker(root: Path, paths: list[str]) -> bool:
    """True when a tracked workflow has an enabled job that calls the shared container pipeline."""
    for path in paths:
        if not (path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))):
            continue
        try:
            document = yaml.safe_load((root / path).read_text(encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError):
            continue
        jobs = document.get("jobs") if isinstance(document, dict) else None
        for job in (jobs or {}).values() if isinstance(jobs, dict) else ():
            if isinstance(job, dict) and str(job.get("uses", "")).startswith(CONTAINER) and _enabled(job):
                return True
    return False


def inspect(root: Path, paths: list[str]) -> list[str]:
    """Every finding for one repository (empty means conformant or not a connector)."""
    if not is_connector(root, paths):
        return []
    findings: list[str] = []
    if "docker/Dockerfile" not in paths:
        findings.append("docker/Dockerfile is not tracked (a release publishes the <version>-mcp image)")
    if not publishes_docker(root, paths):
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
