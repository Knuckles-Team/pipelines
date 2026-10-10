"""PR-mode scoping for spec-status: which spec dirs a branch actually touches.

With 10+ parallel PR lanes, another lane's landing on ``main`` regenerates
*other* specs' ``status.json``, so a full-repo check fails every open PR on
every unrelated landing. This narrows a check/write to only the spec dirs a
branch touches since a base: a changed ``specs/<dir>/`` path, or a commit
whose ``Spec:`` trailer names an ID that dir owns. Untouched dirs are
skipped. See :mod:`pipelines_hooks.specs.status` for the ``--changed-only``
CLI surface and the full-repo mode it stays the default for.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.baseref import upstream_base
from pipelines_hooks.core.gitenv import git_text, nul_split
from pipelines_hooks.core.settings import setting
from pipelines_hooks.specs.requirements_doc import parse_rows
from pipelines_hooks.specs.trailer_ids import TRAILER_JOIN, named_ids


def _id_owners(root: Path) -> dict[str, str]:
    """Every requirement ID's owning spec dir, from the current requirements.md files."""
    owners: dict[str, str] = {}
    for requirements_path in sorted(root.glob("specs/*/requirements.md")):
        for row in parse_rows(requirements_path.read_text(encoding="utf-8")):
            owners[row.id] = requirements_path.parent.name
    return owners


def touched_spec_dirs(root: Path, base: str) -> set[str]:
    """Spec dir names this branch touches since ``base``.

    A dir is touched by a changed ``specs/<dir>/`` path (``git diff
    --name-only base...HEAD``), or by a commit in ``base..HEAD`` whose
    ``Spec:`` trailer names a requirement ID that dir owns.
    """
    changed = nul_split(git_text(root, ("diff", "--name-only", "-z", f"{base}...HEAD")))
    dirs = {
        parts[1]
        for path in changed
        for parts in (Path(path).parts,)
        if len(parts) > 1 and parts[0] == "specs"
    }
    merge_base = git_text(root, ("merge-base", base, "HEAD")).strip()
    raw = git_text(
        root,
        (
            "log",
            "--no-merges",
            f"--format=%(trailers:key=Spec,valueonly,separator={TRAILER_JOIN})",
            f"{merge_base}..HEAD",
        ),
    )
    owners = _id_owners(root)
    dirs |= {owners[rid] for rid in named_ids(raw.splitlines()) if rid in owners}
    return dirs


def scope_to_changed(
    root: Path, generated: dict[Path, dict], base_ref: str | None
) -> tuple[dict[Path, dict], str]:
    """``generated`` narrowed to touched dirs, plus a human-readable scope note."""
    base = upstream_base(root, base_ref)
    if base is None:
        return generated, " (--changed-only requested, but no base resolved: full-repo scope)"
    touched = touched_spec_dirs(root, base)
    scoped = {path: document for path, document in generated.items() if path.parent.name in touched}
    return scoped, f" ({len(touched)} spec dir(s) touched since {base[:12]})"


def wants_changed_only(arguments: argparse.Namespace) -> bool:
    """Explicit ``--changed-only``, or auto-enabled for a hosted pull_request job."""
    return arguments.changed_only or setting("GITHUB_EVENT_NAME") == "pull_request"


def apply_changed_only(
    root: Path, generated: dict[Path, dict], arguments: argparse.Namespace
) -> tuple[dict[Path, dict], str]:
    """``generated``, scoped to touched dirs when PR mode is wanted; otherwise unchanged."""
    if not wants_changed_only(arguments):
        return generated, ""
    return scope_to_changed(root, generated, arguments.base_ref)
