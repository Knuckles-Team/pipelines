"""``harness-bundles-untracked``: no generated coding harness bundle is committed (PIPE-RELEASE-R028.2).

Generated bundle paths are ``.claude-plugin/plugin.json``, anything under ``.codex-plugin/`` or ``.grok-plugin/`` and a
tracked tree under the output directory declared in ``[tool.pipelines.harness_bundles]``. A declared catalog file is the
one exception. The finding is ``BUNDLE_COMMITTED`` with each path.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

from pipelines_hooks.core.gitenv import git_text, nul_split, repo_root
from pipelines_hooks.release.declared import table

PLUGIN_FILE = ".claude-plugin/plugin.json"
PLUGIN_TREES = (".codex-plugin/", ".grok-plugin/")


def declared(root: Path) -> dict:
    """The ``[tool.pipelines.harness_bundles]`` table (empty when the repository declares none)."""
    return table(root, "harness_bundles")


def check(tracked: Iterable[str], declaration: dict) -> list[str]:
    """Tracked paths that are generated bundle output."""
    catalog = declaration.get("catalog")
    output = str(declaration.get("output", "")).strip("/")
    trees = (*PLUGIN_TREES, f"{output}/" if output else "")
    found = []
    for path in sorted(tracked):
        if path == catalog:
            continue
        if path == PLUGIN_FILE or any(t and path.startswith(t) for t in trees):
            found.append(path)
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    paths = check(nul_split(git_text(root, ["ls-files", "-z"])), declared(root))
    for path in paths:
        print(f"BUNDLE_COMMITTED {path}")
    return 1 if paths else 0
