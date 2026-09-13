"""Execute RUN steps verbatim, threading $GITHUB_ENV/$GITHUB_PATH like a runner does."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import platformdirs

from pipelines_hooks.ci_replica.matrix import strip_expressions
from pipelines_hooks.core.settings import process_environment, setting

NON_BLOCKING = frozenset({"ENV_SETUP", "ARTIFACT_IO", "NOT_VALIDATED_LOCALLY", "DRY_RUN"})


def local_tmpdir() -> str:
    """A local-only execution adjustment (a runner gets an ephemeral TMPDIR for free).

    ``CI_GATE_TMPDIR`` when set, else a directory in the user's cache: on disk, so
    a large build does not fill a memory-backed ``/tmp``.
    """
    default = platformdirs.user_cache_path("pipelines-hooks") / "ci-gate-tmp"
    path = Path(setting("CI_GATE_TMPDIR", str(default)))
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def job_environment(document: dict, job_id: str) -> dict[str, str]:
    environment = process_environment()
    environment.update({k: str(v) for k, v in (document.get("env") or {}).items()})
    environment.update({k: str(v) for k, v in (document["jobs"][job_id].get("env") or {}).items()})
    environment["TMPDIR"] = local_tmpdir()
    return environment


def _thread_outputs(files: dict[str, Path], environment: dict[str, str]) -> None:
    for line in files["GITHUB_ENV"].read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            environment[key.strip()] = value
    for entry in filter(str.strip, files["GITHUB_PATH"].read_text(encoding="utf-8").splitlines()):
        environment["PATH"] = entry.strip() + os.pathsep + environment.get("PATH", "")


def run_step(run_text: str, *, root: Path, environment: dict[str, str]) -> tuple[object, float]:
    """``(exit status or "TIMEOUT", seconds)``; ``environment`` is updated in place."""
    command, stripped = strip_expressions(run_text)
    if stripped:
        print(f"    [gha-expr stripped to empty locally: {stripped}]")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="gh-step-") as raw:
        files = {name: Path(raw) / name.lower() for name in ("GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH")}
        for path in files.values():
            path.touch()
        step_env = {**environment, **{name: str(path) for name, path in files.items()}}
        step_env.setdefault("RUNNER_TEMP", environment["TMPDIR"])
        try:
            status: object = subprocess.run(["bash", "-c", command], cwd=str(root), env=step_env, timeout=int(setting("CI_GATE_STEP_TIMEOUT_SECS", "3600")), check=False).returncode
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
        _thread_outputs(files, environment)
    return status, time.monotonic() - started


def local_hygiene(root: Path) -> None:
    """NOT a workflow step: remove a previous local run's ambiguous build outputs (printed loudly)."""
    removed = [name for name in ("dist-primary", "dist-reproduction", "dist") if (root / name).exists()]
    for name in removed:
        shutil.rmtree(root / name, ignore_errors=True)
    if removed:
        print(f"[local-only hygiene, NOT a workflow step] removed stale: {removed}")


def failed(status: object) -> bool:
    return (isinstance(status, str) and status not in NON_BLOCKING) or (isinstance(status, int) and status != 0)
