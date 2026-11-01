# Quickstart — PIPE-GATES

Run the gate proofs from a checkout of this repository.

## Scenario 1: partition and verdict publication

1. Run `uv run --frozen python -m pytest -q tests/hooks/test_gate_sets.py tests/hooks/test_gate_runner.py`.
2. Expect the fast set to hold exactly five gates and the full set to hold the other three.
3. Run `uv run --frozen python -m pytest -q tests/test_verdict_publish.py` once `PIPE-GATES-R004.1` lands. Expect one verdict record per gate and an unchanged verdict on an endpoint error.

## Scenario 2: the spec gates

1. Run `uv run --frozen python -m pytest -q tests/test_spec_standard.py tests/test_spec_completeness.py tests/test_spec_artifacts.py`.
2. Expect every finding to name its row or file.
3. Run `uv run --frozen pipelines-hook spec` in a spec-bearing repository. Expect exit 0 when every touched spec is complete.

## Scenario 3: contract coverage

1. Run `uv run --frozen python -m pytest -q tests/hooks/test_contract_coverage.py` once `PIPE-GATES-R034` lands.
2. Expect a citation of another repository's row without a contract to fail for a touched spec and warn for an untouched one.
