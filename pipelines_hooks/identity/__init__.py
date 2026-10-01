"""commit-identity: a commit's resolved author/committer must be on a configured allowlist.

The allowlist is configuration the consuming repository supplies (bounded,
versioned JSON of explicit ``{name, email}`` pairs; see
:mod:`pipelines_hooks.identity.allowlist`), never a value this package ships.
:mod:`pipelines_hooks.identity.commit_gate` checks the identity git would
resolve for a new commit right now; :mod:`pipelines_hooks.identity.range_gate`
re-walks a whole commit range the same way at push time and in CI, so a
bypassed or disabled commit-time hook cannot let a disallowed identity reach a
shared branch unexamined.
"""
