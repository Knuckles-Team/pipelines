"""connector-standard: no standard file is committed, and codespell passes with the shared default words."""

from __future__ import annotations

from pipelines_hooks.connector import codespell, files


def main(argv: list[str]) -> int:
    """The worst exit status of the file check and the spelling check; both always run."""
    return max(files.main(argv), codespell.main(argv))
