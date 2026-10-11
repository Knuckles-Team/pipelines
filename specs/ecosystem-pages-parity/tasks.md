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
