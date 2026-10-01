# Test contract — PIPE-IDENTITY-001

Use disposable Git fixture repositories with a pinned, synthetic allowlist configuration fixture.
Assert exit status and the specific field named in a rejection; never assert on or log the full
configured allowlist.

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-1 | A well-formed, bounded allowlist configuration loads and validates without error. |
| N-1 | FR-1 | An empty, oversized, or schema-invalid configuration is rejected before any commit is checked. |
| P-2 | FR-2 | A commit whose resolved author and committer both match a configured entry is accepted. |
| N-2 | FR-2 | A commit whose resolved author or committer matches no configured entry is rejected, naming the mismatched field only. |
| P-3 | FR-3 | A push whose full outgoing commit range matches the configured allowlist succeeds. |
| N-3 | FR-3 | A push containing one non-matching commit anywhere in the outgoing range is refused, even when the branch tip itself matches. |
| P-4 | FR-4 | A CI run over a pull request range independently re-checks and accepts a fully matching range. |
| N-4 | FR-4 | A CI run rejects a range containing a non-matching commit even when the local pre-push check was skipped or bypassed for that commit. |
| N-5 | FR-5 | A missing or unreadable allowlist configuration fails closed (exit 2) in CI and prints a local skip naming the remedy command outside CI, rather than passing every identity. |

Contract tests use fixture git repositories built with `pipelines_hooks.core.gitenv`-style sanitized
invocations (explicit `-c user.name=`/`-c user.email=` per commit) rather than the ambient local git
identity, so test fixtures never depend on, assert on, or log the real identity of whoever runs the
suite. Run the repository's YAML parse, relevant pytest, and configured CCCC/jscpd/Dupehound/KISS
gates on the implementation. Record an unavailable scanner as a gap, never as a pass.
