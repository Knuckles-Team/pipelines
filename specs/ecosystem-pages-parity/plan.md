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

## Source mappings and architecture (PIPE-PAGES-R009, PIPE-PAGES-R012, PIPE-PAGES-R013)

The production call path is `create_snapshot` -> `enrich_records` -> `read_metadata`.
`render` -> `current_panels` wires the result to code cells, relationship tables, and component diagrams.
`main` writes the companion `architecture.mmd` before the existing Pages upload.

The generator reads source declarations from `spec.md` and `plan.md` outside fenced examples.
`Depends-on` declares prerequisites; `Extends` and `References` retain separate meanings.
Local IDs resolve through canonical status ownership. External declarations carry explicit source URLs.
The delivery view must not use the older prose-mention dependency heuristic in `spec_graph_parse`.

`Code` declarations and existing file citations identify implementation, test, and documentation references.
Local existence is evidence of a file only. External files and coverage remain unverified.
The page groups all specs by repository and declared component, including orphan specs and Unassigned components.
Package diagrams use SVG within HTML; Mermaid source carries labelled edges without adding a renderer dependency.
Existing plan diagrams remain available as escaped source. Missing plan diagrams remain visible.

The integration regression enters through `main`, writes the actual output artifacts, and preserves source status bytes.
No generated status, delivery state, or timeline changes belong to this mapping change.

R012.20-.25: Source binding authority and exhaustive language/tool inventory; capability ID gate refusing missing/invalid identities.

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

R021.79-.84: Coverage runner and per-project inventory; closure gate refusing untested paths at any threshold.

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
Source credit: the source document “SDD enhanced”, Meristem queue candidate 64. No research citation was supplied.
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
Source credit: the source document “PyTests Enhancement Meristem”, Meristem queue candidate 67. No research citation was supplied.
Acceptance: implement `tests/hooks/test_test_quality_hook.py`, then run `uv run --frozen python -m pytest tests/hooks/test_test_quality_hook.py -q`. Tests run real fixture components and then the CLI against their generated receipts. `test_component_lazy_import_cli` invokes the production gate with allowed and forbidden imports inside both synchronous and asynchronous entry functions. Assert that an allowed lazy-only dependency is reachable and a forbidden lazy edge exits 1 at its line. A type-only reference remains separately classified and cannot rescue an otherwise orphaned module. A computed import with unresolved reachability exits 2 and records uncertainty. Preserve the existing real-handoff, property-proof and skipped-receipt cases.

R021.85-.90: Graph-loaded workflow with durable hydration; Meristem consumer and independent readback acceptance.

## Skill grading (PIPE-PAGES-R023)

Data flow: skill-grade CLI -> declared skill files -> deterministic criteria -> located evidence -> grade receipt.
Existing code: `pipelines_hooks/docs/public_surface_links.py:29` checks local link containment. `scripts/readiness/evidence.py:41` proves a skills directory exists; `scripts/skill_graph/au.py:78` extracts skill catalogue data. Neither grades skill quality.
Reachable today: no. A grader and its registry entry are absent. Source searches for frontmatter, skill grade, description quality and skill metadata found no grader to reuse. Add the small grader module and reuse the link parser, scheme checks and `CannotRun` mapping. The existing link helper joins targets to the repository root; calling it unchanged misresolves nested skill links. Extend its interface with a document base while keeping the containment root independent.
Attach point: `pipelines_hooks/cli.py:14` and `pipelines_hooks/cli.py:59`, plus the published hook, catalogue and self-run configuration used by `.github/workflows/ci.yml:86`.
Decision: grade declared inputs with a versioned policy, never a model-generated subjective score. Default frontmatter requires nonempty name and description. Description checks require purpose and use-condition fields in the policy's declared form. Body sections are Usage and Examples by default. Metadata checks UTF-8 readability, a regular file, and no escaping symlink. Each criterion is binary at its declared weight; a policy replacement must name its version and predicates.
Link resolution: derive the base from the source document directory within the repository. Decode and normalize local destinations, resolve symlinks, then enforce repository containment. Parent-relative links may reach another repository directory. Never substitute the skill directory for the containment root or resolve all skill links from the repository root. Preserve root README/AGENTS behavior.
Rejected: treating directory presence or catalogue extraction as quality evidence. Grade receipts bind inputs and policy, while installation and admission remain with the host.
Cross-repository rows: `EG-TYPED-PACKS` owns skill contracts; `ARBORA-FLEET-R034` owns admission. This gate emits evidence and does not approve a skill.
Source credit: the source document “Code enhancement skill rule”, Meristem queue candidate 63. No research citation was supplied.
Acceptance: implement `tests/hooks/test_skill_grade_hook.py`, then run `uv run --frozen python -m pytest tests/hooks/test_skill_grade_hook.py -q`. Invoke the published CLI on valid and adversarial skill fixtures and assert every criterion and exit code. `test_nested_skill_links_cli` uses `skills/demo/SKILL.md` with a sibling `guide.md` and an in-repository parent link; both pass. Missing targets, decoded traversal outside the repository and symlink escape fail with located evidence. A root README fixture retains the existing resolution behavior.

## Similarity guidance (PIPE-PAGES-R024)

Data flow: changed-source CLI -> pinned structural scanner -> validated clone report -> diagnostic and enforcement partitions -> reviewed-distinct register -> located guidance.
Existing code: `pipelines_hooks/clones/dupehound.py:64` constructs the scanner command; `pipelines_hooks/clones/dupehound_report.py:66` validates findings; `pipelines_hooks/clones/dupehound_gate.py:28` enforces the reviewed register. `pipelines_hooks/clones/contract.py:14` sets 0.85 and the shared contract retains token minima and exclusions.
Reachable today: yes for detection and enforcement through `pipelines_hooks/clones/dupehound_gate.py:46`; no for the additional 0.80 diagnostic partition and extraction advice. These additions have no production caller today.
Attach point: extend the existing command, report and verdict chain, reached through `pipelines_hooks/cli.py:59`; create no second scanner or allowlist. A diagnostic finding cannot erase a register rot failure.
Decision: preserve the reviewed 0.85 blocking threshold while flagging 0.80-and-above pairs as requested. Below 0.85, guidance is diagnostic. Defaults live in the shared contract and can only change by reviewed producer policy. Tests cover 0.799, 0.80, 0.849 and 0.85 using deterministic report fixtures, then exercise real Rust and Python scanner fixtures through the CLI. Threshold invariants require finite values with 0 <= diagnostic <= enforcement <= 1.
Rejected: replacing the scanner or lowering every consumer's enforcement threshold from source inspiration alone. Keep existing Rust/Python support, token minima, scope rules and digest-bound distinct-pair review. Extraction advice is a review proposal with both locations, not an automatic code rewrite.
Cross-repository rows: none added; consumers retain the same hook ID and published policy.
Source credit: `open-source-libraries/kiss/README.md`, Meristem queue candidate 66, informs the user need for similarity and extraction guidance. No arXiv citation was supplied. The design reuses this repository's existing scanner contract.
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
Grammar: one document title and optional introductory prose precede release sections. Each release uses `## [VERSION] - YYYY-MM-DD`; the only undated form is a single first `## [Unreleased]`. Date ordering is non-increasing; same-day releases are allowed. Version labels are unique and use three dot-separated nonnegative decimal components without leading zeroes, except zero itself. An optional hyphen introduces dot-separated prerelease identifiers; each is nonempty ASCII letters, digits or hyphens, and a digits-only identifier has no leading zeroes. An optional plus introduces build identifiers using the same characters and nonempty dot-separated form, with leading zeroes allowed. No other characters, prefixes or suffix forms are valid; the policy tag prefix is applied only when forming URL endpoints. Category headings use level three; a release entry is a nonempty bullet under one allowed category, with indented continuation text. Fenced code is not interpreted as headings or links. Reject misplaced bullets, repeated categories, malformed headings and unsupported nesting. An empty Unreleased section is allowed when at least one dated release supplies its comparison anchor; published release sections need at least one entry. Categories with no entries are omitted.
Breaking entries: `[Breaking]` is an explicit local marker on an entry, independent of its standard category. Added describes features and Fixed describes fixes; Changed or Removed can carry a breaking entry. The checker validates declared structure and markers but cannot infer whether all incompatible changes were documented. It does not require every release to contain all change kinds.
Links: each bracketed version heading resolves exactly once through a Markdown reference definition. Its HTTPS comparison URL must match the declared template for the previous listed release and the current version's tag. The oldest release may use its declared release/tag URL instead. Unreleased compares the latest listed release to the policy's development reference (default HEAD). With no dated release, an Unreleased-only document is refused with `CannotRun`, exit 2 and reason `missing-release-anchor` at the Unreleased heading, even when it is empty or a link definition is present. A title-only document is exit 1 for missing release sections. The initial-history refusal ends after adding the first valid dated release and its release/tag link, plus an Unreleased comparison from that release to the development reference. Never infer a baseline from repository creation, guess a tag or substitute a repository-home URL. Reject undefined/duplicate references, unsafe schemes and wrong endpoints without contacting the server. A one-release fixture exercises the oldest-release case. No claim is made about remote URL availability or tag provenance; release qualification owns that proof.
Limits and refusal: default UTF-8 size cap is 1 MiB, line count 20000 and release count 2000. Limits are explicit positive policy values with bounded parser operations. Exceeding a limit, missing the declared file, a symlink/traversal path or an unreadable snapshot is exit 2, not a truncated pass. Invalid grammar is exit 1. Missing-file evidence names the declared path and policy line; document errors name their exact source line. Gate execution never writes changelog content or invokes network access.
Decision: use a declared machine-checkable subset, preserving recognized categories while adding an explicit breaking marker. Reject broad regex searches that mistake fenced examples for releases, checking only changed lines, or accepting any syntactically valid URL as the right comparison.
Cross-repository rows: none. Consumers supply their policy and opt into the shared hook. The configuration does not prescribe or mass-rewrite existing repository release history.
Source credit: the exact ledger record for audit candidate PIPE:19 identifies source task “Brain tasks b097dc10” and the dated/categorized/linked changelog requirement. The original task document was unavailable and was not read. No research citation appears in the record. Candidate lineage and its record digest remain in the audit ledger. This plan states the complete local grammar without relying on an external guide.
Acceptance: implement `tests/hooks/test_changelog_gate.py`, then run `uv run --frozen python -m pytest tests/hooks/test_changelog_gate.py -q`. Invoke both the installed CLI dispatcher and published hook on disposable Git fixtures. Cover valid release types, oldest-release and Unreleased links, independently malformed date/version/category/link, missing file, misplaced entries, duplicate definitions, code-fence examples and parser-limit refusal. In a fresh real Git fixture, stage a title and only an empty Unreleased section. Both CLI and installed hook must exit 2 with `missing-release-anchor` at that heading and no invented endpoints. Adding a guessed comparison URL must not repair the refusal. Stage the first valid dated release and both required links; both entry points must then exit 0. Keep network access unavailable for every step. Assert exact exit codes, line evidence, snapshot isolation and unchanged files. Network access must be unavailable throughout.

## Validation synthesis across existing rollups

Data flow: configured pre-commit or pipelines-hook CLI -> one declared Git snapshot and policy -> real bounded analyzer adapters -> located typed pass/fail/skip report -> deterministic grading/health summary -> exit status and optional JSON/Markdown export.
Existing code versus missing wiring: cli.py:13/59 dispatches existing gates; core/config.py:91 currently reads worktree TOML and needs a snapshot-reader seam. docs/public_surface.py:31 checks links/quick starts, code/env_sprawl.py:scan checks literal-read placement, supply_chain/gate.py:58 gathers specific supply findings, and complexity/census.py:main invokes its scanner. None establishes the new complete inventory, combined lint/type, template provenance, external grading or shared report contracts. Preserve those existing implementations and adapt their structured measurements. New code/modules named below are proposed, not present.
Shared decisions: run checks from a materialized disposable index or committed tree and pass its identity to every adapter; never mix unstaged policy with staged source. Strict configuration sections are added to core/config.py:21. Each new gate is published in .pre-commit-hooks.yaml, the hook catalogue and .config/pre-commit.yaml, then consumed by .github/workflows/ci.yml:86. No runtime application or release orchestrator is introduced. Required unchecked work yields exit 2 before any exit 1; a complete report with required findings exits 1, otherwise 0. Existing individual-gate behavior is preserved.

### PIPE:7: env documentation (R020.19–24)

Runtime environment inventory: default Python support covers tracked first-party package, entrypoint and test roots explicitly declared by policy; central providers supply versioned finite manifests bound to their source digest. Resolve import aliases and wrapper adapters, and report every unresolved environment access. A dynamic name is not documented merely because one observed execution returned a known key. Example files use a declared comment schema for purpose/requiredness/default and assignment for name/value; README uses the same four columns in a declared table. Missing defaults are represented explicitly, not inferred from an empty assignment. New environment-documentation code is absent; existing env-sprawl only checks placement of literal reads. MCP/launcher JSON is a required third consumer surface whenever tracked launcher configurations are declared or discovered. Model launcher identity, applicable runtime-variable closure, JSON pointers and a pinned binding-dialect adapter. Each applicable variable needs a binding matching its safe default and required/sourced semantics. Reconcile discovered and declared launchers so omitted configuration cannot pass. Literal values and references use the dialect's explicit semantics; JSON itself is not assumed to expand shell placeholders. Unsupported dynamic substitution refuses without executing or expanding secrets. Requiredness and purpose remain contract metadata if the launcher format has no native fields; do not inject unsupported keys into MCP JSON. Evidence binds each pointer and source line to the checked consumer digest. A real staged fixture independently removes/renames a binding, changes default/requiredness, corrupts/deletes the JSON file and repairs it; both CLI and pre-commit fail then pass. An unstaged repair cannot hide drift. Deployment examples remain outside this six-input batch.
Acceptance: implement `tests/hooks/test_env_documentation.py` and run `uv run --frozen python -m pytest tests/hooks/test_env_documentation.py -q`. Its CLI fixture uses a real Git repository and the published configured pre-commit entry, asserts exact exit status and located evidence, and denies network access. Model/parser tests alone do not close the integration row.

### PIPE:13: config inventory (R020.25–30)

Standard configuration inventory: canonical locations are policy data, not legacy root filenames. Default roles map to .config/bumpversion.cfg, .config/pre-commit.yaml and pyproject.toml, with pytest in tool.pytest.ini_options; an explicit pytest.ini adapter is also valid. One file may satisfy metadata and pytest only if both schemas pass. Enumerate nested project roots using supported manifest discovery and reconcile with declared inventory; repository consumers invoke this once per registered repository, never silently omit a project. The bump role reuses the canonical configuration and does not duplicate PIPE-RELEASE-R006 version consistency. Rendering replaces only template-owned sections in newly created output; arbitrary existing files require review outside the gate. Source historical template paths are migration inputs, not new canonical locations.
Acceptance: implement `tests/hooks/test_config_inventory.py` and run `uv run --frozen python -m pytest tests/hooks/test_config_inventory.py -q`. Its CLI fixture uses a real Git repository and the published configured pre-commit entry, asserts exact exit status and located evidence, and denies network access. Model/parser tests alone do not close the integration row.

### AU:124: validation report (R020.31–36)

Serializable reports: use a strict validated Pydantic model and add its pinned dependency through the repository lock; cross-process consumers depend on the versioned serialized schema rather than an in-memory object. A repository/category/test hierarchy retains all failure diagnostics up to declared limits; exceeding limits yields cannot-run with truncation metadata, never a complete receipt. Defaults: 10 MiB JSON, 100000 records, 64 KiB redacted diagnostics per result, positive bounded configurable caps. Canonical ordering is repository, category, analyzer/test ID, rule, path, line. JSON object key order is canonical; evidence digest excludes elapsed duration so stable measurements remain reproducible. Export only to explicit caller destinations; checking otherwise leaves the repository unchanged. Consumers plan repairs from this report but acquire no automatic mutation authority. The repository-validation producer calls the same structured lint_type.analyze runner used by lint-type and exports lint, import-order and type as explicit required report categories, including all rule IDs and reasons. JSON/Markdown round-trip acceptance observes each real phase failure through that aggregate entry point, not through a separate standalone run.
Acceptance: implement `tests/hooks/test_validation_report.py` and run `uv run --frozen python -m pytest tests/hooks/test_validation_report.py -q`. Its CLI fixture uses a real Git repository and the published configured pre-commit entry, asserts exact exit status and located evidence, and denies network access. Model/parser tests alone do not close the integration row.

### PIPE:8: lint type policy (R021.19–24)

Lint/import/type policy: the default Python profile requires explicit immutable tool versions in the consumer lock and a reviewed versioned rule selection. The default Ruff lint selection is E4, E7, E9, F and W, with I for the separate import-order phase; mypy runs strict checking without ignored errors or missing-import bypass. The initial supported profile is Python, not an implicit claim of every language. Every discovered first-party source language must have a declared supported adapter or the invocation refuses. External vendored dependencies and generated outputs require provenance-bound classification outside first-party roots; a path exclusion cannot hide first-party debt. All suppression mechanisms accepted by the pinned adapter version must be inspected; an unsupported option refuses. Initial budgets are 120 seconds and 10 MiB output per phase. The no-exceptions clause remains absolute within this profile and does not rewrite the accepted prose policy or existing scanner thresholds.
Acceptance: implement `tests/hooks/test_lint_type_policy.py` and run `uv run --frozen python -m pytest tests/hooks/test_lint_type_policy.py -q`. Its CLI fixture uses a real Git repository and the published configured pre-commit entry, asserts exact exit status and located evidence, and denies network access. Model/parser tests alone do not close the integration row.

### AU:119: analyzer health (R021.25–30)

Combined health policy: only the five health categories participate in scoring. Lint, import-order and type are additional required report categories, unscored but included in verdicts and fix priority. repository_validation.main calls lint_type.analyze once with the identical snapshot/policy; malformed or missing phase results refuse, findings fail regardless of health score. The real aggregate fixture isolates and repairs each code phase, proving exit 1 at unchanged health and exit 0 after repair with all other required checks complete. Default equal positive category weights are 1; zero or negative weights refuse. Within each category, penalty is min(100, sum of unique finding penalties), with critical/high/medium/low penalties 100/25/10/2. Priority severity order is critical, high, medium, low. Category health is 100 minus penalty; overall health is the floor of the weighted mean. A complete report with no findings scores 100. This is a declared local summary rule, not a claim to reproduce another product. A missing category leaves score null rather than renormalizing weights. Required findings still fail even at high score; optional findings remain visible with their own policy disposition. Dependency vulnerability claims require a pinned offline advisory dataset with digest and age bound; without it that coverage is unchecked. Supply-chain's existing pin/config findings are reused without relabeling them as vulnerability coverage. Adapter commands use bounded argv execution and no scanner provisioning. Aggregate acceptance must exercise real tools; deterministic adapter unit fixtures supplement but cannot replace that run.
Acceptance: implement `tests/hooks/test_analyzer_health.py` and run `uv run --frozen python -m pytest tests/hooks/test_analyzer_health.py -q`. Its CLI fixture uses a real Git repository and the published configured pre-commit entry, asserts exact exit status and located evidence, and denies network access. Model/parser tests alone do not close the integration row.

### AU:123: external grade rules (R023.7–12)

External grading rules: the source asks for externally developed heuristics, but does not authorize wholesale copying of another product's rule book. Incorporate only explicitly declared, reviewed and appropriately credited rule definitions through bounded built-in predicate adapters. The fixture rule is an original simple heading predicate. Conflicting rule meanings require an explicit policy decision before grading; no alphabetical overwrite or last-write winner. Rule packs are immutable snapshot inputs, with no executable callbacks. Default external diagnostic findings do not alter the established 20-points-per-criterion scheme; a reviewed replacement still totals 100 and preserves mandatory hard failures.
Acceptance: implement `tests/hooks/test_external_grade_rules.py` and run `uv run --frozen python -m pytest tests/hooks/test_external_grade_rules.py -q`. Its CLI fixture uses a real Git repository and the published configured pre-commit entry, asserts exact exit status and located evidence, and denies network access. Model/parser tests alone do not close the integration row.

### Source lineage and coverage

The six original inputs were read from the authorized source workspace. Source-record digests below preserve exact audit identity; they are not hashes of the source file bytes. No arXiv research was cited by these inputs. Requirements are product-neutral and self-contained; no external product design, score, baseline or implementation is adopted. The analyzer reference contributes only the requested category/aggregation intent. Earlier source limitations for other candidates remain unchanged.

| Candidate | Owning children | Original record SHA-256 |
| --- | --- | --- |
| PIPE:7 | PIPE-PAGES-R020.19–24 | `ead5f88ba77059d5589aff450a306603c482e3096e65d386f2cc4fc8329cdad5` |
| PIPE:13 | PIPE-PAGES-R020.25–30 | `32d96d34d089353cc2acd84c5f383aac70a0f17076c3999c87ce393c2a57f0fd` |
| AU:124 | PIPE-PAGES-R020.31–36 | `98cf091b20486ee2362fc9d1c3b0c8dbbf8167bc29e63c12c2f26f605cbb85a3` |
| PIPE:8 | PIPE-PAGES-R021.19–24 | `89528f401a8e386c65b9d6b9d1a2fa3e582357a5789920774cf8eb5750db0425` |
| AU:119 | PIPE-PAGES-R021.25–30 | `c98a353b9004b5cde39c6d26434c570fb1c1db65043adbfa950b240701066ca1` |
| AU:123 | PIPE-PAGES-R023.7–12 | `9814e34da54466301d7778d157b8a5aafddd7a0791470ec90f1cf0e7da8f6018` |

Cross-repository boundaries: consumers provide inventory, policy, adapters and rule packs. Pipelines owns checking/report contracts only. Host consumers may read reports for repair planning without acquiring execution or write authority. Implementation and real integration acceptance are future work.

## Documentation contract synthesis

Data flow: owner registry/template/guide inputs at one Git snapshot -> documentation-contract adapters -> real generated artifacts and located findings -> served/browser evidence where required -> shared ValidationReport and pre-upload verdict. Extend R020 checks while preserving R002/R003/R008/R010/R011 parent requirements and existing delivery receipts. The six new groups cross-reference those existing owners rather than convert landed leaf rows into new rollups.
Production boundary: pipelines_hooks/cli.py:13/59 is the published dispatcher; docs/public_surface.py:31 currently checks links and quick starts. New specific gates are published in .pre-commit-hooks.yaml and self-run configuration for .github/workflows/ci.yml:86. Their source checks run offline against one index/commit snapshot. Pages checks run after Build Docs at .github/workflows/pages_pipeline.yml:180 and before Upload artifact at line 244; the workflow must include the proposed gate package/adapters in its pinned contract checkout/environment. Extend its real invocation, not only a helper test. Read policy with the same snapshot seam as R020 validation synthesis. Preserve generic public-surface behavior.
Proof boundary: new modules, hooks and browser checks below remain specified. Existing theme palettes, parity, rendering and registry extraction are reused; none is relabeled as complete coverage of the residuals. Browser/runtime acceptance runs only in appropriate configured environments. This definition batch runs no site/container/native build and performs no deployment. Required unchecked evidence is exit 2, measured failures exit 1, and verified complete checks exit 0; do not turn an unsupported pattern or unresolved claim into full coverage.

### PIPE:4: tool mapping (R020.37–42; extends R010)

The source task now exists and was read; its earlier unavailability for PIPE:19 remains a historical limitation of that earlier pass. Consume each owner's pinned contract export, including inherited/nested tool methods. The existing graph corpus groups methods by domain and renders component summaries; retain that code and add a lossless schema adapter instead of calling counts full coverage. A fixture tool implements a deterministic echo method with one nested operation, a required argument, a default and a typed result; the producer exports that real registration. Rendered table links must resolve when served. This gate proves documentation parity, not deployed service correctness.
Acceptance: implement `tests/hooks/test_tool_mapping.py`; run `uv run --frozen python -m pytest tests/hooks/test_tool_mapping.py -q`. Exercise the published CLI and configured hook on a real Git fixture, plus the actual producer/renderer/served browser path named by the hot-path row. Parser-only success does not close this acceptance.

### PIPE:6: guide migration (R020.43–48; extends R002/R020)

Default top-level guide limit is 300 nonblank lines, with an explicit positive repository override; the goal is progressive disclosure, not truncation. Migrations bind two exact trees and preserve stable block identities across moves. Destination roots come from canonical content configuration, not the source's retired docs folder example. Reuse R009's shared HTML/CSS architecture renderer; legacy diagram syntax requires conversion and rendered evidence, not a new competing diagram format. Unknown statements are carried as assumptions with exit 2 until a supported resolver has real evidence; neither text similarity nor an approval signature proves them true. Rendering writes only a new caller-selected scratch destination, and the proposed split remains reviewable before any repository edit.
Acceptance: implement `tests/hooks/test_guide_migration.py`; run `uv run --frozen python -m pytest tests/hooks/test_guide_migration.py -q`. Exercise the published CLI and configured hook on a real Git fixture, plus the actual producer/renderer/served browser path named by the hot-path row. Parser-only success does not close this acceptance.

### PIPE:15: deployment docs (R020.49–54; extends R008/R020)

Interpret the source's four options as uv-managed stdio, uv-managed local streamable HTTP, local container streamable HTTP and remote container URL connection. Docker/Podman are variants of the container pattern, not additional patterns. The remote pattern has distinct operator-side deployment and client-side URL configuration. Use published runtime owner commands and immutable package/image references, never derive an executable from project naming. Bind live-runtime receipts to the same owner version if supplied; the offline shared gate checks documents and contracts only. Real container/transport acceptance belongs to designated build/runtime environments and must not be replaced by command-string presence. Every matrix always has four rows; unsupported capability cannot be hidden by dropping a row or claiming four runnable cases.
Acceptance: implement `tests/hooks/test_deployment_docs.py`; run `uv run --frozen python -m pytest tests/hooks/test_deployment_docs.py -q`. Exercise the published CLI and configured hook on a real Git fixture, plus the actual producer/renderer/served browser path named by the hot-path row. Parser-only success does not close this acceptance.

### PIPE:16: doc inventory (R020.55–60; extends R002/R003/R020)

Expand the existing inventory rather than create a second authority. Documentation configuration may be a role/section in an already-declared file. Canonical content roots come from the existing consumer configuration and Pages content_source; source references to a legacy docs folder do not authorize recreating it. The renderer owns scaffolding and explicit managed sections only, while R020 changelog checks own release structure. Inventory checking is read-only; a separate explicit scratch render supplies a reviewable proposal. Browser/navigation acceptance uses the built artifact from the checked snapshot, not a synthetic page that happens to contain expected strings.
Acceptance: implement `tests/hooks/test_doc_inventory.py`; run `uv run --frozen python -m pytest tests/hooks/test_doc_inventory.py -q`. Exercise the published CLI and configured hook on a real Git fixture, plus the actual producer/renderer/served browser path named by the hot-path row. Parser-only success does not close this acceptance.

### PIPE:20: readme header (R020.61–66; extends R003/R011)

The current REPOS already contains seven owners: Medulla, Meristem, Scion SDK, arbora, Overstory, Tuig and Axil. Correct only the stale five-owner wording in R011; keep its landed receipts and the registry as authority. This audit scope does not imply pipelines or an unrelated repository is a missing eighth consumer. The exact shared header contains title, mark, description, visible badges and the four named links; owner-specific descriptions and marks remain distinct. Status badges need safe provenance and a declared freshness bound; unavailable data is explicitly unknown. The checker verifies declared telemetry, not external monitoring truth.

Provider self-run has an explicit scope result: only the versioned gate policy identity `github.com/Knuckles-Team/pipelines` is non-applicable, with structured `skip`, reason `provider-not-consumer`, exit 0 and zero consumer checks. Resolve canonical full host/namespace/repository from origin, or the sole remote when origin is absent; never use checkout basename or a caller provider flag. The existing `repository_identity.remote_owner` returns only a slug and cannot alone establish this exception. Unknown repositories and missing/ambiguous identities are CannotRun exit 2. Known consumers always validate their header. Record identity source, snapshot and policy/registry digests for the skip; no header grade or consumer coverage receipt may be emitted. This declared scope is non-applicable under R020.34, not a skipped required consumer check. Acceptance runs the actual CLI and self-run hook against provider, unknown and same-basename different-namespace Git fixtures, plus a broken known-consumer fixture attempting a provider override. CI still runs consumer renderer/browser acceptance.
Acceptance: implement `tests/hooks/test_readme_header.py`; run `uv run --frozen python -m pytest tests/hooks/test_readme_header.py -q`. Exercise the published CLI and configured hook on a real Git fixture, plus the actual producer/renderer/served browser path named by the hot-path row. Parser-only success does not close this acceptance.

### PIPE:21: image theme (R020.67–72; extends R003/R020)

Preserve the established shared theme, repository marks and HTML/CSS architecture views. Existing SVG or raster assets remain inputs, with a theme-safe single asset or explicit light/dark alternatives. The source's misdirected connector arrow is captured as semantic source/target identity and rendered geometry, not a blanket claim that any arrow is correct. Default declared text contrast probe threshold is 4.5:1 and meaningful non-text boundary threshold 3:1; these are local policy values, not a certification claim. Intricate or photographic content requires scoped reviewed render evidence and remains unresolved when such evidence is missing. The acceptance runner uses a real browser against the built artifact in both media modes; it does not certify GitHub's live rendering by simulating a page offline. A consumer claiming host-specific rendering must supply a same-revision receipt from that host.
Acceptance: implement `tests/hooks/test_image_theme.py`; run `uv run --frozen python -m pytest tests/hooks/test_image_theme.py -q`. Exercise the published CLI and configured hook on a real Git fixture, plus the actual producer/renderer/served browser path named by the hot-path row. Parser-only success does not close this acceptance.

### Exact input lineage

All six original inputs were read. PIPE:4's formerly unavailable task was found and read in this batch; that does not retroactively claim source review in the earlier PIPE:19 pass. No arXiv research is cited by these inputs. The requirements are product-neutral and self-contained. Record digests identify audit inputs, not source bytes.

| Candidate | New children | Record SHA-256 |
| --- | --- | --- |
| PIPE:4 | PIPE-PAGES-R020.37–42 | `99ed4494b88ba41edd66c3d5e8f8026da878f58a9074002a21a34e6dd6818fed` |
| PIPE:6 | PIPE-PAGES-R020.43–48 | `cee6646cfa2fba504e29c85de9f680654d11e6b5a4345b26ccf91549232fb760` |
| PIPE:15 | PIPE-PAGES-R020.49–54 | `cdbe13b05a0dbec9b60cf7608a06509daedd1b925076132a417261a33f0cca30` |
| PIPE:16 | PIPE-PAGES-R020.55–60 | `5184d56b5a0b235361ba8ba229edd9e7cbaa4545c4405ea3b0d45bc1b73ac2bb` |
| PIPE:20 | PIPE-PAGES-R020.61–66 | `df0c9df43a220ba42110e2fc9248cb7abb3fcf9a56d3a748f4e26d2f802aa6d4` |
| PIPE:21 | PIPE-PAGES-R020.67–72 | `d1b5d8cbbdf7d8c25237002d9f3d74ec2c37aa315a1058f84214665dc6290c6a` |

Source-byte SHA-256 evidence: task b097dc10 `8d1b602b340de2c617569ea065a6d0299397a69e43608332fa9f80a689b7d856`; guide splitting `12192bfe6cade66abffafe81844f9cf95847b2b94b135e13644e4b86c4005488`; environment/deployment conversation `6ea0112bca6b26c0b8f28710f31e9f5dc77994a4b3e61ee70c1b8f4164ab0dea`; four deployment options `ea28329a140f215fd655e2fb80014029f48251d874cd63f9b42ce86788e7d3be`; modernization plan `5b71bc49259e276e2e149f837cc35780c31da21d5a664ca0fd467ac476c5c1b9`; standardization task `c7c5c1545805b72cca225ce1b9ede5fabad308833217b1772212b85e49281520`; shared README request `21d96ae2690c43ccb7c076e1620afead4b731a8357fe64c4a2282eaba89560c3`.

Runtime/deployment capability remains with its existing owner; pipelines owns documentation parity and evidence only. The parent rows keep their existing historical receipts; new acceptance is not claimed by those receipts.


### Amendment — 2026-10-12: readable delivery detail panels

R012.5, R013.4 and R014.3 retain their data semantics. Give specifications, architecture, relationships and record inventory the full sheet width. Wrap definition text within the visible area. Keep wide tables and package diagrams in local scroll containers, with package labels at readable size. Regression checks cover panel spans, bounded definitions and local overflow. Desktop and mobile visual evidence remains a separate validation step.


R013.2 also excludes prose words in References declarations from relationship targets. Retain the full declaration and source path as unparsed evidence. Preserve explicit links, canonical identifiers and relative file references, including unresolved canonical identifiers.

## Structured artifacts and shared validation contracts

The shared CLI at `pipelines_hooks/cli.py:79` calls `run_gate` at line 59.
The new registrations below are proposed; the current registry does not publish these checks.
Reuse canonical status generation at `pipelines_hooks/specs/generator.py:93`; artifact validation must precede it.
Reuse the proposed repository-validation, test-quality, config-inventory and skill-grade adapters owned by existing rows.
Those modules remain implementation work. Their names describe required attachment points, not existing runtime evidence.
KISS census and staged entry points already exist. Their new structural predicates require explicit measurements and consumer adoption.
All planned test names below are future proof obligations. Documentation alone creates no runtime receipt.

### Spec artifacts

`PIPE-PAGES-R020.73` through `PIPE-PAGES-R020.78` extend `PIPE-PAGES-R020`.
Add a spec-artifacts entry to pipelines_hooks/cli.py:13, dispatched through run_gate at line 59. Proposed artifacts.main must validate generator-skill output before the existing specs/generator.py:93 status consumer reads rendered requirements. Generator skills must invoke this adapter with their output path; direct unvalidated output cannot receive a compatibility receipt.

### Spec bundle compatibility

`PIPE-PAGES-R012.8` through `PIPE-PAGES-R012.13` extend `PIPE-PAGES-R012`.
Extend proposed spec-artifacts at pipelines_hooks/cli.py:13 through run_gate at line 59. Validate the bundle before specs/generator.py:93 and dashboard source ingestion. EG-ORCH-VOCAB-R012 owns graph ingestion. Its owner adapter must consume the identical bundle bytes; the Pages renderer must not invent graph compatibility.

### Skill dependency audit

`PIPE-PAGES-R021.31` through `PIPE-PAGES-R021.36` extend `PIPE-PAGES-R021`.
Extend the planned repository-validation registration at pipelines_hooks/cli.py:13 and run_gate at line 59. Proposed repository_validation.main must pass the skill inventory to the supply-chain adapter beside supply_chain/gate.py:58. The owner connector must return a durable proposal identity before approval consumers receive it.

### Aggregate skill grade

`PIPE-PAGES-R023.13` through `PIPE-PAGES-R023.18` extend `PIPE-PAGES-R023`.
Extend planned repository_validation.main to call a structured skill_grade.grade(snapshot, policy) adapter once before its final verdict. Register through pipelines_hooks/cli.py:13 and run_gate at line 59. Reuse the standalone grader contract; neither proposed module exists on this source revision.

### Capability inventory

`PIPE-PAGES-R012.14` through `PIPE-PAGES-R012.19` extend `PIPE-PAGES-R012`.
Create a capability-coverage registration at pipelines_hooks/cli.py:13 and dispatch through run_gate at line 59. Reuse specs/bindings.py test discovery and owner-exported MCP inventories. Add static source adapters before the verdict. Dashboard source declarations must consume the resulting receipt without claiming exhaustive coverage themselves.

### Structural limits

`PIPE-PAGES-R021.37` through `PIPE-PAGES-R021.42` extend `PIPE-PAGES-R021`.
Extend pipelines_hooks/kiss/census.py:31 for build enforcement and kiss/staged.py:50 for changed-source admission. Their existing callers are pipelines_hooks/cli.py:59. Arbora must configure both limits and invoke the shared check in its build. Unsupported scanner measurements require a versioned adapter, not guessed values.

### Source path portability

`PIPE-PAGES-R021.43` through `PIPE-PAGES-R021.48` extend `PIPE-PAGES-R021`.
Register source-path-portability at pipelines_hooks/cli.py:13 and dispatch through run_gate at line 59. Publish a shared pre-commit hook and invoke it before package builds. Inventory Git paths and declared package roots statically; artifact platform tags do not replace source-path validation.

### Coverage closure

`PIPE-PAGES-R021.49` through `PIPE-PAGES-R021.54` extend `PIPE-PAGES-R021`.
Extend the planned test-quality registration at pipelines_hooks/cli.py:13 and run_gate at line 59 with an explicit closure mode. Proposed test_quality.main must invoke the declared runner before evaluating closure. Reuse the existing outcome runner and coverage adapters rather than adding another project registry.

### Validation behavior inventory

`PIPE-PAGES-R020.79` through `PIPE-PAGES-R020.84` extend `PIPE-PAGES-R020`.
Extend the proposed config-inventory registration at pipelines_hooks/cli.py:13 through run_gate at line 59. Reuse the existing project inventory and configured hook parser. Execute the pinned baseline and consumer hooks in disposable trees. Connector spec-hook adoption alone must not establish complete validation coverage.

### Offline unit profile

`PIPE-PAGES-R021.55` through `PIPE-PAGES-R021.60` extend `PIPE-PAGES-R021`.
Extend the planned test-quality registration at pipelines_hooks/cli.py:13 through run_gate at line 59. The proposed outcome runner must apply UnitProfile isolation before test collection and execution. Enforcement must cover subprocesses, not only patched Python socket calls. Consumers must select the unit profile explicitly.

### Ontology governance hook

`PIPE-PAGES-R020.85` through `PIPE-PAGES-R020.90` extend `PIPE-PAGES-R020`.
Register ontology-governance at pipelines_hooks/cli.py:13 and dispatch through run_gate at line 59. Publish the pre-commit hook with complete ontology discovery before commit admission. The adapter must consume the generated OntologyInspect/ShaclValidate client or generated offline authority artifacts. Read-only inspection alone does not establish validation.

### Test layout independence

`PIPE-PAGES-R021.61` through `PIPE-PAGES-R021.66` extend `PIPE-PAGES-R021`.
Extend the planned test-quality entry at pipelines_hooks/cli.py:13 through run_gate at line 59. Reuse proposed config-inventory project roots and the outcome runner. Publish the test-layout profile through the shared hook. Preserve separate real-component integration and recovery acceptance contracts.

### Solution size evidence

`PIPE-PAGES-R021.67` through `PIPE-PAGES-R021.72` extend `PIPE-PAGES-R021`.
Extend planned repository_validation.main before its report export through pipelines_hooks/cli.py:13 and run_gate at line 59. Reuse source inventory and R020 report serialization. Publish measurements to the owner allocation consumer under EG-DECISION-ENGINE-R136.4. Meristem run receipts must preserve the same source and evidence identities.

### Graph workflow receipt

`PIPE-PAGES-R021.73` through `PIPE-PAGES-R021.78` extend `PIPE-PAGES-R021`.
Extend the planned test-quality handoff verifier at pipelines_hooks/cli.py:13 through run_gate at line 59. Consume the owner acceptance receipt joining Meristem graph_orchestrate, execute_workflow and Medulla SourceIngest. The shared gate verifies provenance and outcomes; it must not become a runtime workflow orchestrator.

Historical validation comparison remains blocked until its former command revision and complete behavior inventory are recovered.
Solution-size evidence does not resolve the reserved shortcut-comment policy. The coordinator retains that decision.
Coverage closure reuses the coverage and outcome owners; it does not replace their separate semantic proof contracts.

## PIPE-PAGES-R032

R032.1-.6: Preserve export-time coordinator decision and exact version comparison preventing silent forward/backward moves.

## PIPE-PAGES-R033

R033.1-.6: Bind installer contract to skill/command with explicit IDE/agent target/version matrix and per-target proof.

## PIPE-PAGES-R034

R034.1-.6: Extend portable deployment with single binary/image profile and external-dependency-free capability parity.

## PIPE-PAGES-R035

R035.1-.6: Define stable prompt JSON/Pydantic disk format with exact difference oracle retaining roundtrip coverage.

## PIPE-PAGES-R021.91-.96

R021.91-.96: Complete central-validate behavior inventory and require pre-commit parity across all projects.

## PIPE-PAGES-R037

R037.1-.6: Define unit-test profile with enforced external determinism and mocked dependencies.

## PIPE-PAGES-R038

R038.1-.6: Python-only pre-commit hook consuming Medulla-owned ontology validation with fail-closed authority.

## PIPE-PAGES-R039

R039.1-.6: Complete project test-layout inventory with fixture isolation and order independence.

## PIPE-PAGES-R040

R040.1-.6: Extend Meristem approval criteria to reject coverage-decreasing proposals.

## PIPE-PAGES-R041

R041.1-.6: Configured structural limits with named-function failure reporting in shared gate.

## PIPE-PAGES-R042

R042: `scripts/architecture_explorer/` discovers the organization repositories that have `specs/` in one paged query (`sources.org_repositories`, reconciled with `registry.json`), reads their spec rows, fits the connector fleet in `model.json` to the scan set, places the rows, precomputes layouts with the pinned layout engine (`layout.mjs`) and renders `template.html` with a build-time and head-commit stamp. The organization site workflow in Knuckles-Team/.github builds the canonical copy every 30 minutes and on `repository_dispatch: specs-changed`. `pages_pipeline.yml` gives each core repository a `/architecture/` redirect to it (`architecture_explorer: auto`, `build.py --redirect`) and `notify_org_site.yml` (called by each repository's `org-site.yml` on every main push) sends the dispatch with a GitHub App token when the app secrets are set. One canonical build is simpler than rebuilding eight copies on a schedule and keeps every link current.

R042.1 to R042.4: `build.search_index` turns the placed tree into the compact index that `render` embeds next to the tree; `search.cjs` holds the ranking and hash parsing and is inlined into `template.html` and loaded by node in the tests. The search box reuses `go`, `fitCam` and `openness` through `openCam`, so a result opens its ancestors the way a manual zoom does. `sources.read_aliases` reads each repository's alias file. R042.6 to R042.8: `details.py` cuts each row's description at source read time, renders the safe markdown subset and writes `spec-details/<repo>/<family>.json` next to the page; `template.html` fetches a family on its first expand and copies the parsed HTML through an allowlist.

R042 visual theme: adapt Overstory's system sans typography, rounded neutral controls and bounded translucent reading surfaces to an ocean-blue palette in `template.html`. Use a shared repo-native ocean scene behind translucent gradient glass nodes and shell surfaces, with quiet ocean layer accents and distinct restrained semantic status accents. Bundle the existing OFL-licensed Overstory Inter font, including its license, without a font CDN or runtime dependency. Use only bounded shell blur and inexpensive vector node gradients/shadows: no node blur, animated paint or new layout engine. Reduced-motion, reduced-transparency and forced-colors preferences have explicit fallbacks. This is a presentation-only change: text, model, row status/CQ classification, IDs, links, placement geometry, search, history, pan and infinite zoom remain unchanged. Understory/Studio graph conversion and repository renaming are outside this patch. The read-only PR visual job uses runner Chrome to retain desktop/mobile light/dark root and deep-link screenshots, DOM, the interactive HTML and raw-payload/candidate provenance; it runs existing detail/deep-link tests plus keyboard, zoom, pan, camera-history and search controls without a new browser dependency or deployment.

## Agent-readiness and static delivery (PIPE-PAGES-R043)

This requirement explicitly assigns the existing readiness and static delivery contract to this spec.
It introduces ownership, not a concept alias or a behavior change.
The former documentation-delivery label does not establish a historical one-to-one mapping.
PIPE-GATES-R007 separately owns rejection of obsolete machine annotations.

Code: ../../reference/pages-readiness.md ../../tests/test_pages_readiness.py ../../tests/test_pages_pipeline_contract.py ../../scripts/pages_readiness.py ../../scripts/readiness/cli.py ../../scripts/readiness/delivery.py ../../.github/workflows/pages_pipeline.yml

The workflow calls `scripts/pages_readiness.py` at `.github/workflows/pages_pipeline.yml:253`.
The entry calls `scripts/readiness/cli.py:68` (`main`), then `_main_build`, then `delivery.build`.
The content-source command calls `_main_validate_content_source` and `validate_content_source`.
The existing validator consumes canonical manifests; this requirement adds no generator or policy store.
`reference/pages-readiness.md` documents the contract.
`tests/test_pages_readiness.py` owns validation, static delivery, refusal, and direct-entry evidence.
`tests/test_pages_pipeline_contract.py` owns opt-in workflow and strict-build wiring evidence.
Public-site acceptance and the supported interpreter remain separate qualification obligations.

## Amendments

### 2026-10-25 — tuig explorer naming (PIPE-PAGES-R042)

The source model displays the native CLI as `tuig` while retaining repository
`agent-terminal-ui`, node `tui`, and all child IDs for existing deep links.
Its current transport edge is A2A/REST. Native-only migration descriptions
separate implemented snapshot/inspection views from planned ACP, local runtime,
streaming, approval attachment and durable resume. PyPI wheel delivery requires
release qualification. Source paths refer to the Rust frontend, not the retired
Python/Textual frontend. The canonical organization Pages workflow consumes this
model through `scripts/architecture_explorer/build.py`; generated HTML is not
edited. `test_tuig_preserves_identity_and_distinguishes_planned_runtime` checks
the stable identity, source paths and qualified edges.

### 2026-10-25 — repository title and Tuig subtitle (PIPE-PAGES-R042)

The main node title remains `agent-terminal-ui`. Its lower role label reads
`Tuig TUI / CLI`, identifying Tuig as part of that repository rather than
renaming the architecture node. The executable remains lowercase `tuig`;
stable IDs, repository mapping, transport and release/runtime qualification
are unchanged. The existing identity test checks both display labels and the
lowercase executable description.

### 2026-10-25 — ecosystem display brands (PIPE-PAGES-R042)

This amendment supersedes the earlier terminal title/subtitle choices: the
canonical model uses the five approved product display names documented in
`reference/ecosystem-boundaries.md`.
Axil Desk is the desktop GUI; Epistemic Graph and Arbora retain their names.
The Tuig executable remains `tuig`. Stable node IDs, repository slugs, code
paths, imports, dependency identifiers and protocol contracts do not change.
Existing runtime and release qualification caveats remain in force.
The normal explorer generator consumes these labels; no generated organization
site output is hand-edited. The display-brand regression test exercises that
generator and checks brand labels alongside their unchanged repository IDs.

### 2026-10-25 — desktop visual parts (PIPE-PAGES-R042)

The Axil Desk node retains `geniusbot` and the `desktop-client` family home.
Ten child parts group the existing R001–R020 requirement roots and all their
descendants by explicit ID rules. The groups cover backend integration,
lifecycle, approvals, terminal, panels, packaging, tokens, documentation,
run inspection and source quality. They add no requirement, transport edge,
source path or delivery claim. Unknown roots stay visible as Unmapped.
Placement and normal-generation tests protect unique placement, repository
identity and unchanged row/status totals. Generated Pages output is not edited.

### 2026-10-25 — Understory, Studio and Meristem display alignment (PIPE-PAGES-R042)

Name the existing dashboard authoring node Overstory Studio, describe Understory
as the knowledge exploration surface, and correct the in-run harness display
name to Meristem. Preserve node and repository IDs, family placement, code paths,
authority text, evidence and outstanding qualification caveats. The ocean-theme
preview retains its original payload provenance; normal generation consumes the
new labels separately. No renderer or capability is added.


### 2026-10-25 — Ambient ocean motion behind glass (PIPE-PAGES-R042)

Adapt the user's three-wave ocean wallpaper reference as three shared SVG bands
with slow compositor-only transforms, not a per-pixel canvas animation. Wallpaper
stays beneath the diagram and its stable reading surfaces and cannot intercept
input. Motion defaults on with a persistent, accessible opt-out; reduced motion
or reduced transparency disables it, and hidden pages pause it. Forced colors
hide the decoration. Verify actual browser animation phases, control persistence
and pause behavior alongside existing zoom/navigation tests. Phase screenshots
are sampled real CSS animation frames, not a video or elapsed-time benchmark.


### 2026-10-25 — Neutral fog glass over ocean wallpaper (PIPE-PAGES-R042)

Retain the approved ambient ocean wallpaper, but remove added blue pigments from
shells, node materials and ordinary controls. Lift light glass toward neutral
white and raise fog opacity by roughly 10–16 percentage points; use neutral
smoke in dark mode. Reserve color for semantic statuses, restrained category
text/markers and selected controls. Recheck actual alpha-composited node and
header text surfaces; preserve data, camera, navigation and motion controls.


### 2026-10-25 — Natural ocean wallpaper fidelity (PIPE-PAGES-R042)

Replace abstract wave ribbons with one optimized, locally embedded generated
seascape (sky, soft clouds, horizon, irregular wavelets and restrained foam).
Keep its perspective fixed; three sparse low-opacity glint layers retain gentle
compositor-only motion and all existing accessibility preferences. Record artwork
provenance honestly: static generated art with CSS glints, not video or fluid
simulation. Thin graph connectors gain a cheap neutral contrast understroke,
not blur. Verify text against conservative black/white backdrop bounds and
inspect actual desktop/mobile light/dark pixels before merging.


### 2026-10-25 — Top-level title case and visible role subtitles (PIPE-PAGES-R042)

Apply the finite reviewed top-level display-label/role corrections, including
Scion / Connector SDK, Meristem / Agent Harness and Universal Skills / Agent
Skills, without changing technical IDs. Adjust closed-card text row spacing so
those roles paint beneath names at ordinary desktop root zoom without colliding
with counts or parts. Keep graph geometry and camera/navigation unchanged.
A candidate-model fixture screenshot and canvas paint evidence are explicitly
separate from the unchanged live-payload before/after visual snapshot.

### 2026-10-25 canonical repository references

Following the six upstream repository renames, the explorer registry and model
use canonical repository slugs while keeping node IDs, ownership kinds, local
checkout paths, source paths and requirement IDs unchanged. Discovery must not
reclassify these core/client repositories as new connectors. The regression
`test_renamed_repositories_keep_ownership_placement_and_canonical_details` covers
canonical discovery, placement and generated spec-detail links (PIPE-PAGES-R042.9
and PIPE-PAGES-R042.7). Package and specification aliases remain separate.

### Abstract ocean motion and category-glass refinement (2026-10-25)

Follow-up to the accepted neutral-glass renderer: replace the active photographic
wallpaper with three broad native vector ocean forms, with clearly observable
compositor-only flow. Preserve neutral shell controls, graph geometry, identifiers,
canonical repository ownership, status classification and all navigation behavior.
Restore restrained category hue on graph-card materials (not heavy borders), and
protect canvas band/zone/loop labels with neutral reading plates. Validate text
against the actual wave and tinted-glass composites in both themes. Retain motion
opt-out, reduced-motion/forced-colors handling and hidden-page pause. Hosted visual
proof must include unforced real elapsed-time Chrome frames, not animation seeking
or a virtual-time-only claim; no runtime CDN, video or new dependency is added.

### Swimlane glass prototype (2026-10-25)

Use the existing overview band bounds as shared low-opacity frosted panes with
quiet neutral edges, a small category marker and complete gutter headings.
Retain node geometry, camera behavior, card category hues, connector visibility,
canonical ownership and requirement identities. This is a separate visual
follow-up; it must not delay deployment of the approved abstract ocean version.
No new blur layer, animated object or runtime dependency is introduced. Validate
text contrast including the lane material beneath both card-gradient endpoints.

### Quiet lane hierarchy and count-track separation (2026-10-26)

Supersede the glass lane panes with restrained, aligned gutter typography and
short semantic markers. Remove lane fills, frames and decorative chevrons while
preserving the existing band bounds, complete human labels, card hues, ocean
motion and camera geometry. Reserve one stable card-bottom completion track;
derive the count baseline from real text descent plus a clear gap, rather than
letting a percentage-height bar rise through the numbers. Hosted acceptance adds
actual canvas text/bar bounds at desktop/mobile overview and nested Overstory and
Medulla cameras; all required cases must execute without browser skips. Preserve
canonical repository ownership, requirement/status data and deep-link semantics.

### Collision-aware diagram annotations (2026-10-26)

Replace the remaining zone, self-evolution loop and connector caption plates with
one measured Inter annotation pass, shared with lane headings. Place captions only
in free space after collecting visible card/title-strip bounds, connector segments,
arrowheads, grouping outlines and control bounds. Preserve complete label text;
crowded captions use a quiet normal-flow contextual rail outside the canvas, also
available when the ledger is hidden. An accessible hint link focuses the rail and
explicitly exits fullscreen when necessary; recalculate hint collision bounds after
link text changes. Do not alter world geometry, data, statuses,
node IDs, navigation, card hues or ocean motion. Hosted evidence must measure actual
text paint against obstacles at default, deep-link, nested and mobile cameras,
including the external-systems caption and self-evolution loop, without skips.

### Strict architecture story producer (2026-10-26; PIPE-PAGES-R042)

Introduce an opt-in, build-time story contract before connecting it to the public
renderer. Require canonical repository/row identities, full-commit provenance,
reviewed spec and relationship applicability, exact deduplicated summaries, and
explicit scored versus completed-NA priority. Reject invalid or absent evidence
before writing artifacts. Collect separate repository PR/issue totals with the
existing authorized token only; failed refreshes may retain verified original
observations within an explicit maximum age, never invent zero. The existing
19 zero-row leaves and relationship attestations need independent review; this
producer must not manufacture exemptions or change their delivery state. Current
production adapters remain unchanged until that review and staged build integration.
