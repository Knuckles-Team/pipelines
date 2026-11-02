# Quickstart — PIPE-IDENTITY

Run the identity proofs from a checkout of this repository.

## Scenario 1: an off-list identity is rejected

1. Run `uv run --frozen python -m pytest -q tests/hooks/test_identity_commit.py tests/hooks/test_identity_wiring.py`.
2. Expect the published `commit-identity` command to exit 1 and name only the failing field.

## Scenario 2: the whole range is re-checked

1. Run `uv run --frozen python -m pytest -q tests/hooks/test_identity_range.py tests/hooks/test_identity_fork_exemption.py`.
2. Expect one off-list commit buried in a range to fail the range, and a fork pull request to be exempt.

## Scenario 3: the platform identity gets no exemption

1. Run `uv run --frozen python -m pytest -q tests/hooks/test_identity_range.py -k service_identity` once `PIPE-IDENTITY-R001.1` lands.
2. Expect a listed service identity to pass and an unlisted one to be refused.
