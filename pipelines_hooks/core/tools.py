"""The pinned native scanner contract.

One reviewed version per scanner for the whole fleet (the versions
epistemic-graph's ``scripts/scanner_contract.py`` pins). A consuming repository
pins these by pinning this hook repository's revision. Hooks resolve binaries
that are already installed; they never download, compile or substitute one,
and a missing or drifted binary is exit 2, never a clean pass.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.core.settings import setting

PINNED_VERSIONS = {
    "cccc": "1.6.0",
    "kiss": "0.4.10",
    "dupehound": "0.1.2",
    "jscpd": "5.0.16",
}
#: jscpd v5 reports itself as ``cpd``.
_VERSION_PREFIX = {"cccc": "cccc", "kiss": "kiss", "dupehound": "dupehound", "jscpd": "cpd"}


def expected_version_line(tool: str) -> str:
    """The exact ``--version`` output the pinned binary prints."""
    return f"{_VERSION_PREFIX[tool]} {PINNED_VERSIONS[tool]}"


def _executable(candidate: Path) -> bool:
    return candidate.is_file() and os.access(candidate, os.X_OK)


def resolve(tool: str) -> str:
    """An installed binary: ``$<TOOL>_BIN``, then fixed prefixes, then PATH."""
    override = setting(f"{tool.upper()}_BIN")
    if override:
        candidate = Path(override).expanduser()
        if not _executable(candidate):
            raise CannotRun(f"${tool.upper()}_BIN is not an executable file: {candidate}")
        return str(candidate)
    home = Path.home()
    for candidate in (home / ".local/bin" / tool, Path("/usr/local/bin") / tool, home / ".cargo/bin" / tool):
        if _executable(candidate):
            return str(candidate)
    found = shutil.which(tool)
    if found:
        return found
    raise CannotRun(
        f"{tool} is not installed; install the pinned {PINNED_VERSIONS[tool]} "
        "binary (hooks never install scanners)"
    )


def verified(tool: str) -> str:
    """The resolved binary after proving its exact pinned version."""
    executable = resolve(tool)
    try:
        result = subprocess.run(
            [executable, "--version"],
            env=sanitized_env(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"could not run {executable} --version: {exc}") from exc
    got = (result.stdout or "").strip()
    expected = expected_version_line(tool)
    if result.returncode != 0 or got != expected:
        raise CannotRun(f"{tool} version drift: expected {expected!r}, got {got!r}")
    return executable
