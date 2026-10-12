# Test contract — PIPE-RELEASE

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

## Kernel wheel completeness and dependency loops

`tests/test_wheel_kernel_completeness.py::test_release_bundle_blocks_missing_kernel_wheel` must fail the bundle when a platform wheel is absent. `tests/hooks/test_dependency_cycles.py::test_supply_chain_hook_blocks_dependency_loop` must exit 1 on a group loop.

## Project version consistency

| ID | Requirement | Test and expected result |
|---|---|---|
| T-PIPE-RELEASE-R006.1 | PIPE-RELEASE-R006.1 | Run `test_project_version_inventory` in `tests/hooks/test_project_version_sync.py`. Accept a complete three-role inventory; reject unknown roles, duplicate locations and missing role coverage. |
| T-PIPE-RELEASE-R006.2 | PIPE-RELEASE-R006.2 | Run `test_project_version_values` in `tests/hooks/test_project_version_sync.py`. Equal values pass; independently changing metadata, source, documentation or canonical current version fails at the exact location. |
| T-PIPE-RELEASE-R006.3 | PIPE-RELEASE-R006.3 | Run `test_project_version_hook_wiring` in `tests/hooks/test_project_version_sync.py`. The installed CLI and published hook select the same snapshot and fail on an inconsistent unchanged declared surface. |
| T-PIPE-RELEASE-R006.4 | PIPE-RELEASE-R006.4 | Run `test_project_version_refusals` in `tests/hooks/test_project_version_sync.py`. Missing, malformed or competing configs and ambiguous extraction exit 2; mismatches exit 1 and cannot produce a passing receipt. |
| T-PIPE-RELEASE-R006.5 | PIPE-RELEASE-R006.5 | Run `test_project_version_evidence` in `tests/hooks/test_project_version_sync.py`. Evidence identifies the exact checked Git bytes and all three roles; unchecked cases have no successful verdict. |
| T-PIPE-RELEASE-R006.6 | PIPE-RELEASE-R006.6 | Run `test_project_version_sync_cli` in `tests/hooks/test_project_version_sync.py`. Assert real dispatcher/hook exit codes, exact locations, snapshot isolation, all-surface bumping and unchanged caller files during gate checks. |
