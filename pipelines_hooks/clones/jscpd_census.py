"""jscpd-census: the whole tracked tree at HEAD, reported, never failing.

The census is the advisory number that drives clone debt down; the
differential gate is what fails. Findings are printed in full so debt stays
visible -- nothing is written to disk and no count is frozen.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Any

from pipelines_hooks.clones import jscpd_keys, jscpd_run, jscpd_snapshot
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tools import verified


def census_document(root: Path) -> tuple[dict[str, Any], jscpd_keys.Pairs]:
    """The validated HEAD report and its keyed pairs."""
    executable = verified("jscpd")
    with tempfile.TemporaryDirectory(prefix="jscpd-census-") as raw:
        snapshot = jscpd_snapshot.materialize(root, "HEAD", Path(raw) / "tree")
        document = jscpd_run.run(executable, snapshot)
        return document, jscpd_keys.keys(document, snapshot)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="jscpd-census", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    tracked = jscpd_snapshot.in_scope_paths(root, "HEAD")
    print(f"jscpd gate [census]: {len(tracked)} tracked in-scope file(s)")
    if not tracked:
        return 0
    document, pairs = census_document(root)
    print(jscpd_run.stats_line(document, "census"))
    for key in sorted(pairs):
        print(f"  {jscpd_keys.render_pair(key, pairs[key])}")
    print("jscpd gate [census]: advisory; findings are neither a baseline nor a failure")
    return 0
