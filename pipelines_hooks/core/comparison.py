"""Choose an index or committed-range comparison for staged gates."""

from __future__ import annotations

import re
from pathlib import Path

from pipelines_hooks.core.baseref import ZERO_SHA, commit
from pipelines_hooks.core.bounded_json import read_bounded_json
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, has_head, nul_split, staged_paths
from pipelines_hooks.core.settings import setting


def _event_value(payload: object, event: str) -> object:
    """The PR base SHA or the push ``before`` SHA; a malformed payload raises ``KeyError``."""
    path = ("pull_request", "base", "sha") if event == "pull_request" else ("before",)
    value = payload
    for key in path:
        if not isinstance(value, dict):
            raise KeyError(key)
        value = value[key]
    return value


def _event_base() -> str:
    event = setting("GITHUB_EVENT_NAME")
    if event == "workflow_dispatch":
        return ZERO_SHA
    if event not in {"pull_request", "push"}:
        raise CannotRun("CI comparison needs a PR/push/manual event or --base-ref")
    path = setting("GITHUB_EVENT_PATH")
    if not path:
        raise CannotRun("CI comparison needs GITHUB_EVENT_PATH or --base-ref")
    try:
        payload = read_bounded_json(Path(path), 2 * 1024 * 1024, what="GitHub event payload", error=CannotRun)
        value = _event_value(payload, event)
    except (OSError, UnicodeError, KeyError, TypeError) as exc:
        raise CannotRun("CI comparison needs a readable PR/push base or --base-ref") from exc
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
        raise CannotRun("CI comparison needs a PR/push base SHA or --base-ref")
    if event == "pull_request" and value == ZERO_SHA:
        raise CannotRun("CI pull-request comparison needs a nonzero base SHA")
    return value


def _required_commit(root: Path, ref: str) -> str:
    base = commit(root, ref)
    if base is None:
        raise CannotRun(f"base ref {ref!r} does not resolve; fetch the base commit before this gate")
    return base


def _ci_base(root: Path) -> str | None:
    requested = _event_base()
    if requested != ZERO_SHA:
        return _required_commit(root, requested)
    # A new ref or manual run has no incoming range. Check the last commit.
    if git_text(root, ("rev-parse", "--is-shallow-repository")).strip() == "true":
        raise CannotRun("CI last-commit comparison needs full history; fetch before this gate")
    return commit(root, "HEAD^")


def comparison(root: Path, explicit: str | None = None) -> tuple[list[str], str | None, str]:
    """Return changed paths and before/after blob prefixes; empty means index."""
    staged = staged_paths(root)
    base: str | None
    if explicit:
        base = _required_commit(root, explicit)
    elif setting("GITHUB_EVENT_NAME"):
        base = _ci_base(root)
    elif staged or not setting("PRE_COMMIT_FROM_REF"):
        return staged, "HEAD" if has_head(root) else None, ""
    else:
        base = _required_commit(root, setting("PRE_COMMIT_FROM_REF"))
    args = (
        ("diff", "--name-only", "-z", "--diff-filter=ACMR", base, "HEAD", "--")
        if base
        else ("ls-tree", "-r", "--name-only", "-z", "HEAD")
    )
    return sorted(set(nul_split(git_text(root, args)))), base, "HEAD"


def rename_sources(root: Path, before: str | None, after: str) -> dict[str, str]:
    """Map each renamed path to its source path in the comparison (``git diff -M``).

    A renamed file is compared with its source, so a pure rename or a small edit
    to a moved file reports only what changed instead of the whole file as new.
    """
    if before is None:
        return {}
    args = (
        ("diff", "--cached", "-M", "--name-status", "-z", "--diff-filter=R", before, "--")
        if not after
        else ("diff", "-M", "--name-status", "-z", "--diff-filter=R", before, after, "--")
    )
    fields = nul_split(git_text(root, args, preserve_index=not after))
    sources: dict[str, str] = {}
    for index in range(0, len(fields) - 2, 3):
        status, old, new = fields[index : index + 3]
        if status.startswith("R"):
            sources[new] = old
    return sources
