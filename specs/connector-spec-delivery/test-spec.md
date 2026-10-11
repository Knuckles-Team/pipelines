# Test contract — PIPE-CONNSPEC-001

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-1 | The files named in PIPE-CONNSPEC-R001 to PIPE-CONNSPEC-R005 exist in this repository and the reference workflows call the reusable Pages workflow. |
| P-2 | FR-2 | For each connector, the check in each child requirement passes on its default branch. |
| N-1 | FR-2 | A connector missing any child is reported as SPECIFIED by the rollup, never as complete. |
| PIPE-CONNSPEC-R006 | `test_moved_retired_identity_uses_shared_status_parser` | A retired historical ID passes; two active misleading-prose variants fail. |

PIPE-CONNSPEC-R001 is also bound by tests/hooks/test_spec_landing_attribution.py: explicit declarations retain the actual commit SHA; pending siblings, prose-only mentions and none exemption reasons do not land. Range, shorthand and multiple-trailer cases remain supported. Existing spec-status tests retain legacy receipt idempotence and revert coverage.
