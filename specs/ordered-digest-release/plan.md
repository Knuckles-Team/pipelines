# Architecture — PIPE-RELEASE

## Existing components and flow

`.github/workflows/container_pipeline.yml` builds caller images. `.github/actions/verify-source-commit/` binds a build to the checkout. Python, maturin, services, and Pages workflows provide existing job contracts. Workflow contract tests classify hosted gates. Extend these seams with a small release coordinator and schema; do not build another image builder or fork each workflow.

Flow: candidate declaration → schema/graph validation → exact source/build/CI receipts → deterministic dependency order → stage publication → CI observation → digest mapping → consumer manifest verification → deployment-owner handoff. Inputs and outputs are versioned public artifacts with SHA-256 digests, source commits, and run URLs. `latest` is never release authority.

## Candidate model

Each candidate has stable repository identity, full source commit, artifact/image digest, predecessor component IDs, profile digest, API/schema compatibility range, required public CI check receipts, and consumer manifest references. Validate graph before any write. Reject unknown IDs, duplicates, self edges, cycles, malformed digests, wrong source provenance, and floating references. Keep credentials out of manifest.

## Qualification and ordering

Use one deterministic topological sort and dependency closure. Query hosted checks for exact revisions; absent, skipped, timed-out, or failing mandatory checks block. Derive an idempotency key from candidate-set digest, commit, artifact digest, and stage. Persist progress as a public receipt so retries resume only the same immutable candidate; changed input starts a new release. Wait for predecessor CI before downstream pushes. Cancellation records partial state, never success.

## Digest boundary

Reuse source verification in build workflows. Record the registry-returned immutable digest, not a generated tag. Handoff verifies declared consumer manifest references and names each mismatch. GraphOS validates the trusted candidate and owns runtime topological rollout. Deployment owners apply reviewed digest-pinned manifests and publish runtime probes. No cluster login, secret lookup, or manifest mutation belongs in generic order tests.

## Portable execution

Provide read-only dry run over fixture artifacts. Contract tests replace hosted CI and registry responses with deterministic fixtures. Production workflow obtains scoped credentials per stage and redacts logs. Build may need self-hosted capability; parsing, ordering, source binding, and consumer-reference tests run on hosted runners. Release failure does not block unrelated source PRs.

## Security, compatibility, and quality

Use least-privilege GitHub permissions, immutable action refs, no persisted checkout credential, and explicit publication authorization. Existing floating-tag consumers migrate before readiness. Apply configured CCCC (`complexity-staged`/`complexity-census`, 10/15), `jscpd-differential` and advisory census, `dupehound-changed`, KISS staged/census, YAML validation, and workflow contract tests. Reuse existing helpers and avoid duplicate checks across workflows.

## Kernel wheel completeness (PIPE-RELEASE-R004)

Data flow: release bundle step → `main` (`.github/actions/wheel-readiness/readiness.py:325`) → `aggregate` (`bundle.py:98`) → `missing_cells` (new `kernels.py`) → receipt with `kernel_cells`, or `KernelCellMissing`.

Types: `KernelCell(target, python_tag, wheel)` and `KernelMatrix(required, found)`. A wheel counts when its archive lists a compiled extension that matches its platform tag. The gate fails closed on a missing cell.

Reused: `TARGETS` (`targets.py:7`), `wheel_set` (`readiness.py:233`), `aggregate` (`bundle.py:98`). New: the Python version axis and the binary check. Existing code: `targets.py:7`, `targets.py:30`, `bundle.py:98`, `readiness.py:233`, `readiness.py:343`. Reachable today: no, the matrix check does not exist; `aggregate` is reached.

Decision: check the archive contents rather than the filename tag, because a pure-Python wheel can carry a platform tag. Rejected: trusting the platform tag alone. Search terms used: kernel, manylinux, abi3, wheel, `.so`.

Cross-repository: the epistemic-graph kernel wheels consume this gate, owner prefix `EG`; contract name `kernel_cells`.

## Dependency loop gate (PIPE-RELEASE-R005)

Data flow: `pipelines-hook supply-chain` → `main` (`cli.py:79`) → gate (`gate.py:71`) → `dependency_findings` (`dependencies.py:79`) → `loop_findings` (new `dependency_cycles.py`) → `SC-DEP-LOOP` findings.

Types: `DependencyEdge(source_group, target_group, via)` and `DependencyLoop(members)`. Groups cover root, optional extras and development groups. A loop is a strongly connected component above one member, or a self-loop.

Reused: `declared_dependencies` (`dependencies.py:32`) for group tables; the component search shape from `import_cycles.py:41`. Existing code: `dependencies.py:32`, `dependencies.py:79`, `gate.py:71`, `cli.py:28`, `import_cycles.py:41`. Reachable today: no, nothing builds a group graph; `dependency_findings` is reached.

Decision: build the graph per manifest at gate time. Rejected: detecting loops only at lock time, because the lock step already fails late and without member names. Search terms used: circular, cycle, include-group, strongly connected, optional-dependencies, dependency-groups.
