# PIPE-EH-247 — Dependency-ordered digest release orchestration

Status: SPECIFIED. Owner: `pipelines`. Source requirement: EH-247, shared CI/release ordering portion only. Acceptance: NOT_AUDITED.

## Purpose and user stories

A release operator can promote a qualified set of ecosystem repositories in dependency order, with every deployed image bound to an immutable digest. A contributor can reproduce ordering and refusal logic from public workflow contracts and fixtures without a preconfigured cluster.

## Functional requirements

- **FR-1 — Candidate set.** Accept a versioned public candidate manifest containing repository, exact source commit, build artifact identity, image digest, profile digest, API/schema compatibility range, predecessor component IDs, public build/check receipts, and consumer manifest references. Reject cycles, missing dependencies, duplicate identities, floating tags, and mismatched source/digest provenance. Tags are display only.
- **FR-2 — Qualification.** Require recorded build, test, and consumer contract results at each exact source commit. Skipped, missing, or failing mandatory results block the candidate and its descendants; report the eligible subset without claiming a full release.
- **FR-3 — Ordered publication.** Compute deterministic topological order. Publish one dependency stage at a time, await hosted CI for each pushed revision, and stop before downstream publication on failure. Record commit, workflow run, image digest, and outcome per stage. Retry is idempotent for the same candidate digest.
- **FR-4 — Digest handoff.** Produce an integrity-checked digest mapping for deployment consumers. Verify every declared workload reference uses the qualified digest before marking that consumer ready. The deployment owner applies manifests and probes its environment.
- **FR-5 — Portable operation.** Dry-run ordering, fixture qualification, and contract verification run on a hosted runner or local checkout with injected inputs. Live cluster, builder, registry credential, and secret manager are required only for corresponding build/deploy stages, never source-level PR validation.

## Acceptance scenarios

1. Three candidates A → B → C with valid receipts and digests dry-run in A, B, C order; hosted promotion records CI and digest handoff at each stage.
2. Missing digest, floating tag, failed CI, cycle, or consumer mismatch stops affected downstream publication with precise refusal.
3. Re-running an interrupted stage does not republish a completed digest or substitute a different commit.
4. A public contributor runs all parsing, ordering, and negative contract tests without infrastructure secrets.

## Ownership and interface

`pipelines` owns generic workflow ordering, verification, receipt schema, and reusable build/publish actions. Product repositories own build inputs and source quality. [graph-os portable deployment](https://github.com/Knuckles-Team/graph-os/tree/main/specs/portable-deployment) owns its service manifest and runtime deployment; other consumers own equivalent manifests. The handoff is a trusted versioned candidate manifest with component ID, repository, full source commit, immutable artifact digest, profile digest, API/schema compatibility range, predecessor IDs, and public build/check receipts. [GraphOS dependency-ordered release](https://github.com/Knuckles-Team/graph-os/tree/main/specs/dependency-ordered-release) consumes this manifest, validates it, and owns rollout ordering, readiness probes, and rollback. Pipelines orders source publication and awaits CI; it does not apply runtime stages. This workflow never edits consumer manifests or treats one environment's probe as proof for another.

## Traceability

| Requirement | Design | Tests | Evidence |
|---|---|---|---|
| FR-1 | [Candidate model](plan.md#candidate-model) | P-1, N-1, N-2 | schema and validation |
| FR-2 | [Qualification](plan.md#qualification-and-ordering) | P-2, N-3 | exact CI runs |
| FR-3 | [Qualification](plan.md#qualification-and-ordering) | P-3, N-4, N-5 | ordered stage log |
| FR-4 | [Digest boundary](plan.md#digest-boundary) | P-4, N-6 | artifact digest and manifest check |
| FR-5 | [Portable execution](plan.md#portable-execution) | P-5 | secret-free hosted/local run |

## Success and open decisions

No downstream stage runs before each predecessor qualifies at its exact revision. Every ready consumer reference uses the qualified digest. Select public candidate manifest location and receipt integrity mechanism during implementation; both must allow independent verification from public artifacts. Live rollout acceptance remains with deployment owners.
