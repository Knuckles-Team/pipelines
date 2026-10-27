# Test contract — PIPE-CONNSPEC

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-1 | The files named in PIPE-CONNSPEC-R001 to PIPE-CONNSPEC-R005 exist in this repository and the reference workflows call the reusable Pages workflow. |
| P-2 | FR-2 | For each connector, the check in each child requirement passes on its default branch. |
| N-1 | FR-2 | A connector missing any child is reported as SPECIFIED by the rollup, never as complete. |
| PIPE-CONNSPEC-R006 | `test_moved_retired_identity_uses_shared_status_parser` | A retired historical ID passes; two active misleading-prose variants fail. |

PIPE-CONNSPEC-R001 is also bound by tests/hooks/test_spec_landing_attribution.py: explicit declarations retain the actual commit SHA; pending siblings, prose-only mentions and none exemption reasons do not land. Range, shorthand and multiple-trailer cases remain supported. Existing spec-status tests retain legacy receipt idempotence and revert coverage.

PIPE-CONNSPEC-R001 also binds tests/hooks/test_spec_repository_identity.py: remote ownership corrects stale worktree names for new and legacy status files, live receipts survive migration and regeneration, and absent or ambiguous remotes retain safe fallback behavior.

PIPE-CONNSPEC-R001 also binds `test_verified_rollup_carries_its_childrens_evidence` in tests/hooks/test_spec_status.py. A rollup that reaches VERIFIED names its children's landing commits and bound tests. A LANDED rollup names their landing commits.

PIPE-CONNSPEC-R001 is also bound by the pending-merge tests in tests/hooks/test_spec_status.py. They assert actual landing SHAs and test bindings from both parents, exclude the `Spec: none` exemption and synthetic context from evidence, preserve HEAD/index/MERGE_HEAD, cover explicit-head use even with unresolved conflicts, and fail closed for default unresolved or worktree/index-mismatch cases.

## Requirement state read from the engine

| Row | Proving test |
|---|---|
| `PIPE-CONNSPEC-R009` | See each child. |
| `PIPE-CONNSPEC-R009.1` | `tests/hooks/test_engine_state.py::test_difference_names_rows` |
| `PIPE-CONNSPEC-R009.2` | `tests/hooks/test_engine_state.py::test_generator_and_engine_agree` |

PIPE-CONNSPEC-R011 binds tests/hooks/test_spec_standard_aliases.py: exact renumbering preserves historical landings and test bindings; historical and current trailer ranges pass. Active or retired source rows (including retired-first active duplicates), missing or retired targets, prose-only targets, chains, cycles and prefix collisions refuse. Unbound targets and unknown trailers still fail. Unlisted children do not inherit an exact alias. Existing alias tests continue to pass.

PIPE-CONNSPEC-R012 binds tests/hooks/test_goal_priority.py: Row-level Depends-on.
PIPE-CONNSPEC-R013 binds tests/hooks/test_goal_priority.py: Priority from competency questions.
PIPE-CONNSPEC-R014 binds tests/hooks/test_goal_priority.py: Priority, frontier, and unserved from the organization aggregate.
PIPE-CONNSPEC-R015 binds tests/hooks/test_goal_priority.py: Derived release bundles.
PIPE-CONNSPEC-R016 binds tests/test_architecture_delivery.py: Architecture page delivery views.
