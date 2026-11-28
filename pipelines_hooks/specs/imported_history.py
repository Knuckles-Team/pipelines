"""Imported-history boundary for ``spec-trailers`` (PIPE-CONNSPEC-R001.3).

A repository extracted from another one with its history carries commits whose
``Spec:`` trailers cite rows of the source repository. Those commits were gated
there, and an alias can only target a local row, so they are not re-gated here.

The repository declares each boundary in ``pyproject.toml``::

    [tool.pipelines_hooks.spec_trailers]
    imported_history = [
        { merge = "<40-hex sha>", parent = "<40-hex sha>", source = "<owner/repo>" },
    ]

The gate drops every commit reachable from a declared imported parent. The merge
commit itself and everything after it stay in the range. Validation fails closed
with a stable code, and there is no wildcard form and no way to name a local commit.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, run_git

_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")
_KEYS = frozenset({"merge", "parent", "source"})


@dataclass(frozen=True)
class Boundary:
    """One validated imported-history boundary."""

    merge: str
    parent: str
    source: str


def _refuse(code: str, detail: str) -> CannotRun:
    return CannotRun(f"{code}: {detail}")


def _resolve(root: Path, sha: str, what: str) -> str:
    result = run_git(root, ("rev-parse", "--verify", "-q", "--end-of-options", f"{sha}^{{commit}}"))
    if result.returncode != 0 or (result.stdout or "").strip() != sha:
        raise _refuse("IMPORT_BOUNDARY_UNKNOWN", f"{what} {sha} is not a commit in this repository")
    return sha


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return run_git(root, ("merge-base", "--is-ancestor", ancestor, descendant)).returncode == 0


def _entry(raw: object) -> tuple[str, str, str]:
    if not isinstance(raw, Mapping) or set(raw) != _KEYS:
        raise _refuse("IMPORT_BOUNDARY_INVALID", "each entry needs exactly merge, parent and source")
    merge, parent, source = (raw[key] for key in ("merge", "parent", "source"))
    if not (isinstance(merge, str) and isinstance(parent, str) and _SHA.fullmatch(merge) and _SHA.fullmatch(parent)):
        raise _refuse("IMPORT_BOUNDARY_INVALID", "merge and parent must be full lowercase commit ids")
    if not isinstance(source, str) or not _SOURCE.fullmatch(source):
        raise _refuse("IMPORT_BOUNDARY_INVALID", "source must be <owner>/<repo>")
    return merge, parent, source


def _validate(root: Path, merge: str, parent: str, source: str) -> Boundary:
    _resolve(root, merge, "merge")
    _resolve(root, parent, "parent")
    if not _is_ancestor(root, merge, "HEAD"):
        raise _refuse("IMPORT_BOUNDARY_UNKNOWN", f"merge {merge} is not in the history of HEAD")
    parents = git_text(root, ("rev-list", "--parents", "-n", "1", merge)).split()[1:]
    if len(parents) < 2:
        raise _refuse("IMPORT_BOUNDARY_NOT_MERGE", f"{merge} is not a merge commit")
    if parent not in parents:
        raise _refuse("IMPORT_BOUNDARY_NOT_PARENT", f"{parent} is not a parent of merge {merge}")
    if parent == parents[0]:
        raise _refuse(
            "IMPORT_BOUNDARY_NOT_IMPORTED", f"{parent} is the first parent of {merge}, which is local history"
        )
    # Imported history must be unrelated to the local line, so no local commit is reachable from it.
    if run_git(root, ("merge-base", parents[0], parent)).returncode != 1:
        raise _refuse("IMPORT_BOUNDARY_NOT_IMPORTED", f"{parent} shares history with the first parent of {merge}")
    return Boundary(merge=merge, parent=parent, source=source)


def load_boundaries(root: Path) -> tuple[Boundary, ...]:
    """The repository's validated boundaries; any invalid entry refuses the whole run."""
    entries = load_config(root).section("spec_trailers").get("imported_history", [])
    if not isinstance(entries, list):
        raise _refuse("IMPORT_BOUNDARY_INVALID", "imported_history must be a list of tables")
    return tuple(_validate(root, *_entry(raw)) for raw in entries)
