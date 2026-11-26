"""jscpd-differential: fail only for clone pairs that did not exist at the base.

A change whose in-scope paths the scanner reads no code of (comment-only,
deletion-only) is ``CannotRun``, never a pass. Pairs are compared by fragment
digest, so a moved fragment is not new duplication. BEFORE is the base commit's tree; AFTER is ``git merge-tree --write-tree`` of
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


def _pairs(executable: str, root: Path, *, ref: str | None, scratch: Path) -> tuple[jscpd_keys.Pairs, Path | None]:
    """The pairs of one tree and the snapshot directory that was scanned."""
    if ref is None or not jscpd_snapshot.in_scope_paths(root, ref):
        print(f"jscpd gate [{ref or 'empty'}]: no in-scope files")
        return {}, None
    snapshot = jscpd_snapshot.materialize(root, ref, scratch)
    document = jscpd_run.run(executable, snapshot)
    print(jscpd_run.stats_line(document, ref[:12]))
    return jscpd_keys.keys(document, snapshot), snapshot


def _require_evaluated(executable: str, changed: list[str], snapshot: Path | None, scratch: Path) -> None:
    """Refuse a change whose in-scope paths the scanner read nothing of.

    A comment-only or deletion-only change leaves no token for the scanner to
    compare, so a clean verdict would say nothing about it. The changed files
    that still exist are scanned on their own; when the scanner reports no
    source among them the verdict is ``CannotRun`` (PIPE-GATES-R079).
    """
    only = scratch / "changed"
    only.mkdir(parents=True)
    present = [path for path in changed if snapshot is not None and (snapshot / path).is_file()]
    for path in present:
        target = only / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((snapshot / path).read_bytes())
    sources = jscpd_run.run(executable, only)["statistics"]["total"]["sources"] if present else 0
    if sources == 0:
        raise CannotRun(
            f"the scanner read no code of the {len(changed)} changed in-scope path(s) "
            f"({', '.join(changed[:5])}); a comment-only or deletion-only change cannot be evaluated: "
            "combine it with the function-level change it belongs to"
        )


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
    raw = git_text(root, ("diff", "--name-only", "-z", "--diff-filter=ACMRD", f"{base}...HEAD"))
    return sorted(path for path in nul_split(raw) if is_jscpd_path(path))


def enforce(root: Path, base: str | None) -> int:
    changed = _changed(root, base)
    if not changed:
        print("jscpd gate [enforce]: no changed code/config/template path")
        return 0
    executable = verified("jscpd")
    after_tree = _after_tree(root, base)
    with tempfile.TemporaryDirectory(prefix="jscpd-enforce-") as raw:
        before, _ = _pairs(executable, root, ref=base, scratch=Path(raw) / "before")
        after, snapshot = _pairs(executable, root, ref=after_tree, scratch=Path(raw) / "after")
        _require_evaluated(executable, changed, snapshot, Path(raw))
    new = jscpd_keys.new_pairs(before, after)
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
