# Architecture — PIPE-GATES

## Existing wiring

`reference/gate-standard.md` fixes the eight blocking checks and where each runs today: `format`, `hygiene`, and `secrets` at pre-commit; `types`, `tests-fast`, and `spec` at pre-push or pull request CI; `tests` on the affected subset at pull request and on the full suite at main and tags; `supply-chain` at main and tags. `pipelines_hooks/` publishes the shared gate modules through `pipelines-hook`, and `.pre-commit-hooks.yaml` exports the group hooks `secrets`, `spec`, and `tests-fast` to every consumer. The `tests-fast` gate already proves a gate can run over a diff scope rather than a full working copy. Nothing today states the two landing sides as one machine-checkable policy, and no gate runs against an engine tree with no checkout.

## Gate partition

PIPE-GATES-R001 publishes the split. The pre-land fast set is `format`, `hygiene`, `secrets`, `types`, and `tests-fast`. It runs server-side against the changeset's tree in seconds and alone decides whether the changeset lands. The post-land full set is the complement within the eight blocking gates: `spec`, `tests`, and `supply-chain`. It runs after landing. The partition lives in one machine-readable declaration beside the gate standard; the workflow contracts and the partition test read that declaration. A gate moves between sets only by changing the declaration under review. The full set reuses the existing `tests` and `supply-chain` behavior; it does not invent a second full suite.

## Failure policy

PIPE-GATES-R002 fixes the post-land decision. Auto-revert is the default: the failed changeset reverts without operator action. The gate runner classifies each failure as `product` or `infrastructure`; an unclassified failure is `product`. Fix-forward applies only when the owner opens a fix-forward task within 300 s of the failed verdict. A passing re-run never changes a product failure's decision, under the zero-flake policy. An infrastructure failure, such as a lost runner, may re-run once. A passing re-run records `infrastructure-rerun`. The decision record carries the gate ID, the changeset ID, the verdict, the failure class, the threshold that fired, and the evidence digest, and it is replayable. Pipelines publishes the policy; the engine stores the record beside the changeset. The 300 s window is a starting default; a measured latency on this platform replaces it.

## Tree-based execution

PIPE-GATES-R003 binds every blocking gate to the epistemic-graph tree. A gate reads file content by path and blob digest. It needs no working copy. The contract is equality: the verdict and evidence digest on the tree agree with the same gate on a materialized checkout of the same revision. The engine supplies the tree reads; the served landing operations run the gates. No gate in either set may demand a checkout. A gate that still reads a local path is a defect against this row.

## Quality and release gates

The implementation runs this repository's own gates: format, hygiene, secrets, types, tests-fast, spec, and the affected tests, then the full suite on main. The partition and policy tests are ordinary tests under `tests/`, not new hooks.

## Amendments

- 2026-10-20: The engine tree reads arrive with the epistemic-graph
  changeset tree (EG-SCM-R004). Until then the source provider interface
  and the disk provider serve the tree. The verdict-equality contract
  test runs on the disk provider. The T-004 engine-tree fixture needs the
  engine reads. The consumer-side gates (format, hygiene, types, tests)
  run in the consumer environment. The runner fails closed on a gate the
  environment has not bound. The task window is half-open: a task opened
  exactly at the window edge does not open it.

## Engine records (PIPE-GATES-R004, PIPE-CONNSPEC-R009, PIPE-RELEASE-R009)

Three pipelines steps write lifecycle records to the engine. Each step uses plain HTTP to the
arbora operations and imports no ecosystem package. Gate runs publish verdicts (EG-SCM-R008).
The status generator compares its output with the engine-derived state (EG-SDLC-R005). The
release workflow records each release (EG-SDLC-R002). A failed post never changes a verdict,
a status file or a published release.
