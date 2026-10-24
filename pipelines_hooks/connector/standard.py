"""connector-standard: no standard file is committed; codespell, the shared security checks and API parity hold."""

from __future__ import annotations

from pipelines_hooks.connector import api_parity, codespell, files, security


def main(argv: list[str]) -> int:
    """The worst exit status of the member checks; every member always runs."""
    return max(member.main(argv) for member in [files, codespell, security, api_parity])
