"""commit-identity-range: every commit in the outgoing/incoming range is allowlisted.

Re-walks ``base..HEAD`` (the remote revision pre-commit is pushing over, else
``origin/main``, else the whole history --
:func:`pipelines_hooks.core.baseref.upstream_base`) through the identical
allowlist check ``commit-identity`` applies at commit time, so a commit made
before the allowlist existed, or made with a bypassed or skipped local hook,
is still caught here, and independently again when CI re-runs this same gate
over the full incoming range. Only the failing commit and field are named; the
configured allowlist is never echoed back.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pipelines_hooks.core.baseref import upstream_base
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.identity.allowlist import Identity, matches, resolved_allowlist
from pipelines_hooks.identity.resolve import CommitIdentity, range_identities


def _rejected_field(commit: CommitIdentity, identities: tuple[Identity, ...]) -> str | None:
    if not matches(commit.author.name, commit.author.email, identities):
        return "author"
    if not matches(commit.committer.name, commit.committer.email, identities):
        return "committer"
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="commit-identity-range", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--allowlist", type=Path, default=None, help="override the configured allowlist path")
    parser.add_argument("--base", default=None, help="base revision (default: see module docstring)")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    identities = resolved_allowlist(root, args.allowlist)
    commits = range_identities(root, upstream_base(root, args.base))
    failures = [(commit.sha[:12], _rejected_field(commit, identities)) for commit in commits]
    named = [(sha, field) for sha, field in failures if field]
    if named:
        for sha, field in named:
            print(f"commit-identity-range: FAIL: {sha} {field} identity is not on the configured allowlist")
        return 1
    print(f"commit-identity-range: OK: {len(commits)} commit(s) allowed")
    return 0
