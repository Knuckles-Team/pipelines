# PIPE-VALIDATION — Shared validation

Owner: pipelines. Cross-repo IDs: none.
Public provenance: the [spec standard](../../reference/spec-standard.md) and the [gate standard](../../reference/gate-standard.md).

## Delivery mapping

Component: Validation

Code: ../../pipelines_hooks/validation/policy.py ../../pipelines_hooks/validation/runner.py ../../pipelines_hooks/validation/cli.py

## User Scenarios & Testing

### User Story 1 - One bounded report for declared checks (Priority: P1)

A contributor runs `pipelines-hook validate` and gets one bounded report for the repository checks the repository declares. The command never installs a dependency, and a missing prerequisite blocks a required check instead of passing it.

**Acceptance Scenarios**:

1. **Given** a policy that declares two offline checks, **When** `validate` runs, **Then** each check runs once in an isolated subprocess and the report shows pass, fail, unavailable or timeout for each.
2. **Given** a required check that times out, **When** the run ends, **Then** the exit code is 2 and the report names the check and the elapsed time.
3. **Given** an advisory check that fails, **When** the run ends, **Then** the exit code stays 0 and the summary still shows the finding.

### User Story 2 - Connector repositories use the shared standard (Priority: P2)

A connector maintainer keeps no copy of the shared files. The `connector-standard` hook flags a committed copy, runs the shared spelling, security and parity checks, and the reference configuration names only published hooks.

**Acceptance Scenarios**:

1. **Given** a connector that tracks `scripts/bootstrap.sh`, **When** `connector-standard` runs, **Then** it reports a finding that names the replacement.
2. **Given** a client method that no MCP tool calls, **When** `connector-api-parity` runs, **Then** it lists the unmapped method and fails below the declared baseline.

### Edge Cases

- A passive Git event (post-merge, post-checkout, post-rewrite) returns an inactive result and loads no policy.
- An unknown policy key, a duplicate check ID or an unsupported gate is refused before dispatch.
- SIGTERM or SIGINT during a run terminates the worker group and keeps the signal exit code.
- A display name that is the only source of a candidate passes only outside attribution context.

## Requirements

- **FR-001**: Load a strict policy and run each declared check within a deadline, reporting required and advisory outcomes. Rows: `PIPE-VALIDATION-R001.1`, `PIPE-VALIDATION-R001.2`, `PIPE-VALIDATION-R001.3`, `PIPE-VALIDATION-R001.4`, `PIPE-VALIDATION-R001.5`.
- **FR-002**: Retain the Meristem ignore acceptance in the shared gitignore checker. Rows: `PIPE-VALIDATION-R001.6`.
- **FR-003**: Provide the connector standard files and checks instead of copies. Rows: `PIPE-VALIDATION-R001.7`, `PIPE-VALIDATION-R001.8`, `PIPE-VALIDATION-R001.9`, `PIPE-VALIDATION-R001.10`, `PIPE-VALIDATION-R001.11`, `PIPE-VALIDATION-R001.12`.
- **FR-004**: Match a Git display name only in identity fields or explicit attribution. Rows: `PIPE-VALIDATION-R002`.

## Success Criteria

- **SC-001**: A required failure, an unavailable prerequisite or a timeout exits non-zero in every run. Rows: `PIPE-VALIDATION-R001.3`.
- **SC-002**: A run ends within its declared run budget and leaves no worker process. Rows: `PIPE-VALIDATION-R001.4`.

## Assumptions

- Version 1 admits only `root-hygiene`, `gitignore-convergence` and `sprawl`; these gates read local source and Git state.
- Consumers keep their reviewed pre-commit stage policy; the command installs no Git hook.
- A bare personal name outside attribution may pass when Git supplied the only source, a tradeoff the owner approved before implementation.

## Why a new spec

The search covered `specs/gates` and `specs/connector-spec-delivery`. `PIPE-GATES` states each gate and the landing policy. `PIPE-CONNSPEC` states the connector rollout. Neither owns the bounded `validate` command, its policy file or the connector standard checks, so this spec owns them.

## Scope and interfaces

Pipelines owns dispatch and reporting. Consumers declare checks in `.config/validation.toml`. Version 1 does not migrate unrelated acceptance requirements. Non-goals: installing dependencies, registering post-merge, post-checkout or post-rewrite hooks, and network access.

## Traceability

| Label | Rows | Design section | Test ID | Evidence |
|---|---|---|---|---|
| FR-001 | `PIPE-VALIDATION-R001.1`, `PIPE-VALIDATION-R001.2`, `PIPE-VALIDATION-R001.3`, `PIPE-VALIDATION-R001.4`, `PIPE-VALIDATION-R001.5` | [Design](plan.md#phase-1-design) | T-001 | report and exit code |
| FR-002 | `PIPE-VALIDATION-R001.6` | [Design](plan.md#phase-1-design) | T-002 | ignore acceptance fixtures |
| FR-003 | `PIPE-VALIDATION-R001.7` | [Design](plan.md#phase-1-design) | T-003 | connector findings |
| FR-004 | `PIPE-VALIDATION-R002` | [Design](plan.md#phase-1-design) | T-004 | privacy CLI output |

Requirement IDs are defined in [requirements.md](requirements.md).
