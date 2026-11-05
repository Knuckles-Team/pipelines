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
- A platform-opened pull request gets no skip, no bypass and no merge by the platform principal.
- An unreachable engine yields an advisory finding for the state and contract checks.
- A task opened exactly at the 300 s window edge does not open the window.

## Requirements

- **FR-001**: The eight blocking gates partition into a pre-land fast set and a post-land full set. Rows: `PIPE-GATES-R001`.
- **FR-002**: A failed post-land gate triggers a recorded auto-revert or fix-forward decision. Rows: `PIPE-GATES-R002`.
- **FR-003**: Every blocking gate runs against the engine tree without a local checkout. Rows: `PIPE-GATES-R003`.
- **FR-004**: Gates publish verdicts and computed states to the engine. Rows: `PIPE-GATES-R004`, `PIPE-GATES-R004.3`, `PIPE-GATES-R004.5`.
- **FR-005**: A row that cites another repository's row is covered by a contract. Rows: `PIPE-GATES-R034`, `PIPE-GATES-R034.2`.
- **FR-006**: Platform-delivered pull requests keep owner-only merge and pass every gate unchanged. Rows: `PIPE-GATES-R016.116.1`, `PIPE-GATES-R016.116.2`.
- **FR-007**: Heavy Rust CI and agent build lanes run on warm build slots that deploy from one configuration on Kubernetes, Docker Compose, Podman and SSH hosts. Rows: `PIPE-GATES-R070`, `PIPE-GATES-R071`, `PIPE-GATES-R072`, `PIPE-GATES-R073`, `PIPE-GATES-R074`, `PIPE-GATES-R075`.
- **FR-008**: The shared gates hold the local-gate behaviors that repository-manager does not run itself: hook root resolution in a linked worktree, exhaustive-dispatch complexity scoring, clone gating against the merge base with fail-closed evaluation, the distinct-pair register, test module resolution in the KISS hook, digest-pinned secret-history exceptions and digest verification of a tree without a working copy. Rows: `PIPE-GATES-R076`, `PIPE-GATES-R077`, `PIPE-GATES-R078`, `PIPE-GATES-R079`, `PIPE-GATES-R080`, `PIPE-GATES-R081`, `PIPE-GATES-R082`, `PIPE-GATES-R083`, `PIPE-GATES-R084`.

## Success Criteria

- **SC-001**: A landing decision completes in seconds from the changeset tree. Rows: `PIPE-GATES-R001`.
- **SC-002**: Engine states equal the generator states for every row and task of a revision. Rows: `PIPE-GATES-R004.6`.
- **SC-003**: An uncovered cross-repository citation in a touched spec never lands. Rows: `PIPE-GATES-R034.5`.
- **SC-004**: A warm one-file-change check takes under 60 seconds and a cold prime under 15 minutes on an 8-job slot. Rows: `PIPE-GATES-R075`.

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
| FR-006 | `PIPE-GATES-R016.116.1` | [Quality and release gates](plan.md#quality-and-release-gates) | T-055, T-056 | |
| FR-007 | `PIPE-GATES-R070` | [Warm build slots](plan.md#warm-build-slots-pipe-gates-r070-to-r075) | T-079, T-080, T-081, T-082, T-083, T-084 | |
