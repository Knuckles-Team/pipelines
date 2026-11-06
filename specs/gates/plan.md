# PIPE-GATES — Implementation plan

Governing spec: [spec.md](spec.md). Rows: [requirements.md](requirements.md).

## Summary

This plan serves the rows of `PIPE-GATES`. A landing decision costs seconds. The spec-standard gates publish verdicts and computed states to the engine. A new gate refuses a cross-repository citation that no contract covers. The earlier design record sits under Phase 1.

## Technical Context

- **Language/Version**: Python 3.14 (floor 3.12)
- **Primary Dependencies**: The `pipelines_hooks` package; plain HTTP to the arbora `source.*` operations.
- **Storage**: N/A. Gates read files and git history; the engine stores the records.
- **Testing**: pytest under `tests/hooks/`. Each row names its test and proof level.
- **Target Platform**: Linux CI runners and developer machines
- **Project Type**: Library and command-line hooks
- **Performance Goals**: The fast set decides a landing in seconds. A row states any further budget.
- **Constraints**: Public files stay neutral and portable. A publish failure never changes a verdict.
- **Scale/Scope**: The rows of requirements.md.

## Constitution Check

- **I. One owner per concept**: No departure is recorded in this plan; the rows carry the proof.
- **II. Extend before you create**: No departure is recorded in this plan; the rows carry the proof.
- **III. Specs describe the current state only**: No departure is recorded in this plan; the rows carry the proof.
- **IV. Requirements are neutral and controlled**: No departure is recorded in this plan; the rows carry the proof.
- **V. Hard cutover, no legacy path**: No departure is recorded in this plan; the rows carry the proof.
- **VI. Names carry no version suffix**: No departure is recorded in this plan; the rows carry the proof.
- **VII. One engine, no second database, no sync**: No departure is recorded in this plan; the rows carry the proof.
- **VIII. Ask the graph, not a bespoke operation**: No departure is recorded in this plan; the rows carry the proof.
- **IX. Connectors depend on the SDK and are called through arbora**: No departure is recorded in this plan; the rows carry the proof.
- **X. Every ontology class rolls up to the core**: No departure is recorded in this plan; the rows carry the proof.
- **XI. Code stays small, simple and unduplicated**: No departure is recorded in this plan; the rows carry the proof.
- **XII. No ratchets and no suppressions**: No departure is recorded in this plan; the rows carry the proof.
- **XIII. Zero flakes**: No departure is recorded in this plan; the rows carry the proof.
- **XIV. Compile first, then review**: No departure is recorded in this plan; the rows carry the proof.
- **XV. Python 3.14 standard, 3.12 floor**: No departure is recorded in this plan; the rows carry the proof.
- **XVI. Install and deploy only from published releases**: No departure is recorded in this plan; the rows carry the proof.
- **XVII. Publish the gate's tool before the gate**: No departure is recorded in this plan; the rows carry the proof.
- **XVIII. Landed means reachable**: No departure is recorded in this plan; the rows carry the proof.
- **XIX. A tag push publishes, with no manual approval**: No departure is recorded in this plan; the rows carry the proof.
- **XX. Secrets are never traced or logged**: No departure is recorded in this plan; the rows carry the proof.
- **XXI. Public files stay portable and neutral**: No departure is recorded in this plan; the rows carry the proof.

## Project Structure

```text
specs/gates/                              existing: spec.md, plan.md, requirements.md, tasks.md, test-spec.md
pipelines_hooks/states_publish.py         new: publish row and task states (PIPE-GATES-R004.3)
pipelines_hooks/specs/contracts.py        new: contract-coverage gate (PIPE-GATES-R034)
pipelines_hooks/code/coverage_decrease.py new: coverage-decrease gate (PIPE-GATES-R049)
pipelines_hooks/specs/status.py           existing: calls publish_states
pipelines_hooks/cli.py                    existing: gate table and spec group
tests/hooks/test_states_publish.py        new
tests/hooks/test_contract_coverage.py     new
```

## Phase 0: Research

One unknown: where the build cache must live to meet the timing budgets. Its resolution is in [research.md](research.md).

## Phase 1: Design

### Existing wiring and graph automation

The spec-driven artifacts feed the engine graph (`MEDULLA-SDLC-R014`). The gates publish verdicts and computed states, so the graph and the spec-delivery page read one source (`MEDULLA-SDLC-R005.7`). A contract is the boundary registry. It names the provider row and the consumer row of a seam. The engine seam graph then routes a new requirement to both owners (`MEDULLA-SDLC-R014.4`). The gate `contract-coverage` enforces coverage on touched specs.

### Existing wiring

`reference/gate-standard.md` fixes the eight blocking checks and where each runs today: `format`, `hygiene`, and `secrets` at pre-commit; `types`, `tests-fast`, and `spec` at pre-push or pull request CI; `tests` on the affected subset at pull request and on the full suite at main and tags; `supply-chain` at main and tags. `pipelines_hooks/` publishes the shared gate modules through `pipelines-hook`, and `.pre-commit-hooks.yaml` exports the group hooks `secrets`, `spec`, and `tests-fast` to every consumer. The `tests-fast` gate already proves a gate can run over a diff scope rather than a full working copy. Nothing today states the two landing sides as one machine-checkable policy, and no gate runs against an engine tree with no checkout.

### Gate partition

PIPE-GATES-R001 publishes the split. The pre-land fast set is `format`, `hygiene`, `secrets`, `types`, and `tests-fast`. It runs server-side against the changeset's tree in seconds and alone decides whether the changeset lands. The post-land full set is the complement within the eight blocking gates: `spec`, `tests`, and `supply-chain`. It runs after landing. The partition lives in one machine-readable declaration beside the gate standard; the workflow contracts and the partition test read that declaration. A gate moves between sets only by changing the declaration under review. The full set reuses the existing `tests` and `supply-chain` behavior; it does not invent a second full suite.

### Failure policy

PIPE-GATES-R002 fixes the post-land decision. Auto-revert is the default: the failed changeset reverts without operator action. The gate runner classifies each failure as `product` or `infrastructure`; an unclassified failure is `product`. Fix-forward applies only when the owner opens a fix-forward task within 300 s of the failed verdict. A passing re-run never changes a product failure's decision, under the zero-flake policy. An infrastructure failure, such as a lost runner, may re-run once. A passing re-run records `infrastructure-rerun`. The decision record carries the gate ID, the changeset ID, the verdict, the failure class, the threshold that fired, and the evidence digest, and it is replayable. Pipelines publishes the policy; the engine stores the record beside the changeset. The 300 s window is a starting default; a measured latency on this platform replaces it.

### Tree-based execution

PIPE-GATES-R003 binds every blocking gate to the Medulla tree. A gate reads file content by path and blob digest. It needs no working copy. The contract is equality: the verdict and evidence digest on the tree agree with the same gate on a materialized checkout of the same revision. The engine supplies the tree reads; the served landing operations run the gates. No gate in either set may demand a checkout. A gate that still reads a local path is a defect against this row.

### Quality and release gates

The implementation runs this repository's own gates: format, hygiene, secrets, types, tests-fast, spec, and the affected tests, then the full suite on main. The partition and policy tests are ordinary tests under `tests/`, not new hooks.

### Amendments

- 2026-10-20: The engine tree reads arrive with the Medulla
  changeset tree (MEDULLA-SCM-R004). Until then the source provider interface
  and the disk provider serve the tree. The verdict-equality contract
  test runs on the disk provider. The `PIPE-GATES-R003` engine-tree fixture needs the
  engine reads. The consumer-side gates (format, hygiene, types, tests)
  run in the consumer environment. The runner fails closed on a gate the
  environment has not bound. The task window is half-open: a task opened
  exactly at the window edge does not open it.

### Engine records (PIPE-GATES-R004, PIPE-CONNSPEC-R009, PIPE-RELEASE-R009)

Three pipelines steps write lifecycle records to the engine. Each step uses plain HTTP to the
arbora operations and imports no ecosystem package. Gate runs publish verdicts (MEDULLA-SCM-R008).
The status generator compares its output with the engine-derived state (MEDULLA-SDLC-R005). The
release workflow records each release (MEDULLA-SDLC-R002). A failed post never changes a verdict,
a status file or a published release.
### Migration waves (R006)

Repositories move to engine changesets one wave at a time. The order runs from the lowest risk to the highest: webarchiver, small connectors, the other connectors, skills with pipelines and the user interfaces, the Scion SDK with the harness, arbora, and Medulla last. RM-SCM-R001 and RM-SCM-R002 import history and keep the GitHub mirror in sync. A wave exits only when the mirror matches every landed changeset for 7 days. Wave 7 also needs two restores of the engine source from the mirror.

### Product names in spec text (R005)

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

### Warm build slots (PIPE-GATES-R070 to R075)

One image per repository pin set and one configuration file render to four runtimes through one function per runtime. The cache sits on local solid-state storage outside the checkout. Lifecycle commands share the runtime adapters. Routing and credential isolation are workflow checks, so a fork pull request cannot reach a slot.

### Gates moved from repository governance (PIPE-GATES-R076 to R084)

Each row extends the live hook it names; the planned rows add a test or a small module beside the same call path. The clone rows share `enforce` in `pipelines_hooks/clones/jscpd_gate.py`: `R078` fixes the merge-base measurement, `R079` makes an unevaluable change fail closed and `R080` keeps a move from counting. The distinct-pair register stays in `pipelines_hooks/clones/ledger.py`. Digest verification of a tree extends the `FileProvider` contract of `PIPE-GATES-R003` and never calls Git.

### Explicit state machines (PIPE-GATES-R085 to R086)

Article XXXI states the rule; `R085` keeps it whole with a constitution test. `R086` adds one staged hook and one census hook that share one rule set, so the two languages never drift.

Design. `.pre-commit-hooks.yaml` gains `state-machine-shape` (stages pre-commit and pre-push) and `state-machine-census` (stage manual) after the `no-stub` entry. Both run `pipelines-hook`, which `pipelines_hooks/cli.py:48` maps to `pipelines_hooks/code/state_machine.py::main`. `main` lists the files, calls `read_python` (`state_machine_py.py`, the `ast` module) or `read_rust` (`state_machine_rs.py`, a tree-sitter syntax tree), calls `bind_tests` (`state_machine_tests.py`) for each declared machine, and calls `findings` (`state_machine_rules.py`) for each `Machine`. The `Machine` and `Finding` records live in `state_machine_model.py`. The split keeps each file within the ten-function limit.

Detection. A type is a Python class or a Rust `struct` or `enum`. A status field is named `status`, `state`, `phase`, `stage` or `lifecycle`. An implicit machine is a type with a status field, lifecycle flags or lifecycle timestamps and no declared table or function. A declared machine has a constant named `LEGAL`, `TRANSITIONS` or `EDGES`, or a function named `transition`, `apply` or `step` that returns or raises a type ending in `Refused`. Test code is skipped. Receiver resolution is by `self`, then by field name within the package or crate.

Finding codes. Rule 1 `SM-MULTI-ASSIGN`. Rule 2 `SM-STRING-STATUS`. Rule 3 `SM-LIFECYCLE-FLAGS`. Rule 4 `SM-UNTESTED-EDGE` and `SM-NO-REFUSAL-TEST`. Rule 5 `SM-NO-DECLARATION`. The ontology rule `SM-ONTOLOGY-NOT-CORE-ROLLED` comes from `connector-ontology-map graph-check` (R086.6). Output is `<file>:<line> <type> <code> rule <n>`. Exit 0 is clean, 1 is findings, 2 is a gate that could not run.

Fixtures. `tests/hooks/fixtures/state_machine/py/` and `.../rs/` each hold five directories: `two_assigners`, `string_compare`, `lifecycle_flags`, `no_refusal_tests` and `compliant`. The compliant directory holds a full table, one test per edge and a refusal test.

Order and sizing. R086.1 first, then R086.2 to R086.4 in parallel, then R086.5 and R086.6. The rollup is delivered last. Its census is red until the consumer machine rows are verified, so those rows land first. Each child scores 6 or less: one to three modules, one repository, and no more than two roots. R086.5 and R086.6 own the registration and the ontology wiring.

### Connector surface standard (PIPE-GATES-R014)

`reference/connector-surface.md` is the standard. `connector-surface-audit` reads one checkout and assembles one record in `audit_connector`. Three modules keep each check small. `connector_surface_tools` reads tools and resources with an AST walk. `connector_surface_contracts` reads the SDK builder calls of `connector_contracts.py`, or Turtle typed with the SDK contract vocabulary. `connector_surface_prompts` checks each prompt as an agent definition. The static tool list derives `<prefix>_<method>` from the declared client class; the SDK self-check (`SCION-CONNECTOR-CONTROL-R916.4`) proves the live list. The `surface` member of `connector-standard` runs the audit in every connector repository. The fleet census reads each repository through `git archive`, so shared checkouts keep their worktrees. Earlier text required an `owl:imports` of the core ontology and the provider entry-point groups; both are now gaps, because packs extend core classes and the SDK finds content by convention.

## Phase 2: Task approach

tasks.md carries one numbered task line for each new row. Tasks run producer first. A task marked `[P]` may run in parallel with its neighbours.

## Complexity Tracking

none

## Build contract

Each row names its test. The repository pre-commit and pre-push hooks and the pull request gates apply. No row may use a suppression or a ratchet. The new gate module must stay under the complexity and duplication limits of this repository.

## Production caller chain

- Verdicts: `run_gate_on` at `pipelines_hooks/gate_runner.py:62` calls `publish_verdict` (`PIPE-GATES-R004.1`).
- States: `main` at `pipelines_hooks/specs/status.py:110` calls `publish_states` (`PIPE-GATES-R004.4`).
- Connector surface: hook `connector-standard` runs `standard.main`, whose `surface` member (`pipelines_hooks/connector/standard.py:15`) calls `audit_connector` at `pipelines_hooks/hygiene/connector_surface.py:346` (`PIPE-GATES-R014.8`).
- Contracts: hook `spec` at `.pre-commit-hooks.yaml:45` reaches the group at `pipelines_hooks/cli.py:80`, which runs `contract-coverage` (`PIPE-GATES-R034.3`).

## Cross-repo seams

- `MEDULLA-SDLC-R005.7` consumes the published states.
- `MEDULLA-SDLC-R014.4` ingests the contracts as a seam graph.
- `ARBORA-OPS-R853` serves the `spec.status` read.
- `SCION-CONNECTOR-CONTROL-R916.2` provides the declaration builders the surface gate reads (`PIPE-GATES-R014.5`); contract `contracts/connector-surface-declarations.md`.
- `SCION-CONNECTOR-CONTROL-R916.8` provides the prompt agent-definition fields (`PIPE-GATES-R014.3`).
- `MEDULLA-SRC-AUTH-R001` resolves routing from the data locations (`PIPE-GATES-R014.7`).
