# PIPE-CONNSPEC — Connector spec-delivery rollout

## Purpose and user stories

A maintainer of any connector or agent package sees the same spec-delivery method and the same published status page as the five core repositories. The core implementation in this repository is the single reference, so every connector is checked the same way.

### User Story 1 - Connector maintainer adopts the method (Priority: P1)

A connector maintainer wants the generated status, the three spec hooks, the Pages caller and the rapid-delivery skill section, so that the connector is checked and published like a core repository.

**Acceptance Scenarios**:

1. **Given** a connector with a `specs/` tree and the template pre-commit block, **When** `pipelines-hook spec-status` runs, **Then** it computes every spec and fails only if a `status.json` is tracked.
2. **Given** a connector whose Pages workflow calls `pages_pipeline.yml@main` with `spec_dashboard_enabled: true`, **When** the workflow runs, **Then** the spec-delivery page publishes.

### User Story 2 - Lane agent keeps the gates honest (Priority: P2)

A lane agent wants the gate hooks and the trailer rules to behave the same in every repository, so that a landing is accepted or refused on the same evidence everywhere.

**Acceptance Scenarios**:

1. **Given** a commit with a `Spec:` trailer naming a row with a bound test, **When** `spec-trailers` runs, **Then** the commit passes.
2. **Given** a commit that names an unknown row, **When** `spec-trailers` runs, **Then** it fails and names the row.

### Edge Cases

- A shallow clone refuses `spec-status` with exit 2 and a full-history remedy, and writes nothing.
- A connector that lists fewer than the three spec hooks stays SPECIFIED for that child row, and its rollup stays at the minimum state of its children.
- A retired historical ID passes the standard gate; an active row that only mentions retirement fails.

## Functional requirements

- **FR-1 — One standard.** PIPE-CONNSPEC-R001 to PIPE-CONNSPEC-R005 state the standard by pointing at the core implementation: generated status and hooks, test bindings, the page, the reference callers, and the lane contract.
- **FR-2 — Per-connector adoption.** PIPE-CONNSPEC-R101 to PIPE-CONNSPEC-R174 each cover one of the 74 connector repositories listed under the agents section of the workspace manifest, with four children: a generated `specs/` tree, the three hooks, the Pages caller, and the rapid-delivery skill section.

## Assumptions

- The core implementation in this repository is the single reference; a connector copies it and adds no logic of its own.
- Each connector repository is reachable with the GitHub contents API for the row checks.

## Scope and interfaces

Excludes the five core repositories, pipelines itself, third-party clones, services, images, and the skill repositories (universal-skills, skill-graphs). No code is changed by this spec. It tracks the rollout only.
