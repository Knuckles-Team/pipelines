# PIPE-GATES — Gate landing policy

Owner: pipelines. Cross-repo IDs: `MEDULLA-SCM-R008`, `MEDULLA-SDLC-R005.7`, `MEDULLA-SDLC-R014.4`, `ARBORA-OPS-R853`.
Public provenance: the [spec standard](../../reference/spec-standard.md) and the [gate standard](../../reference/gate-standard.md).

## Delivery mapping

Component: Gates

Depends-on: MEDULLA-SCM-R008

## User Scenarios & Testing

### User Story 1 - Land in seconds (Priority: P1)

An agent submits a changeset. The server runs the fast gates against the changeset tree, lands on a pass, and runs the full set afterwards. A failed post-land gate triggers a recorded decision. No step needs a local checkout.

**Acceptance Scenarios**:

1. **Given** a changeset that passes the fast set, **When** it is submitted, **Then** it lands and the full set runs afterwards.
2. **Given** a failed post-land gate, **When** no fix-forward task opens within 300 s, **Then** the changeset reverts with a recorded decision.

### User Story 2 - The graph and the page agree (Priority: P2)

A maintainer reads requirement and task states in the engine graph and on the spec-delivery page. Both must show the same states, because the gates publish the computed states with the verdicts.

**Acceptance Scenarios**:

1. **Given** a fixture repository, **When** the `spec` hook runs, **Then** the engine holds a verdict record and a state record for each row and task.
2. **Given** a state that differs between graph and page, **When** `states-agree` runs, **Then** it fails and names the row and each side.

### User Story 3 - Cross-repository citations have a contract (Priority: P3)

A spec author cites a row of another repository. A hand-written contract must name the provider row and the consumer row. It must also hold the wire shape, the refusal codes, the authoritative types and the test vectors.

**Acceptance Scenarios**:

1. **Given** a touched spec that cites another repository's row, **When** no contract covers the pair, **Then** the gate fails with a finding.
2. **Given** a covering contract, **When** the gate runs again, **Then** it passes.

### Edge Cases

- A publish failure must not change a gate verdict.
- An unreachable engine yields an advisory finding for the state and contract checks.
- A task opened exactly at the 300 s window edge does not open the window.

## Requirements

- **FR-001**: The eight blocking gates partition into a pre-land fast set and a post-land full set. Rows: `PIPE-GATES-R001`.
- **FR-002**: A failed post-land gate triggers a recorded auto-revert or fix-forward decision. Rows: `PIPE-GATES-R002`.
- **FR-003**: Every blocking gate runs against the engine tree without a local checkout. Rows: `PIPE-GATES-R003`.
- **FR-004**: Gates publish verdicts and computed states to the engine. Rows: `PIPE-GATES-R004`, `PIPE-GATES-R004.3`, `PIPE-GATES-R004.5`.
- **FR-005**: A row that cites another repository's row is covered by a contract. Rows: `PIPE-GATES-R034`, `PIPE-GATES-R034.2`.

## Success Criteria

- **SC-001**: A landing decision completes in seconds from the changeset tree. Rows: `PIPE-GATES-R001`.
- **SC-002**: Engine states equal the generator states for every row and task of a revision. Rows: `PIPE-GATES-R004.6`.
- **SC-003**: An uncovered cross-repository citation in a touched spec never lands. Rows: `PIPE-GATES-R034.5`.

## Assumptions

- The arbora `source.*` operations accept the verdict and state records.
- No merge queue exists by design.

## Why a new spec

Search: `git grep -n "gate\|landing\|revert" -- specs` on pipelines main. The families PIPE-PAGES, PIPE-RELEASE, PIPE-IDENTITY, PIPE-CONNSPEC and PIPE-VALIDATION own no landing policy, gate partition or post-land failure handling. This spec owns them.

## Scope and interfaces

Pipelines owns the gate-set policy and the published gate behavior. The changeset store, tree reads and decision records live in Medulla. The served landing operations live in arbora. This spec builds no engine storage and no client transport. Advisory checks enter neither set.

## Traceability

| Label | Rows | Design section | Test ID | Evidence |
|---|---|---|---|---|
| FR-001 | `PIPE-GATES-R001` | [Gate partition](plan.md#gate-partition) | T-001 | |
| FR-002 | `PIPE-GATES-R002` | [Failure policy](plan.md#failure-policy) | T-002, T-003 | |
| FR-003 | `PIPE-GATES-R003` | [Tree-based execution](plan.md#tree-based-execution) | T-004 | |
| FR-004 | `PIPE-GATES-R004.3` | [Engine records](plan.md#engine-records-pipe-gates-r004-pipe-connspec-r009-pipe-release-r009) | T-034 | |
| FR-005 | `PIPE-GATES-R034.2` | [Existing wiring and graph automation](plan.md#existing-wiring-and-graph-automation) | T-039 | |
