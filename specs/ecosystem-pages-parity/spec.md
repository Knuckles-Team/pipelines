# PIPE-PAGES — Ecosystem Pages parity and release receipt

## Purpose and user stories

An external contributor can inspect a public receipt and see which ecosystem sites use the shared Pages contract and which exact revisions were checked. A release operator can refuse theme or switcher promotion when a declared consumer differs from promoted assets. A site maintainer can contribute without a private workspace, cluster, or live browser session.

## User Scenarios & Testing

### User Story 1 - Inspect a public receipt (Priority: P1)

An external contributor opens the receipt and sees which ecosystem sites use the shared Pages contract and which exact revisions were checked.

**Given** a declaration of six public consumers at immutable commits, **When** the checker runs twice on the same inputs, **Then** both runs yield identical verification fields and the receipt names every consumer commit and tree.

### User Story 2 - Refuse promotion on drift (Priority: P1)

A release operator refuses theme or switcher promotion when a declared consumer differs from the promoted assets.

**Given** one consumer asset that differs by one byte, **When** the checker compares it with the pinned shared revision, **Then** the result is nonzero, names the consumer and the asset, and no current-pass receipt exists.

### User Story 3 - Contribute without a private workspace (Priority: P2)

A site maintainer contributes without a private workspace, cluster or live browser session.

**Given** a fetch failure or a missing public artifact, **When** the checker runs, **Then** the consumer is reported as unverified and never as passed.

### Edge Cases

- A duplicate consumer identity, a mutable revision or an absent revision fails before any comparison.
- An untracked local overlay or a dirty fetched tree fails even when tracked assets match.
- A changed commit with identical assets still marks the earlier receipt historical.
- An escaped symlink or a missing content source fails closed.

## Requirements

- **FR-1 — Declared fleet.** Accept a versioned list of public consumer repositories and immutable revisions. Reject duplicate identities, missing revisions, inaccessible repositories, and untracked local overlays. Missing consumers never pass implicitly. Rows: PIPE-PAGES-R001.
- **FR-2 — Exact parity.** Compare each consumer's declared shared theme/navigation assets with the immutable `pipelines` revision used by its Pages workflow. Report every asset, expected and actual digest, consumer commit, and mismatch reason. Use fetched public source or artifacts; require no sibling checkout. Rows: PIPE-PAGES-R008.
- **FR-3 — Release receipt.** Produce reproducible machine-readable verification and a readable Pages view carrying fleet input digest, pipeline commit, consumer commit/tree IDs, results, and generation time. Mark a receipt historical when any referenced revision changes. Rows: PIPE-PAGES-R001.
- **FR-4 — Bounded gate.** Parity gates only shared Pages theme/navigation promotion. Unrelated code PRs do not need live Pages or a documentation gate. A published-site probe may supplement release acceptance. Rows: PIPE-PAGES-R008.
- **FR-5 — Ownership.** `pipelines` owns shared theme, checker, receipt schema, and generic workflow. Each consumer owns its `mkdocs.yml`, content source, generated assets, and publication. This spec does not certify any consumer implementation. Rows: PIPE-PAGES-R008, PIPE-PAGES-R011.

## Success Criteria

- **SC-001 — Exact refs.** Six consumers resolve to exact commits and trees without a sibling workspace. Rows: PIPE-PAGES-R001, PIPE-PAGES-R008.
- **SC-002 — Drift is visible.** One changed byte yields a nonzero exit that names the repository and the asset. Rows: PIPE-PAGES-R008.
- **SC-003 — One list.** The repository switcher, the spec-delivery menu and the drill-down links read one core repository list. Rows: PIPE-PAGES-R001, PIPE-PAGES-R014.1, PIPE-PAGES-R019.3.
- **SC-004 — Generated pages match registries.** Every generated reference page equals the render of its registry in check mode. Rows: PIPE-PAGES-R005, PIPE-PAGES-R010.

## Assumptions

- Consumer repositories are public and reachable by exact commit during a run.
- The shared theme and the checker live in `pipelines`; each consumer owns its content and publication.
- Hosted Pages URLs and browser probes are release evidence, not unit-test prerequisites.

## Acceptance scenarios

1. Six valid consumers at immutable commits yield six exact-ref results; repeated runs yield identical verification fields.
2. One stale/modified asset, changed commit, or untracked overlay produces a nonzero result naming the consumer and asset, with no current-pass receipt.
3. A newly declared consumer is included without editing a hard-coded repository tuple.
4. A fetch failure or missing public artifact is explicitly unverified rather than successful.

## Interfaces and exclusions

The declaration contains `{repository, revision, content_source, shared_theme_enabled}` and optional site URL. The schema-versioned receipt carries source/comparison digests and no secrets. Runtime deployment manifests, identity routing, and site content belong to their owners. [arbora portable deployment](https://github.com/Knuckles-Team/arbora/tree/main/specs/portable-deployment) owns its runtime contract; [repository-manager](https://github.com/Knuckles-Team/repository-manager/tree/main/specs) owns repository catalog inputs. This spec has sufficient detail without those documents.

## Traceability

| Requirement | Design | Tests | Evidence |
|---|---|---|---|
| FR-1 | [Input and provenance](plan.md#input-and-provenance) | P-1, N-1, N-2 | declaration and exact-ref log |
| FR-2 | [Comparison](plan.md#comparison-and-publication) | P-2, N-3, N-4 | asset digest table |
| FR-3 | [Comparison](plan.md#comparison-and-publication) | P-3, N-5 | receipt and schema check |
| FR-4 | [Integration](plan.md#integration-boundary) | P-4, N-6 | promotion result and unrelated PR proof |
| FR-5 | [Integration](plan.md#integration-boundary) | P-5 | consumer commit links |

## Open decision

Select the public declaration location and approver for new consumers before activation. Both choices must preserve immutable revisions and source provenance. Source implementation alone does not establish Pages release acceptance.

Requirement IDs are defined in [requirements.md](requirements.md); delivery state per ID is in `status.json`.
