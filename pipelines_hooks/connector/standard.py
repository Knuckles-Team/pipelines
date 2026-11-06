"""connector-standard: no standard file is committed; codespell, the shared security checks, API parity, the skill gates and the connector surface standard hold."""

from __future__ import annotations

import sys

from pipelines_hooks.connector import api_parity, codespell, files, security, skills, surface

MEMBERS = {
    "files": files,
    "codespell": codespell,
    "security": security,
    "api-parity": api_parity,
    "skills": skills,
    "surface": surface,
}


def main(argv: list[str]) -> int:
    """The worst exit status of the member checks; every member always runs and the failed ones are named."""
    status = {name: member.main(argv) for name, member in MEMBERS.items()}
    sys.stdout.flush()
    failed = [name for name, code in status.items() if code]
    if failed:
        print(f"connector-standard: FAILED members: {', '.join(failed)}", file=sys.stderr)
    return max(status.values())
