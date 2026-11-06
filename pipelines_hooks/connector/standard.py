"""connector-standard: no standard file is committed; codespell, the shared security checks, API parity, the skill gates and the connector surface standard hold."""

from __future__ import annotations

import sys
from typing import Any

from pipelines_hooks.core.errors import Unavailable
from pipelines_hooks.core.settings import setting
from pipelines_hooks.connector import api_parity, codespell, files, security, skills, surface

MEMBERS = {
    "files": files,
    "codespell": codespell,
    "security": security,
    "api-parity": api_parity,
    "skills": skills,
    "surface": surface,
}


def _run(name: str, member: Any, argv: list[str]) -> int:
    """One member's status; an absent prerequisite fails closed in CI and skips that member locally."""
    try:
        return int(member.main(argv))
    except Unavailable as exc:
        if setting("CI").casefold() not in {"", "0", "false", "no"}:
            print(f"connector-standard: {name}: CANNOT RUN: {exc}", file=sys.stderr)
            return 2
        print(f"SKIPPED (connector-standard: {name}): {exc}", file=sys.stderr)
        return 0


def main(argv: list[str]) -> int:
    """The worst exit status of the member checks; every member always runs and the failed ones are named."""
    status = {name: _run(name, member, argv) for name, member in MEMBERS.items()}
    sys.stdout.flush()
    failed = [name for name, code in status.items() if code]
    if failed:
        print(f"connector-standard: FAILED members: {', '.join(failed)}", file=sys.stderr)
    return max(status.values())
