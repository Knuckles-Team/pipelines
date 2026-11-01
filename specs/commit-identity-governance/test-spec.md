# Test contract — PIPE-IDENTITY

Use disposable Git fixture repositories with a pinned, synthetic allowlist configuration fixture. Assert exit status and the specific field named in a rejection. Never assert on or log the full configured allowlist. Every identity in a fixture is a synthetic `*.invalid` address, and each commit passes explicit `-c user.name=` and `-c user.email=` values, so no test depends on the identity of whoever runs the suite.

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-001 | PIPE-IDENTITY-R001.2: a well-formed, bounded allowlist loads and validates without error. |
| N-1 | FR-001 | PIPE-IDENTITY-R001.2: an empty, oversized or schema-invalid configuration is rejected before any commit is checked. |
| P-2 | FR-002 | PIPE-IDENTITY-R001.3: a commit whose resolved author and committer both match a configured entry is accepted. |
| N-2 | FR-002 | PIPE-IDENTITY-R001.3: a commit whose author or committer matches no entry is rejected, naming the mismatched field only. |
| P-3 | FR-003 | PIPE-IDENTITY-R001.4: a push whose full outgoing range matches the allowlist succeeds. |
| N-3 | FR-003 | PIPE-IDENTITY-R001.4: a push with one non-matching commit anywhere in the range is refused, even when the tip matches. |
| P-4 | FR-003 | PIPE-IDENTITY-R001.4: a CI run over a pull request range re-checks and accepts a fully matching range. |
| N-4 | FR-003 | PIPE-IDENTITY-R001.4: a CI run rejects a range with a non-matching commit even when the local check was bypassed. |
| N-5 | FR-004 | PIPE-IDENTITY-R001.5: a missing explicit allowlist fails closed (exit 2) in CI and prints a local skip naming the remedy outside CI. A malformed file always exits 2. |
| P-5 | FR-005 | PIPE-IDENTITY-R001.6 and PIPE-IDENTITY-R001.7: both gate ids resolve, and the published command rejects an off-list identity and accepts a clean range. |
| P-6 | FR-006 | PIPE-IDENTITY-R001.1: a range committed under an allowlisted service identity passes exactly as one under the owner identity. |
| N-6 | FR-006 | PIPE-IDENTITY-R001.1: a range committed under a service identity absent from the allowlist is refused in CI. |

Run the repository's YAML parse, the relevant pytest files and the configured complexity, duplication and KISS gates on the implementation. Record an unavailable scanner as a gap, never as a pass.
