# PIPE-GATES — Gate landing policy

## Purpose and user stories

A landing decision costs seconds, not a queue. An agent submits a changeset; the server runs the fast gates against the changeset's tree, lands on a pass, and runs the full set afterwards. A failed post-land gate triggers a policy decision, auto-revert or fix-forward, with a recorded result. No step requires a local checkout.

## Requirements and acceptance

The [requirements](requirements.md) state the three owned behaviors: the pre-land versus post-land partition of the eight blocking gates (PIPE-GATES-R001), the auto-revert versus fix-forward decision policy with its thresholds (PIPE-GATES-R002), and gate execution against the engine tree without a local checkout (PIPE-GATES-R003).

## Why a new spec

Search: `git grep -n "gate\|landing\|revert" -- specs` on pipelines main. The existing families are PIPE-PAGES (Pages parity), PIPE-RELEASE (release orchestration), PIPE-IDENTITY (commit identity), PIPE-CONNSPEC (spec-delivery rollout), and PIPE-VALIDATION (bounded offline validation). PIPE-VALIDATION runs declared checks on a local checkout with passive Git events. It owns no landing policy, no gate partition, and no post-land failure handling. No spec owns which gates gate a landing, what happens after landing, or how a gate runs without a checkout.

## Scope and interfaces

Pipelines owns the gate-set policy and the published gate behavior behind it. The changeset store, the tree reads, and the decision records live in epistemic-graph; the served landing operations live in arbora. This spec names the partition, the policy, and the tree-based gate contract. It builds no engine storage and no client transport. Advisory checks enter neither set. No merge queue exists by design.

## Traceability

| Requirement | Design section | Test ID | Evidence |
|---|---|---|---|
| PIPE-GATES-R001 | [Gate partition](plan.md#gate-partition) | T-001 | |
| PIPE-GATES-R002 | [Failure policy](plan.md#failure-policy) | T-002, T-003 | |
| PIPE-GATES-R003 | [Tree-based execution](plan.md#tree-based-execution) | T-004 | |
