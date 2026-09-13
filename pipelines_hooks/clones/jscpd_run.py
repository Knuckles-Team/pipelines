"""Run the pinned jscpd over one snapshot and return its validated report."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pipelines_hooks.clones import contract
from pipelines_hooks.clones.jscpd_report import load_report
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env

AMBIENT_CONFIGS = (".jscpd.json", ".jscpdrc", ".jscpdrc.json", ".jscpdrc.yaml", ".jscpdrc.yml", "jscpd.config.js", "jscpd.config.cjs")
EMPTY_REPORT: dict[str, Any] = {
    "duplicates": [],
    "statistics": {"total": {"clones": 0, "sources": 0, "duplicatedLines": 0, "lines": 0, "percentage": 0.0}},
}


def guard_ambient_config(directory: Path) -> None:
    """jscpd auto-loads cwd config files; an unreviewed one would change its semantics."""
    for name in AMBIENT_CONFIGS:
        candidate = directory / name
        if candidate.exists() or candidate.is_symlink():
            raise CannotRun(f"{name} exists; jscpd would auto-load it. Remove it (the contract is in the hook)")


def command(executable: str, output: Path, target: Path) -> list[str]:
    """jscpd v5's exit code is not the finding count; the validated JSON is the truth."""
    return [
        executable, "--min-tokens", str(contract.JSCPD_MIN_TOKENS), "--min-lines", str(contract.JSCPD_MIN_LINES),
        "--mode", contract.JSCPD_MODE, "--format", ",".join(contract.JSCPD_FORMATS),
        "--ignore", ",".join(contract.EXCLUSIONS), "--absolute", "-r", "json", "-o", str(output),
        "--formats-exts", contract.format_exts_arg(), "--formats-names", contract.format_names_arg(),
        str(target),
    ]


def run(executable: str, snapshot: Path) -> dict[str, Any]:
    """The validated report for a whole snapshot directory."""
    guard_ambient_config(snapshot)
    with tempfile.TemporaryDirectory(prefix="jscpd-report-") as raw:
        output = Path(raw)
        try:
            result = subprocess.run(
                command(executable, output, snapshot), cwd=str(snapshot), env=sanitized_env(),
                capture_output=True, text=True, timeout=900, check=False,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            raise CannotRun(f"could not run jscpd: {exc}") from exc
        if result.returncode != 0:
            raise CannotRun(f"jscpd exited {result.returncode}: {(result.stderr or result.stdout or '')[-800:]}")
        return load_report(output / "jscpd-report.json", root=snapshot)


def stats_line(document: dict[str, Any], label: str) -> str:
    total = document["statistics"]["total"]
    return (
        f"jscpd gate [{label}]: {total['clones']} clone(s), {total['sources']} source(s), "
        f"{total['duplicatedLines']} of {total['lines']} lines duplicated ({float(total['percentage']):.2f}%)"
    )
