# Tasks — PIPE-PAGES

- [ ] Review public consumer declaration and receipt schema with full commits, content sources, and owner links.
- [ ] Refactor existing parity script to use exact fetched commits and shared theme enumeration, removing fixed names and worktree fallback.
- [ ] Add strict dirty/untracked, missing-ref, traversal, and mismatch refusal with asset-specific diagnostics.
- [ ] Produce deterministic JSON verification fields and readable Pages summary; retain historical links.
- [ ] Bind parity only to shared theme/navigation promotion; update workflow contract without a live gate on unrelated PRs.
- [ ] Add P-1–P-5 and N-1–N-6 tests; validate YAML, schema, CCCC, jscpd, Dupehound, KISS, and Pages contract.
- [ ] Publish from exact commits, collect consumer/served-site evidence, and update delivery and acceptance separately.

No task above cites a `requirements.md` ID by name. PIPE-PAGES-R001 (repository switcher sync) is
closed by tasks 1-4 above (declared fleet, exact parity, release receipt). PIPE-PAGES-R007 and
PIPE-PAGES-R011 (ecosystem flow diagram, present-tense home page) are already `LANDED` per
`status.json` with merged-head evidence and need no new task.
- [ ] Build or confirm the remaining documentation-site content requirements not covered above:
      layered navigation from overview to reference, present-tense wording with an accessible
      embedded quick start, one progressively disclosed skill-graph content corpus, architecture and
      API-contract reference pages generated from their registries, generated/gate-checked artifacts
      rehomed out of the legacy docs directory, and HTML/CSS architecture views with no ASCII or
      Mermaid diagrams. Closes PIPE-PAGES-R002, PIPE-PAGES-R003, PIPE-PAGES-R004, PIPE-PAGES-R005,
      PIPE-PAGES-R006, PIPE-PAGES-R008, PIPE-PAGES-R009, PIPE-PAGES-R010.
- [ ] PIPE-PAGES-R012: Concept references on the spec-delivery page. Producer first; children below.
- [ ] PIPE-PAGES-R012.1: Add `concepts_for_row(row, roots)` to `scripts/spec_dashboard_sources.py`.
- [ ] PIPE-PAGES-R012.2: Add `explicit_concepts(text)` to `scripts/spec_dashboard_sources.py`.
- [ ] PIPE-PAGES-R012.3: Add one anchor per concept in `scripts/skill_graph/render_pages.py` (`render_concepts_md`): each bullet gets the slug id `concept-<slug>`.
- [ ] PIPE-PAGES-R012.4: Add `concept_links(ids, base)` to `scripts/spec_dashboard_panels.py`.
- [ ] PIPE-PAGES-R012.5: Call `concept_links` from `spec_row` in `scripts/spec_dashboard_panels.py` and from the requirement table in `scripts/spec_dashboard_structure.py`, so every spec row and requirement row carries a Concepts cell..
- [ ] PIPE-PAGES-R012.6: Add the count of `no concept mapped` rows to `count_caption` in `scripts/spec_dashboard_render.py`, so the page states the number of unmapped rows..
- [ ] PIPE-PAGES-R012.7: Add `check_concept_links(page, concepts_md)` to `scripts/spec_dashboard_sources.py`.
- [ ] PIPE-PAGES-R013: Spec relationship view on the spec-delivery page. Producer first; children below.
- [ ] PIPE-PAGES-R013.1: Add `spec_edges(records)` to `scripts/spec_graph_core.py`.
- [ ] PIPE-PAGES-R013.2: Add the `extends` edge to `spec_edges` in `scripts/spec_graph_core.py`.
- [ ] PIPE-PAGES-R013.3: Add `layer_specs(nodes, edges)` to `scripts/spec_dashboard_structure.py`.
- [ ] PIPE-PAGES-R013.4: Add `relation_view(nodes, edges)` to `scripts/spec_dashboard_panels.py`.
- [ ] PIPE-PAGES-R013.5: Render edges in `relation_view` as labelled CSS connectors (`depends on`, `extends`), and render a legend that explains the two labels and the state colours.
- [ ] PIPE-PAGES-R013.6: Add `relation_table(nodes, edges)` to `scripts/spec_dashboard_panels.py`.
- [ ] PIPE-PAGES-R013.7: Cap the view at 40 specs in `relation_view`.
- [ ] PIPE-PAGES-R014: Three-level drill-down from the ecosystem view to the spec. Producer first; children below.
- [ ] PIPE-PAGES-R014.1: Add `ecosystem_components()` to `scripts/spec_dashboard_sources.py`.
- [ ] PIPE-PAGES-R014.2: Define the URL form in `scripts/spec_dashboard_sources.py`: level 1 `https://knuckles-team.github.io/<repo>/spec-delivery/`, level 2 `.../spec-delivery/#spec-<ID>`, level 3 row `.../spec-delivery/#req-<ID>`.
- [ ] PIPE-PAGES-R014.3: Emit the anchors in `spec_row` (`scripts/spec_dashboard_panels.py`): each spec section gets `id="spec-<ID>"` and lists its rows, state, concepts, and bound tests; each row gets `id="req-<ID>"`..
- [ ] PIPE-PAGES-R014.4: Link each box in `relation_view` (`scripts/spec_dashboard_panels.py`) to `#spec-<ID>` of its own page, or to the other repository's page for a cross-repository node..
- [ ] PIPE-PAGES-R014.5: Cross-repository row, owner `Knuckles-Team/.github` (BLOCKED until that repository carries a spec tree): link each component in `profile/README.md` to `ecosystem_components()` URLs at level 1.
- [ ] PIPE-PAGES-R014.6: Add `check_drilldown_links(readme, site_index)` to `scripts/spec_dashboard_sources.py`.
- [ ] PIPE-PAGES-R015: One generator for connectors and client repositories. Producer first; children below.
- [ ] PIPE-PAGES-R015.1: The reusable workflow `.github/workflows/pages_pipeline.yml` must run the R012 to R014 steps for every caller.
- [ ] PIPE-PAGES-R015.2: agent-webui, agent-terminal-ui, and geniusbot adopt it through the caller pattern in PIPE-CONNSPEC-R004.
- [ ] PIPE-PAGES-R015.3: Connector repositories get the same page through PIPE-CONNSPEC-R101 and following.

- [ ] Recheck historical R001/R003/R009 acceptance notes against current exact source and served-site evidence.
- [ ] Validate R013.3 cycle layout with the planned order-independence test.
- [ ] PIPE-PAGES-R016: **Spec-delivery page shows only the current spec state.** Rollup of the children below
- [ ] PIPE-PAGES-R016.1: Remove the `history` field and the `--history-limit` option from `create_snapshot` and `argument_parser` in `scripts/spec_dashboard.py`. The snapshot holds only records read from the current tree, so no ID absent from that tree enters it.
- [ ] PIPE-PAGES-R016.2: Remove `history_panels` and the history and per-commit panels from `scripts/spec_dashboard_render.py`, then delete `scripts/spec_dashboard_charts.py`, `scripts/spec_dashboard_history.py`, `scripts/spec_dashboard_history_metrics.py`, and `scripts/spec_dashboard_history_views.py` with their tests. No state-transition table, chart, metric or panel is rendered.
- [ ] PIPE-PAGES-R016.3: Render only records present in the current `specs/` tree. A requirement ID that was removed in an earlier commit appears nowhere in the HTML.
- [ ] PIPE-PAGES-R016.4: Remove the history scripts from the sparse checkout and the history option from the dashboard call in `.github/workflows/pages_pipeline.yml`. The Pages workflow does not invoke the history modules.
- [ ] PIPE-PAGES-R016.5: Do not render records whose state is `RETIRED`. `read_records` in `scripts/spec_dashboard_sources.py` drops them.
- [ ] PIPE-PAGES-R017: **Three states only.** Rollup of the children below. A requirement row and a spec have one state field with the values `SPECIFIED`, `LANDED` and `VERIFIED`.
- [ ] PIPE-PAGES-R017.1: The state legend lists exactly three states, `SPECIFIED`, `LANDED` and `VERIFIED`, each with a one-line definition, in `definitions_panel` in `scripts/spec_dashboard_panels.py`.
- [ ] PIPE-PAGES-R017.2: Every record row shows one state cell. The page has no acceptance column, no release column and no second state label.
- [ ] PIPE-PAGES-R017.3: A `delivery_state` outside the three states, after `RETIRED` is filtered, renders as `INVALID` and counts in one visible invalid-state number.
- [ ] PIPE-PAGES-R018: **Spec delivery is a native menu entry on every documentation site.** Rollup of the children below
- [ ] PIPE-PAGES-R018.1: Add the `spec_delivery` flag to `extra:` in `templates/mkdocs-theme/base.mkdocs.yml` as `!ENV [SPEC_DELIVERY_ENABLED, false]`. Set the variable from `inputs.spec_dashboard_enabled` on the Build Docs step of `.github/workflows/pages_pipeline.yml`.
- [ ] PIPE-PAGES-R018.2: Render a `Spec delivery` link in `templates/mkdocs-theme/overrides/main.html`. The link must use `base_url` and `/spec-delivery/`, and the block must render only when the flag is set.
- [ ] PIPE-PAGES-R018.3: List the `spec-delivery/` page of each repository in a native `<details>` list inside the same navigation landmark. The list must iterate `extra.ecosystem.sites` and must hold no second repository list.
- [ ] PIPE-PAGES-R018.4: Keep every `extra.ecosystem.sites` URL in `templates/mkdocs-theme/base.mkdocs.yml` equal to its `REPOS` entry in `scripts/skill_graph/model.py`.
- [ ] PIPE-PAGES-R018.5: Style the entry in a `<style>` element inside the block in `templates/mkdocs-theme/overrides/main.html` with a visible focus outline. The override is served from the theme checkout through `custom_dir`, so the theme sync check needs no consumer change.
- [ ] PIPE-PAGES-R019: **The spec-delivery page carries the documentation site's navigation.** Rollup of the children below. Readers must move between the documentation and the page without the browser's address bar.
- [ ] PIPE-PAGES-R019.1: Add `site_nav(repository)` to `scripts/spec_dashboard_nav.py`. It renders `<nav aria-label="Site">` with the repository name and a `Documentation` link, both to `../`.
- [ ] PIPE-PAGES-R019.2: Mark the current page in `site_nav` with `aria-current="page"` on the `Spec delivery` entry.
- [ ] PIPE-PAGES-R019.3: List every repository in `site_nav` from `ecosystem_components()` in `scripts/spec_dashboard_drilldown.py`. Link each to its level-1 URL and mark the current repository. Define no second list.
- [ ] PIPE-PAGES-R019.4: Add `skip_link()` to `scripts/spec_dashboard_nav.py` and wrap the sheet in `<main id="main">` in `render` in `scripts/spec_dashboard_render.py`. Style the bar with the existing tokens in `scripts/spec_dashboard_style.py`.
- [ ] PIPE-PAGES-R019.5: Add `scripts/spec_dashboard_nav.py` to the sparse checkout in `.github/workflows/pages_pipeline.yml`. The page must keep every existing panel.
- [ ] PIPE-PAGES-R020: **Documentation claims must match the repository.** Rollup of the children below. The public-surface gate resolves each documented path, command, gate name and count against the tree.
- [ ] PIPE-PAGES-R020.1: **Model.** Add frozen dataclass `DocClaim` (file, line, kind, text) to `pipelines_hooks/docs/claims.py`. The `kind` field takes one of `path`, `command`, `gate`, `count`, `diagram-node`.
- [ ] PIPE-PAGES-R020.2: **Behavior.** Add `claim_findings(root, claims)` to `pipelines_hooks/docs/claims.py`. Each kind has one named resolver in `RESOLVERS`: a path must exist, a gate must be in `GATES`, a count must equal the measured count, a diagram node must match a registry name. Each resolver is a replaceable default.
- [ ] PIPE-PAGES-R020.3: **Wiring.** Call `claim_findings` from `validate` at `pipelines_hooks/docs/public_surface.py:31`. `main` in `pipelines_hooks/cli.py:79` reaches it through `run_gate` at `pipelines_hooks/cli.py:66`. The `public-surface` hook at `.pre-commit-hooks.yaml:183` is the production caller.
- [ ] PIPE-PAGES-R020.4: **Refusal.** When a claim has no resolver or the registry is unreadable, `claim_findings` returns the typed finding `claims-unchecked` with the file and line. It never passes silently.
- [ ] PIPE-PAGES-R020.5: **Evidence.** The gate prints one line `claims: checked N, unresolved M` and one finding per unresolved claim as `file:line kind text`.
- [ ] PIPE-PAGES-R020.6: **Hot-path proof.** The entry point is `pipelines-hook public-surface`, run through `main` in `pipelines_hooks/cli.py:79` on a fixture repository whose README names a missing path. The hook must exit 1 and print that path's `file:line`.
- [ ] PIPE-PAGES-R021: **Test quality gate for repository validation.** Rollup of the children below. The gate rejects placeholder tests and unjustified suppressions, and enforces a coverage threshold. Each finding names its rule and location, so the fixer addresses the root cause before the re-test.
- [ ] PIPE-PAGES-R021.1: **Model.** Add frozen dataclass `TestQualityFinding` (path, line, rule) to `pipelines_hooks/code/test_quality.py`. The `rule` field takes one of `placeholder-test`, `unjustified-suppression`, `coverage-below-threshold`.
- [ ] PIPE-PAGES-R021.2: **Behavior.** Add `scan(root, threshold)` to `pipelines_hooks/code/test_quality.py`. A test whose body is only `pass`, `...` or `assert True` is a placeholder. A suppression needs a reason of at least 10 characters. The coverage threshold defaults to 80 percent. Each rule is a replaceable default.
- [ ] PIPE-PAGES-R021.3: **Wiring.** This row creates the call site. Add `test-quality` to `GATES` at `pipelines_hooks/cli.py:33` and a hook entry beside `no-stub` at `.pre-commit-hooks.yaml:141`. `run_gate` at `pipelines_hooks/cli.py:59` is its caller.
- [ ] PIPE-PAGES-R021.4: **Refusal.** When no coverage report exists, `main` raises `CannotRun`. `run_gate` maps it to exit 2. The gate never reports a pass without a measured percentage.
- [ ] PIPE-PAGES-R021.5: **Evidence.** The gate prints `test-quality: files N, placeholders M, coverage P%, threshold T%` and one `path:line rule` line per finding.
- [ ] PIPE-PAGES-R021.6: **Hot-path proof.** The entry point is `pipelines-hook test-quality` through `main` in `pipelines_hooks/cli.py:79`. A fixture repository with a placeholder test and 70 percent coverage must exit 1 and list both findings.
- [ ] PIPE-PAGES-R022: **Scheduled mutation testing reports test gaps.** Rollup of the children below. A scheduled run mutates core modules, and each surviving mutation is reported as a test gap with its module and line.
- [ ] PIPE-PAGES-R022.1: **Model.** Add frozen dataclasses `MutationPolicy` (modules, schedule) and `SurvivingMutation` (module, line, operator) to `pipelines_hooks/code/mutation_gaps.py`. The default `modules` value is `pipelines_hooks/core`.
- [ ] PIPE-PAGES-R022.2: **Behavior.** Add `survivors(policy, runner)` to `pipelines_hooks/code/mutation_gaps.py`. It returns one `SurvivingMutation` per mutant the tests did not kill and none for killed mutants. The runner is a replaceable default.
- [ ] PIPE-PAGES-R022.3: **Wiring.** This row creates the call site. Add `mutation-gaps` to `GATES` at `pipelines_hooks/cli.py:33`. Add `.github/workflows/mutation.yml` with a weekly schedule that runs `pipelines-hook mutation-gaps`. `run_gate` at `pipelines_hooks/cli.py:59` is the caller.
- [ ] PIPE-PAGES-R022.4: **Refusal.** When the runner is absent, `main` raises `Unavailable`, which `run_gate` at `pipelines_hooks/cli.py:66` fails closed in CI. A module with no tests yields the finding `no-tests-for-module`.
- [ ] PIPE-PAGES-R022.5: **Evidence.** The report prints one line `module:line operator` per survivor and one `module: killed K, survived S` line per module.
- [ ] PIPE-PAGES-R022.6: **Hot-path proof.** The entry point is `pipelines-hook mutation-gaps` through `main` in `pipelines_hooks/cli.py:79`. A fixture module with one untested branch must exit 1 and print that module and line.
- [ ] PIPE-PAGES-R020.7: Model: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R020.8: Behavior: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R020.9: Wiring: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R020.10: Refusal: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R020.11: Evidence: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R020.12: Hot-path proof: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R021.7: Model: Assert the closed edge kinds and separate runtime/type-only permissions. Implement and bind `test_component_contract_model` in `tests/hooks/test_test_quality_hook.py`.
- [ ] PIPE-PAGES-R021.8: Behavior: Assert allowed lazy imports preserve reachability, forbidden lazy imports fail, and type-only imports cannot prove runtime reachability. Implement and bind `test_component_contract_checks` in `tests/hooks/test_test_quality_hook.py`.
- [ ] PIPE-PAGES-R021.9: Wiring: Assert the CLI boundary/orphan path consumes the static runtime graph and cycle checks retain the eager graph. Implement and bind `test_component_checks_are_wired` in `tests/hooks/test_test_quality_hook.py`.
- [ ] PIPE-PAGES-R021.10: Refusal: Assert unresolved dynamic reachability is exit 2, never a false clean or definite orphan; retain receipt refusals. Implement and bind `test_component_proof_refusals` in `tests/hooks/test_test_quality_hook.py`.
- [ ] PIPE-PAGES-R021.11: Evidence: Assert runtime, type-only and unresolved dynamic evidence remain distinguishable. Implement and bind `test_component_evidence_receipts` in `tests/hooks/test_test_quality_hook.py`.
- [ ] PIPE-PAGES-R021.12: Hot-path proof: Assert CLI exit codes, exact edge locations, type-only separation and no false orphan for allowed lazy imports. Implement and bind `test_component_handoff_cli` and `test_component_lazy_import_cli` in `tests/hooks/test_test_quality_hook.py`.
- [ ] PIPE-PAGES-R023.1: Model: implement the requirement and its acceptance test. Carry a document base separately from the containment root.
- [ ] PIPE-PAGES-R023.2: Behavior: implement the requirement and its acceptance test. Resolve nested and parent-relative links from the document while enforcing repository containment.
- [ ] PIPE-PAGES-R023.3: Wiring: implement the requirement and its acceptance test. Adapt the shared helper without changing root README behavior.
- [ ] PIPE-PAGES-R023.4: Refusal: implement the requirement and its acceptance test. Refuse traversal outside the repository, escaped document bases and symlinks outside the repository.
- [ ] PIPE-PAGES-R023.5: Evidence: implement the requirement and its acceptance test. Emit located source-document and resolved-target evidence.
- [ ] PIPE-PAGES-R023.6: Hot-path proof: implement the requirement and its acceptance test. Run `test_nested_skill_links_cli` in `tests/hooks/test_skill_grade_hook.py`; sibling and in-repository parent links pass, missing or escaping links fail.
- [ ] PIPE-PAGES-R024.1: Model: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R024.2: Behavior: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R024.3: Wiring: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R024.4: Refusal: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R024.5: Evidence: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R024.6: Hot-path proof: implement the requirement and its acceptance test.
- [ ] PIPE-PAGES-R021.13: Model: Reject unknown outcome kinds, empty observables and missing source bindings; accept return, error and side-effect contracts. Implement and bind `test_outcome_contract_schema` in `tests/hooks/test_test_quality_outcomes.py`.
- [ ] PIPE-PAGES-R021.14: Behavior: Reject a passing test that ignores the result; accept exact return, error and state assertions that detect their counterexamples. Implement and bind `test_outcome_counterexamples` in `tests/hooks/test_test_quality_outcomes.py`.
- [ ] PIPE-PAGES-R021.15: Wiring: Assert the published CLI invokes the configured runner, validates its receipts and includes outcome findings in its exit code. Implement and bind `test_outcome_checker_wiring` in `tests/hooks/test_test_quality_outcomes.py`.
- [ ] PIPE-PAGES-R021.16: Refusal: Missing contracts and surviving counterexamples exit 1; stale, skipped, setup-failing and timed-out proofs exit 2. Implement and bind `test_outcome_proof_refusals` in `tests/hooks/test_test_quality_outcomes.py`.
- [ ] PIPE-PAGES-R021.17: Evidence: Assert distinct static/runtime records and digest-bound receipts; never report coverage or assertion count as outcome proof. Implement and bind `test_outcome_evidence` in `tests/hooks/test_test_quality_outcomes.py`.
- [ ] PIPE-PAGES-R021.18: Hot-path proof: Assert exit 0 for proved outcomes, exit 1 for missing observation and exit 2 for unchecked proof through the real CLI and runner. Implement and bind `test_outcome_quality_cli` in `tests/hooks/test_test_quality_outcomes.py`.
