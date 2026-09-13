"""The command line every differential gate shares: a repository and a base ref."""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root


def root_and_base_ref(prog: str, description: str | None, argv: list[str]) -> tuple[Path, str | None]:
    """``(repository root, --base-ref or None)`` parsed from ``argv``."""
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", "--diff", dest="base_ref", default=None)
    args = parser.parse_args(argv)
    return repo_root(args.root), args.base_ref
