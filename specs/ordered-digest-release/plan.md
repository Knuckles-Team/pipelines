# Architecture — PIPE-RELEASE

## Existing components and flow

`.github/workflows/container_pipeline.yml` builds caller images. `.github/actions/verify-source-commit/` binds a build to the checkout. Python, maturin, services, and Pages workflows provide existing job contracts. Workflow contract tests classify hosted gates. Extend these seams with a small release coordinator and schema; do not build another image builder or fork each workflow.

Flow: candidate declaration → schema/graph validation → exact source/build/CI receipts → deterministic dependency order → stage publication → CI observation → digest mapping → consumer manifest verification → deployment-owner handoff. Inputs and outputs are versioned public artifacts with SHA-256 digests, source commits, and run URLs. `latest` is never release authority.

## Candidate model

Each candidate has stable repository identity, full source commit, artifact/image digest, predecessor component IDs, profile digest, API/schema compatibility range, required public CI check receipts, and consumer manifest references. Validate graph before any write. Reject unknown IDs, duplicates, self edges, cycles, malformed digests, wrong source provenance, and floating references. Keep credentials out of manifest.

## Qualification and ordering

Use one deterministic topological sort and dependency closure. Query hosted checks for exact revisions; absent, skipped, timed-out, or failing mandatory checks block. Derive an idempotency key from candidate-set digest, commit, artifact digest, and stage. Persist progress as a public receipt so retries resume only the same immutable candidate; changed input starts a new release. Wait for predecessor CI before downstream pushes. Cancellation records partial state, never success.

## Digest boundary

Reuse source verification in build workflows. Record the registry-returned immutable digest, not a generated tag. Handoff verifies declared consumer manifest references and names each mismatch. Arbora validates the trusted candidate and owns runtime topological rollout. Deployment owners apply reviewed digest-pinned manifests and publish runtime probes. No cluster login, secret lookup, or manifest mutation belongs in generic order tests.

## Portable execution

Provide read-only dry run over fixture artifacts. Contract tests replace hosted CI and registry responses with deterministic fixtures. Production workflow obtains scoped credentials per stage and redacts logs. Build may need self-hosted capability; parsing, ordering, source binding, and consumer-reference tests run on hosted runners. Release failure does not block unrelated source PRs.

## Security, compatibility, and quality

Use least-privilege GitHub permissions, immutable action refs, no persisted checkout credential, and explicit publication authorization. Existing floating-tag consumers migrate before readiness. Apply configured CCCC (`complexity-staged`/`complexity-census`, 10/15), `jscpd-differential` and advisory census, `dupehound-changed`, KISS staged/census, YAML validation, and workflow contract tests. Reuse existing helpers and avoid duplicate checks across workflows.

## Kernel wheel completeness (PIPE-RELEASE-R004)

Data flow: release bundle step → `main` (`.github/actions/wheel-readiness/readiness.py:325`) → `aggregate` (`bundle.py:98`) → `missing_cells` (new `kernels.py`) → receipt with `kernel_cells`, or `KernelCellMissing`.

Types: `KernelCell(target, python_tag, wheel)` and `KernelMatrix(required, found)`. A wheel counts when its archive lists a compiled extension that matches its platform tag. The gate fails closed on a missing cell.

Reused: `TARGETS` (`targets.py:7`), `wheel_set` (`readiness.py:233`), `aggregate` (`bundle.py:98`). New: the Python version axis and the binary check. Existing code: `targets.py:7`, `targets.py:30`, `bundle.py:98`, `readiness.py:233`, `readiness.py:343`. Reachable today: no, the matrix check does not exist; `aggregate` is reached.

Decision: check the archive contents rather than the filename tag, because a pure-Python wheel can carry a platform tag. Rejected: trusting the platform tag alone. Search terms used: kernel, manylinux, abi3, wheel, `.so`.

Cross-repository: the Medulla kernel wheels consume this gate, owner prefix `EG`; contract name `kernel_cells`.

## Dependency loop gate (PIPE-RELEASE-R005)

Data flow: `pipelines-hook supply-chain` → `main` (`cli.py:79`) → gate (`gate.py:71`) → `dependency_findings` (`dependencies.py:79`) → `loop_findings` (new `dependency_cycles.py`) → `SC-DEP-LOOP` findings.

Types: `DependencyEdge(source_group, target_group, via)` and `DependencyLoop(members)`. Groups cover root, optional extras and development groups. A loop is a strongly connected component above one member, or a self-loop.

Reused: `declared_dependencies` (`dependencies.py:32`) for group tables; the component search shape from `import_cycles.py:41`. Existing code: `dependencies.py:32`, `dependencies.py:79`, `gate.py:71`, `cli.py:28`, `import_cycles.py:41`. Reachable today: no, nothing builds a group graph; `dependency_findings` is reached.

Decision: build the graph per manifest at gate time. Rejected: detecting loops only at lock time, because the lock step already fails late and without member names. Search terms used: circular, cycle, include-group, strongly connected, optional-dependencies, dependency-groups.


## Project version consistency (PIPE-RELEASE-R006)

Data flow: project-version-sync CLI/shared hook -> one selected Git snapshot -> canonical bump configuration -> complete typed location inventory -> extraction and template checks -> located verdict.
Existing code: `.config/bumpversion.cfg:2` declares current version; `.config/bumpversion.cfg:6` contains only the metadata replacement. `pipelines_hooks/core/versions_gate.py:10` verifies pinned scanner executables and provides no project synchronization. `pipelines_hooks/core/comparison.py:53` selects index versus committed input; `pipelines_hooks/core/gitenv.py:81` reads Git blobs. `pipelines_hooks/cli.py:59` supplies dispatch and typed failure handling.
Reachable today: no. There is no project-version-sync module or gate registration. Searches for bump, version sync, version consistency and metadata version found the bump configuration and scanner check, not an implementation. Reuse Git snapshot/error helpers and the existing bump tool's format; keep scanner-versions and release R001–R005 unchanged.
Attach point: new `pipelines_hooks/release/project_version.py:main` is registered at `pipelines_hooks/cli.py:13`. Publish `project-version-sync` beside the existing version hook at `.pre-commit-hooks.yaml:67`, with `pass_filenames: false` and `always_run: true`. The self-run hook configuration is consumed by `.github/workflows/ci.yml:86`. This is an offline code gate, with no registry, release upload or live network prerequisite.
Configuration: use `.config/bumpversion.cfg` by default, with an explicit CLI locator for a reviewed alternative. The canonical bump file owns all version values and file replacement entries. A versioned adapter derives the typed inventory from that file; role/selector annotations must remain compatible with the chosen bump tool. No separate independently maintained version list is permitted. Missing role declarations or incompatible format features fail closed. Multiple effective authorities are ambiguous even if their versions happen to agree; sample documents are not effective configuration authorities.
Extraction: metadata selectors address a declared string key, source selectors address a declared literal assignment, and documentation selectors address an explicit version marker. An adapter may support further formats only through a named schema version. Every selector has an exact positive match count, and every match must equal current_version. Extract the observed token independently of current_version so drift yields version-mismatch, not a misleading missing-selector error. Prefixes, suffixes and quoting are part of the declared templates; round-trip checks render templates against the observed token and a synthetic next token to ensure replacement changes only that token. Do not import source modules, evaluate expressions or silently normalize distinct spellings. Preserve historical changelog versions, external dependency pins and unrelated version examples.
Snapshot boundary: the pre-commit invocation reads the index, including staged configuration, and records its tree identity. CI/range invocation uses the selected committed tree and reads its configuration from that same tree. Changed paths choose the input mode, never reduce the declared inventory. Reject missing Git objects and non-regular Git entries. Worktree dirt and untracked files cannot rescue missing or stale tracked evidence. The gate performs no bump, commit or tag operation, even if the canonical config enables those operations for the separate bump command.
Decision: enforce complete agreement with one config and emit deterministic observations. A repository with metadata-only bump entries does not satisfy source/docs coverage. Adapt existing extraction/replacement declarations instead of creating a second version authority. Reject substring grep, import-based discovery and relabeling scanner verification as project consistency.
Cross-repository rows: none added. Each consumer supplies its own compatible canonical bump configuration and adopts the shared hook. Version selection and release authorization remain with the repository owner; this gate only checks consistency.
Source credit: audit candidate PIPE:5 from the source document “Verify” supplies the one-configuration requirement. No research citation was supplied. Exact source lineage and record digest remain in the audit ledger.
Acceptance: implement `tests/hooks/test_project_version_sync.py`, then run `uv run --frozen python -m pytest tests/hooks/test_project_version_sync.py -q`. The fixture initializes Git and installs the published local hook entry. It checks equal versions, independent drift in all roles, canonical-version drift, missing/malformed/duplicate configuration, extraction counts that differ from the declared count and unsupported dynamic source expressions. A location declaring two matches passes only when both tokens agree with current_version; one or three matches fail. Assert index/commit isolation in both directions, no writes by the gate, and location/digest evidence. In a separate disposable fixture, invoke the real configured bump command, verify all three replacements and run the gate again. Parser-only tests do not close the CLI/hook acceptance row.


## Shared gates workflow and tag-only publish (PIPE-RELEASE-R007)

Data flow: caller `gates` job -> `gates_pipeline.yml@main` -> pre-commit stages over the diff range -> `pr-test-scope` subset -> verdict; release caller -> `python_pipeline.yml` `require-tag` guard -> publish.
Existing code: `.github/workflows/python_pipeline.yml` publishes and tags on whatever ref calls it; `pipelines_hooks/ci_replica/test_scope.py` maps a diff to tests; every core repository hand-writes the gates block. Reachable today: no shared gates workflow, `require-tag` or `fast-tests` exists.
Attach point: new `.github/workflows/gates_pipeline.yml`; `python_pipeline.yml` input `require-tag`; `templates/workflows/gates-skip.yml`; `pipelines_hooks/ci_replica/fast_tests.py` registered at `pipelines_hooks/cli.py` and `.pre-commit-hooks.yaml`; reference `reference/ci-standard.md`.
Decision: additive only, every input defaulted, because every caller references pipelines at `@main`. Concurrency stays with the caller (a reusable workflow cannot set it). Rejected: removing tagging from `python_pipeline` now, since that would break today's push callers; callers opt in with `require-tag` when they move to tag-triggered releases.
Acceptance: `uv run --frozen python -m pytest tests/test_gates_pipeline_contract.py tests/hooks/test_fast_tests.py -q`.


## Amendments

### 2026-10-12 — PIPE-RELEASE-R003 wheel output boundary

The Python publisher must build a wheel-only output directory. Use the build
tool option that prevents an auxiliary `.gitignore` file. Keep `wheel_set`
strict: hidden files, source archives, other files and symlinked wheels still
block publication. `tests/test_python_wheel_output.py` executes the publication
step's actual build command against a small pure-Python package with network
access disabled and the existing build environment. It checks the valid wheel
and injects unwanted output to prove refusal. No index proof or upload runs in
this regression.

## Role closure, phased release and version inventory

These child contracts preserve the existing publication, dependency-cycle and version-consistency obligations.
The public dispatcher remains `pipelines_hooks/cli.py:79` through `run_gate` at line 59.
New CLI registrations and modules below are proposed attachment points, not existing delivery receipts.
Repository-manager retains release admission and fleet ordering; Scion SDK retains package compatibility semantics.
Existing release source-binding and artifact qualification rules remain independent prerequisites.

### Role extra closure

`PIPE-RELEASE-R005.7` through `PIPE-RELEASE-R005.12` extend `PIPE-RELEASE-R005`.
Register role-closure at pipelines_hooks/cli.py:13 through run_gate at line 59. Proposed role_closure.main must consume the package producer artifact before release readiness aggregation at .github/actions/wheel-readiness/bundle.py:98. Reuse dependency groups from R005 and static boundaries from PIPE-PAGES-R021.7. Static import analysis alone cannot prove installed closure.

### Release phase progress

`PIPE-RELEASE-R001.1` through `PIPE-RELEASE-R001.6` extend `PIPE-RELEASE-R001`.
Create release-phases at pipelines_hooks/cli.py:13 through run_gate at line 59. Proposed phases.main must consume repository-manager readiness and ordered candidate exports before invoking release producers. Repository-manager retains fleet-order authority. The CLI emits JSON lines to its consuming UI. Overflow disconnects that subscriber with an explicit sequence-gap record; resumption requires a fresh authoritative progress snapshot.

### Version inventory completeness

`PIPE-RELEASE-R006.7` through `PIPE-RELEASE-R006.12` extend `PIPE-RELEASE-R006`.
Extend proposed project_version.main through pipelines_hooks/cli.py:13 and run_gate at line 59. Reuse R006 snapshot selection. Add a code-enhancer consumer binding: owner repository, revision, real entry-point path and function, invocation argv and inventory digest. That entry must invoke project-version-sync before admitting a version proposal. Its concrete owner call site remains unresolved; a generic CLI pass cannot prove consumer integration.

### Major upgrade pre pin

`PIPE-RELEASE-R001.7` through `PIPE-RELEASE-R001.12` extend `PIPE-RELEASE-R001`.
Extend the proposed release-phases entry at pipelines_hooks/cli.py:13 through run_gate at line 59. Place the Scion SDK compatibility adapter before version-bump argv execution and pin writes. Repository-manager retains fleet rollout admission; Scion SDK retains compatibility semantics. Pipelines must consume those producer receipts without duplicating certification rules.

The package owner must publish the authoritative supported-role export before role completeness can be evaluated.
The concrete code-enhancer owner and production call site remain unresolved prerequisites for consumer integration.
A generic CLI fixture cannot close that consumer obligation. Six child rows do not themselves establish completeness.
Delay measurement starts after predecessor qualification. Restarted runs must revalidate and wait a fresh full interval.
Preflight refusal writes no pins. Post-admission failures retain explicit partial effects; no cross-repository atomicity is claimed.

### 2026-10-12 — PIPE-RELEASE-R002 publication source binding

Reuse the source verifier's frozen workflow commit and wheel readiness proof.
Before Python or native-wheel upload, compare the frozen source with checkout
HEAD, release metadata and the workflow SHA. Read the repository and exact tag
through GitHub's API; peel annotated tags with a bounded traversal. A conflicting
tag, unavailable metadata or unsupported target blocks publication. Repeat the
check before creating the release and pass the verified full commit explicitly
as its target. A moving default branch cannot select the release source.

The guard never creates or changes a tag. Existing releases and package versions
remain untouched. Tests in `tests/test_release_source.py` exercise a branch
advance after source freeze, lightweight and annotated tag conflicts, metadata
failures and the real shared action wiring using disposable Git repositories.
No package build, index upload or live release is required by these tests.


### Amendment — language-specific PR selection (2026-10-18)

PIPE-RELEASE-R007.2 keeps the shared scope collector neutral to language.
Python selection filters helper modules before adding test paths; Rust selection
retains Cargo package names without applying pytest filename rules. Regression
coverage includes mixed Python/Rust changes, duplicate crate hits, empty and
unrelated changes, and conservative Rust fallback. This repairs omitted Rust
checks without changing the full-suite or unavailable-diff contracts.
