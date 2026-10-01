# PIPE-PAGES-001 — Ecosystem Pages parity and release receipt

Status: SPECIFIED. Owner: `pipelines`. Source requirement: PIPE-PAGES-R001. Acceptance: NOT_AUDITED.
Every requirement ID this spec owns is defined in [requirements.md](requirements.md); delivery
state and evidence for each ID are recorded in [status.json](status.json).

## Purpose and user stories

An external contributor can inspect a public receipt and see which ecosystem sites use the shared Pages contract and which exact revisions were checked. A release operator can refuse theme or switcher promotion when a declared consumer differs from promoted assets. A site maintainer can contribute without a private workspace, cluster, or live browser session.

## Functional requirements

- **FR-1 — Declared fleet.** Accept a versioned list of public consumer repositories and immutable revisions. Reject duplicate identities, missing revisions, inaccessible repositories, and untracked local overlays. Missing consumers never pass implicitly.
- **FR-2 — Exact parity.** Compare each consumer's declared shared theme/navigation assets with the immutable `pipelines` revision used by its Pages workflow. Report every asset, expected and actual digest, consumer commit, and mismatch reason. Use fetched public source or artifacts; require no sibling checkout.
- **FR-3 — Release receipt.** Produce reproducible machine-readable verification and a readable Pages view carrying fleet input digest, pipeline commit, consumer commit/tree IDs, results, and generation time. Mark a receipt historical when any referenced revision changes.
- **FR-4 — Bounded gate.** Parity gates only shared Pages theme/navigation promotion. Unrelated code PRs do not need live Pages or a documentation gate. A published-site probe may supplement release acceptance.
- **FR-5 — Ownership.** `pipelines` owns shared theme, checker, receipt schema, and generic workflow. Each consumer owns its `mkdocs.yml`, content source, generated assets, and publication. This spec does not certify any consumer implementation.

## Acceptance scenarios

1. Six valid consumers at immutable commits yield six exact-ref results; repeated runs yield identical verification fields.
2. One stale/modified asset, changed commit, or untracked overlay produces a nonzero result naming the consumer and asset, with no current-pass receipt.
3. A newly declared consumer is included without editing a hard-coded repository tuple.
4. A fetch failure or missing public artifact is explicitly unverified rather than successful.

## Interfaces and exclusions

The declaration contains `{repository, revision, content_source, shared_theme_enabled}` and optional site URL. The schema-versioned receipt carries source/comparison digests and no secrets. Runtime deployment manifests, identity routing, and site content belong to their owners. [graph-os portable deployment](https://github.com/Knuckles-Team/graph-os/tree/main/specs/portable-deployment) owns its runtime contract; [repository-manager](https://github.com/Knuckles-Team/repository-manager/tree/main/specs) owns repository catalog inputs. This spec has sufficient detail without those documents.

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
