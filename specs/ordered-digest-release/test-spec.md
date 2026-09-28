# Test contract — PIPE-EH-247

Use public synthetic candidate manifests and CI/registry responses. Unit and workflow tests require no cluster or secrets; a real release supplies separate exact-run evidence.

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-1 | Valid A → B → C manifest validates source/digest fields. |
| N-1 | FR-1 | Duplicate, missing dependency, self edge, or cycle fails before publication. |
| N-2 | FR-1 | Floating tag, malformed digest, or provenance mismatch fails closed. |
| P-2 | FR-2 | Required exact-commit checks pass and mark only that candidate eligible. |
| N-3 | FR-2 | Missing, skipped, failed, or wrong-commit check blocks candidate and descendants. |
| P-3 | FR-3 | Stable order publishes A then B then C and records hosted CI. |
| N-4 | FR-3 | Failed predecessor CI prevents next push and retains partial receipt. |
| N-5 | FR-3 | Same-digest retry is idempotent; changed commit/digest cannot resume old receipt. |
| P-4 | FR-4 | Digest-pinned manifest exactly matches qualified mapping. |
| N-6 | FR-4 | Wrong or floating workload reference names workload and blocks readiness. |
| P-5 | FR-5 | Dry-run, parser, ordering, and negative tests run without infrastructure secrets. |

Contract tests inspect immutable workflow/action pins, source binding, least-privilege permissions, exact CI polling, and digest handoff. Real acceptance also records registry digest, hosted run IDs, reviewed consumer manifest commit, and deployment-owner runtime evidence. Run YAML, pytest, CCCC, jscpd, Dupehound, and KISS on implementation. Mocked tests never imply a green release.
