# Test contract — PIPE-GATES

The tests live under `tests/hooks/` and run the published gate entry points, never a reimplementation.

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-001 | PIPE-GATES-R001 | Contract | The published gate configuration declaring all eight blocking gates. | The fast set is exactly `format`, `hygiene`, `secrets`, `types`, `tests-fast`. The full set is exactly the remaining three. The sets are disjoint and their union is the eight blocking gates. |
| T-002 | PIPE-GATES-R002 | Unit | A recorded post-land failure, no fix-forward task, a failing second run. | The decision is auto-revert. The record carries the gate ID, the changeset ID, the verdict, the threshold, and the evidence digest. |
| T-003 | PIPE-GATES-R002 | Unit | A recorded post-land failure with a fix-forward task inside 300 s, and a failure whose second run passes. | The decision is fix-forward in the first case. No revert follows the passing rerun in the second. Both records are complete and replayable. |
| T-004 | PIPE-GATES-R003 | Integration | One blocking gate on an engine-tree fixture and on an identical materialized checkout. | Both runs produce the same verdict and the same evidence digest. The tree run creates no checkout. |

## Negative and boundary cases

T-001 also fails a configuration missing one blocking gate or declaring a ninth. T-002 covers a task opened after the 300 s window, which auto-reverts, and an unavailable second run, which auto-reverts and records the unavailability. T-003 covers a task opened at the window boundary and a second run that fails again, which auto-reverts. T-004 covers an empty prefix and a tree revision with no checkout available at all.

## Quality and release proof

Run `uv run --frozen python -m pytest -q` and the pre-commit and pre-push hook stages on the implementation. Record the revision, each command, and the pass or fail. A test in this repository is not served acceptance for the engine-side tree reads.

## Gate verdicts published to the engine

| Row | Proving test |
|---|---|
| `PIPE-GATES-R004` | See each child. |
| `PIPE-GATES-R004.1` | `tests/test_verdict_publish.py::test_gate_run_posts_one_verdict` |
| `PIPE-GATES-R004.2` | `tests/test_verdict_publish.py::test_fast_set_publishes_and_survives_endpoint_error` |
