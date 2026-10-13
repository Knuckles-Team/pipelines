# PIPE-VALIDATION — Shared validation

Status: PROPOSED. Owner: pipelines.

## Purpose and scope

Contributors run `pipelines-hook validate` to get one bounded report for declared
repository checks. Pipelines owns dispatch and reporting. Consumers declare
checks in `.config/validation.toml`. Version 1 supports the existing offline
repository hygiene gates; it does not migrate unrelated acceptance requirements.

## Requirements and acceptance

The [requirements](requirements.md) define strict policy loading, passive Git
events, required outcomes, deadlines, evidence, and acceptance preservation.
The command never installs dependencies. Missing prerequisites block required
validation. Each result distinguishes pass, fail, unavailable, and timeout.

## Traceability

See [plan.md](plan.md) and [test-spec.md](test-spec.md). Test and publication
evidence remains pending until executed and recorded.
