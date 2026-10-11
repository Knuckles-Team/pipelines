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
| T-PIPE-PAGES-R012.5 | PIPE-PAGES-R012.5 | `test_spec_row_carries_concepts_cell` in `tests/test_spec_dashboard_concepts.py` expects one cell per rendered row. |
| T-PIPE-PAGES-R012.6 | PIPE-PAGES-R012.6 | `test_caption_counts_unmapped_rows` in `tests/test_spec_dashboard_concepts.py` expects the count in the caption. |
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
| T-PIPE-PAGES-R014.3 | PIPE-PAGES-R014.3 | `test_spec_section_has_anchor` in `tests/test_spec_dashboard_drilldown.py` expects the anchor and four content blocks. |
| T-PIPE-PAGES-R014.4 | PIPE-PAGES-R014.4 | `test_relation_box_links_to_spec_section` in `tests/test_spec_dashboard_drilldown.py` expects the href on every box. |
| T-PIPE-PAGES-R014.5 | PIPE-PAGES-R014.5 | `test_profile_links_cover_components` in `tests/test_render_profile_links.py` expects one level-1 link per component. |
| T-PIPE-PAGES-R014.6 | PIPE-PAGES-R014.6 | `test_unresolved_component_link_fails` in `tests/test_spec_dashboard_drilldown.py` expects exit 1 for a missing page. |
| T-PIPE-PAGES-R015.1 | PIPE-PAGES-R015.1 | `test_pages_workflow_runs_relation_steps` in `tests/test_pages_pipeline_contract.py` expects the steps and no repository names. |
| T-PIPE-PAGES-R015.2 | PIPE-PAGES-R015.2 | `test_client_callers_use_reusable_workflow` in `tests/test_pages_pipeline_contract.py` expects each caller to reference the workflow at `main`. |
| T-PIPE-PAGES-R015.3 | PIPE-PAGES-R015.3 | `test_connector_page_has_concepts_and_relations` in `tests/test_spec_dashboard_render.py` expects both blocks in a connector fixture. |


## Planned cycle-layout acceptance

`tests/test_spec_dashboard_relations.py::test_cycle_layers_are_order_independent` must cover self-loops and three-node cycles.
Incoming and outgoing dependencies must retain their depth after strongly connected components collapse.
Input permutations must produce identical layers. The relationship table must retain every original edge.
This test is planned; this documentation change does not implement it.
| T-PIPE-PAGES-R016.1 | PIPE-PAGES-R016.1 | Run `test_snapshot_has_no_history_field` in `tests/test_spec_dashboard.py` expects no `history` key in the snapshot. |
| T-PIPE-PAGES-R016.2 | PIPE-PAGES-R016.2 | Run `test_page_has_no_history_panels` in `tests/test_spec_dashboard.py` expects no history, transition or timeline marker in the HTML. |
| T-PIPE-PAGES-R016.3 | PIPE-PAGES-R016.3 | Run `test_removed_id_absent_from_page` in `tests/test_spec_dashboard.py` expects a removed ID to be absent from the page built from a repository whose history contains it. |
| T-PIPE-PAGES-R016.4 | PIPE-PAGES-R016.4 | Run `test_workflow_does_not_reference_history_scripts` in `tests/test_spec_dashboard.py` expects no `spec_dashboard_history` or `spec_dashboard_charts` in the workflow. |
| T-PIPE-PAGES-R016.5 | PIPE-PAGES-R016.5 | Run `test_retired_record_is_not_rendered` in `tests/test_spec_dashboard.py` expects one VERIFIED record rendered and the RETIRED ID absent. |
| T-PIPE-PAGES-R017.1 | PIPE-PAGES-R017.1 | Run `test_legend_has_three_states` in `tests/test_spec_dashboard_states.py` expects exactly three legend rows. |
| T-PIPE-PAGES-R017.2 | PIPE-PAGES-R017.2 | Run `test_row_has_one_state_cell` in `tests/test_spec_dashboard_states.py` expects one state cell and no acceptance text. |
| T-PIPE-PAGES-R017.3 | PIPE-PAGES-R017.3 | Run `test_unknown_state_renders_invalid` in `tests/test_spec_dashboard_states.py` expects `INVALID` and a count of one. |
| T-PIPE-PAGES-R018.1 | PIPE-PAGES-R018.1 | Run `test_flag_is_env_driven` in `tests/test_spec_delivery_nav.py` expects the `!ENV` flag and the workflow variable. |
| T-PIPE-PAGES-R018.2 | PIPE-PAGES-R018.2 | Run `test_entry_is_root_relative_and_flag_gated` in `tests/test_spec_delivery_nav.py` expects `base_url`, no host, and the flag guard. |
| T-PIPE-PAGES-R018.3 | PIPE-PAGES-R018.3 | Run `test_menu_iterates_the_single_site_list` in `tests/test_spec_delivery_nav.py` expects the loop over `extra.ecosystem.sites` and no literal repository URL in the template. |
| T-PIPE-PAGES-R018.4 | PIPE-PAGES-R018.4 | Run `test_site_urls_match_repos` in `tests/test_spec_delivery_nav.py` expects each site URL to equal the REPOS URL for its slug. |
| T-PIPE-PAGES-R018.5 | PIPE-PAGES-R018.5 | Run `test_theme_sync_check_passes_with_entry` in `tests/test_spec_delivery_nav.py` expects an empty drift list. |
| T-PIPE-PAGES-R019.1 | PIPE-PAGES-R019.1 | Run `test_nav_landmark_links_documentation` in `tests/test_spec_dashboard_nav.py` expects the stated result. |
| T-PIPE-PAGES-R019.2 | PIPE-PAGES-R019.2 | Run `test_current_page_is_marked` in `tests/test_spec_dashboard_nav.py` expects the stated result. |
| T-PIPE-PAGES-R019.3 | PIPE-PAGES-R019.3 | Run `test_repository_links_equal_single_source` in `tests/test_spec_dashboard_nav.py` expects the stated result. |
| T-PIPE-PAGES-R019.4 | PIPE-PAGES-R019.4 | Run `test_skip_link_targets_main` in `tests/test_spec_dashboard_nav.py` expects the stated result. |
| T-PIPE-PAGES-R019.5 | PIPE-PAGES-R019.5 | Run `test_page_keeps_existing_panels` in `tests/test_spec_dashboard_nav.py` expects the stated result. |
| T-PIPE-PAGES-R020.1 | PIPE-PAGES-R020.1 | Run `test_doc_claim_kind_is_closed` in `tests/hooks/test_doc_claims.py` expects a `ValueError` for any other kind. |
| T-PIPE-PAGES-R020.2 | PIPE-PAGES-R020.2 | Run `test_resolvers_check_each_kind` in `tests/hooks/test_doc_claims.py` expects one finding per false claim and none for true claims. |
| T-PIPE-PAGES-R020.3 | PIPE-PAGES-R020.3 | Run `test_validate_calls_claim_findings` in `tests/hooks/test_doc_claims.py` expects a claim finding from `validate` on a stale fixture. |
| T-PIPE-PAGES-R020.4 | PIPE-PAGES-R020.4 | Run `test_unresolvable_claim_is_reported` in `tests/hooks/test_doc_claims.py` expects the `claims-unchecked` finding. |
| T-PIPE-PAGES-R020.5 | PIPE-PAGES-R020.5 | Run `test_claims_summary_line` in `tests/hooks/test_doc_claims.py` expects the counts to equal the fixture. |
| T-PIPE-PAGES-R020.6 | PIPE-PAGES-R020.6 | Run `test_public_surface_hook_fails_on_stale_claim` in `tests/hooks/test_public_surface_claims.py` expects exit 1 and the finding. |
| T-PIPE-PAGES-R021.1 | PIPE-PAGES-R021.1 | Run `test_finding_rule_is_closed` in `tests/hooks/test_test_quality.py` expects a `ValueError` for any other rule. |
| T-PIPE-PAGES-R021.2 | PIPE-PAGES-R021.2 | Run `test_scan_flags_placeholder_and_bare_suppression` in `tests/hooks/test_test_quality.py` expects one finding per violation. |
| T-PIPE-PAGES-R021.3 | PIPE-PAGES-R021.3 | Run `test_test_quality_is_registered` in `tests/hooks/test_test_quality.py` expects the name in `GATES` and in the hook file. |
| T-PIPE-PAGES-R021.4 | PIPE-PAGES-R021.4 | Run `test_missing_coverage_report_cannot_run` in `tests/hooks/test_test_quality.py` expects exit 2. |
| T-PIPE-PAGES-R021.5 | PIPE-PAGES-R021.5 | Run `test_test_quality_summary_line` in `tests/hooks/test_test_quality.py` expects the stated fields. |
| T-PIPE-PAGES-R021.6 | PIPE-PAGES-R021.6 | Run `test_test_quality_hook_fails_fixture` in `tests/hooks/test_test_quality_hook.py` expects exit 1 and two findings. |
| T-PIPE-PAGES-R022.1 | PIPE-PAGES-R022.1 | Run `test_policy_defaults` in `tests/hooks/test_mutation_gaps.py` expects the default module list. |
| T-PIPE-PAGES-R022.2 | PIPE-PAGES-R022.2 | Run `test_only_survivors_are_reported` in `tests/hooks/test_mutation_gaps.py` expects survivors only. |
| T-PIPE-PAGES-R022.3 | PIPE-PAGES-R022.3 | Run `test_mutation_workflow_runs_gate` in `tests/hooks/test_mutation_gaps.py` expects the cron entry and the gate command. |
| T-PIPE-PAGES-R022.4 | PIPE-PAGES-R022.4 | Run `test_absent_runner_fails_closed_in_ci` in `tests/hooks/test_mutation_gaps.py` expects exit 2 under `CI=1`. |
| T-PIPE-PAGES-R022.5 | PIPE-PAGES-R022.5 | Run `test_mutation_report_lines` in `tests/hooks/test_mutation_gaps.py` expects the stated lines. |
| T-PIPE-PAGES-R022.6 | PIPE-PAGES-R022.6 | Run `test_mutation_gaps_hook_reports_untested_branch` in `tests/hooks/test_mutation_gaps_hook.py` expects exit 1 and the line. |
| T-PIPE-PAGES-R020.7 | PIPE-PAGES-R020.7 | Run `test_located_finding_schema` in `tests/hooks/test_public_surface_claims.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R020.8 | PIPE-PAGES-R020.8 | Run `test_located_evidence_matches_tree` in `tests/hooks/test_public_surface_claims.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R020.9 | PIPE-PAGES-R020.9 | Run `test_finding_validator_is_wired` in `tests/hooks/test_public_surface_claims.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R020.10 | PIPE-PAGES-R020.10 | Run `test_unsupported_finding_refused` in `tests/hooks/test_public_surface_claims.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R020.11 | PIPE-PAGES-R020.11 | Run `test_located_evidence_export` in `tests/hooks/test_public_surface_claims.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R020.12 | PIPE-PAGES-R020.12 | Run `test_public_surface_located_evidence_cli` in `tests/hooks/test_public_surface_claims.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R021.7 | PIPE-PAGES-R021.7 | Run `test_component_contract_model` in `tests/hooks/test_test_quality_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R021.8 | PIPE-PAGES-R021.8 | Run `test_component_contract_checks` in `tests/hooks/test_test_quality_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R021.9 | PIPE-PAGES-R021.9 | Run `test_component_checks_are_wired` in `tests/hooks/test_test_quality_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R021.10 | PIPE-PAGES-R021.10 | Run `test_component_proof_refusals` in `tests/hooks/test_test_quality_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R021.11 | PIPE-PAGES-R021.11 | Run `test_component_evidence_receipts` in `tests/hooks/test_test_quality_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R021.12 | PIPE-PAGES-R021.12 | Run `test_component_handoff_cli` in `tests/hooks/test_test_quality_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R023.1 | PIPE-PAGES-R023.1 | Run `test_skill_grade_model` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R023.2 | PIPE-PAGES-R023.2 | Run `test_skill_grade_criteria` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R023.3 | PIPE-PAGES-R023.3 | Run `test_skill_grade_registration` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R023.4 | PIPE-PAGES-R023.4 | Run `test_skill_grade_refusals` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R023.5 | PIPE-PAGES-R023.5 | Run `test_skill_grade_evidence` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R023.6 | PIPE-PAGES-R023.6 | Run `test_skill_grade_cli` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.1 | PIPE-PAGES-R024.1 | Run `test_similarity_report_model` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.2 | PIPE-PAGES-R024.2 | Run `test_similarity_threshold_boundaries` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.3 | PIPE-PAGES-R024.3 | Run `test_similarity_reporting_wiring` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.4 | PIPE-PAGES-R024.4 | Run `test_similarity_refusals` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.5 | PIPE-PAGES-R024.5 | Run `test_similarity_evidence` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.6 | PIPE-PAGES-R024.6 | Run `test_similarity_guidance_cli` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
