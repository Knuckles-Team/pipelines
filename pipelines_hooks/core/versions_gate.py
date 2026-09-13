"""scanner-versions: prove every pinned native scanner is installed at its exact version."""

from __future__ import annotations

import argparse

from pipelines_hooks.core.tools import PINNED_VERSIONS, expected_version_line, verified


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="scanner-versions", description=__doc__)
    parser.add_argument("tools", nargs="*", choices=sorted(PINNED_VERSIONS), default=sorted(PINNED_VERSIONS))
    tools = parser.parse_args(argv).tools or sorted(PINNED_VERSIONS)
    for tool in tools:
        print(f"scanner-versions: {expected_version_line(tool)} at {verified(tool)}")
    return 0
