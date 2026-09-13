"""jscpd-differential: fail only for clone pairs that did not exist at the base.

BEFORE is the base commit's tree; AFTER is ``git merge-tree --write-tree`` of
the base and HEAD, i.e. the tree this change would actually produce on its
base (measure the merged tree, not the branch tip). The base is ``--base-ref``,
then ``CX_DUP_BASE_REF``, the pushed-over remote revision, ``origin/main``,
``main``, then ``HEAD^``; a single-commit repository compares with no pairs.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from pipelines_hooks.clones import jscpd_keys, jscpd_run, jscpd_snapshot
from pipelines_hooks.clones.contract import is_jscpd_path
from pipelines_hooks.core.baseref import change_base
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.args import root_and_base_ref
from pipelines_hooks.core.gitenv import git_text, nul_split
from pipelines_hooks.core.tools import verified

_OBJECT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _pairs(executable: str, root: Path, *, ref: str | None, scratch: Path) -> jscpd_keys.Pairs:
    if ref is None or not jscpd_snapshot.in_scope_paths(root, ref):
        print(f"jscpd gate [{ref or 'empty'}]: no in-scope files")
        return {}
    snapshot = jscpd_snapshot.materialize(root, ref, scratch)
    document = jscpd_run.run(executable, snapshot)
    print(jscpd_run.stats_line(document, ref[:12]))
    return jscpd_keys.keys(document, snapshot)


def _after_tree(root: Path, base: str | None) -> str:
    if base is None:
        return git_text(root, ("rev-parse", "HEAD^{tree}")).strip()
    merged = git_text(root, ("merge-tree", "--write-tree", base, "HEAD")).strip().splitlines()[0]
    if not _OBJECT.fullmatch(merged):
        raise CannotRun("git merge-tree returned an invalid tree object id")
    return merged


def _changed(root: Path, base: str | None) -> list[str]:
    if base is None:
        return jscpd_snapshot.in_scope_paths(root, "HEAD")
    raw = git_text(root, ("diff", "--name-only", "-z", "--diff-filter=ACMR", f"{base}...HEAD"))
    return sorted(path for path in nul_split(raw) if is_jscpd_path(path))


def enforce(root: Path, base: str | None) -> int:
    if not _changed(root, base):
        print("jscpd gate [enforce]: no changed code/config/template path")
        return 0
    executable = verified("jscpd")
    after_tree = _after_tree(root, base)
    with tempfile.TemporaryDirectory(prefix="jscpd-enforce-") as raw:
        before = _pairs(executable, root, ref=base, scratch=Path(raw) / "before")
        after = _pairs(executable, root, ref=after_tree, scratch=Path(raw) / "after")
    new = sorted(set(after) - set(before))
    print(f"jscpd gate [enforce]: {len(before)} pre-existing pair(s), {len(after)} after, {len(new)} NEW")
    for key in new:
        print(f"  {jscpd_keys.render_pair(key, after[key])} (fragment {key[1][:12]})")
    if new:
        print("jscpd gate [enforce]: FAIL: remove the duplication; this gate has no suppression mechanism")
        return 1
    print("jscpd gate [enforce]: PASS: no new block duplication")
    return 0


def main(argv: list[str]) -> int:
    root, base_ref = root_and_base_ref("jscpd-differential", __doc__, argv)
    return enforce(root, change_base(root, base_ref))
