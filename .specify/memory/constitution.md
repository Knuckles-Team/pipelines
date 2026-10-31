# Arbora ecosystem constitution

This constitution states the principles that every repository of the ecosystem follows. Each principle traces to a gate, a standard or a test that enforces it today. A `plan.md` Constitution Check answers the "Plan check" question of each article.

**Version**: 1.2.0 | **Ratified**: 2026-10-31 | **Last amended**: 2026-10-31

## Core Principles

### I. One owner per concept

Each concept, fact, decision and operation has exactly one owning repository. Other repositories reference the owner by stable ID and never keep a copy.

*Rationale*: Two owners drift apart. A second planner, store or policy table for an owned capability is a defect, not a convenience.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: coupling, sdk-conformance, connector-standard, spec-standard -->
- `coupling`: coupling
- `sdk-conformance`: Connector uses SDK capabilities instead of its own copies (warns)
- `connector-standard`: Connector standard - no committed central files, shared codespell, security checks, API parity
- `spec-standard`: Spec standard - names, file set, title, index
<!-- generated:end -->

Standards and tests:

- [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md): repository table, routing procedure and forbidden-import matrix.
- [Spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): the Ownership boundaries section.
- `tests/hooks/test_coupling.py`, `tests/hooks/test_sdk_conformance.py`.

**Plan check:** Does the plan name one owning repository per part and file each part in that owner's `specs/`?

### II. Extend before you create

A change starts with a search of the existing specs and code. It extends the owning spec or the live component. It creates a new one only when no owner exists, and records the search.

*Rationale*: Parallel lanes otherwise produce duplicate implementations and duplicate specs. An audit or review never owns a spec of its own.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: spec-standard, spec-decomposition, spec-bind-suggest -->
- `spec-standard`: Spec standard - names, file set, title, index
- `spec-decomposition`: Spec decomposition - requirements/tasks/test-spec/status.json IDs agree
- `spec-bind-suggest`: Spec bind suggest - rank existing tests that may verify a SPECIFIED or LANDED row (read-only)
<!-- generated:end -->

Standards and tests:

- [Spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): the Extend first and Audits sections.
- `tests/test_spec_standard.py`, `tests/hooks/test_spec_bind_suggest.py`.

**Plan check:** Does the plan record the search for an owning spec and component, and extend the owner where one exists?

### III. Specs describe the current state only

A spec and its rows state what is true now. The generator computes the state of every row from rows, `Spec:` trailers and bound tests. Git holds history.

*Rationale*: A hand-written status or a history view goes stale. A computed state cannot disagree with the code.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: spec-standard, spec-status, spec-trailers -->
- `spec-standard`: Spec standard - names, file set, title, index
- `spec-status`: Spec status - generated specs/*/status.json matches requirements.md, git history and test bindings
- `spec-trailers`: Spec trailers - verified delivery or constrained evidence withdrawal
<!-- generated:end -->

Standards and tests:

- [Spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): the States and The gate sections.
- `tests/test_spec_standard.py::test_status_header_is_a_finding`, `tests/hooks/test_spec_status.py`, `tests/hooks/test_spec_trailers.py`.

**Plan check:** Does every new row state present behavior, with its test named, and no state or history text?

### IV. Requirements are neutral and controlled

Specs, plans and tasks describe our capability in generic terms and open standards. They never name a third-party product or vendor. A product name may appear only in a dependency manifest, in vendored-source attribution or in an upstream pin, such as the upstream source line of a vendored skill. Requirement text never carries one. Sentences hold 20 words or fewer and use `must`, `should` or `may`.

*Rationale*: A product name dates a requirement and ties it to a vendor. Short, uniform sentences make a requirement testable.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: spec-standard, ste-staged, ste-census, ste-staleness-census -->
- `spec-standard`: Spec standard - names, file set, title, index
- `ste-staged`: EG-STE-Lite - staged or CI docs, diff-scoped
- `ste-census`: EG-STE-Lite census - every in-scope doc, enforced
- `ste-staleness-census`: Doc staleness census - every in-scope doc, enforced
<!-- generated:end -->

Standards and tests:

- [Wording standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ste.md) and the Wording section of the spec standard.
- `tests/test_spec_third_party_names.py`, `tests/hooks/test_ste.py`.

**Plan check:** Does the new spec text avoid third-party product names and keep each sentence to 20 words or fewer?

### V. Hard cutover, no legacy path

A change that replaces a path removes the old path in the same release. The repository holds no fallback, shim, alias, compatibility layer or "remove later" row.

*Rationale*: A kept legacy path doubles the surface to test and never gets removed. The operator upgrades; the code does not carry the past.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: no-legacy-concepts, sprawl, no-stub, stubs, lockfile-version-mirrors -->
- `no-legacy-concepts`: No legacy numeric-pillar concept markers
- `sprawl`: Anti-sprawl (versioned clones, merge artifacts, tracked binaries)
- `no-stub`: No production stub markers or unmarked NotImplementedError
- `stubs`: No stub bodies and no deferred-work comments
- `lockfile-version-mirrors`: lockfile-version-mirrors
<!-- generated:end -->

Standards and tests:

- [Gate standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/gate-standard.md): the Rules section deletes a duplicate hook rather than keeping it.
- `tests/hooks/test_no_legacy_concepts.py`, `tests/hooks/test_hygiene.py`, `tests/hooks/test_code.py`.

**Plan check:** Does the plan delete the old path, with its callers, in the same release, and add no shim or alias?

### VI. Names carry no version suffix

A component, module, class or file name never carries a version marker such as `V1`, `v2` or `_new`. The version lives in package metadata and in the wire contract.

*Rationale*: A suffixed name freezes a stale generation next to the live one and invites a second implementation.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: sprawl, connector-name, project-version-sync -->
- `sprawl`: Anti-sprawl (versioned clones, merge artifacts, tracked binaries)
- `connector-name`: Connector names agree with the declared fleet name
- `project-version-sync`: Project version sync - metadata, source and documentation agree with one canonical bump configuration
<!-- generated:end -->

Standards and tests:

- [Gate standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/gate-standard.md): the `sprawl` member covers versioned clones.
- `tests/hooks/test_hygiene.py`, `tests/hooks/test_connector_name.py`, `tests/hooks/test_project_version_sync.py`.

**Plan check:** Does every new name describe intent, with no version or generation suffix?

### VII. One engine, no second database, no sync

Facts and durable state live in one engine. No repository keeps a second database, a mirror or a sync job for them. An external database is a connector source.

*Rationale*: A copy of a fact needs a sync, and a sync needs a conflict policy. One engine removes both.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: coupling, sdk-conformance, import-cycles -->
- `coupling`: coupling
- `sdk-conformance`: Connector uses SDK capabilities instead of its own copies (warns)
- `import-cycles`: Import cycles - zero eager cycles
<!-- generated:end -->

Standards and tests:

- [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md): the forbidden-import matrix lists the storage packages each repository must not import.
- `tests/hooks/test_coupling.py`, `tests/hooks/test_dependency_cycles.py`.

**Plan check:** Does the plan store every fact in the one engine, with no second store or sync job?

### VIII. Ask the graph, not a bespoke operation

A catalog, lineage or source question is answered by a general query over the graph, through an existing intent tool. A new read operation is added only when no query can express it.

*Rationale*: A per-question read operation multiplies the served surface. The ontology and its competency questions already answer the question.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: connector-ontology-map, connector-surface-audit -->
- `connector-ontology-map`: Propose and apply parent classes for orphan connector ontology classes (manual)
- `connector-surface-audit`: Connector ships and serves tools, prompts, skills, resources and a parent-linked ontology (reports)
<!-- generated:end -->

Standards and tests:

- [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md): the worked examples route reads to the graph.
- `pipelines_hooks/hygiene/ontology_cqs.json`, `tests/hooks/test_ontology_graph_check.py`.

**Plan check:** Can every read in the plan be a graph query, and does the plan add no per-question read operation?

### IX. Connectors depend on the SDK and are called through arbora

A connector reaches its external system only through the SDK. It depends on the SDK alone. It serves one tool per API operation and serves skills, prompts and resources the fastmcp way. Callers reach a connector through arbora.

*Rationale*: One transport, auth and TLS implementation serves every connector. Condensed action tools hide operations from callers and from the audit.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: connector-standard, connector-name, connector-graphql, sdk-conformance, connector-surface-audit, release-standard -->
- `connector-standard`: Connector standard - no committed central files, shared codespell, security checks, API parity
- `connector-name`: Connector names agree with the declared fleet name
- `connector-graphql`: Connector GraphQL is declared via the SDK graphql extra (warns)
- `sdk-conformance`: Connector uses SDK capabilities instead of its own copies (warns)
- `connector-surface-audit`: Connector ships and serves tools, prompts, skills, resources and a parent-linked ontology (reports)
- `release-standard`: release standard (connector has docker/Dockerfile and calls the shared container pipeline; warns)
<!-- generated:end -->

Standards and tests:

- [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md): Connectors row and forbidden-import matrix.
- The connector scaffold of the `mcp-builder` skill in `universal-skills`: tools, sources, ontology, prompts, skills and tests.
- `tests/hooks/test_connector_name.py`, `tests/hooks/test_connector_surface.py`, `tests/hooks/test_connector_graphql.py`, `tests/hooks/test_sdk_conformance.py`.

**Plan check:** Does the connector depend on the SDK alone, serve one tool per operation, and get called only through arbora?

### X. Every ontology class rolls up to the core

Every pack class extends a core class. A pack never imports the core ontology as a bridge. A parent is a reviewed class, never an invented one.

*Rationale*: An orphan class is invisible to cross-source questions. Rolling up keeps one vocabulary.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: connector-ontology-map -->
- `connector-ontology-map`: Propose and apply parent classes for orphan connector ontology classes (manual)
<!-- generated:end -->

Standards and tests:

- `pipelines-hook connector-ontology-map graph-check` reports unreachable and unrolled classes.
- `tests/hooks/test_ontology_graph_check.py`, `tests/hooks/test_ontology_orphan_map.py`.

**Plan check:** Does each new ontology class extend a core class, with no import of the core ontology?

### XI. Code stays small, simple and unduplicated

Functions, files and classes stay inside the KISS limits. Complexity stays inside the cyclomatic and cognitive caps. New clones of existing code are refused. The numbers are in the thresholds table.

*Rationale*: Small units are testable and reviewable. Duplicates drift apart. One tool measures each property.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: kiss-staged, kiss-census, complexity-staged, complexity-census, dupehound-changed, jscpd-differential, jscpd-census, scanner-versions -->
- `kiss-staged`: KISS - staged Python/Rust, diff-scoped
- `kiss-census`: KISS census - every tracked file plus orphan modules, enforced
- `complexity-staged`: Complexity (cccc) - no new or worsened function over cyclomatic 10 / cognitive 15
- `complexity-census`: Complexity census (cccc) - absolute zero outside the terms of acceptance
- `dupehound-changed`: Clone gate - changed functions (dupehound)
- `jscpd-differential`: Clone gate - new blocks (jscpd, merged-tree differential)
- `jscpd-census`: Clone census - tracked tree (jscpd, advisory)
- `scanner-versions`: Pinned native scanners are installed at their exact versions
<!-- generated:end -->

Standards and tests:

- [Gate standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/gate-standard.md): the Advisory checks section lists the clone and complexity gates.
- `tests/hooks/test_kiss.py`, `tests/hooks/test_complexity.py`, `tests/hooks/test_clones.py`, `tests/hooks/test_structural_limits.py`.

**Plan check:** Do all new and changed units stay inside the limits in the thresholds table, with no copy of existing code?

### XII. No ratchets and no suppressions

A finding is fixed at its cause. A threshold is never raised to fit what passes, a finding is never suppressed, and a baseline never hides debt. Debt stays visible in the census.

*Rationale*: A ratchet turns a gate into a record of past failures. Exposed debt gets paid down.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: swallowed-errors, event-loop-blocking, kiss-census, complexity-census, pre-commit-patch-safety -->
- `swallowed-errors`: Swallowed errors - no cause-dropping handler added
- `event-loop-blocking`: Event-loop blocking - no blocking call added in async code
- `kiss-census`: KISS census - every tracked file plus orphan modules, enforced
- `complexity-census`: Complexity census (cccc) - absolute zero outside the terms of acceptance
- `pre-commit-patch-safety`: No live uncommitted work parked in the pre-commit patch cache
<!-- generated:end -->

Standards and tests:

- [Gate standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/gate-standard.md): a hook that only keeps another gate passing is deleted.
- The header of `.config/kiss.toml` states that the file is not a baseline.
- `tests/hooks/test_code.py`, `tests/hooks/test_hygiene.py`, `tests/hooks/test_complexity_exempt_score.py`.

**Plan check:** Does the plan fix each finding at its cause, with no raised limit, suppression or baseline entry?

### XIII. Zero flakes

A test either passes or fails for a reason. A gate never counts a re-run pass for a product failure. A flaky test is fixed at its cause and proved by repeated parallel runs.

*Rationale*: A gate that passes on retry measures luck. Only a lost runner or similar infrastructure failure may be re-run, and the run states it.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: tests-fast, test-layout, gate-set -->
- `tests-fast`: Fast tests - only the tests the pushed diff affects (120 s cap)
- `test-layout`: Test layout independence - isolated order and fixture inventory
- `gate-set`: Gate sets - run the pre-land fast or the post-land full set against a source
<!-- generated:end -->

Standards and tests:

- [Gate standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/gate-standard.md): the Gate sets section classifies a failure as product or infrastructure.
- `tests/hooks/test_landing_policy.py`, `tests/hooks/test_test_layout_independence.py`, `tests/hooks/test_fast_tests.py`.

**Plan check:** Do the new tests pass in any order and in parallel, with no gate that accepts a re-run pass?

### XIV. Compile first, then review

Verification runs the cheapest decisive check first: format, hygiene, secrets, types, then the affected tests. A reviewer reads a change only after it compiles and the fast set passes.

*Rationale*: A compile failure found at review wastes a human pass. The fast set decides in seconds.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: gate-set, tests-fast, uv-lock-check -->
- `gate-set`: Gate sets - run the pre-land fast or the post-land full set against a source
- `tests-fast`: Fast tests - only the tests the pushed diff affects (120 s cap)
- `uv-lock-check`: uv.lock is current (uv lock --check; never mutates)
<!-- generated:end -->

Standards and tests:

- [Gate standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/gate-standard.md): the Gate sets section declares the fast set.
- `pipelines_hooks/gate_sets.toml`, `tests/hooks/test_gate_sets.py`.

**Plan check:** Does the plan name the fast-set commands that run before review?

### XV. Python 3.14 standard, 3.12 floor

Everything that runs uses Python 3.14. Package metadata keeps a 3.12 floor, tooling targets that floor, and each repository has one backward leg on 3.12.

*Rationale*: One runtime keeps environments equal. The floor keeps downstream users supported.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: project-version-sync, uv-lock-check, lockfile-version-mirrors -->
- `project-version-sync`: Project version sync - metadata, source and documentation agree with one canonical bump configuration
- `uv-lock-check`: uv.lock is current (uv lock --check; never mutates)
- `lockfile-version-mirrors`: lockfile-version-mirrors
<!-- generated:end -->

Standards and tests:

- [Gate standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/gate-standard.md): the Python version section.
- [CI standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ci-standard.md): the `backward-python` input.
- [Python wheel release readiness](https://github.com/Knuckles-Team/pipelines/blob/main/reference/python-release-readiness.md).

**Plan check:** Does the change run on Python 3.14, use no syntax newer than 3.12, and keep the one 3.12 leg?

### XVI. Install and deploy only from published releases

Every package installs from the public package index. A deployment uses a published release. A git, path or URL source is a development aid and never a release dependency.

*Rationale*: A source install cannot be reproduced or audited. A published release has one digest and one identity.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: dependency-readiness, packaging-roles, uv-lock-check, supply-chain, release-standard -->
- `dependency-readiness`: RELEASE dependency readiness (repository-manager)
- `packaging-roles`: Packaging role/extra closure (explicit contract and evidence paths)
- `uv-lock-check`: uv.lock is current (uv lock --check; never mutates)
- `supply-chain`: Immutable workflow, container and dependency sources
- `release-standard`: release standard (connector has docker/Dockerfile and calls the shared container pipeline; warns)
<!-- generated:end -->

Standards and tests:

- [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md): the opening rule on package installs.
- [Python wheel release readiness](https://github.com/Knuckles-Team/pipelines/blob/main/reference/python-release-readiness.md), [container runtime](https://github.com/Knuckles-Team/pipelines/blob/main/reference/container-runtime.md) and [publication identity](https://github.com/Knuckles-Team/pipelines/blob/main/reference/publication-identity.md).
- `tests/hooks/test_dependency_readiness.py`, `tests/hooks/test_supply_chain.py`, `tests/test_release_version_guard.py`.

**Plan check:** Does every dependency and deployment in the plan come from a published release?

### XVII. Publish the gate's tool before the gate

A gate that a consumer adopts must run from a published release of its tool. The shared hooks are referenced at `main`, and a hook is removed only after its last reference is gone.

*Rationale*: A gate that needs an unpublished tool fails every consumer for a reason that is not theirs.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: gate-set, validate -->
- `gate-set`: Gate sets - run the pre-land fast or the post-land full set against a source
- `validate`: Repository validation
<!-- generated:end -->

Standards and tests:

- [Pre-commit standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/precommit-standard.md): Rules 1 and 2.
- [CI standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ci-standard.md).
- `tests/hooks/test_catalogue.py::test_every_registered_gate_is_published`.

**Plan check:** Is the tool of every gate in the plan already published, before any consumer adopts the gate?

### XVIII. Landed means reachable

A row is delivered only when a production caller reaches it. The plan names the entry point, the call path and the wiring site. An orphan module is not delivered.

*Rationale*: Code that nothing calls proves nothing. A hot-path test proves the wiring.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: kiss-census, import-cycles, no-stub, spec-trailers, spec-decomposition -->
- `kiss-census`: KISS census - every tracked file plus orphan modules, enforced
- `import-cycles`: Import cycles - zero eager cycles
- `no-stub`: No production stub markers or unmarked NotImplementedError
- `spec-trailers`: Spec trailers - verified delivery or constrained evidence withdrawal
- `spec-decomposition`: Spec decomposition - requirements/tasks/test-spec/status.json IDs agree
<!-- generated:end -->

Standards and tests:

- [Spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): the wiring row and hot-path proof row rules.
- `tests/hooks/test_kiss.py`, `tests/hooks/test_spec_decomposition.py`, `tests/hooks/test_spec_trailers.py`.

**Plan check:** Does the plan trace the row from a production entry point to the new code, with a hot-path test?

### XIX. A tag push publishes, with no manual approval

A release is a `v*` tag pushed by a maintainer. The tag runs the publish jobs. A push to the default branch never publishes, and no workflow holds a merge or push token.

*Rationale*: One trigger makes a release reproducible and auditable. A manual approval step hides who released what.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: release-standard, project-version-sync, supply-chain -->
- `release-standard`: release standard (connector has docker/Dockerfile and calls the shared container pipeline; warns)
- `project-version-sync`: Project version sync - metadata, source and documentation agree with one canonical bump configuration
- `supply-chain`: Immutable workflow, container and dependency sources
<!-- generated:end -->

Standards and tests:

- [CI standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ci-standard.md): the Connector pipeline and Auto-merge and releases sections.
- [Trusted runner policy](https://github.com/Knuckles-Team/pipelines/blob/main/reference/trusted-runner-policy.yml).
- `tests/test_no_merge_workflows.py`, `tests/test_connector_release_pipeline.py`, `tests/test_trusted_runner_contract.py`.

**Plan check:** Does the release path publish only on a `v*` tag push, with no approval step and no merge token?

### XX. Secrets are never traced or logged

A credential never appears in a trace, a log, a command echo, a commit or a tracked file.

*Rationale*: A leaked credential must be rotated everywhere. Prevention is cheaper than rotation.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: secrets, security-sanitizer, secret-history, stdout-writes, env-sprawl -->
- `secrets`: Secrets and identity - credentials, host/identity data, commit identities
- `security-sanitizer`: Security and garbage sanitizer
- `secret-history`: Credential-shaped content in the unpublished commit range
- `stdout-writes`: Stdio JSON-RPC purity (no stdout writes in the served surface)
- `env-sprawl`: Configuration - environment read only in the declared module
<!-- generated:end -->

Standards and tests:

- [Gate standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/gate-standard.md): the `secrets` group members.
- `tests/hooks/test_security.py`, `tests/hooks/test_code.py`.

**Plan check:** Does the plan keep every credential out of logs, traces, commands and tracked files?

### XXI. Public files stay portable and neutral

A public file describes capabilities generically. It never names a host, private domain, internal network, local path, deployment topology, private repository or internal tool. It holds no personal identity or operator-specific name. Environment facts live only in private operations repositories. A commit carries an allowlisted identity.

*Rationale*: A public artifact outlives its environment. A local path or private name breaks for every other reader.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: tracked-privacy, source-path-portability, public-surface, commit-identity, commit-identity-range -->
- `tracked-privacy`: Tracked artifacts contain no host-specific data, local or model identities
- `source-path-portability`: Source path portability - tracked package paths are cross-platform legal
- `public-surface`: Public README/AGENTS surface contract
- `commit-identity`: Commit identity - the commit being made has an allowlisted author and committer
- `commit-identity-range`: Commit identity (range) - every commit in the outgoing/incoming range is allowlisted
<!-- generated:end -->

Standards and tests:

- [Tracked artifact privacy](https://github.com/Knuckles-Team/pipelines/blob/main/reference/privacy.md).
- `scripts/check_public_specs.py`, `tests/hooks/test_privacy.py`, `tests/hooks/test_source_path_portability.py`, `tests/hooks/test_identity_commit.py`.

**Plan check:** Do the new public files contain only portable, neutral text?

### XXII. Names, titles and artifact placement

File and directory names are lower-case kebab-case. A tool may require upper case for `README.md`, `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `LICENSE` and `CHANGELOG.md`. A spec directory is the stable lower-case family ID with no numeric prefix. A requirement ID is upper case `<PREFIX>-R<n>`. A heading uses sentence case. A row title is a bold sentence that ends with a period. A plan lives only in specs/<family>/plan.md, a template only in `.specify/templates/` and the constitution only in `.specify/memory/`.

*Rationale*: One predictable place and one spelling for each artifact lets a person, a tool and a gate find it without a search. A second copy drifts.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: spec-standard, spec-templates -->
- `spec-standard`: Spec standard - names, file set, title, index
- `spec-templates`: Spec templates - .specify/templates equals the vended pipelines templates
<!-- generated:end -->

Standards and tests:

- [Spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): the Names, Files and Optional artifacts sections.
- `tests/test_spec_placement.py`, `tests/test_spec_templates.py`, `tests/test_spec_artifacts.py`.

**Plan check:** Do all new files and directories use lower-case kebab-case names and sit in the one place the constitution names for them?

### XXIII. Versioning and release

One canonical bump configuration per repository, `.bumpversion.cfg` read by bump2version, is the only way a version changes. Nobody hand-edits a version field. The `project-version-sync` gate checks that metadata, source and documentation agree, and `check-bumpversion` checks the configuration where a repository carries it. A `v*` tag push publishes the package, the image and the pages with no manual approval. A release ships only delivered cross-repository spec bundles (the PIPE-RELEASE bundle rows), in dependency order.

*Rationale*: One path for a version keeps every copy equal. A tag that publishes without a hand step leaves nothing to forget. A bundle ships whole, so a consumer never sees half a change.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: project-version-sync, release-standard -->
- `project-version-sync`: Project version sync - metadata, source and documentation agree with one canonical bump configuration
- `release-standard`: release standard (connector has docker/Dockerfile and calls the shared container pipeline; warns)
<!-- generated:end -->

Standards and tests:

- [Python release readiness](https://github.com/Knuckles-Team/pipelines/blob/main/reference/python-release-readiness.md).
- `tests/hooks/test_project_version_sync.py`, `tests/hooks/test_release_standard.py`, `tests/test_release_bundle.py`, `tests/test_no_merge_workflows.py`.

**Plan check:** Does the change bump versions only through the bump configuration and land in a delivered bundle?

### XXIV. Specifications are complete enough to implement without assumptions

Every behaviour row names the production caller chain from the entry point to the new code, the exact files to create or change, the types and fields, the refusal codes from the one refusal taxonomy, the write path, the knobs with starting values (safety and gate knobs are fixed), the `Depends on:` row IDs, each cross-repository seam by ID on both sides with a contract document, a test as `path::name` at the proof level the acceptance names, and one `Shape:` sentence that names the files, the types and the existing helper to reuse. A spec is ready only when an implementer who reasons little could deliver every row from the text alone. It holds no open `[NEEDS CLARIFICATION]` marker, no "TBD" and no undefined term, and the Build contract of its plan lists the real gate thresholds.

*Rationale*: A row that leaves a choice open makes each implementer design a different structure. A complete row makes the result the same for everyone.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: spec-standard -->
- `spec-standard`: Spec standard - names, file set, title, index
<!-- generated:end -->

Standards and tests:

- [Spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): the Complete rows and Consistency analysis sections.
- `pipelines_hooks/specs/completeness.py`, `tests/test_spec_completeness.py`.

**Plan check:** Could an implementer with no context deliver each row from its text alone?

### XXV. Small, modular units

Each package, crate and module has one responsibility. The dependency graph between packages and crates is acyclic and layered downward. A pull request compiles only the units it touches and their dependents. A repository constitution may set a size limit for its units.

*Rationale*: A small unit builds fast and reviews fast. A cycle or a wide unit forces every change to rebuild the world.

**Enforced by:**

Gates:

<!-- generated:begin constitution hooks: kiss-staged, kiss-census -->
- `kiss-staged`: KISS - staged Python/Rust, diff-scoped
- `kiss-census`: KISS census - every tracked file plus orphan modules, enforced
<!-- generated:end -->

Standards and tests:

- [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md): the forbidden-import matrix.
- `tests/hooks/test_kiss.py`, `tests/hooks/test_structural_limits.py`.

**Plan check:** Does the change keep one responsibility per unit, add no dependency cycle and compile only the units it touches and their dependents?

## Additional Constraints

The limits below are rendered from the gate configuration by `scripts/constitution.py`. A change to a limit changes the configuration, and the table follows. `python scripts/constitution.py --check` fails when the table is out of date.

<!-- generated:begin constitution thresholds -->
| Limit | Value | Source |
|---|---|---|
| Blocking checks per repository | 8 | `pipelines_hooks/gate_sets.toml` |
| Pre-land fast set | `format`, `hygiene`, `secrets`, `types`, `tests-fast` | `pipelines_hooks/gate_sets.toml` |
| Post-land full set | `spec`, `tests`, `supply-chain` | `pipelines_hooks/gate_sets.toml` |
| Affected-tests cap at push | 120 s | `pipelines_hooks/ci_replica/fast_tests.py` |
| Repository validation budget | 20 s | `.config/validation.toml` |
| Pull request gate job | 10 min | `.github/workflows/connector_pr_pipeline.yml` |
| Required-check aggregate job | 5 min | `templates/workflows/ci.yml` |
| Python requirement | `>=3.12` | `pyproject.toml` |
| Python environment | `3.14` | `.python-version` |
| Cyclomatic complexity per function | 10 | `pipelines_hooks/complexity/__init__.py` |
| Cognitive complexity per function | 15 | `pipelines_hooks/complexity/__init__.py` |
| Words per sentence | 20 | `pipelines_hooks/ste/scan.py` |
| Clone similarity (dupehound, blocking) | 0.85 | `pipelines_hooks/clones/contract.py` |
| Clone similarity (dupehound, diagnostic) | 0.8 | `pipelines_hooks/clones/contract.py` |
| Clone minimum size (dupehound) | 40 tokens | `pipelines_hooks/clones/contract.py` |
| Clone minimum size (jscpd) | 50 tokens, 5 lines | `pipelines_hooks/clones/contract.py` |
| Clone similarity (KISS) | 0.9 | `.config/kiss.toml` |
| Statements per function | 35 | `.config/kiss.toml` |
| Local variables per function | 15 | `.config/kiss.toml` |
| Calls per function | 20 | `.config/kiss.toml` |
| Positional arguments | 3 | `.config/kiss.toml` |
| Indentation depth | 4 | `.config/kiss.toml` |
| Nested function depth | 2 | `.config/kiss.toml` |
| Returns per function | 5 | `.config/kiss.toml` |
| Boolean parameters | 1 | `.config/kiss.toml` |
| Statements per try block | 3 | `.config/kiss.toml` |
| Methods per class | 10 | `.config/kiss.toml` |
| Imported names per file | 30 | `.config/kiss.toml` |
| Statements per file | 200 | `.config/kiss.toml` |
| Lines per file | 300 | `.config/kiss.toml` |
| Functions per file | 10 | `.config/kiss.toml` |
| Interface types per file | 1 | `.config/kiss.toml` |
<!-- generated:end -->

A repository may set stricter limits in its own constitution. It must not set looser limits without an amendment to this constitution.

## Development Workflow

A change follows one path from requirement to release.

1. **Spec.** Search for the owner, then extend the `requirements.md` of that spec. Each row states one outcome and names the test that proves it.
2. **Plan.** `plan.md` traces the row to the live call path and answers the Plan check of every article. It adds `contracts/`, `data-model.md`, `quickstart.md` and `research.md` only where they carry content (see the spec standard).
3. **Tasks.** `tasks.md` lists numbered task lines, each naming a row ID.
4. **Implement.** Work in the owning repository only, in units of about five minutes.
5. **Gates.** The pre-commit and pre-push hooks run the fast set. Pull request CI runs the same pre-commit file and the affected tests.
6. **Landing.** The commit carries a `Spec: <ID>` trailer. The pull request enables auto-merge and merges once the `CI required` check passes.
7. **Release bundle.** A maintainer pushes a `v*` tag. The tag publishes the package, the image and the Pages site from the published release.

Every contributor and agent works in isolation:

- One branch and one linked worktree per change, created from `main` with the worktree operations of the repository-manager connector or with plain `git worktree add`.
- Never stash and never force-push in a shared checkout.
- Stage explicit paths only. Never stage a whole tree.
- Hooks always run. Never bypass them.
- One pull request per change, with auto-merge armed once the checks are green.

## Governance

- **Authority.** This constitution outranks any repository practice that conflicts with it. A repository constitution inherits it and adds only repository-specific articles and stricter limits.
- **Amendment.** Amend by a pull request to `pipelines` that edits this file. The pull request states the impact on each article and on each repository constitution.
- **Versioning.** The constitution uses semantic versioning. A major version removes or redefines an article. A minor version adds an article or a constraint. A patch version clarifies wording.
- **Dates.** *Ratified* is the date of version 1.0.0. *Last amended* is the date of the latest merged amendment.
- **Inheritance.** Each repository keeps `.specify/memory/constitution.md`, which states the organization version it inherits and links this file.
- **Compliance.** A plan that cannot answer yes to a Plan check records the deviation. It records it in the section "Risks, alternatives, and decisions" with an owner.

**Version**: 1.2.0 | **Ratified**: 2026-10-31 | **Last amended**: 2026-10-31
