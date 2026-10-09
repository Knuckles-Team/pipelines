"""Test bindings: a ``# spec: ID`` / ``// spec: ID`` line, or ``mark.spec(...)``."""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.specs.ids import BIND_RE, ID

_GREP_PATTERN = r"(//|#)\s*spec:\s*[A-Z]|mark\.spec\("
_EXCLUDED_PATHSPECS = (":!specs", ":!docs", ":!*.md")
MAX_GREP_OUTPUT_BYTES = 16 * 1024 * 1024


def _grep_bindings(root: Path) -> str:
    command = ["git", "grep", "-n", "-I", "-E", _GREP_PATTERN, "--", ".", *_EXCLUDED_PATHSPECS]
    try:
        result = subprocess.run(command, cwd=str(root), env=sanitized_env(), capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotRun(f"spec-status: test-binding scan is unavailable: {exc}") from None
    if result.returncode not in {0, 1} or len(result.stdout) > MAX_GREP_OUTPUT_BYTES:
        raise CannotRun("spec-status: test-binding scan failed or exceeded its output bound")
    return result.stdout


def _ids_in_match(match: re.Match[str]) -> list[str]:
    body = match.group(1) or match.group(2) or ""
    return re.findall(ID, body)


def test_bindings(root: Path) -> dict[str, list[str]]:
    """requirement ID -> sorted ``path:line`` locations of a bound test."""
    found: dict[str, list[str]] = defaultdict(list)
    for line in _grep_bindings(root).splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        path, lineno, text = parts
        for match in BIND_RE.finditer(text):
            for rid in _ids_in_match(match):
                found[rid].append(f"{path}:{lineno}")
    return found
