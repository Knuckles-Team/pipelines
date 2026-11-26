# Coverage evidence for proposal admission seam

Provider: pipelines PIPE-PAGES-R040.2 (mechanism: PIPE-GATES-R049)
Consumer: meristem MERISTEM-HARNESS-CYCLE-R001.13

## Wire shape

Proposal admission calls `pipelines-hook coverage-decrease --evidence FILE --proposal ID` (registered in `GATES` in `pipelines_hooks/cli.py`) with one evidence file that holds a baseline and a candidate measurement, each `{percent, revision, tool}`. The gate prints one JSON line with the proposal, both percentages and both revisions, and exits 0 only when the candidate is equal to or above the baseline and the baseline revision is an ancestor of the candidate revision.

## Refusal codes

- Exit 1: the candidate is below the baseline.
- Exit 2: a measurement or one of its fields is absent, or a revision does not resolve.
- Exit 1: the baseline revision is not an ancestor of the candidate revision.
- Exit 2: the gate cannot run, mapped by `run_gate` (`pipelines_hooks/cli.py:102`).

## Authoritative types

`CoverageEvidence` in `pipelines_hooks/code/coverage_decrease.py`. The admitting repository keeps the graph authorization and the materialization receipt; this gate stores neither.

## Test vectors

`tests/hooks/test_coverage_admission.py::test_planted_decrease_exits_one` and `tests/hooks/test_coverage_admission.py::test_missing_or_stale_evidence_fails_instead_of_passing`.
