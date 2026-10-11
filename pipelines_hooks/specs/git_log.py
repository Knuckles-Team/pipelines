"""Landing commits: non-merge commits reachable from ``head`` that touch product paths."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from pipelines_hooks.core.gitenv import git_text, run_git
from pipelines_hooks.specs.ids import expand_ranges, is_product_path
from pipelines_hooks.specs.trailer_ids import NONE_EXEMPTION

_RECORD_SEP = "\x1e"
_FIELD_SEP = "\x1f"
_REVERT_RE = re.compile(r"This reverts commit ([0-9a-f]{40})")


class _Record(NamedTuple):
    sha: str
    message: str
    trailers: str
    files: str


def _parse_record(record: str) -> _Record | None:
    if _FIELD_SEP not in record:
        return None
    sha, message, trailers, files = record.split(_FIELD_SEP, 3)
    return _Record(sha, message, trailers, files)


def _declarations(message: str, trailers: str) -> str:
    """Explicit Spec trailers, plus the historical Spec-only subject form."""
    subject = message.splitlines()[0] if message else ""
    if subject.lower().startswith("spec:"):
        trailers += "\n" + subject.partition(":")[2].strip()
    return expand_ranges("\n".join(
        line for line in trailers.splitlines()
        if not NONE_EXEMPTION.match(line.strip())
    ))


def _merge_members(root: Path, sha: str) -> set[str]:
    """A reverted merge (``git revert -m 1``) undoes every commit it brought in.

    A revert message can name a commit this clone does not have (it was never
    pushed, or its branch was deleted). Such a commit brought nothing into this
    history, so it has no members here.
    """
    if run_git(root, ("cat-file", "-e", f"{sha}^{{commit}}")).returncode != 0:
        return set()
    parents = git_text(root, ("rev-list", "--parents", "-n", "1", sha)).split()[1:]
    if len(parents) < 2:
        return set()
    return set(git_text(root, ("rev-list", f"{parents[0]}..{sha}")).split())


def expand_reverted(root: Path, reverted: set[str]) -> set[str]:
    """Reverted SHAs plus every member of a reverted merge."""
    out = set(reverted)
    for sha in reverted:
        out |= _merge_members(root, sha)
    return out


def landing_commits(root: Path, head: str) -> dict[str, str]:
    """commit SHA -> expanded declarations, for non-merge product commits.

    A commit named by a later ``This reverts commit <sha>`` is dropped: it
    stops counting as a landing (SPEC-STATUS-LIFECYCLE.md Sec3).
    """
    log_format = (
        f"--format={_RECORD_SEP}%H{_FIELD_SEP}%B{_FIELD_SEP}"
        f"%(trailers:key=Spec,valueonly,unfold=true){_FIELD_SEP}"
    )
    raw = git_text(root, ("log", head, "--no-merges", log_format, "--name-only"))
    commits: dict[str, str] = {}
    reverted: set[str] = set()
    for record in raw.split(_RECORD_SEP):
        parsed = _parse_record(record)
        if parsed is None:
            continue
        sha, message, trailers, files = parsed
        reverted |= set(_REVERT_RE.findall(message))
        if any(is_product_path(f) for f in files.split()):
            commits[sha] = _declarations(message, trailers)
    for sha in expand_reverted(root, reverted):
        commits.pop(sha, None)
    return commits


def reverted_shas(root: Path, head: str) -> set[str]:
    """Every commit undone by a later revert reachable from ``head`` (merge members included)."""
    raw = git_text(root, ("log", head, "--format=%B", "--grep=This reverts commit"))
    return expand_reverted(root, set(_REVERT_RE.findall(raw)))


def reachable_shas(root: Path, head: str) -> set[str]:
    """Every commit SHA reachable from ``head`` (for legacy evidence validation)."""
    return set(git_text(root, ("rev-list", head)).split())
