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
| T-PIPE-PAGES-R012.1 | PIPE-PAGES-R012.1 | `test_source_declarations_and_citations_in_both_documents` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.2 | PIPE-PAGES-R012.2 | Needs a status-regeneration integration check. `test_enrichment_preserves_delivery_records_and_status_bytes` checks enrichment only; it does not prove regeneration. |
| T-PIPE-PAGES-R012.3 | PIPE-PAGES-R012.3 | `test_implementation_tests_docs_and_missing_sources_are_distinct` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.4 | PIPE-PAGES-R012.4 | `test_code_cells_replace_concepts` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.5 | PIPE-PAGES-R012.5 | `test_implementation_tests_docs_and_missing_sources_are_distinct` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.6 | PIPE-PAGES-R012.6 | `test_code_cells_replace_concepts` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.7 | PIPE-PAGES-R012.7 | `test_examples_unsafe_links_and_parent_escape_are_not_mappings` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R013.1 | PIPE-PAGES-R013.1 | `test_local_and_external_dependencies_have_links_and_canonical_identity` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R013.2 | PIPE-PAGES-R013.2 | `test_explicit_edge_kinds_remain_distinct_from_mentions` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R013.3 | PIPE-PAGES-R013.3 | `test_unknowns_empty_and_isolated_specs_remain_discoverable` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R013.4 | PIPE-PAGES-R013.4 | `test_deterministic_escaped_output_and_plan_diagram_coverage` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R013.5 | PIPE-PAGES-R013.5 | `test_local_and_external_dependencies_have_links_and_canonical_identity` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R013.6 | PIPE-PAGES-R013.6 | `test_unknowns_empty_and_isolated_specs_remain_discoverable` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R013.7 | PIPE-PAGES-R013.7 | `test_large_groups_keep_all_specs_and_relationships` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R014.1 | PIPE-PAGES-R014.1 | `test_components_equal_core_list` in `tests/test_spec_dashboard_drilldown.py` expects equality with the R001 list. |
| T-PIPE-PAGES-R014.2 | PIPE-PAGES-R014.2 | `test_anchor_forms` in `tests/test_spec_dashboard_drilldown.py` expects the three forms. |
| T-PIPE-PAGES-R014.3 | PIPE-PAGES-R014.3 | `test_spec_section_has_anchor` in `tests/test_spec_dashboard_drilldown.py` expects the anchor and four content blocks. |
| T-PIPE-PAGES-R014.4 | PIPE-PAGES-R014.4 | `test_relation_box_links_to_spec_section` in `tests/test_spec_dashboard_drilldown.py` expects the href on every box. |
| T-PIPE-PAGES-R014.5 | PIPE-PAGES-R014.5 | `test_profile_links_cover_components` in `tests/test_render_profile_links.py` expects one level-1 link per component. |
| T-PIPE-PAGES-R014.6 | PIPE-PAGES-R014.6 | `test_unresolved_component_link_fails` in `tests/test_spec_dashboard_drilldown.py` expects exit 1 for a missing page. |
| T-PIPE-PAGES-R015.1 | PIPE-PAGES-R015.1 | `test_pages_workflow_runs_relation_steps` in `tests/test_pages_pipeline_contract.py` expects the steps and no repository names. |
| T-PIPE-PAGES-R015.2 | PIPE-PAGES-R015.2 | `test_client_callers_use_reusable_workflow` in `tests/test_pages_pipeline_contract.py` expects each caller to reference the workflow at `main`. |
| T-PIPE-PAGES-R015.3 | PIPE-PAGES-R015.3 | `test_generator_entry_point_writes_architecture` in `tests/test_spec_dashboard_metadata.py`. |


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
| T-PIPE-PAGES-R021.7 | PIPE-PAGES-R021.7 | Run `test_component_contract_model` in `tests/hooks/test_test_quality_hook.py`. Assert the closed edge kinds and separate runtime/type-only permissions. |
| T-PIPE-PAGES-R021.8 | PIPE-PAGES-R021.8 | Run `test_component_contract_checks` in `tests/hooks/test_test_quality_hook.py`. Assert allowed lazy imports preserve reachability, forbidden lazy imports fail, and type-only imports cannot prove runtime reachability. |
| T-PIPE-PAGES-R021.9 | PIPE-PAGES-R021.9 | Run `test_component_checks_are_wired` in `tests/hooks/test_test_quality_hook.py`. Assert the CLI boundary/orphan path consumes the static runtime graph and cycle checks retain the eager graph. |
| T-PIPE-PAGES-R021.10 | PIPE-PAGES-R021.10 | Run `test_component_proof_refusals` in `tests/hooks/test_test_quality_hook.py`. Assert unresolved dynamic reachability is exit 2, never a false clean or definite orphan; retain receipt refusals. |
| T-PIPE-PAGES-R021.11 | PIPE-PAGES-R021.11 | Run `test_component_evidence_receipts` in `tests/hooks/test_test_quality_hook.py`. Assert runtime, type-only and unresolved dynamic evidence remain distinguishable. |
| T-PIPE-PAGES-R021.12 | PIPE-PAGES-R021.12 | Run `test_component_handoff_cli` and `test_component_lazy_import_cli` in `tests/hooks/test_test_quality_hook.py`. Assert CLI exit codes, exact edge locations, type-only separation and no false orphan for allowed lazy imports. |
| T-PIPE-PAGES-R023.1 | PIPE-PAGES-R023.1 | Run `test_skill_grade_model` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. Carry a document base separately from the containment root. |
| T-PIPE-PAGES-R023.2 | PIPE-PAGES-R023.2 | Run `test_skill_grade_criteria` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. Resolve nested and parent-relative links from the document while enforcing repository containment. |
| T-PIPE-PAGES-R023.3 | PIPE-PAGES-R023.3 | Run `test_skill_grade_registration` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. Adapt the shared helper without changing root README behavior. |
| T-PIPE-PAGES-R023.4 | PIPE-PAGES-R023.4 | Run `test_skill_grade_refusals` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. Refuse traversal outside the repository, escaped document bases and symlinks outside the repository. |
| T-PIPE-PAGES-R023.5 | PIPE-PAGES-R023.5 | Run `test_skill_grade_evidence` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. Emit located source-document and resolved-target evidence. |
| T-PIPE-PAGES-R023.6 | PIPE-PAGES-R023.6 | Run `test_skill_grade_cli` in `tests/hooks/test_skill_grade_hook.py`; assert the requirement outcomes. Run `test_nested_skill_links_cli` in `tests/hooks/test_skill_grade_hook.py`; sibling and in-repository parent links pass, missing or escaping links fail. |
| T-PIPE-PAGES-R024.1 | PIPE-PAGES-R024.1 | Run `test_similarity_report_model` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.2 | PIPE-PAGES-R024.2 | Run `test_similarity_threshold_boundaries` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.3 | PIPE-PAGES-R024.3 | Run `test_similarity_reporting_wiring` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.4 | PIPE-PAGES-R024.4 | Run `test_similarity_refusals` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.5 | PIPE-PAGES-R024.5 | Run `test_similarity_evidence` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R024.6 | PIPE-PAGES-R024.6 | Run `test_similarity_guidance_cli` in `tests/hooks/test_similarity_guidance_hook.py`; assert the requirement outcomes. |
| T-PIPE-PAGES-R021.13 | PIPE-PAGES-R021.13 | Run `test_outcome_contract_schema` in `tests/hooks/test_test_quality_outcomes.py`. Reject unknown outcome kinds, empty observables and missing source bindings; accept return, error and side-effect contracts. |
| T-PIPE-PAGES-R021.14 | PIPE-PAGES-R021.14 | Run `test_outcome_counterexamples` in `tests/hooks/test_test_quality_outcomes.py`. Reject a passing test that ignores the result; accept exact return, error and state assertions that detect their counterexamples. |
| T-PIPE-PAGES-R021.15 | PIPE-PAGES-R021.15 | Run `test_outcome_checker_wiring` in `tests/hooks/test_test_quality_outcomes.py`. Assert the published CLI invokes the configured runner, validates its receipts and includes outcome findings in its exit code. |
| T-PIPE-PAGES-R021.16 | PIPE-PAGES-R021.16 | Run `test_outcome_proof_refusals` in `tests/hooks/test_test_quality_outcomes.py`. Missing contracts and surviving counterexamples exit 1; stale, skipped, setup-failing and timed-out proofs exit 2. |
| T-PIPE-PAGES-R021.17 | PIPE-PAGES-R021.17 | Run `test_outcome_evidence` in `tests/hooks/test_test_quality_outcomes.py`. Assert distinct static/runtime records and digest-bound receipts; never report coverage or assertion count as outcome proof. |
| T-PIPE-PAGES-R021.18 | PIPE-PAGES-R021.18 | Run `test_outcome_quality_cli` in `tests/hooks/test_test_quality_outcomes.py`. Assert exit 0 for proved outcomes, exit 1 for missing observation and exit 2 for unchecked proof through the real CLI and runner. |
| T-PIPE-PAGES-R020.13 | PIPE-PAGES-R020.13 | Run `test_changelog_model` in `tests/hooks/test_changelog_gate.py`. Reject unknown grammar fields and duplicate releases; represent dated releases and an optional unreleased section with exact locations. |
| T-PIPE-PAGES-R020.14 | PIPE-PAGES-R020.14 | Run `test_changelog_grammar` in `tests/hooks/test_changelog_gate.py`. Accept dated categorized releases; independently reject invalid dates/versions, misplaced entries, duplicate headings and unknown categories. |
| T-PIPE-PAGES-R020.15 | PIPE-PAGES-R020.15 | Run `test_changelog_hook_wiring` in `tests/hooks/test_changelog_gate.py`. The published CLI/hook reads policy and changelog from one Git snapshot and invokes the new grammar checker. |
| T-PIPE-PAGES-R020.16 | PIPE-PAGES-R020.16 | Run `test_changelog_refusals` in `tests/hooks/test_changelog_gate.py`. Missing files and malformed policy exit 2; missing links and malformed release entries exit 1, with path and source line. |
| T-PIPE-PAGES-R020.17 | PIPE-PAGES-R020.17 | Run `test_changelog_evidence` in `tests/hooks/test_changelog_gate.py`. Bind findings to exact Git bytes and explicitly mark network reachability and change completeness as unverified. |
| T-PIPE-PAGES-R020.18 | PIPE-PAGES-R020.18 | Run `test_changelog_cli` in `tests/hooks/test_changelog_gate.py`. Assert valid exit 0, grammar exit 1, missing-file and initial-history exit 2, then a valid first-release repair to exit 0, exact locations, snapshot isolation and no file writes or network calls. |
| T-PIPE-PAGES-R020.19 | PIPE-PAGES-R020.19 | Run `test_env_documentation_model` in `tests/hooks/test_env_documentation.py`. Reject duplicate names, unknown fields, contradictory defaults and unmapped launcher bindings. |
| T-PIPE-PAGES-R020.20 | PIPE-PAGES-R020.20 | Run `test_env_documentation_behavior` in `tests/hooks/test_env_documentation.py`. Independently corrupt each documentation field and remove, rename or contradict each launcher binding to fail. |
| T-PIPE-PAGES-R020.21 | PIPE-PAGES-R020.21 | Run `test_env_documentation_wiring` in `tests/hooks/test_env_documentation.py`. Invoke CLI and configured pre-commit with all three consumer surfaces from the same indexed snapshot. |
| T-PIPE-PAGES-R020.22 | PIPE-PAGES-R020.22 | Run `test_env_documentation_refusal` in `tests/hooks/test_env_documentation.py`. Malformed and missing launcher JSON fails; unsupported substitutions and computed names refuse without execution. |
| T-PIPE-PAGES-R020.23 | PIPE-PAGES-R020.23 | Run `test_env_documentation_evidence` in `tests/hooks/test_env_documentation.py`. Check exact third-surface locations/digests, missing binding evidence, uncertainty and secret redaction. |
| T-PIPE-PAGES-R020.24 | PIPE-PAGES-R020.24 | Run `test_env_documentation_cli` in `tests/hooks/test_env_documentation.py`. Assert CLI/hook exits 0/1/2 for all three surfaces, exact JSON pointers, snapshot isolation and no launch/import/network execution. |
| T-PIPE-PAGES-R020.25 | PIPE-PAGES-R020.25 | Run `test_config_inventory_model` in `tests/hooks/test_config_inventory.py`. Require all four roles for every declared project and reject duplicate effective authorities. |
| T-PIPE-PAGES-R020.26 | PIPE-PAGES-R020.26 | Run `test_config_inventory_behavior` in `tests/hooks/test_config_inventory.py`. Render all roles twice byte-identically and detect missing files, sections and managed-field drift. |
| T-PIPE-PAGES-R020.27 | PIPE-PAGES-R020.27 | Run `test_config_inventory_wiring` in `tests/hooks/test_config_inventory.py`. The installed hook invokes check mode; an explicit scratch render runs the same templates and parsers. |
| T-PIPE-PAGES-R020.28 | PIPE-PAGES-R020.28 | Run `test_config_inventory_refusal` in `tests/hooks/test_config_inventory.py`. Reject traversal and overwrite, and fail a project omitted from the declared inventory. |
| T-PIPE-PAGES-R020.29 | PIPE-PAGES-R020.29 | Run `test_config_inventory_evidence` in `tests/hooks/test_config_inventory.py`. Prove all projects and four roles appear, and drift identifies the affected section. |
| T-PIPE-PAGES-R020.30 | PIPE-PAGES-R020.30 | Run `test_config_inventory_cli` in `tests/hooks/test_config_inventory.py`. Assert deterministic rendering, per-role failures, complete multi-project coverage and no check-mode writes. |
| T-PIPE-PAGES-R020.31 | PIPE-PAGES-R020.31 | Run `test_validation_report_model` in `tests/hooks/test_validation_report.py`. Reject unknown outcomes, duplicate record identities and counts inconsistent with records. |
| T-PIPE-PAGES-R020.32 | PIPE-PAGES-R020.32 | Run `test_validation_report_behavior` in `tests/hooks/test_validation_report.py`. Round-trip mixed nested outcomes and compare every field, stable ordering and recomputed metrics. |
| T-PIPE-PAGES-R020.33 | PIPE-PAGES-R020.33 | Run `test_validation_report_wiring` in `tests/hooks/test_validation_report.py`. Run aggregate lint-type results through JSON/Markdown and retain all three phase categories, rules and verdicts. |
| T-PIPE-PAGES-R020.34 | PIPE-PAGES-R020.34 | Run `test_validation_report_refusal` in `tests/hooks/test_validation_report.py`. Tampered verdict/counts, required skips and malformed/truncated JSON refuse rather than pass. |
| T-PIPE-PAGES-R020.35 | PIPE-PAGES-R020.35 | Run `test_validation_report_evidence` in `tests/hooks/test_validation_report.py`. Retain failure detail and skip reasons through JSON and Markdown; never leak secret payloads. |
| T-PIPE-PAGES-R020.36 | PIPE-PAGES-R020.36 | Run `test_validation_report_cli` in `tests/hooks/test_validation_report.py`. Assert real lint/import/type round-trip, exit 1 at unchanged health score, repaired exit 0 and required-phase skip exit 2. |
| T-PIPE-PAGES-R021.19 | PIPE-PAGES-R021.19 | Run `test_lint_type_policy_model` in `tests/hooks/test_lint_type_policy.py`. Reject unpinned tools, missing phases and scope omissions. |
| T-PIPE-PAGES-R021.20 | PIPE-PAGES-R021.20 | Run `test_lint_type_policy_behavior` in `tests/hooks/test_lint_type_policy.py`. Independent lint, import-order, type and suppression fixtures fail; a clean supported project passes. |
| T-PIPE-PAGES-R021.21 | PIPE-PAGES-R021.21 | Run `test_lint_type_policy_wiring` in `tests/hooks/test_lint_type_policy.py`. Configured pre-commit calls all three real tool phases and the shared report adapter. |
| T-PIPE-PAGES-R021.22 | PIPE-PAGES-R021.22 | Run `test_lint_type_policy_refusal` in `tests/hooks/test_lint_type_policy.py`. Unavailable type checker and an unsupported declared language must not return a clean verdict. |
| T-PIPE-PAGES-R021.23 | PIPE-PAGES-R021.23 | Run `test_lint_type_policy_evidence` in `tests/hooks/test_lint_type_policy.py`. Prove all three phases ran against identical source bytes and each diagnostic retains its original rule ID. |
| T-PIPE-PAGES-R021.24 | PIPE-PAGES-R021.24 | Run `test_lint_type_policy_cli` in `tests/hooks/test_lint_type_policy.py`. Assert real analyzer results, zero-exception enforcement, snapshot isolation and no autofix/network writes. |
| T-PIPE-PAGES-R021.25 | PIPE-PAGES-R021.25 | Run `test_analyzer_health_model` in `tests/hooks/test_analyzer_health.py`. Accept the five scored and three required unscored categories; reject unknown categories and invalid weights or snapshots. |
| T-PIPE-PAGES-R021.26 | PIPE-PAGES-R021.26 | Run `test_analyzer_health_behavior` in `tests/hooks/test_analyzer_health.py`. Stable permutations yield identical score/order; missing categories cannot inflate health. |
| T-PIPE-PAGES-R021.27 | PIPE-PAGES-R021.27 | Run `test_analyzer_health_wiring` in `tests/hooks/test_analyzer_health.py`. The aggregate calls the real structured lint-type runner once and exports every phase with existing health adapters. |
| T-PIPE-PAGES-R021.28 | PIPE-PAGES-R021.28 | Run `test_analyzer_health_refusal` in `tests/hooks/test_analyzer_health.py`. A clean score cannot mask a secret finding, skipped required adapter or stale coverage receipt. |
| T-PIPE-PAGES-R021.29 | PIPE-PAGES-R021.29 | Run `test_analyzer_health_evidence` in `tests/hooks/test_analyzer_health.py`. Recompute health from only scored categories; retain required lint/import/type verdicts, priority and evidence. |
| T-PIPE-PAGES-R021.30 | PIPE-PAGES-R021.30 | Run `test_analyzer_health_cli` in `tests/hooks/test_analyzer_health.py`. Assert real aggregate lint/import/type reachability, failing-to-repaired verdicts, stable health score and required-skip exit 2. |
| T-PIPE-PAGES-R023.7 | PIPE-PAGES-R023.7 | Run `test_external_grade_rules_model` in `tests/hooks/test_external_grade_rules.py`. Reject duplicate rule IDs, unsupported predicate adapters and unpinned rule packs. |
| T-PIPE-PAGES-R023.8 | PIPE-PAGES-R023.8 | Run `test_external_grade_rules_behavior` in `tests/hooks/test_external_grade_rules.py`. An applied external rule is identifiable; a conflicting or unmapped heuristic cannot silently alter grade. |
| T-PIPE-PAGES-R023.9 | PIPE-PAGES-R023.9 | Run `test_external_grade_rules_wiring` in `tests/hooks/test_external_grade_rules.py`. The real skill-grade CLI loads the declared pack and emits its exact rule ID in JSON and Markdown. |
| T-PIPE-PAGES-R023.10 | PIPE-PAGES-R023.10 | Run `test_external_grade_rules_refusal` in `tests/hooks/test_external_grade_rules.py`. Tampered packs and unsupported prose-only rules refuse; applicable hard failures retain exit 1. |
| T-PIPE-PAGES-R023.11 | PIPE-PAGES-R023.11 | Run `test_external_grade_rules_evidence` in `tests/hooks/test_external_grade_rules.py`. Round-trip per-finding rule lineage and prove unchanged baseline grading when packs are diagnostic only. |
| T-PIPE-PAGES-R023.12 | PIPE-PAGES-R023.12 | Run `test_external_grade_rules_cli` in `tests/hooks/test_external_grade_rules.py`. Assert installed CLI/hook integration, exact external rule evidence and stable serialized grading. |
| T-PIPE-PAGES-R020.37 | PIPE-PAGES-R020.37 | Run `test_tool_mapping_model` in `tests/hooks/test_tool_mapping.py`. Reject duplicate identities, missing schema fields and unbound examples. |
| T-PIPE-PAGES-R020.38 | PIPE-PAGES-R020.38 | Run `test_tool_mapping_behavior` in `tests/hooks/test_tool_mapping.py`. Independently remove a tool, nested method, parameter, result or example and fail. |
| T-PIPE-PAGES-R020.39 | PIPE-PAGES-R020.39 | Run `test_tool_mapping_wiring` in `tests/hooks/test_tool_mapping.py`. The configured docs CLI/hook consumes the real exported registry and generated mapping. |
| T-PIPE-PAGES-R020.40 | PIPE-PAGES-R020.40 | Run `test_tool_mapping_refusal` in `tests/hooks/test_tool_mapping.py`. Unknown schema and stale registry refuse; an omitted tool is a located failure. |
| T-PIPE-PAGES-R020.41 | PIPE-PAGES-R020.41 | Run `test_tool_mapping_evidence` in `tests/hooks/test_tool_mapping.py`. Locate absent nested rows and preserve the distinction between schema and runtime evidence. |
| T-PIPE-PAGES-R020.42 | PIPE-PAGES-R020.42 | Run `test_tool_mapping_cli` in `tests/hooks/test_tool_mapping.py`. Assert real producer-to-renderer-to-hook integration and stale-export exit 2. |
| T-PIPE-PAGES-R020.43 | PIPE-PAGES-R020.43 | Run `test_guide_migration_model` in `tests/hooks/test_guide_migration.py`. Reject duplicate IDs, uncovered source ranges and destinations outside canonical content roots. |
| T-PIPE-PAGES-R020.44 | PIPE-PAGES-R020.44 | Run `test_guide_migration_behavior` in `tests/hooks/test_guide_migration.py`. Omitting or changing an assertion without matching evidence fails; unsupported claim kinds remain unresolved. |
| T-PIPE-PAGES-R020.45 | PIPE-PAGES-R020.45 | Run `test_guide_migration_wiring` in `tests/hooks/test_guide_migration.py`. The real CLI materializes the declared split and the hook checks its served navigation and claim evidence. |
| T-PIPE-PAGES-R020.46 | PIPE-PAGES-R020.46 | Run `test_guide_migration_refusal` in `tests/hooks/test_guide_migration.py`. Unresolved assertions and unrenderable diagrams cannot produce complete migration evidence. |
| T-PIPE-PAGES-R020.47 | PIPE-PAGES-R020.47 | Run `test_guide_migration_evidence` in `tests/hooks/test_guide_migration.py`. A coverage total equals the original inventory and each moved claim retains its evidence kind. |
| T-PIPE-PAGES-R020.48 | PIPE-PAGES-R020.48 | Run `test_guide_migration_cli` in `tests/hooks/test_guide_migration.py`. Assert actual CLI/hook, renderer and served-link behavior without helper-only completion. |
| T-PIPE-PAGES-R020.49 | PIPE-PAGES-R020.49 | Run `test_deployment_docs_model` in `tests/hooks/test_deployment_docs.py`. Require all four records and parse configuration/command shapes without fabricated capabilities. |
| T-PIPE-PAGES-R020.50 | PIPE-PAGES-R020.50 | Run `test_deployment_docs_behavior` in `tests/hooks/test_deployment_docs.py`. Missing configuration, command or mismatched transport fails independently in every pattern. |
| T-PIPE-PAGES-R020.51 | PIPE-PAGES-R020.51 | Run `test_deployment_docs_wiring` in `tests/hooks/test_deployment_docs.py`. Configured pre-commit and docs CLI validate the same owner export, JSON and argv matrix. |
| T-PIPE-PAGES-R020.52 | PIPE-PAGES-R020.52 | Run `test_deployment_docs_refusal` in `tests/hooks/test_deployment_docs.py`. Unsupported patterns are explicit constraints, never false pass coverage or invented commands. |
| T-PIPE-PAGES-R020.53 | PIPE-PAGES-R020.53 | Run `test_deployment_docs_evidence` in `tests/hooks/test_deployment_docs.py`. Export all four patterns and distinguish docs parity from a runtime deployment receipt. |
| T-PIPE-PAGES-R020.54 | PIPE-PAGES-R020.54 | Run `test_deployment_docs_cli` in `tests/hooks/test_deployment_docs.py`. Assert four-pattern CLI/hook parity and independent owner runtime receipts; documentation alone cannot certify deployment. |
| T-PIPE-PAGES-R020.55 | PIPE-PAGES-R020.55 | Run `test_doc_inventory_model` in `tests/hooks/test_doc_inventory.py`. Require every documentation role for every project and reject duplicate canonical authorities. |
| T-PIPE-PAGES-R020.56 | PIPE-PAGES-R020.56 | Run `test_doc_inventory_behavior` in `tests/hooks/test_doc_inventory.py`. Missing roles, malformed config, stale managed sections and orphan navigation fail independently. |
| T-PIPE-PAGES-R020.57 | PIPE-PAGES-R020.57 | Run `test_doc_inventory_wiring` in `tests/hooks/test_doc_inventory.py`. The existing proposed config-inventory entry consumes both configuration and documentation roles once. |
| T-PIPE-PAGES-R020.58 | PIPE-PAGES-R020.58 | Run `test_doc_inventory_refusal` in `tests/hooks/test_doc_inventory.py`. Retired-path fallback and an undiscovered declared project cannot pass. |
| T-PIPE-PAGES-R020.59 | PIPE-PAGES-R020.59 | Run `test_doc_inventory_evidence` in `tests/hooks/test_doc_inventory.py`. Prove every role and project is checked and preserve user-owned prose during rendering. |
| T-PIPE-PAGES-R020.60 | PIPE-PAGES-R020.60 | Run `test_doc_inventory_cli` in `tests/hooks/test_doc_inventory.py`. Assert deterministic generation, real served navigation and whole-inventory drift failures. |
| T-PIPE-PAGES-R020.61 | PIPE-PAGES-R020.61 | Run `test_readme_header_model` in `tests/hooks/test_readme_header.py`. Reject missing/duplicate consumer header fields; only the exact provider identity selects non-applicable scope. |
| T-PIPE-PAGES-R020.62 | PIPE-PAGES-R020.62 | Run `test_readme_header_behavior` in `tests/hooks/test_readme_header.py`. Missing interface/status links, hidden badges, stale owner counts and reused wrong-project marks fail. |
| T-PIPE-PAGES-R020.63 | PIPE-PAGES-R020.63 | Run `test_readme_header_wiring` in `tests/hooks/test_readme_header.py`. The installed provider self-run yields declared non-applicable exit 0; known consumers still execute the shared renderer/checker. |
| T-PIPE-PAGES-R020.64 | PIPE-PAGES-R020.64 | Run `test_readme_header_refusal` in `tests/hooks/test_readme_header.py`. Unknown consumer, same basename under another namespace and unresolved identity exit 2; unavailable telemetry cannot become a measured success. |
| T-PIPE-PAGES-R020.65 | PIPE-PAGES-R020.65 | Run `test_readme_header_evidence` in `tests/hooks/test_readme_header.py`. Bind seven-owner coverage to its registry; provider skip evidence cannot count as a passed consumer or completed header check. |
| T-PIPE-PAGES-R020.66 | PIPE-PAGES-R020.66 | Run `test_readme_header_cli` in `tests/hooks/test_readme_header.py`. Assert real renderer/browser coverage plus provider CLI/self-run exit 0, unknown identity exit 2 and no consumer bypass through a provider flag. |
| T-PIPE-PAGES-R020.67 | PIPE-PAGES-R020.67 | Run `test_image_theme_model` in `tests/hooks/test_image_theme.py`. Reject omitted images, missing theme modes and ambiguous diagram edge identities. |
| T-PIPE-PAGES-R020.68 | PIPE-PAGES-R020.68 | Run `test_image_theme_behavior` in `tests/hooks/test_image_theme.py`. Missing dark variant, invisible labels, wrong diagram arrow endpoints and unaccounted images fail. |
| T-PIPE-PAGES-R020.69 | PIPE-PAGES-R020.69 | Run `test_image_theme_wiring` in `tests/hooks/test_image_theme.py`. The production docs check evaluates the actual served artifact under both browser media settings. |
| T-PIPE-PAGES-R020.70 | PIPE-PAGES-R020.70 | Run `test_image_theme_refusal` in `tests/hooks/test_image_theme.py`. An image lacking trustworthy theme evidence cannot silently pass or disappear from inventory. |
| T-PIPE-PAGES-R020.71 | PIPE-PAGES-R020.71 | Run `test_image_theme_evidence` in `tests/hooks/test_image_theme.py`. Every image has two bound render results with exact failure locations and reasons. |
| T-PIPE-PAGES-R020.72 | PIPE-PAGES-R020.72 | Run `test_image_theme_cli` in `tests/hooks/test_image_theme.py`. Assert real served dual-media coverage for every image, failed adversarial probes and stale-receipt exit 2. |
| T-PIPE-PAGES-R020.73 | PIPE-PAGES-R020.73 | Run `test_spec_artifacts_model` in `tests/hooks/test_spec_artifacts.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.74 | PIPE-PAGES-R020.74 | Run `test_spec_artifacts_behavior` in `tests/hooks/test_spec_artifacts.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.75 | PIPE-PAGES-R020.75 | Run `test_spec_artifacts_wiring` in `tests/hooks/test_spec_artifacts.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.76 | PIPE-PAGES-R020.76 | Run `test_spec_artifacts_refusal` in `tests/hooks/test_spec_artifacts.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.77 | PIPE-PAGES-R020.77 | Run `test_spec_artifacts_evidence` in `tests/hooks/test_spec_artifacts.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.78 | PIPE-PAGES-R020.78 | Run `test_spec_artifacts_cli` in `tests/hooks/test_spec_artifacts.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.8 | PIPE-PAGES-R012.8 | Run `test_spec_bundle_compatibility_model` in `tests/hooks/test_spec_bundle_compatibility.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.9 | PIPE-PAGES-R012.9 | Run `test_spec_bundle_compatibility_behavior` in `tests/hooks/test_spec_bundle_compatibility.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.10 | PIPE-PAGES-R012.10 | Run `test_spec_bundle_compatibility_wiring` in `tests/hooks/test_spec_bundle_compatibility.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.11 | PIPE-PAGES-R012.11 | Run `test_spec_bundle_compatibility_refusal` in `tests/hooks/test_spec_bundle_compatibility.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.12 | PIPE-PAGES-R012.12 | Run `test_spec_bundle_compatibility_evidence` in `tests/hooks/test_spec_bundle_compatibility.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.13 | PIPE-PAGES-R012.13 | Run `test_spec_bundle_compatibility_cli` in `tests/hooks/test_spec_bundle_compatibility.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.31 | PIPE-PAGES-R021.31 | Run `test_skill_dependency_audit_model` in `tests/hooks/test_skill_dependency_audit.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.32 | PIPE-PAGES-R021.32 | Run `test_skill_dependency_audit_behavior` in `tests/hooks/test_skill_dependency_audit.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.33 | PIPE-PAGES-R021.33 | Run `test_skill_dependency_audit_wiring` in `tests/hooks/test_skill_dependency_audit.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.34 | PIPE-PAGES-R021.34 | Run `test_skill_dependency_audit_refusal` in `tests/hooks/test_skill_dependency_audit.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.35 | PIPE-PAGES-R021.35 | Run `test_skill_dependency_audit_evidence` in `tests/hooks/test_skill_dependency_audit.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.36 | PIPE-PAGES-R021.36 | Run `test_skill_dependency_audit_cli` in `tests/hooks/test_skill_dependency_audit.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.13 | PIPE-PAGES-R023.13 | Run `test_aggregate_skill_grade_model` in `tests/hooks/test_aggregate_skill_grade.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.14 | PIPE-PAGES-R023.14 | Run `test_aggregate_skill_grade_behavior` in `tests/hooks/test_aggregate_skill_grade.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.15 | PIPE-PAGES-R023.15 | Run `test_aggregate_skill_grade_wiring` in `tests/hooks/test_aggregate_skill_grade.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.16 | PIPE-PAGES-R023.16 | Run `test_aggregate_skill_grade_refusal` in `tests/hooks/test_aggregate_skill_grade.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.17 | PIPE-PAGES-R023.17 | Run `test_aggregate_skill_grade_evidence` in `tests/hooks/test_aggregate_skill_grade.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.18 | PIPE-PAGES-R023.18 | Run `test_aggregate_skill_grade_cli` in `tests/hooks/test_aggregate_skill_grade.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.14 | PIPE-PAGES-R012.14 | Run `test_capability_inventory_model` in `tests/hooks/test_capability_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.15 | PIPE-PAGES-R012.15 | Run `test_capability_inventory_behavior` in `tests/hooks/test_capability_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.16 | PIPE-PAGES-R012.16 | Run `test_capability_inventory_wiring` in `tests/hooks/test_capability_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.17 | PIPE-PAGES-R012.17 | Run `test_capability_inventory_refusal` in `tests/hooks/test_capability_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.18 | PIPE-PAGES-R012.18 | Run `test_capability_inventory_evidence` in `tests/hooks/test_capability_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.19 | PIPE-PAGES-R012.19 | Run `test_capability_inventory_cli` in `tests/hooks/test_capability_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.37 | PIPE-PAGES-R021.37 | Run `test_structural_limits_model` in `tests/hooks/test_structural_limits.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.38 | PIPE-PAGES-R021.38 | Run `test_structural_limits_behavior` in `tests/hooks/test_structural_limits.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.39 | PIPE-PAGES-R021.39 | Run `test_structural_limits_wiring` in `tests/hooks/test_structural_limits.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.40 | PIPE-PAGES-R021.40 | Run `test_structural_limits_refusal` in `tests/hooks/test_structural_limits.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.41 | PIPE-PAGES-R021.41 | Run `test_structural_limits_evidence` in `tests/hooks/test_structural_limits.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.42 | PIPE-PAGES-R021.42 | Run `test_structural_limits_cli` in `tests/hooks/test_structural_limits.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.43 | PIPE-PAGES-R021.43 | Run `test_source_path_portability_model` in `tests/hooks/test_source_path_portability.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.44 | PIPE-PAGES-R021.44 | Run `test_source_path_portability_behavior` in `tests/hooks/test_source_path_portability.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.45 | PIPE-PAGES-R021.45 | Run `test_source_path_portability_wiring` in `tests/hooks/test_source_path_portability.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.46 | PIPE-PAGES-R021.46 | Run `test_source_path_portability_refusal` in `tests/hooks/test_source_path_portability.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.47 | PIPE-PAGES-R021.47 | Run `test_source_path_portability_evidence` in `tests/hooks/test_source_path_portability.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.48 | PIPE-PAGES-R021.48 | Run `test_source_path_portability_cli` in `tests/hooks/test_source_path_portability.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.49 | PIPE-PAGES-R021.49 | Run `test_coverage_closure_model` in `tests/hooks/test_coverage_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.50 | PIPE-PAGES-R021.50 | Run `test_coverage_closure_behavior` in `tests/hooks/test_coverage_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.51 | PIPE-PAGES-R021.51 | Run `test_coverage_closure_wiring` in `tests/hooks/test_coverage_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.52 | PIPE-PAGES-R021.52 | Run `test_coverage_closure_refusal` in `tests/hooks/test_coverage_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.53 | PIPE-PAGES-R021.53 | Run `test_coverage_closure_evidence` in `tests/hooks/test_coverage_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.54 | PIPE-PAGES-R021.54 | Run `test_coverage_closure_cli` in `tests/hooks/test_coverage_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.79 | PIPE-PAGES-R020.79 | Run `test_validation_behavior_inventory_model` in `tests/hooks/test_validation_behavior_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.80 | PIPE-PAGES-R020.80 | Run `test_validation_behavior_inventory_behavior` in `tests/hooks/test_validation_behavior_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.81 | PIPE-PAGES-R020.81 | Run `test_validation_behavior_inventory_wiring` in `tests/hooks/test_validation_behavior_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.82 | PIPE-PAGES-R020.82 | Run `test_validation_behavior_inventory_refusal` in `tests/hooks/test_validation_behavior_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.83 | PIPE-PAGES-R020.83 | Run `test_validation_behavior_inventory_evidence` in `tests/hooks/test_validation_behavior_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.84 | PIPE-PAGES-R020.84 | Run `test_validation_behavior_inventory_cli` in `tests/hooks/test_validation_behavior_inventory.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.55 | PIPE-PAGES-R021.55 | Run `test_offline_unit_profile_model` in `tests/hooks/test_offline_unit_profile.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.56 | PIPE-PAGES-R021.56 | Run `test_offline_unit_profile_behavior` in `tests/hooks/test_offline_unit_profile.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.57 | PIPE-PAGES-R021.57 | Run `test_offline_unit_profile_wiring` in `tests/hooks/test_offline_unit_profile.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.58 | PIPE-PAGES-R021.58 | Run `test_offline_unit_profile_refusal` in `tests/hooks/test_offline_unit_profile.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.59 | PIPE-PAGES-R021.59 | Run `test_offline_unit_profile_evidence` in `tests/hooks/test_offline_unit_profile.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.60 | PIPE-PAGES-R021.60 | Run `test_offline_unit_profile_cli` in `tests/hooks/test_offline_unit_profile.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.85 | PIPE-PAGES-R020.85 | Run `test_ontology_governance_hook_model` in `tests/hooks/test_ontology_governance_hook.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.86 | PIPE-PAGES-R020.86 | Run `test_ontology_governance_hook_behavior` in `tests/hooks/test_ontology_governance_hook.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.87 | PIPE-PAGES-R020.87 | Run `test_ontology_governance_hook_wiring` in `tests/hooks/test_ontology_governance_hook.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.88 | PIPE-PAGES-R020.88 | Run `test_ontology_governance_hook_refusal` in `tests/hooks/test_ontology_governance_hook.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.89 | PIPE-PAGES-R020.89 | Run `test_ontology_governance_hook_evidence` in `tests/hooks/test_ontology_governance_hook.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.90 | PIPE-PAGES-R020.90 | Run `test_ontology_governance_hook_cli` in `tests/hooks/test_ontology_governance_hook.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.61 | PIPE-PAGES-R021.61 | Run `test_test_layout_independence_model` in `tests/hooks/test_test_layout_independence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.62 | PIPE-PAGES-R021.62 | Run `test_test_layout_independence_behavior` in `tests/hooks/test_test_layout_independence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.63 | PIPE-PAGES-R021.63 | Run `test_test_layout_independence_wiring` in `tests/hooks/test_test_layout_independence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.64 | PIPE-PAGES-R021.64 | Run `test_test_layout_independence_refusal` in `tests/hooks/test_test_layout_independence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.65 | PIPE-PAGES-R021.65 | Run `test_test_layout_independence_evidence` in `tests/hooks/test_test_layout_independence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.66 | PIPE-PAGES-R021.66 | Run `test_test_layout_independence_cli` in `tests/hooks/test_test_layout_independence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.67 | PIPE-PAGES-R021.67 | Run `test_solution_size_evidence_model` in `tests/hooks/test_solution_size_evidence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.68 | PIPE-PAGES-R021.68 | Run `test_solution_size_evidence_behavior` in `tests/hooks/test_solution_size_evidence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.69 | PIPE-PAGES-R021.69 | Run `test_solution_size_evidence_wiring` in `tests/hooks/test_solution_size_evidence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.70 | PIPE-PAGES-R021.70 | Run `test_solution_size_evidence_refusal` in `tests/hooks/test_solution_size_evidence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.71 | PIPE-PAGES-R021.71 | Run `test_solution_size_evidence_evidence` in `tests/hooks/test_solution_size_evidence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.72 | PIPE-PAGES-R021.72 | Run `test_solution_size_evidence_cli` in `tests/hooks/test_solution_size_evidence.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.73 | PIPE-PAGES-R021.73 | Run `test_graph_workflow_receipt_model` in `tests/hooks/test_graph_workflow_receipt.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.74 | PIPE-PAGES-R021.74 | Run `test_graph_workflow_receipt_behavior` in `tests/hooks/test_graph_workflow_receipt.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.75 | PIPE-PAGES-R021.75 | Run `test_graph_workflow_receipt_wiring` in `tests/hooks/test_graph_workflow_receipt.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.76 | PIPE-PAGES-R021.76 | Run `test_graph_workflow_receipt_refusal` in `tests/hooks/test_graph_workflow_receipt.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.77 | PIPE-PAGES-R021.77 | Run `test_graph_workflow_receipt_evidence` in `tests/hooks/test_graph_workflow_receipt.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.78 | PIPE-PAGES-R021.78 | Run `test_graph_workflow_receipt_cli` in `tests/hooks/test_graph_workflow_receipt.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R042 | PIPE-PAGES-R042 | Run `tests/test_architecture_explorer.py`, `test_architecture_explorer_defaults_to_core_repositories_and_builds_before_upload` `test_architecture_explorer_link_opens_the_current_repository_node` and `test_check_requires_the_diagram_to_link_the_explorer`. Assert placement, deleted-row removal, discovery reconciliation, the freshness stamp, the page and redirect variants, the dispatch step, the theme wiring and the diagram link. |
| T-PIPE-PAGES-R042.1 | PIPE-PAGES-R042.1 | `tests/test_architecture_explorer.py::test_search_index_covers_every_row_and_maps_it_to_a_node` and `tests/test_architecture_explorer.py::test_search_index_carries_repository_aliases`. Index every row and node. Bind the mapped node of each row to the tree. Carry the alias table so a retired ID resolves. |
| T-PIPE-PAGES-R042.2 | PIPE-PAGES-R042.2 | `tests/test_architecture_explorer.py::test_a_capability_search_ranks_the_owning_row_first` and `tests/test_architecture_explorer.py::test_an_id_search_is_exact`. Rank capability terms. Keep ID search exact. Put the owning row ahead of repeated boilerplate titles. |
| T-PIPE-PAGES-R042.3 | PIPE-PAGES-R042.3 | `tests/test_architecture_explorer.py::test_deep_links_parse`. Parse every deep-link form. Write the hash back. |
| T-PIPE-PAGES-R042.4 | PIPE-PAGES-R042.4 | `tests/test_architecture_explorer.py::test_a_q_deep_link_lands_on_the_owning_part_in_a_browser` loads the page in a headless Chromium when one is installed. Land on the owning node with the matching rows shown. Expose the combobox and listbox roles. |
| T-PIPE-PAGES-R042.5 | PIPE-PAGES-R042.5 | `tests/test_architecture_explorer.py::test_the_map_fills_the_viewport_with_full_screen_and_panel_toggle`. Assert no width cap, full-height layout, the full-screen and panel controls, and a wide overview layout. |

## Agent-readiness and static delivery

| ID | Requirement | Test and expected result |
|---|---|---|
| T-PIPE-PAGES-R043.1 | PIPE-PAGES-R043.1 | `tests/test_pages_readiness.py::test_second_build_and_offline_tck_are_idempotent`. The readiness validator must consume declared input, schema, readiness manifest, and Markdown mirror manifest without another generator. |
| T-PIPE-PAGES-R043.2 | PIPE-PAGES-R043.2 | `tests/test_pages_readiness.py::test_build_publishes_source_markdown_and_served_mime`. The delivery builder must publish declared Markdown fallbacks and discovery files while preserving existing site directives. |
| T-PIPE-PAGES-R043.3 | PIPE-PAGES-R043.3 | `tests/test_pages_pipeline_contract.py::test_enabled_path_checks_strict_build_and_runs_owned_tck`. The workflow at `.github/workflows/pages_pipeline.yml:223` must invoke the readiness CLI only through explicit opt-in. |
| T-PIPE-PAGES-R043.4 | PIPE-PAGES-R043.4 | `tests/test_pages_readiness.py::test_stale_source_digest_fails_closed`. The validator must reject stale source digests and private capability references before publication. |
| T-PIPE-PAGES-R043.5 | PIPE-PAGES-R043.5 | `tests/test_pages_readiness.py::test_cli_failure_result_is_versioned`. The CLI must report versioned failure results rather than imply successful validation. |
| T-PIPE-PAGES-R043.6 | PIPE-PAGES-R043.6 | `tests/test_pages_readiness.py::test_direct_entry_requires_and_loads_the_sparse_readiness_package`. The direct script entry must load the sparse readiness package and validate the declared content source. |
