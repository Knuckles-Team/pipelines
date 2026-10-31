# PIPE-RELEASE — Dependency-ordered digest release orchestration

Owner: pipelines. Cross-repo IDs: `ARBORA-ACCEPTANCE-R006.7`, `MEDULLA-SDLC-R014.7`, `MEDULLA-SDLC-R018`.
Public provenance: [arbora dependency-ordered release](https://github.com/Knuckles-Team/arbora/tree/main/specs/dependency-ordered-release).

## Delivery mapping

Component: Release

Depends-on: ARBORA-ACCEPTANCE-R006

## User Scenarios & Testing

### User Story 1 - Promote in dependency order (Priority: P1)

A release operator promotes a qualified set of repositories in dependency order. Every deployed image binds to an immutable digest. A contributor reproduces ordering and refusal logic from public workflow contracts and fixtures without a cluster.

**Acceptance Scenarios**:

1. **Given** candidates A, B and C with valid receipts, **When** the dry run orders them, **Then** the order is A, B, C.
2. **Given** a missing digest, floating tag, failed CI, cycle or consumer mismatch, **When** publication starts, **Then** downstream publication stops with a precise refusal.
3. **Given** an interrupted stage, **When** it re-runs, **Then** it does not republish a completed digest or change the commit.

### User Story 2 - Plan a release from the dependency graph (Priority: P2)

A release planner reads a computed plan for each bundle. The plan lists rows per repository, the dependency closure, the derived train order, the scenario and the open tasks. The engine graph holds the same plan.

**Acceptance Scenarios**:

1. **Given** a bundle across two projects, **When** the plan renders, **Then** the train order is topological and no repository name is hard-coded.
2. **Given** a dependency cycle across bundles, **When** the plan renders, **Then** it refuses with `BUNDLE_CYCLE` and names the cycle.

### User Story 3 - Reach the program exit gates (Priority: P3)

A program owner reads one table of exit gates. Each gate names its owning rows and its phase. The final gate holds only when all gates hold.

**Acceptance Scenarios**:

1. **Given** the plan table, **When** `--exit-gates` runs, **Then** every row and phase resolves.
2. **Given** a connector row that is not delivered, **When** the final gate runs, **Then** it fails and lists the row.

### Edge Cases

- A candidate with a floating tag must fail before any publication effect.
- A skipped mandatory result blocks the candidate and its descendants.
- A plan with a cycle must write no partial output.

## Requirements

- **FR-001**: Accept a versioned public candidate manifest and reject cycles, missing dependencies, duplicates and floating tags. Rows: `PIPE-RELEASE-R001`.
- **FR-002**: Require recorded build, test and consumer results at each exact commit. Rows: `PIPE-RELEASE-R002`.
- **FR-003**: Publish one dependency stage at a time in a deterministic order, and stop on failure. Rows: `PIPE-RELEASE-R001`.
- **FR-004**: Release scope and delivery are computed from bundles. Rows: `PIPE-RELEASE-R020`, `PIPE-RELEASE-R021`, `PIPE-RELEASE-R022`.
- **FR-005**: The release plan derives from the dependency graph. Rows: `PIPE-RELEASE-R025`, `PIPE-RELEASE-R025.2`.
- **FR-006**: Program exit gates are plan sections with owning rows. Rows: `PIPE-RELEASE-R026`, `PIPE-RELEASE-R026.1`.

## Success Criteria

- **SC-001**: No downstream stage runs before each predecessor qualifies at its exact revision. Rows: `PIPE-RELEASE-R001`.
- **SC-002**: Equal bundle inputs give an equal plan document. Rows: `PIPE-RELEASE-R025.4`.
- **SC-003**: Every exit gate row in the plan table resolves to a defined row. Rows: `PIPE-RELEASE-R026.4`.

## Assumptions

- Public candidate manifests carry the fields the rows name.
- Live rollout acceptance remains with the deployment owners.

## Why a new spec

This spec predates the extension rules and owns release orchestration. The plan and exit-gate rows extend it. No other spec owns release planning.

## Scope and interfaces

Pipelines owns generic workflow ordering, verification, the receipt schema and the reusable build and publish actions. Product repositories own build inputs and source quality. [Arbora dependency-ordered release](https://github.com/Knuckles-Team/arbora/tree/main/specs/dependency-ordered-release) consumes the candidate manifest and owns rollout, readiness probes and rollback. Pipelines never applies runtime stages.

## Traceability

| Label | Rows | Design section | Test ID | Evidence |
|---|---|---|---|---|
| FR-001 | `PIPE-RELEASE-R001` | [Candidate model](plan.md#candidate-model) | P-1, N-1, N-2 | |
| FR-002 | `PIPE-RELEASE-R002` | [Qualification](plan.md#qualification-and-ordering) | P-2, N-3 | |
| FR-003 | `PIPE-RELEASE-R001` | [Qualification](plan.md#qualification-and-ordering) | P-3, N-4, N-5 | |
| FR-004 | `PIPE-RELEASE-R020` | [Digest boundary](plan.md#digest-boundary) | P-4, N-6 | |
| FR-005 | `PIPE-RELEASE-R025.2` | [Release planning](plan.md#release-planning) | T-PIPE-RELEASE-R025.2 | |
| FR-006 | `PIPE-RELEASE-R026.1` | [Program exit gates](plan.md#program-exit-gates) | T-PIPE-RELEASE-R026.1 | |
