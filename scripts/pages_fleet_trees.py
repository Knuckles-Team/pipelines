"""Read-only exact-commit provider for disposable, already fetched Git fixtures.

Layout: <fixture root>/<owner>/<repository>/<full commit>/.git. This provider
never fetches, checks out, executes consumer code, or writes to a consumer.
It proves local object identity, not public availability or fetch provenance.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from scripts.pages_fleet_declaration import ParityError, identity, object_git
from scripts.readiness.filesystem import _safe_existing_dir, _safe_existing_path, _safe_root


@dataclass(frozen=True)
class ExactTree:
    root: Path
    commit: str
    tree: str

    def clean(self) -> None:
        """Reject tracked changes and all untracked/ignored overlays."""
        if object_git(self.root, ["rev-parse", "HEAD"]).strip() != self.commit:
            raise ParityError("checkout-revision-mismatch")
        if object_git(self.root, ["status", "--porcelain", "--untracked-files=all", "--ignored"]):
            raise ParityError("tree-overlay")
        # Index flags can conceal worktree changes from ordinary git status.
        flags = object_git(self.root, ["ls-files", "-v"]).splitlines()
        if any(line[:1] != "H" for line in flags):
            raise ParityError("index-flags-unsupported")

    def read(self, relative: str) -> bytes:
        """Read exact Git blob bytes, rejecting filesystem and Git symlinks."""
        _safe_existing_path(self.root, relative, "asset")
        entry = object_git(self.root, ["ls-tree", self.commit, "--", relative])
        if not entry.startswith(("100644 blob ", "100755 blob ")):
            raise ParityError("asset-not-regular")
        oid = entry.split()[2]
        result = subprocess.run(
            ["git", "--no-replace-objects", "cat-file", "blob", oid], cwd=self.root,
            env=sanitized_env(), capture_output=True, check=False, timeout=30,
        )
        if result.returncode:
            raise ParityError("asset-unavailable")
        return result.stdout


def resolve(root: Path, reference: dict) -> ExactTree:
    """No sibling fallback, branch resolution, or reuse of another revision."""
    identity(reference)
    relative = f"{reference['repository']}/{reference['revision']}"
    directory = _safe_existing_dir(_safe_root(root), relative, "fixture")
    if Path(object_git(directory, ["rev-parse", "--show-toplevel"]).strip()) != directory:
        raise ParityError("fixture-not-repository-root")
    commit = reference["revision"]
    if object_git(directory, ["cat-file", "-t", commit]).strip() != "commit":
        raise ParityError("revision-not-commit")
    tree = object_git(directory, ["rev-parse", f"{commit}^{{tree}}"]).strip()
    result = ExactTree(directory, commit, tree)
    result.clean()
    return result


# External error text may contain credentials or private machine paths.
UNVERIFIED_ERRORS = (ParityError, CannotRun, ValueError, OSError, subprocess.SubprocessError)
