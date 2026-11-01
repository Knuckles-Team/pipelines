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
| T-PIPE-PAGES-R042.4 | PIPE-PAGES-R042.4 | `tests/test_architecture_explorer.py::test_a_q_deep_link_lands_on_the_owning_part_in_a_browser` loads the page in a headless Chromium when one is installed. Land on the owning node with the matching rows shown. Expose the combobox and listbox roles. `tests/test_architecture_explorer.py::test_every_person_layer_top_node_is_external_and_no_row_places_on_it` asserts people, clients and sources are external and take no rows. |
| T-PIPE-PAGES-R042.5 | PIPE-PAGES-R042.5 | `tests/test_architecture_explorer.py::test_the_map_fills_the_viewport_with_full_screen_and_panel_toggle`. Assert no width cap, full-height layout, the full-screen and panel controls, and a wide overview layout. |
| T-PIPE-PAGES-R042.6 | PIPE-PAGES-R042.6 | `tests/test_architecture_explorer.py::test_description_is_the_first_plain_sentence_capped_at_160`, `tests/test_architecture_explorer.py::test_page_rows_carry_desc_and_never_the_full_text`, `tests/test_architecture_explorer.py::test_page_size_grows_by_a_bounded_amount_per_row` and `tests/test_architecture_explorer.py::test_search_matches_a_description_only_after_title_and_id_matches`. Check the first-sentence cut, the 160 cap, no full text in the page, bounded size growth and description search ranking. |
| T-PIPE-PAGES-R042.7 | PIPE-PAGES-R042.7 | `tests/test_architecture_explorer.py::test_one_family_json_is_written_per_family_with_full_row_detail`, `tests/test_architecture_explorer.py::test_a_row_whose_family_has_no_plan_still_gets_detail` and `tests/test_architecture_explorer.py::test_expanding_a_row_fetches_its_family_once_and_renders_it_safely`. Check one file per family, evidence links, test-spec lines, design documents, a family without a plan, and an inline expand in a browser. |
| T-PIPE-PAGES-R042.8 | PIPE-PAGES-R042.8 | `tests/test_architecture_explorer.py::test_markdown_escapes_raw_html_and_drops_unsafe_links` and `tests/test_architecture_explorer.py::test_page_never_assigns_markup_and_exposes_the_expand_controls`. A script in a spec file comes out escaped, unsafe links are dropped and the page assigns no markup. |
| T-PIPE-PAGES-R042.9 | PIPE-PAGES-R042.9 | `tests/test_architecture_explorer.py::test_every_registered_repository_has_a_part_and_its_rows_place_without_the_allowlist`. Every registry repository is owned by a part, and skill-graphs rows place on Skill graphs with an empty allowlist. |
| T-PIPE-PAGES-R042.10 | PIPE-PAGES-R042.10 | `tests/test_architecture_explorer.py::test_footer_links_the_guide_and_front_door_and_only_specified_rows_point_to_the_guide`. The footer links the guide and front door, the header does not, and only the `SPECIFIED` row detail points to the guide. |
| T-PIPE-PAGES-R042.11 | PIPE-PAGES-R042.11 | `tests/test_architecture_explorer.py::test_contribution_path_is_in_the_page_head_details_and_llms_txt` and `tests/test_architecture_explorer.py::test_a_build_writes_llms_txt_beside_the_page`. The collapsed block, both head links, the description, the written `llms.txt` and every URL against the build constants. |

## Agent-readiness and static delivery

| ID | Requirement | Test and expected result |
|---|---|---|
| T-PIPE-PAGES-R043.1 | PIPE-PAGES-R043.1 | `tests/test_pages_readiness.py::test_second_build_and_offline_tck_are_idempotent`. The readiness validator must consume declared input, schema, readiness manifest, and Markdown mirror manifest without another generator. |
| T-PIPE-PAGES-R043.2 | PIPE-PAGES-R043.2 | `tests/test_pages_readiness.py::test_build_publishes_source_markdown_and_served_mime`. The delivery builder must publish declared Markdown fallbacks and discovery files while preserving existing site directives. |
| T-PIPE-PAGES-R043.3 | PIPE-PAGES-R043.3 | `tests/test_pages_pipeline_contract.py::test_enabled_path_checks_strict_build_and_runs_owned_tck`. The workflow at `.github/workflows/pages_pipeline.yml:223` must invoke the readiness CLI only through explicit opt-in. |
| T-PIPE-PAGES-R043.4 | PIPE-PAGES-R043.4 | `tests/test_pages_readiness.py::test_stale_source_digest_fails_closed`. The validator must reject stale source digests and private capability references before publication. |
| T-PIPE-PAGES-R043.5 | PIPE-PAGES-R043.5 | `tests/test_pages_readiness.py::test_cli_failure_result_is_versioned`. The CLI must report versioned failure results rather than imply successful validation. |
| T-PIPE-PAGES-R043.6 | PIPE-PAGES-R043.6 | `tests/test_pages_readiness.py::test_direct_entry_requires_and_loads_the_sparse_readiness_package`. The direct script entry must load the sparse readiness package and validate the declared content source. |

## Entries added for rows without a prior entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-PAGES-R051.1 | PIPE-PAGES-R051.1 | Test: `tests/test_architecture_explorer.py::test_family_files_carry_every_spec_document_with_an_outline`. |
| T-PIPE-PAGES-R051.2 | PIPE-PAGES-R051.2 | Test: `tests/test_architecture_explorer.py::test_a_repository_constitution_is_written_versioned_and_linked`. |
| T-PIPE-PAGES-R051.3 | PIPE-PAGES-R051.3 | Test: `tests/test_architecture_explorer.py::test_delivery_cards_carry_title_phase_task_progress_and_document_bits`. |
| T-PIPE-PAGES-R051.4 | PIPE-PAGES-R051.4 | Test: `tests/test_architecture_explorer.py::test_the_node_panel_renders_own_cards_and_links_each_document`. |
| T-PIPE-PAGES-R051.5 | PIPE-PAGES-R051.5 | Test: `tests/test_architecture_explorer.py::test_doc_deep_links_parse_and_round_trip` and `::test_the_reader_opens_a_plan_section_and_links_row_ids_in_a_browser`. |
| T-PIPE-PAGES-R051.6 | PIPE-PAGES-R051.6 | Test: `tests/test_architecture_explorer.py::test_the_program_view_has_a_toggle_and_five_phase_columns`. |
| T-PIPE-PAGES-R051.7 | PIPE-PAGES-R051.7 | Test: `tests/test_architecture_explorer.py::test_a_failing_principle_in_the_constitution_check_warns`. |
| T-PIPE-PAGES-R051.8 | PIPE-PAGES-R051.8 | Test: `tests/test_architecture_explorer.py::test_search_extras_hold_task_lines_and_plan_headings_and_rank_last`. |
| T-PIPE-PAGES-R051.9 | PIPE-PAGES-R051.9 | Test: `tests/test_architecture_explorer.py::test_the_page_stays_within_ten_percent_and_inlines_no_document` and `::test_new_panels_use_glass_levels_and_respect_reduced_motion`. |
| T-PIPE-PAGES-R052 | PIPE-PAGES-R052 | Test: `tests/test_architecture_explorer.py::test_canopy_is_a_part_inside_pipelines_and_owns_its_rows`. |

## Entries added for rows without a prior entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-PAGES-R001 | PIPE-PAGES-R001 | A parity check confirms the switcher's repository list matches the declared core-repository set and release receipt, and a source scan confirms the obsolete standalone deployment generator no longer exists. |
| T-PIPE-PAGES-R002 | PIPE-PAGES-R002 | A navigation-depth and link-structure audit confirms each tier, introduction, component, and reference, exists and links progressively into the next. |
| T-PIPE-PAGES-R003 | PIPE-PAGES-R003 | Strict documentation build, theme, accessibility, and content-diff checks confirm the README order, embedded start, shared visuals, and present-tense wording. |
| T-PIPE-PAGES-R007 | PIPE-PAGES-R007 | Focused theme rendering tests plus a changed-file documentation build confirm the diagram's flow, project titles, and logo marks render correctly. |
| T-PIPE-PAGES-R008 | PIPE-PAGES-R008 | A multi-page render, link, and accessibility audit plus a changed-file build check confirm ownership statements, the quick start, and accessible navigation on the consumer site. |
| T-PIPE-PAGES-R011 | PIPE-PAGES-R011 | Strict MkDocs render, accessibility, theme, and privacy gates, together with the documentation build run, confirm the home page's content and that it passes without regressions. |
| T-PIPE-PAGES-R012.20 | PIPE-PAGES-R012.20 | Run `test_eg7_capability_authority_model` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.21 | PIPE-PAGES-R012.21 | Run `test_eg7_complete_binding_coverage` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.22 | PIPE-PAGES-R012.22 | Run `test_eg7_binding_gate_wiring` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.23 | PIPE-PAGES-R012.23 | Run `test_eg7_refusal_missing_identity` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.24 | PIPE-PAGES-R012.24 | Run `test_eg7_coverage_evidence` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R012.25 | PIPE-PAGES-R012.25 | Run `test_eg7_identity_enforcement_cli` in `tests/test_spec_dashboard_metadata.py`. |
| T-PIPE-PAGES-R021.79 | PIPE-PAGES-R021.79 | Run `test_pipe9_coverage_runner_model` in `tests/hooks/test_coverage_closure.py`. |
| T-PIPE-PAGES-R021.80 | PIPE-PAGES-R021.80 | Run `test_pipe9_inventory_behavior` in `tests/hooks/test_coverage_closure.py`. |
| T-PIPE-PAGES-R021.81 | PIPE-PAGES-R021.81 | Run `test_pipe9_gate_wiring` in `tests/hooks/test_coverage_closure.py`. |
| T-PIPE-PAGES-R021.82 | PIPE-PAGES-R021.82 | Run `test_pipe9_threshold_refusal` in `tests/hooks/test_coverage_closure.py`. |
| T-PIPE-PAGES-R021.83 | PIPE-PAGES-R021.83 | Run `test_pipe9_closure_evidence` in `tests/hooks/test_coverage_closure.py`. |
| T-PIPE-PAGES-R021.84 | PIPE-PAGES-R021.84 | Run `test_pipe9_closure_cli` in `tests/hooks/test_coverage_closure.py`. |
| T-PIPE-PAGES-R021.85 | PIPE-PAGES-R021.85 | Run `test_pipe10_workflow_model` in `tests/hooks/test_graph_workflow_receipt.py`. |
| T-PIPE-PAGES-R021.86 | PIPE-PAGES-R021.86 | Run `test_pipe10_readback_behavior` in `tests/hooks/test_graph_workflow_receipt.py`. |
| T-PIPE-PAGES-R021.87 | PIPE-PAGES-R021.87 | Run `test_pipe10_gate_wiring` in `tests/hooks/test_graph_workflow_receipt.py`. |
| T-PIPE-PAGES-R021.88 | PIPE-PAGES-R021.88 | Run `test_pipe10_readback_refusal` in `tests/hooks/test_graph_workflow_receipt.py`. |
| T-PIPE-PAGES-R021.89 | PIPE-PAGES-R021.89 | Run `test_pipe10_receipt_evidence` in `tests/hooks/test_graph_workflow_receipt.py`. |
| T-PIPE-PAGES-R021.90 | PIPE-PAGES-R021.90 | Run `test_pipe10_cli_proof` in `tests/hooks/test_graph_workflow_receipt.py`. |
| T-PIPE-PAGES-R025.3 | PIPE-PAGES-R025.3 | Run integration test. |
| T-PIPE-PAGES-R026.1 | PIPE-PAGES-R026.1 | Run schema validation test. |
| T-PIPE-PAGES-R026.2 | PIPE-PAGES-R026.2 | Run generator test. |
| T-PIPE-PAGES-R026.3 | PIPE-PAGES-R026.3 | Run consumer test. |
| T-PIPE-PAGES-R026.4 | PIPE-PAGES-R026.4 | Run refusal test. |
| T-PIPE-PAGES-R026.5 | PIPE-PAGES-R026.5 | Run round-trip test. |
| T-PIPE-PAGES-R026.6 | PIPE-PAGES-R026.6 | Run `test_artifact_schema_cli`. |
| T-PIPE-PAGES-R027.1 | PIPE-PAGES-R027.1 | Run format test. |
| T-PIPE-PAGES-R027.2 | PIPE-PAGES-R027.2 | Run interop test. |
| T-PIPE-PAGES-R027.3 | PIPE-PAGES-R027.3 | Run classification test. |
| T-PIPE-PAGES-R027.4 | PIPE-PAGES-R027.4 | Run compat test. |
| T-PIPE-PAGES-R027.5 | PIPE-PAGES-R027.5 | Run agreement test. |
| T-PIPE-PAGES-R027.6 | PIPE-PAGES-R027.6 | Run `test_spec_format_compat_cli`. |
| T-PIPE-PAGES-R028.1 | PIPE-PAGES-R028.1 | Run phase test. |
| T-PIPE-PAGES-R028.2 | PIPE-PAGES-R028.2 | Run execution test. |
| T-PIPE-PAGES-R028.3 | PIPE-PAGES-R028.3 | Run stream test. |
| T-PIPE-PAGES-R028.4 | PIPE-PAGES-R028.4 | Run event test. |
| T-PIPE-PAGES-R028.5 | PIPE-PAGES-R028.5 | Run transition test. |
| T-PIPE-PAGES-R028.6 | PIPE-PAGES-R028.6 | Run `test_release_phase_coordination_cli`. |
| T-PIPE-PAGES-R029.1 | PIPE-PAGES-R029.1 | Run inventory test. |
| T-PIPE-PAGES-R029.2 | PIPE-PAGES-R029.2 | Run audit test. |
| T-PIPE-PAGES-R029.3 | PIPE-PAGES-R029.3 | Run approval test. |
| T-PIPE-PAGES-R029.4 | PIPE-PAGES-R029.4 | Run auth test. |
| T-PIPE-PAGES-R029.5 | PIPE-PAGES-R029.5 | Run binding test. |
| T-PIPE-PAGES-R029.6 | PIPE-PAGES-R029.6 | Run `test_skill_dependency_audit_cli`. |
| T-PIPE-PAGES-R030.1 | PIPE-PAGES-R030.1 | Run discovery test. |
| T-PIPE-PAGES-R030.2 | PIPE-PAGES-R030.2 | Run comparison test. |
| T-PIPE-PAGES-R030.3 | PIPE-PAGES-R030.3 | Run refusal test. |
| T-PIPE-PAGES-R030.4 | PIPE-PAGES-R030.4 | Run undeclared test. |
| T-PIPE-PAGES-R030.5 | PIPE-PAGES-R030.5 | Run gap test. |
| T-PIPE-PAGES-R030.6 | PIPE-PAGES-R030.6 | Run `test_version_reference_discovery_cli`. |
| T-PIPE-PAGES-R023.19 | PIPE-PAGES-R023.19 | Run `test_aggregate_skill_grade_cli`. |
| T-PIPE-PAGES-R032.1 | PIPE-PAGES-R032.1 | Run export-import model test. |
| T-PIPE-PAGES-R032.2 | PIPE-PAGES-R032.2 | Run round-trip behavior test. |
| T-PIPE-PAGES-R032.3 | PIPE-PAGES-R032.3 | Run export wiring test. |
| T-PIPE-PAGES-R032.4 | PIPE-PAGES-R032.4 | Run version refusal test. |
| T-PIPE-PAGES-R032.5 | PIPE-PAGES-R032.5 | Run version comparison evidence test. |
| T-PIPE-PAGES-R032.6 | PIPE-PAGES-R032.6 | Run `test_eg56_export_import_cli`. |
| T-PIPE-PAGES-R033.1 | PIPE-PAGES-R033.1 | Run installer model test. |
| T-PIPE-PAGES-R033.2 | PIPE-PAGES-R033.2 | Run target binding behavior test. |
| T-PIPE-PAGES-R033.3 | PIPE-PAGES-R033.3 | Run harness wiring test. |
| T-PIPE-PAGES-R033.4 | PIPE-PAGES-R033.4 | Run target proof refusal test. |
| T-PIPE-PAGES-R033.5 | PIPE-PAGES-R033.5 | Run target coverage evidence test. |
| T-PIPE-PAGES-R033.6 | PIPE-PAGES-R033.6 | Run `test_au96_target_binding_cli`. |
| T-PIPE-PAGES-R034.1 | PIPE-PAGES-R034.1 | Run portable profile model test. |
| T-PIPE-PAGES-R034.2 | PIPE-PAGES-R034.2 | Run dependency-free behavior test. |
| T-PIPE-PAGES-R034.3 | PIPE-PAGES-R034.3 | Run parity matrix wiring test. |
| T-PIPE-PAGES-R034.4 | PIPE-PAGES-R034.4 | Run parity refusal test. |
| T-PIPE-PAGES-R034.5 | PIPE-PAGES-R034.5 | Run parity evidence test. |
| T-PIPE-PAGES-R034.6 | PIPE-PAGES-R034.6 | Run `test_eg53_portable_deployment_cli`. |
| T-PIPE-PAGES-R021.91 | PIPE-PAGES-R021.91 | Complete inventory lists every validation action. |
| T-PIPE-PAGES-R021.92 | PIPE-PAGES-R021.92 | Hook adopters configure and pass both success and failure cases. |
| T-PIPE-PAGES-R021.93 | PIPE-PAGES-R021.93 | Pre-commit configuration names every mapped behavior for all projects. |
| T-PIPE-PAGES-R021.94 | PIPE-PAGES-R021.94 | Baseline gaps remain visible in inventory and findings. |
| T-PIPE-PAGES-R021.95 | PIPE-PAGES-R021.95 | Baseline state appears in all hook findings. |
| T-PIPE-PAGES-R021.96 | PIPE-PAGES-R021.96 | Test missing behavior in pre-commit configuration. |
| T-PIPE-PAGES-R037.1 | PIPE-PAGES-R037.1 | Profile specifies doubles for database, API, client code. |
| T-PIPE-PAGES-R037.2 | PIPE-PAGES-R037.2 | Unit runner rejects planted network and container attempts. |
| T-PIPE-PAGES-R037.3 | PIPE-PAGES-R037.3 | Profile adoption gates must reject unmocked external dependencies. |
| T-PIPE-PAGES-R037.4 | PIPE-PAGES-R037.4 | Runner cannot silently skip external dependency mocking. |
| T-PIPE-PAGES-R037.5 | PIPE-PAGES-R037.5 | Evidence separates unit isolation from integration tests. |
| T-PIPE-PAGES-R037.6 | PIPE-PAGES-R037.6 | Test planted database and API calls. |
| T-PIPE-PAGES-R038.1 | PIPE-PAGES-R038.1 | Hook declares ontology file inputs and check outputs. |
| T-PIPE-PAGES-R038.2 | PIPE-PAGES-R038.2 | Failed verdict causes commit refusal via hook exit. |
| T-PIPE-PAGES-R038.3 | PIPE-PAGES-R038.3 | Hook reaches Medulla service identity and pins verdict version. |
| T-PIPE-PAGES-R038.4 | PIPE-PAGES-R038.4 | Missing verdicts block commits rather than permit them. |
| T-PIPE-PAGES-R038.5 | PIPE-PAGES-R038.5 | Evidence separates local execution from remote verdict authority. |
| T-PIPE-PAGES-R038.6 | PIPE-PAGES-R038.6 | Test proves local authority cannot override Medulla. |
| T-PIPE-PAGES-R040.1 | PIPE-PAGES-R040.1 | Proposal must carry coverage baseline and candidate measurements. |
| T-PIPE-PAGES-R040.2 | PIPE-PAGES-R040.2 | Gate compares candidate metrics against baseline deterministically. |
| T-PIPE-PAGES-R040.3 | PIPE-PAGES-R040.3 | Baseline and candidate evidence bind to revision. |
| T-PIPE-PAGES-R040.4 | PIPE-PAGES-R040.4 | Unmeasured coverage proposals fail rather than pass. |
| T-PIPE-PAGES-R040.5 | PIPE-PAGES-R040.5 | Evidence preserves graph authorization and materialization receipt. |
| T-PIPE-PAGES-R040.6 | PIPE-PAGES-R040.6 | Test planted coverage decrease in candidate revision. |
| T-PIPE-PAGES-R041.1 | PIPE-PAGES-R041.1 | Configuration specifies nonnegative integer limits for each. |
| T-PIPE-PAGES-R041.2 | PIPE-PAGES-R041.2 | Every violation identifies repository-relative path and function. |
| T-PIPE-PAGES-R041.3 | PIPE-PAGES-R041.3 | Arbora configuration pins both limits and invokes check. |
| T-PIPE-PAGES-R041.4 | PIPE-PAGES-R041.4 | Missing limits exit 2; violations above limits exit 1. |
| T-PIPE-PAGES-R041.5 | PIPE-PAGES-R041.5 | Evidence identifies repository-relative path and qualified function. |
| T-PIPE-PAGES-R041.6 | PIPE-PAGES-R041.6 | Test keyword-only, variadic and nested-try function cases. |
| T-PIPE-PAGES-R044 | PIPE-PAGES-R044 | Test: `tests/test_architecture_explorer.py::test_verified_and_delivered_counts_are_separate`. |
| T-PIPE-PAGES-R046 | PIPE-PAGES-R046 | Test: `tests/test_architecture_explorer.py::test_section_panel_counts_own_rows_and_shares_fade`. |
| T-PIPE-PAGES-R047 | PIPE-PAGES-R047 | Test: `tests/test_architecture_explorer.py::test_edges_carry_type_rows_and_legend`. |
| T-PIPE-PAGES-R048 | PIPE-PAGES-R048 | `tests/test_architecture_explorer.py::test_code_view_reclusters_only_changed_items_and_links_rows`. |
| T-PIPE-PAGES-R053 | PIPE-PAGES-R053 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R053.1 | PIPE-PAGES-R053.1 | Test: `tests/test_canopy_drawer.py::test_row_drawer_model_has_excerpts_tasks_checklist_and_unblocks`. Add `RowDrawer` to `scripts/architecture_explorer/details.py`. |
| T-PIPE-PAGES-R053.2 | PIPE-PAGES-R053.2 | Test: `tests/test_canopy_drawer.py::test_excerpts_hold_only_paragraphs_that_name_the_row`. Build each excerpt from the paragraphs that name the row ID. |
| T-PIPE-PAGES-R053.3 | PIPE-PAGES-R053.3 | Test: `tests/test_canopy_drawer.py::test_a_row_click_opens_the_drawer_and_sets_the_row_hash`. Add `renderDrawer(id)` to the page. |
| T-PIPE-PAGES-R053.4 | PIPE-PAGES-R053.4 | Test: `tests/test_canopy_drawer.py::test_missing_row_and_failed_family_load_are_reported_in_the_drawer`. A row ID with no detail entry shows `Row not found` in the drawer and keeps the map. |
| T-PIPE-PAGES-R053.5 | PIPE-PAGES-R053.5 | Test: `tests/test_canopy_drawer.py::test_drawer_lists_exact_paths_and_evidence_links`. The drawer shows the exact file path of each linked artifact and a link to it on the default branch. |
| T-PIPE-PAGES-R053.6 | PIPE-PAGES-R053.6 | Test: `tests/test_canopy_drawer.py::test_the_drawer_opens_in_a_browser_with_tasks_and_unblocks`. Use entry point `build.py` `main`, then open the page in a headless browser and click a row. |
| T-PIPE-PAGES-R054 | PIPE-PAGES-R054 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R054.1 | PIPE-PAGES-R054.1 | Test: `tests/test_canopy_modes.py::test_sdd_phase_enum_orders_six_phases`. Add `SddPhase` to `scripts/architecture_explorer/sdd.py`. |
| T-PIPE-PAGES-R054.2 | PIPE-PAGES-R054.2 | Test: `tests/test_canopy_modes.py::test_each_phase_predicate_holds_only_on_its_artifacts`. Define the predicates over the family artifacts. |
| T-PIPE-PAGES-R054.3 | PIPE-PAGES-R054.3 | Test: `tests/test_canopy_modes.py::test_mode_switch_changes_node_style_without_moving_nodes`. Add a mode switch to the toolbar: five buttons in one `role="group"` with `aria-pressed`. |
| T-PIPE-PAGES-R054.4 | PIPE-PAGES-R054.4 | Test: `tests/test_canopy_modes.py::test_empty_nodes_stay_neutral_and_unknown_mode_falls_back`. A node with no own rows keeps the neutral style in every mode and shows `no own rows` in its label. |
| T-PIPE-PAGES-R054.5 | PIPE-PAGES-R054.5 | Test: `tests/test_canopy_modes.py::test_dependency_edges_match_the_next_up_prerequisites`. Dependency mode draws one edge per prerequisite pair between nodes. |
| T-PIPE-PAGES-R054.6 | PIPE-PAGES-R054.6 | Test: `tests/test_canopy_modes.py::test_sdd_mode_legend_counts_match_the_computed_phases_in_a_browser`. Use entry point `build.py` `main` on a fixture with four spec families, one per phase. |
| T-PIPE-PAGES-R055 | PIPE-PAGES-R055 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R055.1 | PIPE-PAGES-R055.1 | Test: `tests/test_canopy_filters.py::test_next_step_maps_phase_and_state_to_one_chip`. Add `next_step(row, card)` to `scripts/architecture_explorer/sdd.py`. |
| T-PIPE-PAGES-R055.2 | PIPE-PAGES-R055.2 | Test: `tests/test_canopy_filters.py::test_chip_rules_follow_the_documented_order`. Define the chips. |
| T-PIPE-PAGES-R055.3 | PIPE-PAGES-R055.3 | Test: `tests/test_canopy_filters.py::test_chips_combine_with_status_and_release_filters`. Add a chip group `Next step` to the panel filter bar. |
| T-PIPE-PAGES-R055.4 | PIPE-PAGES-R055.4 | Test: `tests/test_canopy_filters.py::test_empty_chips_are_disabled_and_unknown_names_are_ignored`. A chip with zero matching rows stays visible, is disabled, and shows `0`. |
| T-PIPE-PAGES-R055.5 | PIPE-PAGES-R055.5 | Test: `tests/test_canopy_filters.py::test_chip_counts_and_export_next_step_agree`. Each chip shows its row count and a title attribute with its rule in plain words. |
| T-PIPE-PAGES-R055.6 | PIPE-PAGES-R055.6 | Test: `tests/test_canopy_filters.py::test_the_ready_filter_lists_only_next_up_rows_in_a_browser`. Use entry point `build.py` `main` on a fixture with one row per chip. |
| T-PIPE-PAGES-R056 | PIPE-PAGES-R056 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R056.1 | PIPE-PAGES-R056.1 | Test: `tests/test_canopy_releases.py::test_phase_line_in_plan_wins_over_release_phase_and_part_progress_counts`. Add `part_progress` to `release_view` in `scripts/architecture_explorer/releases.py:55`. |
| T-PIPE-PAGES-R056.2 | PIPE-PAGES-R056.2 | Test: `tests/test_canopy_releases.py::test_selecting_a_release_dims_other_nodes_and_shows_part_progress`. Selecting a release highlights the nodes that own scoped rows and dims the others. |
| T-PIPE-PAGES-R056.3 | PIPE-PAGES-R056.3 | Test: `tests/test_canopy_releases.py::test_github_mode_refuses_a_missing_releases_directory`. The organization workflow must check out `releases/` from the generator repository. |
| T-PIPE-PAGES-R056.4 | PIPE-PAGES-R056.4 | Test: `tests/test_canopy_releases.py::test_empty_state_explains_manifests_and_bad_phase_fails_the_build`. When no manifest loads in a local build, the Releases view shows an empty state. |
| T-PIPE-PAGES-R056.5 | PIPE-PAGES-R056.5 | Test: `tests/test_canopy_releases.py::test_release_card_links_manifest_and_unscheduled_count_matches_rows`. Each release card links its manifest file on the default branch and lists its scoped rows per part with progress. |
| T-PIPE-PAGES-R056.6 | PIPE-PAGES-R056.6 | Test: `tests/test_canopy_releases.py::test_release_hash_filters_the_map_in_a_browser`. Use entry point `build.py` `main` with `--mode github` against a fixture that has two manifests. |
| T-PIPE-PAGES-R057 | PIPE-PAGES-R057 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R057.1 | PIPE-PAGES-R057.1 | Test: `tests/test_canopy_export.py::test_export_row_carries_every_present_artifact_path`. Add `ExportRow` and `ViewSpec` dataclasses in new `scripts/architecture_explorer/export.py`. |
| T-PIPE-PAGES-R057.2 | PIPE-PAGES-R057.2 | Test: `tests/test_canopy_export.py::test_hash_round_trips_row_part_mode_filter_release`. Extend `parseHash` and `hashFor` in `scripts/architecture_explorer/search.cjs:13` and `:34` with the keys `row`, `part`, `mode`, `filter` and `release`. |
| T-PIPE-PAGES-R057.3 | PIPE-PAGES-R057.3 | Test: `tests/test_canopy_export.py::test_a_build_writes_rows_json_and_markdown_beside_the_page`. Write `export/rows.json` and `export/rows.md` beside the page for the whole row set. |
| T-PIPE-PAGES-R057.4 | PIPE-PAGES-R057.4 | Test: `tests/test_canopy_export.py::test_unknown_view_values_are_refused_and_unsafe_paths_fail_the_build`. An unknown mode, filter or release in the hash leaves the view unchanged and says so in the live status region. |
| T-PIPE-PAGES-R057.5 | PIPE-PAGES-R057.5 | Test: `tests/test_canopy_export.py::test_export_header_digest_is_stable_and_markdown_lists_paths`. Each export starts with a header: schema version `1`, `built_at`, the head commit of each repository, the row count, the applied view, and a sha256 digest of the row list. |
| T-PIPE-PAGES-R057.6 | PIPE-PAGES-R057.6 | Test: `tests/test_canopy_export.py::test_a_hash_restores_the_view_and_the_export_paths_exist`. Use entry point `build.py` through `main`, then load the page with a hash in a headless browser. |
| T-PIPE-PAGES-R057.7 | PIPE-PAGES-R057.7 | Test: `tests/test_canopy_export.py::test_page_without_scripts_lists_parts_and_links_exports`. Add a `<noscript>` block to the page template. |
| T-PIPE-PAGES-R058 | PIPE-PAGES-R058 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R058.1 | PIPE-PAGES-R058.1 | Test: `tests/test_canopy_research.py::test_open_questions_find_markers_and_unchecked_research_items`. Add `open_questions(docs)` to `scripts/architecture_explorer/sdd.py`. |
| T-PIPE-PAGES-R058.2 | PIPE-PAGES-R058.2 | Test: `tests/test_canopy_research.py::test_counts_follow_the_own_rows_rule_and_zero_shows_no_badge`. A row's count is the questions that name its ID. |
| T-PIPE-PAGES-R058.3 | PIPE-PAGES-R058.3 | Test: `tests/test_canopy_research.py::test_badges_render_on_node_card_and_row_with_screen_reader_text`. Draw a small count badge on a node in `drawNode` at `template.html:635`. |
| T-PIPE-PAGES-R058.4 | PIPE-PAGES-R058.4 | Test: `tests/test_canopy_research.py::test_unreadable_research_marks_the_family_without_failing_the_build`. A research file that cannot be decoded gives the family a `research unreadable` marker and counts zero. |
| T-PIPE-PAGES-R058.5 | PIPE-PAGES-R058.5 | Test: `tests/test_canopy_research.py::test_drawer_and_export_list_the_questions_with_document_and_line`. The drawer of PIPE-PAGES-R053 lists each open question with its document, line and a link. |
| T-PIPE-PAGES-R058.6 | PIPE-PAGES-R058.6 | Test: `tests/test_canopy_research.py::test_research_badge_and_drawer_list_in_a_browser`. Use entry point `build.py` `main` on a fixture whose `research.md` holds two open items. |
