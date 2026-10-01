"""commit-identity: the commit about to be made has an allowlisted author and committer.

Reads the identity git itself resolves for a NEW commit right now (``git var
GIT_AUTHOR_IDENT``/``GIT_COMMITTER_IDENT`` through
:mod:`pipelines_hooks.identity.resolve`), never an ambient environment
selector, and rejects the commit when either does not match an entry in the
configured allowlist (:mod:`pipelines_hooks.identity.allowlist`), naming only
the failing field. A bypassed or disabled local hook cannot widen what reaches
a shared branch: ``commit-identity-range`` independently re-examines the full
outgoing/incoming commit range at push time and in CI.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root, staged_paths
from pipelines_hooks.identity.allowlist import Identity, matches, resolved_allowlist
from pipelines_hooks.identity.resolve import pending_identity


def _rejected_field(author: Identity, committer: Identity, identities: tuple[Identity, ...]) -> str | None:
    if not matches(author.name, author.email, identities):
        return "author"
    if not matches(committer.name, committer.email, identities):
        return "committer"
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="commit-identity", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--allowlist", type=Path, default=None, help="override the configured allowlist path")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    if not staged_paths(root):
        print("commit-identity: OK: nothing staged")
        return 0
    identities = resolved_allowlist(root, args.allowlist)
    author, committer = pending_identity(root)
    field = _rejected_field(author, committer, identities)
    if field:
        print(f"commit-identity: FAIL: the {field} identity is not on the configured allowlist")
        return 1
    print("commit-identity: OK: author and committer identity allowed")
    return 0
