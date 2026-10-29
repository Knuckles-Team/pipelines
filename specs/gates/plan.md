# Architecture — PIPE-GATES

## Existing wiring

`reference/gate-standard.md` fixes the eight blocking checks and where each runs today: `format`, `hygiene`, and `secrets` at pre-commit; `types`, `tests-fast`, and `spec` at pre-push or pull request CI; `tests` on the affected subset at pull request and on the full suite at main and tags; `supply-chain` at main and tags. `pipelines_hooks/` publishes the shared gate modules through `pipelines-hook`, and `.pre-commit-hooks.yaml` exports the group hooks `secrets`, `spec`, and `tests-fast` to every consumer. The `tests-fast` gate already proves a gate can run over a diff scope rather than a full working copy. Nothing today states the two landing sides as one machine-checkable policy, and no gate runs against an engine tree with no checkout.

## Gate partition

PIPE-GATES-R001 publishes the split. The pre-land fast set is `format`, `hygiene`, `secrets`, `types`, and `tests-fast`. It runs server-side against the changeset's tree in seconds and alone decides whether the changeset lands. The post-land full set is the complement within the eight blocking gates: `spec`, `tests`, and `supply-chain`. It runs after landing. The partition lives in one machine-readable declaration beside the gate standard; the workflow contracts and the partition test read that declaration. A gate moves between sets only by changing the declaration under review. The full set reuses the existing `tests` and `supply-chain` behavior; it does not invent a second full suite.

## Failure policy

PIPE-GATES-R002 fixes the post-land decision. Auto-revert is the default: the failed changeset reverts without operator action. The gate runner classifies each failure as `product` or `infrastructure`; an unclassified failure is `product`. Fix-forward applies only when the owner opens a fix-forward task within 300 s of the failed verdict. A passing re-run never changes a product failure's decision, under the zero-flake policy. An infrastructure failure, such as a lost runner, may re-run once. A passing re-run records `infrastructure-rerun`. The decision record carries the gate ID, the changeset ID, the verdict, the failure class, the threshold that fired, and the evidence digest, and it is replayable. Pipelines publishes the policy; the engine stores the record beside the changeset. The 300 s window is a starting default; a measured latency on this platform replaces it.

## Tree-based execution

PIPE-GATES-R003 binds every blocking gate to the Medulla tree. A gate reads file content by path and blob digest. It needs no working copy. The contract is equality: the verdict and evidence digest on the tree agree with the same gate on a materialized checkout of the same revision. The engine supplies the tree reads; the served landing operations run the gates. No gate in either set may demand a checkout. A gate that still reads a local path is a defect against this row.

## Quality and release gates

The implementation runs this repository's own gates: format, hygiene, secrets, types, tests-fast, spec, and the affected tests, then the full suite on main. The partition and policy tests are ordinary tests under `tests/`, not new hooks.

## Amendments

- 2026-10-20: The engine tree reads arrive with the Medulla
  changeset tree (MEDULLA-SCM-R004). Until then the source provider interface
  and the disk provider serve the tree. The verdict-equality contract
  test runs on the disk provider. The T-004 engine-tree fixture needs the
  engine reads. The consumer-side gates (format, hygiene, types, tests)
  run in the consumer environment. The runner fails closed on a gate the
  environment has not bound. The task window is half-open: a task opened
  exactly at the window edge does not open it.

## Engine records (PIPE-GATES-R004, PIPE-CONNSPEC-R009, PIPE-RELEASE-R009)

Three pipelines steps write lifecycle records to the engine. Each step uses plain HTTP to the
arbora operations and imports no ecosystem package. Gate runs publish verdicts (MEDULLA-SCM-R008).
The status generator compares its output with the engine-derived state (MEDULLA-SDLC-R005). The
release workflow records each release (MEDULLA-SDLC-R002). A failed post never changes a verdict,
a status file or a published release.
## Migration waves (R006)

Repositories move to engine changesets one wave at a time. The order runs from the lowest risk to the highest: webarchiver, small connectors, the other connectors, skills with pipelines and the user interfaces, the Scion SDK with the harness, arbora, and Medulla last. RM-SCM-R001 and RM-SCM-R002 import history and keep the GitHub mirror in sync. A wave exits only when the mirror matches every landed changeset for 7 days. Wave 7 also needs two restores of the engine source from the mirror.

## Product names in spec text (R005)

The `spec-standard` check scans authored `specs/**/*.md` text against `pipelines_hooks/specs/third_party_names.toml`. A connector may name its own target system through the `[allow]` table. The check masks inline code, fenced code, URLs, link targets and spec IDs. A lowercase identifier, such as a connector ID, is not a product name.

- 2026-10-22: PIPE-GATES-R007 migrates the removed Meristem legacy-marker checker to the shared owner. Reuse tracked discovery and sanitized Git execution, explicitly selecting the target repository index rather than an ambient hook index. Keep the original pattern and historical exclusions, without a consumer-owned copy or a ninth blocking gate.

- 2026-10-22: PIPE-GATES-R008 and R009 rehome the removed lock-mirror and
  static import-boundary checks in the shared package. The metadata check
  preserves optional artifacts and the editable self-version omission.
  The import check reads consumer-owned package and module-prefix policy,
  uses sanitized tracked discovery, and has no obsolete adapter exemptions.
  Neither gate claims dynamic runtime coverage or changes the gate partition.

- 2026-10-26: PIPE-GATES-R016.92 extends the canonical
  `[tool.pipelines.container]` metadata with `state_volumes`, an exact list of
  `{name, target}` named-volume entries. The renderer emits each as a
  writable Compose `type: volume` mount and a matching top-level declaration;
  `config_mounts` remains the separate read-only bind contract under `/etc`.
  State entries reject host paths, path escapes, duplicate names or targets,
  read-only modes and unknown fields. Central migration accepts the existing
  short named-volume form and the canonical long form only when the
  top-level declaration matches the service mount.
