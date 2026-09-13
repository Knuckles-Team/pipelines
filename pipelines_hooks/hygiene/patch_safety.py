"""pre-commit-patch-safety: no live uncommitted work parked in the pre-commit patch cache.

pre-commit clears unstaged changes before running hooks by writing them to
``$PRE_COMMIT_HOME/patch<timestamp>-<pid>`` and restoring them afterwards. A
killed run leaves the working tree blanked and that patch file as the ONLY
copy. This gate never deletes or blesses anything: it FAILS while any patch
applies cleanly to the repository and is not already present in it. Treat the
patch cache as live working-tree state, never as disposable cache.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root, run_git
from pipelines_hooks.core.settings import setting

PATCH_NAME_RE = re.compile(r"^patch\d+-\d+$")
LIVE = "LIVE-UNAPPLIED"


def default_patch_dir() -> Path:
    if setting("PRE_COMMIT_HOME"):
        return Path(setting("PRE_COMMIT_HOME"))
    cache = setting("XDG_CACHE_HOME")
    return Path(cache) / "pre-commit" if cache else Path.home() / ".cache" / "pre-commit"


def find_patches(patch_dir: Path) -> list[Path]:
    if not patch_dir.is_dir():
        return []
    return sorted(p for p in patch_dir.iterdir() if p.is_file() and PATCH_NAME_RE.match(p.name))


def classify(root: Path, patch: Path) -> str:
    """``LIVE-UNAPPLIED``, ``already-in-tree`` or ``stale-or-foreign``."""
    if run_git(root, ("apply", "--check", str(patch))).returncode == 0:
        return LIVE
    if run_git(root, ("apply", "--check", "--reverse", str(patch))).returncode == 0:
        return "already-in-tree"
    return "stale-or-foreign"


DETAIL = {
    LIVE: "applies cleanly and is NOT in the tree: uncommitted work that deleting this file DESTROYS. "
    "Read it, then APPLY and commit it, or record why it is abandoned before removing it.",
    "already-in-tree": "reverse-applies cleanly: its content is already present in this repository.",
    "stale-or-foreign": "applies neither way: superseded, or from another repository sharing this "
    "per-user cache. NOT proof of safety -- check every other repository before reclaiming.",
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pre-commit-patch-safety", description=__doc__)
    parser.add_argument("--repository-root", "--root", dest="root", type=Path, default=Path.cwd())
    parser.add_argument("--patch-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    patches = find_patches(args.patch_dir or default_patch_dir())
    verdicts = [(patch, classify(root, patch)) for patch in patches]
    for patch, verdict in verdicts:
        print(f"  - {patch.name}: {verdict}\n      {DETAIL[verdict]}")
    live = sum(verdict == LIVE for _, verdict in verdicts)
    if live:
        print(f"FAILED: {live} patch(es) hold live, unapplied work. Do NOT clear the cache to silence this.")
        return 1
    print(f"pre-commit-patch-safety: OK: {len(patches)} patch file(s), none live-unapplied against {root.name}")
    return 0
