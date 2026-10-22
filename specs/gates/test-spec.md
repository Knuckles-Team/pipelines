# Test contract — PIPE-GATES

The tests live under `tests/hooks/` and run the published gate entry points, never a reimplementation.

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-001 | PIPE-GATES-R001 | Contract | The published gate configuration declaring all eight blocking gates. | The fast set is exactly `format`, `hygiene`, `secrets`, `types`, `tests-fast`. The full set is exactly the remaining three. The sets are disjoint and their union is the eight blocking gates. |
| T-002 | PIPE-GATES-R002 | Unit | A recorded product failure, no fix-forward task, and a re-run that passes or fails. | The decision is auto-revert. The record carries the gate ID, the changeset ID, the verdict, the failure class, the threshold, and the evidence digest. |
| T-003 | PIPE-GATES-R002 | Unit | A product failure with a fix-forward task inside 300 s, and an infrastructure failure whose re-run passes. | The decision is fix-forward in the first case and `infrastructure-rerun` in the second. Both records are complete and replayable. |
| T-004 | PIPE-GATES-R003 | Integration | One blocking gate on an engine-tree fixture and on an identical materialized checkout. | Both runs produce the same verdict and the same evidence digest. The tree run creates no checkout. |

## Negative and boundary cases

T-001 also fails a configuration missing one blocking gate or declaring a ninth. T-002 covers a task opened after the 300 s window, which auto-reverts, and an unavailable re-run, which auto-reverts and records the unavailability. T-003 covers a task opened at the window boundary, which auto-reverts, and an infrastructure failure whose re-run fails, which auto-reverts. An unknown failure class is refused. T-004 covers an empty prefix and a tree revision with no checkout available at all.

## Quality and release proof

Run `uv run --frozen python -m pytest -q` and the pre-commit and pre-push hook stages on the implementation. Record the revision, each command, and the pass or fail. A test in this repository is not served acceptance for the engine-side tree reads.

## Gate verdicts published to the engine

| Row | Proving test |
|---|---|
| `PIPE-GATES-R004` | See each child. |
| `PIPE-GATES-R004.1` | `tests/test_verdict_publish.py::test_gate_run_posts_one_verdict` |
| `PIPE-GATES-R004.2` | `tests/test_verdict_publish.py::test_fast_set_publishes_and_survives_endpoint_error` |
## Migration waves and the product-name check (R005, R006)

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-R006.1 | PIPE-GATES-R006.1 | Unit | A fixture migration ledger | `tests/hooks/test_migration_waves.py::test_wave_1_entry_and_exit` evaluates a fixture ledger and asserts each criterion. |
| T-R006.2 | PIPE-GATES-R006.2 | Unit | A fixture migration ledger | `test_wave_2_entry_and_exit` asserts the size bound and the per-repository exit. |
| T-R006.3 | PIPE-GATES-R006.3 | Unit | A fixture migration ledger | `test_wave_3_entry_and_exit` asserts the criteria. |
| T-R006.4 | PIPE-GATES-R006.4 | Unit | A fixture migration ledger | `test_wave_4_entry_and_exit` asserts the criteria. |
| T-R006.5 | PIPE-GATES-R006.5 | Unit | A fixture migration ledger | `test_wave_5_entry_and_exit` asserts the criteria. |
| T-R006.6 | PIPE-GATES-R006.6 | Unit | A fixture migration ledger | `test_wave_6_entry_and_exit` asserts the criteria. |
| T-R006.7 | PIPE-GATES-R006.7 | Unit | A fixture migration ledger | `test_wave_7_entry_and_exit` asserts the criteria and the two restores. |
| T-R005 | PIPE-GATES-R005 | Contract | Fixture spec trees with named products, identifiers and allowances | `tests/test_spec_third_party_names.py` asserts a finding for each named product, a pass for identifiers, code, links and standards, and the per-repository allowance. |

## Legacy concept migration (PIPE-GATES-R007)

`tests/hooks/test_no_legacy_concepts.py` runs the registered CLI and a subprocess entry point. Positive and adversarial fixtures assert the original regex across Python/Rust/Markdown, exact historical exclusions, tracked versus ignored/untracked input, and relative line diagnostics. Foreign worktrees with polluted repository and index selectors must still inspect the requested tree. Deleted files are absent source; unreadable files and unavailable repositories fail closed. `tests/hooks/test_catalogue.py` binds the same CLI to the published hook and manual self-run configuration. This optional migration invariant does not change the eight-gate landing partition.
