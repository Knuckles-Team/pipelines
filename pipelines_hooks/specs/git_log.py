"""Landing commits: non-merge commits reachable from ``head`` that touch product paths."""

from __future__ import annotations

import re
from pathlib import Path

from pipelines_hooks.core.gitenv import git_text
from pipelines_hooks.specs.ids import expand_ranges, is_product_path

_RECORD_SEP = "\x1e"
_FIELD_SEP = "\x1f"
_REVERT_RE = re.compile(r"This reverts commit ([0-9a-f]{40})")


def _parse_record(record: str) -> tuple[str, str, str] | None:
    if _FIELD_SEP not in record:
        return None
    sha, message, files = record.split(_FIELD_SEP, 2)
    return sha, message, files


def _merge_members(root: Path, sha: str) -> set[str]:
    """A reverted merge (``git revert -m 1``) undoes every commit it brought in."""
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
    """commit SHA -> expanded message, for non-merge commits that land product code.

    A commit named by a later ``This reverts commit <sha>`` is dropped: it
    stops counting as a landing (SPEC-STATUS-LIFECYCLE.md Sec3).
    """
    log_format = f"--format={_RECORD_SEP}%H{_FIELD_SEP}%B{_FIELD_SEP}"
    raw = git_text(root, ("log", head, "--no-merges", log_format, "--name-only"))
    commits: dict[str, str] = {}
    reverted: set[str] = set()
    for record in raw.split(_RECORD_SEP):
        parsed = _parse_record(record)
        if parsed is None:
            continue
        sha, message, files = parsed
        reverted |= set(_REVERT_RE.findall(message))
        if any(is_product_path(f) for f in files.split()):
            commits[sha] = expand_ranges(message)
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
