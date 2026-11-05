# Coverage evidence for proposal admission seam

Provider: pipelines PIPE-PAGES-R040.2
Consumer: meristem MERISTEM-HARNESS-CYCLE-R001.13

## Wire shape

Proposal admission calls `pipelines-hook coverage-baseline` (planned, registered in `GATES` at `pipelines_hooks/cli.py:13`) with one evidence file that holds `{proposal, revision, baseline, candidate}`. The gate prints one JSON line `{proposal, revision, baseline, candidate, verdict}` and exits 0 only when the candidate is equal to or above the baseline and the evidence revision equals the proposal revision.

## Refusal codes

- Exit 1: the candidate is below the baseline.
- Exit 1: a measurement is absent, or the evidence revision differs from the proposal revision.
- Exit 2: the gate cannot run, mapped by `run_gate` (`pipelines_hooks/cli.py:102`).

## Authoritative types

`CoverageEvidence` in `pipelines_hooks/validation/coverage_baseline.py` (planned). The admitting repository keeps the graph authorization and the materialization receipt; this gate stores neither.

## Test vectors

Planned `tests/test_coverage_baseline.py::test_planted_decrease_exits_one` and `tests/test_coverage_baseline.py::test_missing_or_stale_evidence_fails_instead_of_passing`.
