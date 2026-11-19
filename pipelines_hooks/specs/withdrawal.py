"""Validate explicit, evidence-only withdrawals without exempting feature work."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, run_git
from pipelines_hooks.specs.narrative import TASK_RE
from pipelines_hooks.specs.withdrawal_git import (
    blob,
    changes,
    declarations as read_declarations,
)
from pipelines_hooks.specs.withdrawal_source import source_withdrawal_only


def _owners(root: Path, ids: set[str]) -> dict[str, str]:
    owners = {}
    for path in root.glob("specs/*/requirements.md"):
        text = path.read_text(encoding="utf-8")
        for rid in ids:
            if not re.search(rf"(?m)^\|\s*`{re.escape(rid)}`\s*\|", text):
                continue
            if rid in owners:
                raise ValueError(f"ambiguous requirement owner: {rid}")
            owners[rid] = path.parent.relative_to(root).as_posix()
    return owners


def _added_only(before: str, after: str) -> bool:
    remaining = iter(after.splitlines(keepends=True))
    return all(any(line == candidate for candidate in remaining) for line in before.splitlines(keepends=True))


_CHECKED = re.compile(r"^(\s*- )\[[xX]\]")


def _task_ids(line: str) -> set[str]:
    """IDs a task line belongs to: the standard numbered form or the bold ``**ID:**`` form."""
    match = TASK_RE.match(line)
    ids = {match.group(1)} if match else set()
    return ids | set(re.findall(r"^\s*- \[[ xX]\] \*\*([^*\s]+):\*\*", line))


def _tasks_only(before: str, after: str, ids: set[str]) -> bool:
    reopened = [
        _CHECKED.sub(r"\1[ ]", line) if _task_ids(line) & ids else line for line in before.splitlines(keepends=True)
    ]
    return "".join(reopened) == after


def _metadata_only(name: str, before: str, after: str, *, ids: set[str]) -> bool:
    if name == "plan.md":
        return _added_only(before, after)
    if name == "tasks.md":
        return _tasks_only(before, after, ids)
    # The independent spec-status gate still requires canonical generation.
    return name == "status.json"


def _removed_ids(path: str, before: str, after: str, *, ids: set[str]) -> set[str]:
    if not path.endswith(".rs") or not source_withdrawal_only(before, after, ids):
        raise ValueError(f"withdrawal changes non-evidence content: {path}")
    return {rid for rid in ids if re.search(rf"(?m)^\s*// spec: {re.escape(rid)}\s*$", before)}


def _validate_changes(root: Path, base: str, *, ids: set[str], removals: set[str], owners: dict[str, str]) -> None:
    removed = set()
    directories = set(owners.values())
    for path, before, after in changes(root, base):
        parent, _, name = path.rpartition("/")
        if parent in directories and _metadata_only(name, before, after, ids=ids):
            continue
        removed.update(_removed_ids(path, before, after, ids=removals))
    if removed != removals:
        raise ValueError("each withdrawn ID must remove an existing Rust comment binding")


def _validate_open_task(root: Path, rid: str, *, owners: dict[str, str]) -> None:
    try:
        text = blob(root, "HEAD", f"{owners[rid]}/tasks.md")
    except CannotRun as exc:
        raise ValueError(f"owning tasks.md is unreadable for never-bound {rid}") from exc
    boxes = [line.lstrip()[:5] for line in text.splitlines() if rid in _task_ids(line)]
    if not boxes or any(box != "- [ ]" for box in boxes):
        raise ValueError(f"never-bound {rid} needs its owning task unchecked")


def _validate_metadata_commit(root: Path, sha: str, ids: set[str], *, owners: dict[str, str]) -> None:
    """A never-bound withdrawal commit changes only its own IDs' evidence metadata."""
    parent = run_git(root, ("rev-parse", "--verify", "--quiet", f"{sha}^1"))
    if parent.returncode != 0:
        raise ValueError(f"never-bound withdrawal commit {sha[:12]} has no parent")
    directories = {owners[rid] for rid in ids}
    for path, before, after in changes(root, parent.stdout.strip(), sha):
        directory, _, name = path.rpartition("/")
        if directory not in directories or not _metadata_only(name, before, after, ids=ids):
            raise ValueError(f"never-bound withdrawal commit changes non-evidence content: {path}")


def _validate_reason(root: Path, requested: set[str], reason: str, *, owners: dict[str, str]) -> None:
    if not requested or len(reason) < 20:
        raise ValueError("every withdrawal needs IDs and a descriptive reason (20+ characters)")
    for rid in requested:
        text = blob(root, "HEAD", f"{owners[rid]}/plan.md")
        if rid not in text or reason not in text:
            raise ValueError(f"owning plan must retain {rid} and its exact withdrawal reason")


def _validate(
    root: Path,
    base: str | None,
    declarations: list[tuple[str, set[str], str]],
    *,
    named: set[str],
    known: set[str],
    bound: set[str],
    bound_at: Callable[[str], set[str]],
) -> set[str]:
    if base is None:
        raise ValueError("withdrawal requires an explicit resolvable base")
    ids = set().union(*(item[1] for item in declarations))
    if not ids or not ids <= named or not ids <= known:
        raise ValueError("withdrawn IDs must be known and retained in Spec trailers")
    if ids & bound:
        raise ValueError("withdrawn IDs still have acceptance bindings")
    owners = _owners(root, ids)
    for _, requested, reason in declarations:
        _validate_reason(root, requested, reason, owners=owners)
    merge_base = git_text(root, ("merge-base", base, "HEAD")).strip()
    # An ID bound at the merge base must remove that binding; one never bound
    # there or at HEAD has nothing to remove, so its own commit must be metadata.
    removals = ids & bound_at(merge_base)
    never_bound = ids - removals
    for rid in never_bound:
        _validate_open_task(root, rid, owners=owners)
    for sha, requested, _ in declarations:
        if requested & never_bound:
            _validate_metadata_commit(root, sha, requested, owners=owners)
    if removals:
        _validate_changes(root, merge_base, ids=ids, removals=removals, owners=owners)
    return ids


def withdrawals(
    root: Path,
    base: str | None,
    *,
    named: set[str],
    known: set[str],
    bound: set[str],
    bound_at: Callable[[str], set[str]],
) -> tuple[set[str], list[str]]:
    """Return exempt IDs only after every evidence-only constraint passes.

    ``bound`` holds the IDs bound in the current tree; ``bound_at`` returns the
    IDs bound at a revision and is read at the merge base.
    """
    declarations = read_declarations(root, base)
    if not declarations:
        return set(), []
    try:
        ids = _validate(root, base, declarations, named=named, known=known, bound=bound, bound_at=bound_at)
    except (ValueError, KeyError) as exc:
        return set(), [f"spec-trailers: FAIL: invalid evidence withdrawal: {exc}"]
    return ids, []
