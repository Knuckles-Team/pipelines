# Test contract — PIPE-PAGES

Use disposable Git fixtures with six consumer shapes and a pinned shared theme commit. Assert exact JSON fields and exit status; retain sanitized output and commit refs as release evidence.

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-1 | Six valid declarations resolve exact commits/trees without sibling workspace. |
| N-1 | FR-1 | Duplicate, absent, malformed, or mutable revision fails before comparison. |
| N-2 | FR-1 | Untracked theme overlay or dirty fetched tree fails even when tracked assets match. |
| P-2 | FR-2 | Byte-identical assets compare equal and every path/digest appears in receipt. |
| N-3 | FR-2 | One changed byte names repository/asset and prevents current-pass receipt. |
| N-4 | FR-2 | Missing content source, escaped symlink, or required asset fails closed. |
| P-3 | FR-3 | Exact-input runs yield identical verification fields; presentation carries schema/time. |
| N-5 | FR-3 | Changed revision makes prior receipt historical; cached pass is not reused. |
| P-4 | FR-4 | Promotion consumes success; unrelated code PR runs without Pages access. |
| N-6 | FR-4 | Failed parity prevents theme promotion with actionable reason. |
| P-5 | FR-5 | Consumer results link own commits; checker does not mutate consumer trees. |

Contract tests inspect `pages_pipeline.yml` for least-privilege checkout, immutable shared source, and release condition. Hosted Pages URL and browser probe are release acceptance evidence, not unit-test prerequisites. Run YAML parse, relevant pytest, and configured CCCC/jscpd/Dupehound/KISS gates on implementation. Record unavailable scanners as gaps, never as passes.
| T-PIPE-PAGES-R012.1 | PIPE-PAGES-R012.1 | `test_concepts_for_row_reads_markers` in `tests/test_spec_dashboard_concepts.py` uses a fixture root with two markers and expects both. |
| T-PIPE-PAGES-R012.2 | PIPE-PAGES-R012.2 | `test_explicit_concepts_override` in `tests/test_spec_dashboard_concepts.py` expects the explicit list to replace the derived list. |
| T-PIPE-PAGES-R012.3 | PIPE-PAGES-R012.3 | `test_concepts_md_has_anchor_per_concept` in `tests/test_skill_graph_pages.py` expects one anchor per corpus concept. |
| T-PIPE-PAGES-R012.4 | PIPE-PAGES-R012.4 | `test_concept_links_and_marker` in `tests/test_spec_dashboard_concepts.py` expects links for two identifiers and the marker for none. |
| T-PIPE-PAGES-R012.5 | PIPE-PAGES-R012.5 | `test_every_row_has_concepts_cell` in `tests/test_spec_dashboard_render.py` expects one cell per rendered row. |
| T-PIPE-PAGES-R012.6 | PIPE-PAGES-R012.6 | `test_caption_counts_unmapped_rows` in `tests/test_spec_dashboard_render.py` expects the count in the caption. |
| T-PIPE-PAGES-R012.7 | PIPE-PAGES-R012.7 | `test_dangling_concept_link_fails` in `tests/test_spec_dashboard_concepts.py` expects exit 1 for a missing anchor and 0 for a present one. |
| T-PIPE-PAGES-R013.1 | PIPE-PAGES-R013.1 | `test_spec_edges_lift_requirement_edges` in `tests/test_spec_graph_edges.py` expects one spec edge per spec pair. |
| T-PIPE-PAGES-R013.2 | PIPE-PAGES-R013.2 | `test_extends_edge_from_spec_md` in `tests/test_spec_graph_edges.py` expects an `extends` edge for the declared line. |
| T-PIPE-PAGES-R013.3 | PIPE-PAGES-R013.3 | `test_layers_by_dependency_depth` in `tests/test_spec_dashboard_relations.py` expects depth 0, 1, 2 for a three-spec chain. |
| T-PIPE-PAGES-R013.4 | PIPE-PAGES-R013.4 | `test_relation_view_is_html_css` in `tests/test_spec_dashboard_relations.py` expects no `<svg`, no `mermaid`, and one box per spec. |
| T-PIPE-PAGES-R013.5 | PIPE-PAGES-R013.5 | `test_relation_view_has_legend_and_labels` in `tests/test_spec_dashboard_relations.py` expects the legend and both labels. |
| T-PIPE-PAGES-R013.6 | PIPE-PAGES-R013.6 | `test_relation_table_matches_edges` in `tests/test_spec_dashboard_relations.py` expects one table row per edge. |
| T-PIPE-PAGES-R013.7 | PIPE-PAGES-R013.7 | `test_view_cap_falls_back_to_table` in `tests/test_spec_dashboard_relations.py` expects no boxes at 41 specs and a full table. |
| T-PIPE-PAGES-R014.1 | PIPE-PAGES-R014.1 | `test_components_equal_core_list` in `tests/test_spec_dashboard_drilldown.py` expects equality with the R001 list. |
| T-PIPE-PAGES-R014.2 | PIPE-PAGES-R014.2 | `test_anchor_forms` in `tests/test_spec_dashboard_drilldown.py` expects the three forms. |
| T-PIPE-PAGES-R014.3 | PIPE-PAGES-R014.3 | `test_spec_section_has_anchor_and_contents` in `tests/test_spec_dashboard_drilldown.py` expects the anchor and four content blocks. |
| T-PIPE-PAGES-R014.4 | PIPE-PAGES-R014.4 | `test_relation_box_links_to_spec_section` in `tests/test_spec_dashboard_drilldown.py` expects the href on every box. |
| T-PIPE-PAGES-R014.5 | PIPE-PAGES-R014.5 | `test_profile_links_cover_components` in `tests/test_render_profile_links.py` expects one level-1 link per component. |
| T-PIPE-PAGES-R014.6 | PIPE-PAGES-R014.6 | `test_unresolved_component_link_fails` in `tests/test_spec_dashboard_drilldown.py` expects exit 1 for a missing page. |
| T-PIPE-PAGES-R015.1 | PIPE-PAGES-R015.1 | `test_pages_workflow_runs_relation_steps` in `tests/test_pages_pipeline_contract.py` expects the steps and no repository names. |
| T-PIPE-PAGES-R015.2 | PIPE-PAGES-R015.2 | `test_client_callers_use_reusable_workflow` in `tests/test_pages_pipeline_contract.py` expects each caller to reference the workflow at `main`. |
| T-PIPE-PAGES-R015.3 | PIPE-PAGES-R015.3 | `test_connector_page_has_concepts_and_relations` in `tests/test_spec_dashboard_render.py` expects both blocks in a connector fixture. |
