# Architecture — PIPE-PAGES

## Existing wiring

`scripts/sync_mkdocs_theme.py` defines shared assets and check mode. `.github/workflows/pages_pipeline.yml` checks out the caller and immutable workflow revision, validates `content_source`, checks theme assets, builds MkDocs, and publishes. `scripts/check_five_repo_parity.py` and `pages/parity.md` are a snapshot implementation with five fixed names and local-worktree assumptions; migrate their comparison/rendering logic rather than adding a second checker. `tests/test_pages_pipeline_contract.py` and `tests/test_pages_readiness.py` are existing test seams.

## Input and provenance

Use a tracked, schema-validated declaration of public GitHub repositories and full commit IDs. Resolve every declaration to a clean fetched tree at its exact commit, including the pipeline source revision. Fail closed on missing ref, duplicate repository, dirty or untracked overlay, missing asset, or ambiguous content source. Never silently use local `main` or a remembered worktree. Fetch credentials are read-only and scoped to public source; emit no token or machine path.

## Comparison and publication

Reuse `sync_theme(..., mode="check")` or factor shared asset enumeration used by both workflow and receipt generator. Hash exact asset bytes and record each match/mismatch. Separate deterministic verification data from generation time so repeated exact-input runs match. Publish JSON and a concise HTML/Markdown summary through the existing Pages workflow after verification. Preserve historical receipts by commit link; changing current fleet input does not upgrade old evidence.

## Integration boundary

The generic workflow accepts a versioned declaration or receipt artifact; consumers opt in and pin its SHA. Tests use disposable Git fixtures or fetched public commits, never a live cluster. Only theme/navigation promotion consumes parity. The organization entrypoint may link the summary but owns its own site assembly. No new fleet runtime or parallel policy database.

## Failure, compatibility, security, and quality

Fetch failure means unverified. Reject traversal, symlink escape, malformed revision, extra declaration fields, and out-of-tree asset names. Keep schema versioned; old local-worktree snapshots remain historical rather than current exact-ref proof. New consumers opt in; removal requires a reviewed declaration change. Use `complexity-staged`/`complexity-census` (CCCC 10/15), `jscpd-differential` plus advisory census, `dupehound-changed`, and `kiss-staged`/`kiss-census` with `.config/kiss.toml`; run workflow YAML and contract tests. Reuse existing parser/theme/Pages wiring to satisfy KISS.

## Concept references (PIPE-PAGES-R012)

Data flow: code roots named in a row (`spec_graph_core.CODE_ROOT`) -> `concepts_for_row` -> `concept_links` -> Concepts cell in `spec_row`. The link target is `/<repo>/concepts/#concept-<slug>`, defined by `render_concepts_md`.

- Mapping source. DECIDED. Derive from `CONCEPT:<ID>` markers under the code roots a row names. An explicit `Concepts:` line overrides the derived list. Evidence: `scripts/skill_graph/render_components_au.py` line 53 documents `CONCEPT:<ID>` markers in `agent_utilities/`, and `spec_graph_core.CODE_ROOT` already extracts the roots per requirement. No second registry results.
- Rejected: deriving from files that bound tests and `Spec:` commits touch. The `Spec:` parser (`pipelines_hooks/specs/trailer_ids.py`) returns IDs only, so the file list needs a new git walk per row. The walk exceeds five minutes of CI time on large repositories.
- Concept anchors. CONFIRMED missing. `render_concepts_md` emits plain bullets with no anchor. R012.3 adds them first.
- Markers outside agent-utilities. CONFIRMED rare. Repositories without markers show `no concept mapped`, counted in the caption.

## Spec relationship view (PIPE-PAGES-R013)

Data flow: `spec_graph_load` records -> `spec_edges` -> `layer_specs` -> `relation_view` and `relation_table` -> panel in `current_panels`. The view follows PIPE-PAGES-R009.

- Edges. CONFIRMED. `spec_graph_core.add_edge` computes requirement-level `depends_on` only, across repositories. `extends` does not exist yet, so R013.2 adds it from an `Extends:` line in `spec.md`. DECIDED.
- Layout. DECIDED. Collapse each strongly connected component before computing dependency depth. Roots of the condensed graph form layer 0. Each other component gets one plus the greatest prerequisite depth. Members of a component share its layer. Sort component members by stable spec ID. Preserve all original edges in the table, including self-loops and cycle edges. Tests cover chains, self-loops, and three-node cycles with incoming and outgoing dependencies. Permuting input order must leave layers unchanged.
- Size cap. DECIDED at 40 specs. Above 40 the page renders the table only and states the limit.
- Accessibility. DECIDED. The table is the text alternative, linked with `aria-describedby`.
- Rejected: Mermaid or SVG layout. R009 forbids Mermaid; SVG gives no gain over CSS columns.

## Drill-down (PIPE-PAGES-R014)

Levels: ecosystem (organisation profile README) -> repository (`/<repo>/spec-delivery/`) -> spec (`#spec-<ID>`) -> row (`#req-<ID>`). `ecosystem_components()` returns the R001 list; it adds no second list.

- Profile README. CONFIRMED to live in `Knuckles-Team/.github` (`profile/README.md`, five core projects in HTML table cells). Owner: `Knuckles-Team/.github`. BLOCKED: that repository has no `specs/` tree for the edit row. R014.5 names the owner; the producer script stays in this repository.
- Link check. DECIDED. `check_drilldown_links` fails on any unresolved component link or anchor.
- Rejected: a hand-kept component list in the README. It repeats the R001 defect.

## Same generator everywhere (PIPE-PAGES-R015)

The reusable workflow `pages_pipeline.yml` (it already runs `--output site/spec-delivery`) carries all steps. Connector rows PIPE-CONNSPEC-R101 and following, and the caller pattern PIPE-CONNSPEC-R004, are linked by ID and not restated. CONFIRMED. Client repositories adopt through their own callers. DECIDED.

## Spec delivery in the site navigation (PIPE-PAGES-R018)

Data flow: `spec_dashboard_enabled` -> `SPEC_DELIVERY_ENABLED` on the Build Docs step -> `extra.spec_delivery` in `templates/mkdocs-theme/base.mkdocs.yml` -> `announce` block in `templates/mkdocs-theme/overrides/main.html` -> link and list on every page.

- Single copy. DECIDED: `custom_dir` in `templates/mkdocs-theme/base.mkdocs.yml` points at `.pipeline-theme/templates/mkdocs-theme/overrides`, so the override and its styles are read from the theme checkout and no consumer syncs `main.html`.

- Attach point. DECIDED: the `announce` block in `templates/mkdocs-theme/overrides/main.html`, beside the site switcher. The list reuses `extra.ecosystem.sites`, the list the switcher already reads. R018.4 pins its URLs to `REPOS`.
- Root-relative link. DECIDED: `base_url` resolves from any page depth, so the link needs no host.
- Rejected: a JavaScript menu built from a generated JSON file. It fails without scripts and adds a second list.
## Site navigation on the page (PIPE-PAGES-R019)

Data flow: `ecosystem_components()` (`scripts/spec_dashboard_drilldown.py:17`) feeds `site_nav`, which `render` places before the frame (`scripts/spec_dashboard_render.py:70`). The page must stay a standalone file at `site/spec-delivery/index.html`.

- Attach point. `render` in `scripts/spec_dashboard_render.py:67` emits the nav and the skip link. DECIDED.
- Decision. The generator must render its own navigation block with relative links. The theme lane adds the matching menu entry on the documentation side. DECIDED.
- Rejected: rendering the page through MkDocs. The workflow writes the page after the MkDocs build, and the drawing sheet needs its own layout.

## Documentation claims gate (PIPE-PAGES-R020)

Data flow: `pipelines-hook public-surface` -> `main` (`pipelines_hooks/cli.py:79`) -> `run_gate` (`pipelines_hooks/cli.py:59`) -> `validate` (`pipelines_hooks/docs/public_surface.py:31`) -> `claim_findings` -> findings and exit status.

- Types. `DocClaim` holds file, line, kind and text. The kind set is closed.
- Attach point. `validate` in `pipelines_hooks/docs/public_surface.py:31`. The `public-surface` hook at `.pre-commit-hooks.yaml:183` calls it in production.
- Failure. An unresolvable claim yields `claims-unchecked`. The gate never passes silently.
- Reused. `local_link_findings` and `quick_start_findings` stay as they are. New: `claims.py` and the resolvers.
- Decision. The gate must resolve claims against the tree and the gate registry. DECIDED.
- Rejected: a hand-kept list of allowed claims. It repeats the drift the gate prevents.
- Cross-repository. Each consumer repository runs the same hook. No row restates a consumer's own docs.

## Test quality gate (PIPE-PAGES-R021)

Data flow: `pipelines-hook test-quality` -> `main` (`pipelines_hooks/cli.py:79`) -> `run_gate` (`pipelines_hooks/cli.py:59`) -> `scan` in `pipelines_hooks/code/test_quality.py` -> findings, summary line, exit status.

- Types. `TestQualityFinding` holds path, line and rule. The rule set is closed.
- Attach point. This plan creates the call site: the `GATES` entry at `pipelines_hooks/cli.py:33` and a hook beside `no-stub` at `.pre-commit-hooks.yaml:141`.
- Failure. A missing coverage report raises `CannotRun`; `run_gate` maps it to exit 2.
- Reused. `repo_root` and `load_config`, as `no-stub` uses them at `pipelines_hooks/code/no_stub.py:79`. New: the scanner.
- Decision. The gate reports the rule and location, and suppression needs a stated reason. DECIDED.
- Rejected: a coverage ratchet that only blocks a decrease. It hides existing debt.
- Cross-repository. None. Consumers adopt the hook through their pre-commit configuration.

## Scheduled mutation testing (PIPE-PAGES-R022)

Data flow: scheduled workflow -> `pipelines-hook mutation-gaps` -> `main` (`pipelines_hooks/cli.py:79`) -> `run_gate` (`pipelines_hooks/cli.py:59`) -> `survivors` in `pipelines_hooks/code/mutation_gaps.py` -> report lines and exit status.

- Types. `MutationPolicy` and `SurvivingMutation`.
- Attach point. This plan creates the call site: the `GATES` entry at `pipelines_hooks/cli.py:33` and `.github/workflows/mutation.yml`.
- Failure. An absent runner raises `Unavailable`; `run_gate` at `pipelines_hooks/cli.py:66` fails closed in CI.
- Reused. The `GATES` registry and `run_gate` error mapping. New: the runner seam and the report.
- Decision. The run is scheduled and covers core modules only. DECIDED.
- Rejected: running mutation tests on every commit. The cost exceeds the five-minute gate budget.
- Cross-repository. None.

## Located evidence (PIPE-PAGES-R020)

Data flow: public-surface CLI -> validate -> claim resolvers -> located evidence validator -> report and exit status.
Existing code: `pipelines_hooks/docs/public_surface.py:31` gathers public-surface findings; `pipelines_hooks/docs/public_surface_links.py:29` resolves local paths. `pipelines_hooks/clones/dupehound_report.py:66` validates clone locations and scores for its own format.
Reachable today: no. The public-surface gate runs, but `pipelines_hooks/docs/claims.py` and the shared measured-evidence validator are absent. Existing clone validation is format-specific and is not a generic code-enhancer finding validator.
Attach point: `validate` at `pipelines_hooks/docs/public_surface.py:31`, dispatched by `run_gate` at `pipelines_hooks/cli.py:59`.
Decision: extend R020 with code and documentation finding provenance. Reuse containment and typed error helpers; require tree-bound measurements before exporting findings. Reject unlocated prose reports rather than guessing their evidence.
Cross-repository rows: `EG-ORCH-VOCAB` owns trace storage; this producer owns gate evidence. A receipt does not confer host admission.
Source credit: the source document “SDD enhanced”, AU queue candidate 64. No research citation was supplied.
Acceptance: implement `tests/hooks/test_public_surface_claims.py`, then run `uv run --frozen python -m pytest tests/hooks/test_public_surface_claims.py -q`. The subprocess tests enter the published CLI and assert exact exit codes and structured findings.

## Component handoff evidence (PIPE-PAGES-R021)

Data flow: test-quality CLI -> component declaration -> all-static dependency traversal -> runtime boundary/reachability and separate type-only checks -> test receipts -> located findings -> verdict.
Existing code: `pipelines_hooks/code/import_graph.py:71` builds Python eager-import edges; `pipelines_hooks/code/import_cycles.py:57` runs the current import gate. `pipelines_hooks/kiss/census.py:31` checks per-file limits; its module contract explicitly excludes orphan detection.
Reachable today: no. Eager-import checks run, but `pipelines_hooks/code/test_quality.py`, its CLI registration and handoff receipt checks are absent. Reuse module discovery and target resolution. The existing eager walker skips function bodies and type-checking guards; it cannot supply the runtime graph for boundary or orphan checks. Add a separate static traversal including imports in function bodies, async functions and runtime conditional branches. Keep `build_eager_graph` exclusively on the eager-cycle path.
Attach point: the R021 gate registered at `pipelines_hooks/cli.py:14`, called by `run_gate` at `pipelines_hooks/cli.py:59` and the standard CI hook workflow.
Decision: require interfaces and risky handoff tests in a tracked declaration. Property receipts carry seed, case count and test outcome; zero cases fail. Real-component integration evidence identifies the components and forbids replacing their handoff with mocks. Pin receipts to source and declaration digests. Unsupported languages need an explicit adapter and otherwise fail closed.
Dependency kinds: eager-runtime and deferred-runtime edges both establish possible runtime reachability and receive the same interface checks. Proven type-only branches have separately declared permissions and never establish runtime reachability. Treat an unproven guard conservatively as a possible runtime edge. Resolve local imports to discovered modules using the existing target helpers; preserve the import location for evidence.
Dynamic uncertainty: computed imports that cannot be resolved statically require declared dynamic entry modules and a located uncertainty record. If that uncertainty prevents a reachability verdict, return exit 2 without a clean claim or a definite orphan.
Rejected: using the eager graph for all dependencies, or deriving architectural intent from imports alone. The eager graph misses lazy imports; declarations establish which runtime and type-only edges are permitted.
Cross-repository rows: none added; repositories supply declarations and executable handoff tests. Existing R021 placeholder, suppression and coverage behavior remains required.
Source credit: the source document “PyTests Enhancement Agent utilities”, AU queue candidate 67. No research citation was supplied.
Acceptance: implement `tests/hooks/test_test_quality_hook.py`, then run `uv run --frozen python -m pytest tests/hooks/test_test_quality_hook.py -q`. Tests run real fixture components and then the CLI against their generated receipts. `test_component_lazy_import_cli` invokes the production gate with allowed and forbidden imports inside both synchronous and asynchronous entry functions. Assert that an allowed lazy-only dependency is reachable and a forbidden lazy edge exits 1 at its line. A type-only reference remains separately classified and cannot rescue an otherwise orphaned module. A computed import with unresolved reachability exits 2 and records uncertainty. Preserve the existing real-handoff, property-proof and skipped-receipt cases.

## Skill grading (PIPE-PAGES-R023)

Data flow: skill-grade CLI -> declared skill files -> deterministic criteria -> located evidence -> grade receipt.
Existing code: `pipelines_hooks/docs/public_surface_links.py:29` checks local link containment. `scripts/readiness/evidence.py:41` proves a skills directory exists; `scripts/skill_graph/au.py:78` extracts skill catalogue data. Neither grades skill quality.
Reachable today: no. A grader and its registry entry are absent. Source searches for frontmatter, skill grade, description quality and skill metadata found no grader to reuse. Add the small grader module and reuse the link parser, scheme checks and `CannotRun` mapping. The existing link helper joins targets to the repository root; calling it unchanged misresolves nested skill links. Extend its interface with a document base while keeping the containment root independent.
Attach point: `pipelines_hooks/cli.py:14` and `pipelines_hooks/cli.py:59`, plus the published hook, catalogue and self-run configuration used by `.github/workflows/ci.yml:86`.
Decision: grade declared inputs with a versioned policy, never a model-generated subjective score. Default frontmatter requires nonempty name and description. Description checks require purpose and use-condition fields in the policy's declared form. Body sections are Usage and Examples by default. Metadata checks UTF-8 readability, a regular file, and no escaping symlink. Each criterion is binary at its declared weight; a policy replacement must name its version and predicates.
Link resolution: derive the base from the source document directory within the repository. Decode and normalize local destinations, resolve symlinks, then enforce repository containment. Parent-relative links may reach another repository directory. Never substitute the skill directory for the containment root or resolve all skill links from the repository root. Preserve root README/AGENTS behavior.
Rejected: treating directory presence or catalogue extraction as quality evidence. Grade receipts bind inputs and policy, while installation and admission remain with the host.
Cross-repository rows: `EG-TYPED-PACKS` owns skill contracts; `GRAPHOS-FLEET-R034` owns admission. This gate emits evidence and does not approve a skill.
Source credit: the source document “Code enhancement skill rule”, AU queue candidate 63. No research citation was supplied.
Acceptance: implement `tests/hooks/test_skill_grade_hook.py`, then run `uv run --frozen python -m pytest tests/hooks/test_skill_grade_hook.py -q`. Invoke the published CLI on valid and adversarial skill fixtures and assert every criterion and exit code. `test_nested_skill_links_cli` uses `skills/demo/SKILL.md` with a sibling `guide.md` and an in-repository parent link; both pass. Missing targets, decoded traversal outside the repository and symlink escape fail with located evidence. A root README fixture retains the existing resolution behavior.

## Similarity guidance (PIPE-PAGES-R024)

Data flow: changed-source CLI -> pinned structural scanner -> validated clone report -> diagnostic and enforcement partitions -> reviewed-distinct register -> located guidance.
Existing code: `pipelines_hooks/clones/dupehound.py:64` constructs the scanner command; `pipelines_hooks/clones/dupehound_report.py:66` validates findings; `pipelines_hooks/clones/dupehound_gate.py:28` enforces the reviewed register. `pipelines_hooks/clones/contract.py:14` sets 0.85 and the shared contract retains token minima and exclusions.
Reachable today: yes for detection and enforcement through `pipelines_hooks/clones/dupehound_gate.py:46`; no for the additional 0.80 diagnostic partition and extraction advice. These additions have no production caller today.
Attach point: extend the existing command, report and verdict chain, reached through `pipelines_hooks/cli.py:59`; create no second scanner or allowlist. A diagnostic finding cannot erase a register rot failure.
Decision: preserve the reviewed 0.85 blocking threshold while flagging 0.80-and-above pairs as requested. Below 0.85, guidance is diagnostic. Defaults live in the shared contract and can only change by reviewed producer policy. Tests cover 0.799, 0.80, 0.849 and 0.85 using deterministic report fixtures, then exercise real Rust and Python scanner fixtures through the CLI. Threshold invariants require finite values with 0 <= diagnostic <= enforcement <= 1.
Rejected: replacing the scanner or lowering every consumer's enforcement threshold from source inspiration alone. Keep existing Rust/Python support, token minima, scope rules and digest-bound distinct-pair review. Extraction advice is a review proposal with both locations, not an automatic code rewrite.
Cross-repository rows: none added; consumers retain the same hook ID and published policy.
Source credit: `open-source-libraries/kiss/README.md`, AU queue candidate 66, informs the user need for similarity and extraction guidance. No arXiv citation was supplied. The design reuses this repository's existing scanner contract.
Acceptance: implement `tests/hooks/test_similarity_guidance_hook.py`, then run `uv run --frozen python -m pytest tests/hooks/test_similarity_guidance_hook.py -q`. The integration test invokes the pinned scanner through the CLI; scanner absence cannot satisfy it. No native scanner build is required for this specification change.

## Meaningful outcome assertions (PIPE-PAGES-R021)

Data flow: test-quality CLI -> declared outcome contracts -> static screening -> isolated baseline/counterexample runs -> bound assertion receipts -> located findings and verdict.
Existing code: `pipelines_hooks/code/no_stub.py:62` scans production placeholders and explicitly skips tests. `pipelines_hooks/cli.py:59` dispatches gates and maps `CannotRun` to exit 2. `.config/pre-commit.yaml:30` already runs the locked test command at pre-push/manual stages. Source searches for assertion, observed outcome, test-quality and outcome proof found no existing semantic assertion checker.
Reachable today: no. The R021 test-quality module and registration remain specified; no runner or checker for declared outcomes exists. Reuse the gate dispatcher, configuration loader, test-runner convention and R020 evidence contract. This is an extension of R021, not a new gate family.
Attach point: add the outcome runner/checker to the R021 `main` before its final verdict, reached through `pipelines_hooks/cli.py:59`. The published `test-quality` CLI and shared hook remain the production entry. Pass commands as argument arrays, with bounded time and output, in disposable trees. Execute no caller-supplied shell string and never mutate the production checkout.
Decision: a tracked repository policy maps collected test IDs, including parameter cases, to subject entry points and applicable return, error and side-effect observables. Collect the complete declared test scope before checking contracts; an omitted collected case fails rather than disappearing from the report. Every case needs at least one applicable outcome. A category may be not applicable only with a recorded reason. The policy supplies concrete expected predicates and reviewed counterexamples; it is not inferred from arbitrary English descriptions.
Proof: run each selected baseline against its real fixture subject. For each applicable outcome, run a bounded counterexample in an isolated copy through the same subject interface and assert failure at the designated outcome assertion. A wrong return, missing/wrong error, and missing/extra side effect exercise the matching declared predicates. A runtime assertion event or supported helper adapter must tie the failure to that outcome; a crash, collection error or unrelated failed assertion is not evidence. Record skipped and uncollected parameter cases as unchecked. Default budgets are 30 seconds per case and 120 seconds per invocation, replaceable only by a versioned repository policy.
Static limits: syntax checks can reject a constant assertion or flag absent observable checks, but cannot establish that a test means what its author intended. Assertions through helpers or exception contexts need explicit adapters. Runtime evidence proves sensitivity only to declared counterexamples; it is not a complete proof of all program semantics. Preserve coverage, placeholder, suppression and component-handoff checks.
Rejected: counting assert keywords or accepting a passing test process as evidence of meaningful outcomes. Both admit tests that invoke a subject and ignore its result. Also reject using a setup failure as a killed counterexample.
Cross-repository rows: none added. Consumers supply tracked outcome contracts and test fixtures. R022 owns broad scheduled mutation campaigns; this contract consumes only bounded, declared counterexamples and does not duplicate that scheduler or claim mutation coverage.
Source credit: the source document identified by audit candidate PIPE:14, “Brain tasks 8bbe63ba”, supplies the requirement for return, error and side-effect assertions. No research citation was supplied. The exact source record and hash remain in the audit ledger.
Acceptance: implement `tests/hooks/test_test_quality_outcomes.py`, then run `uv run --frozen python -m pytest tests/hooks/test_test_quality_outcomes.py -q`. Its subprocess fixture enters `pipelines-hook test-quality`, invokes the configured real test runner and observes return/error/file-state proof. Include an ignored result, unrelated assertion, constant assertion, skipped parameter case and counterexample setup error. Assert located evidence and exit codes, not merely report-string presence.


## Changelog claims and grammar (PIPE-PAGES-R020)

Data flow: changelog CLI/shared hook -> one Git snapshot -> declared changelog policy and file -> bounded Markdown grammar -> located release/category/link evidence -> verdict.
Existing code: `pipelines_hooks/docs/public_surface.py:31` checks README/AGENTS links and quick starts; it does not parse changelog releases. `pipelines_hooks/docs/public_surface_constants.py:7` supplies heading patterns, not a release grammar. `pipelines_hooks/core/config.py:21`, `pipelines_hooks/core/comparison.py:53` and `pipelines_hooks/core/gitenv.py:81` provide configuration, snapshot and blob seams. Source searches for changelog, release notes and dated version found no checker. No current tracked changelog convention is assumed from that absence.
Reachable today: no. The changelog module, policy section and gate registration do not exist. Reuse dispatcher, Git and error helpers. A separate explicit changelog hook preserves the current public-surface promise that generic documentation layout is a review matter.
Ownership: extend the existing R020 documentation-claim rollup with the release-document subset. Do not create a rollup for this low-priority candidate. No ordered-release files, version-sync behavior or release publication rules are changed.
Policy: add the versioned `changelog` section to the shared configuration schema. It declares one repository-relative path (default `CHANGELOG.md`), grammar `changelog-v1`, tag prefix (default `v`), repository URL and comparison/release URL templates. Read policy and content from the same index locally or committed tree in CI; do not let unstaged content repair the checked snapshot. All declared text is checked, not only changed lines.
Grammar: one document title and optional introductory prose precede release sections. Each release uses `## [VERSION] - YYYY-MM-DD`; the only undated form is a single first `## [Unreleased]`. Date ordering is non-increasing; same-day releases are allowed. Version labels must be unique valid semantic versions, including prerelease/build suffixes. Category headings use level three; a release entry is a nonempty bullet under one allowed category, with indented continuation text. Fenced code is not interpreted as headings or links. Reject misplaced bullets, repeated categories, malformed headings and unsupported nesting. An empty Unreleased section is allowed; published release sections need at least one entry. Categories with no entries are omitted.
Breaking entries: `[Breaking]` is an explicit local marker on an entry, independent of its standard category. Added describes features and Fixed describes fixes; Changed or Removed can carry a breaking entry. The checker validates declared structure and markers but cannot infer whether all incompatible changes were documented. It does not require every release to contain all change kinds.
Links: each bracketed version heading resolves exactly once through a Markdown reference definition. Its HTTPS comparison URL must match the declared template for the previous listed release and the current version's tag. The oldest release may use its declared release/tag URL instead. Unreleased compares the latest listed release to the policy's development reference (default HEAD). Reject undefined/duplicate references, unsafe schemes and wrong endpoints without contacting the server. A one-release fixture exercises the oldest-release case. No claim is made about remote URL availability or tag provenance; release qualification owns that proof.
Limits and refusal: default UTF-8 size cap is 1 MiB, line count 20000 and release count 2000. Limits are explicit positive policy values with bounded parser operations. Exceeding a limit, missing the declared file, a symlink/traversal path or an unreadable snapshot is exit 2, not a truncated pass. Invalid grammar is exit 1. Missing-file evidence names the declared path and policy line; document errors name their exact source line. Gate execution never writes changelog content or invokes network access.
Decision: use a declared machine-checkable subset, preserving recognized categories while adding an explicit breaking marker. Reject broad regex searches that mistake fenced examples for releases, checking only changed lines, or accepting any syntactically valid URL as the right comparison.
Cross-repository rows: none. Consumers supply their policy and opt into the shared hook. The configuration does not prescribe or mass-rewrite existing repository release history.
Source credit: audit candidate PIPE:19, source task “Brain tasks b097dc10”, supplies the dated/categorized/linked changelog requirement. No research citation was supplied. Candidate lineage and its original record digest remain in the audit ledger.
Acceptance: implement `tests/hooks/test_changelog_gate.py`, then run `uv run --frozen python -m pytest tests/hooks/test_changelog_gate.py -q`. Invoke both the installed CLI dispatcher and published hook on disposable Git fixtures. Cover valid release types, oldest-release and Unreleased links, independently malformed date/version/category/link, missing file, misplaced entries, duplicate definitions, code-fence examples and parser-limit refusal. Assert exact exit codes, line evidence, snapshot isolation and unchanged files. Network access must be unavailable throughout.

### References

[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) provides the dated release/category/comparison convention. [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) defines version-label syntax. The breaking marker, bounded parser and gate verdicts are this platform's declared policy.
