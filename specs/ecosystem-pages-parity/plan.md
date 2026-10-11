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
