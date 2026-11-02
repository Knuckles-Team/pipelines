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
| T-PIPE-PAGES-R012.1 | PIPE-PAGES-R012.1 | Run `tests/test_spec_dashboard_metadata.py::test_source_declarations_and_citations_in_both_documents`. |
| T-PIPE-PAGES-R012.2 | PIPE-PAGES-R012.2 | Run `tests/test_spec_dashboard_metadata.py::test_enrichment_preserves_delivery_records_and_status_bytes`. Needs a status-regeneration integration check. `test_enrichment_preserves_delivery_records_and_status_bytes` checks enrichment only; it does not prove regeneration. |
| T-PIPE-PAGES-R012.3 | PIPE-PAGES-R012.3 | Run `tests/test_spec_dashboard_metadata.py::test_implementation_tests_docs_and_missing_sources_are_distinct`. |
| T-PIPE-PAGES-R012.4 | PIPE-PAGES-R012.4 | Run `tests/test_spec_dashboard_metadata.py::test_code_cells_replace_concepts`. |
| T-PIPE-PAGES-R012.5 | PIPE-PAGES-R012.5 | Run `tests/test_spec_dashboard_metadata.py::test_implementation_tests_docs_and_missing_sources_are_distinct`. |
| T-PIPE-PAGES-R012.6 | PIPE-PAGES-R012.6 | Run `tests/test_spec_dashboard_metadata.py::test_code_cells_replace_concepts`. |
| T-PIPE-PAGES-R012.7 | PIPE-PAGES-R012.7 | Run `tests/test_spec_dashboard_metadata.py::test_examples_unsafe_links_and_parent_escape_are_not_mappings`. |
| T-PIPE-PAGES-R013.1 | PIPE-PAGES-R013.1 | Run `tests/test_spec_dashboard_metadata.py::test_local_and_external_dependencies_have_links_and_canonical_identity`. |
| T-PIPE-PAGES-R013.2 | PIPE-PAGES-R013.2 | Run `tests/test_spec_dashboard_metadata.py::test_explicit_edge_kinds_remain_distinct_from_mentions`. |
| T-PIPE-PAGES-R013.3 | PIPE-PAGES-R013.3 | Run `tests/test_spec_dashboard_metadata.py::test_unknowns_empty_and_isolated_specs_remain_discoverable`. |
| T-PIPE-PAGES-R013.4 | PIPE-PAGES-R013.4 | Run `tests/test_spec_dashboard_metadata.py::test_deterministic_escaped_output_and_plan_diagram_coverage`. |
| T-PIPE-PAGES-R013.5 | PIPE-PAGES-R013.5 | Run `tests/test_spec_dashboard_metadata.py::test_local_and_external_dependencies_have_links_and_canonical_identity`. |
| T-PIPE-PAGES-R013.6 | PIPE-PAGES-R013.6 | Run `tests/test_spec_dashboard_metadata.py::test_unknowns_empty_and_isolated_specs_remain_discoverable`. |
| T-PIPE-PAGES-R013.7 | PIPE-PAGES-R013.7 | Run `tests/test_spec_dashboard_metadata.py::test_large_groups_keep_all_specs_and_relationships`. |
| T-PIPE-PAGES-R014.1 | PIPE-PAGES-R014.1 | Run `tests/test_spec_dashboard_drilldown.py::test_components_equal_core_list` expects equality with the R001 list. |
| T-PIPE-PAGES-R014.2 | PIPE-PAGES-R014.2 | Run `tests/test_spec_dashboard_drilldown.py::test_anchor_forms` expects the three forms. |
| T-PIPE-PAGES-R014.3 | PIPE-PAGES-R014.3 | Run `tests/test_spec_dashboard_drilldown.py::test_spec_section_has_anchor` expects the anchor and four content blocks. |
| T-PIPE-PAGES-R014.4 | PIPE-PAGES-R014.4 | Run `tests/test_spec_dashboard_drilldown.py::test_relation_box_links_to_spec_section` expects the href on every box. |
| T-PIPE-PAGES-R014.5 | PIPE-PAGES-R014.5 | Run `tests/test_render_profile_links.py::test_profile_links_cover_components` expects one level-1 link per component. |
| T-PIPE-PAGES-R014.6 | PIPE-PAGES-R014.6 | Run `tests/test_spec_dashboard_drilldown.py::test_unresolved_component_link_fails` expects exit 1 for a missing page. |
| T-PIPE-PAGES-R015.1 | PIPE-PAGES-R015.1 | Run `tests/test_pages_pipeline_contract.py::test_pages_workflow_runs_relation_steps` expects the steps and no repository names. |
| T-PIPE-PAGES-R015.2 | PIPE-PAGES-R015.2 | Run `tests/test_pages_pipeline_contract.py::test_client_callers_use_reusable_workflow` expects each caller to reference the workflow at `main`. |
| T-PIPE-PAGES-R015.3 | PIPE-PAGES-R015.3 | Run `tests/test_spec_dashboard_metadata.py::test_generator_entry_point_writes_architecture_and_metadata`. |


## Planned cycle-layout acceptance

`tests/test_spec_dashboard_relations.py::test_cycle_layers_are_order_independent` must cover self-loops and three-node cycles.
Incoming and outgoing dependencies must retain their depth after strongly connected components collapse.
Input permutations must produce identical layers. The relationship table must retain every original edge.
This test is planned; this documentation change does not implement it.
| T-PIPE-PAGES-R016.1 | PIPE-PAGES-R016.1 | Run `tests/test_spec_dashboard.py::test_snapshot_has_no_history_field` expects no `history` key in the snapshot. |
| T-PIPE-PAGES-R016.2 | PIPE-PAGES-R016.2 | Run `tests/test_spec_dashboard.py::test_page_has_no_history_panels` expects no history, transition or timeline marker in the HTML. |
| T-PIPE-PAGES-R016.3 | PIPE-PAGES-R016.3 | Run `tests/test_spec_dashboard.py::test_removed_id_absent_from_page` expects a removed ID to be absent from the page built from a repository whose history contains it. |
| T-PIPE-PAGES-R016.4 | PIPE-PAGES-R016.4 | Run `tests/test_spec_dashboard.py::test_workflow_does_not_reference_history_scripts` expects no `spec_dashboard_history` or `spec_dashboard_charts` in the workflow. |
| T-PIPE-PAGES-R016.5 | PIPE-PAGES-R016.5 | Run `tests/test_spec_dashboard.py::test_retired_record_is_not_rendered` expects one VERIFIED record rendered, the RETIRED ID absent, and one record counted. |
| T-PIPE-PAGES-R017.1 | PIPE-PAGES-R017.1 | Run `tests/test_spec_dashboard_states.py::test_legend_has_three_states`. |
| T-PIPE-PAGES-R017.2 | PIPE-PAGES-R017.2 | Run `tests/test_spec_dashboard_states.py::test_row_has_one_state_cell`. |
| T-PIPE-PAGES-R017.3 | PIPE-PAGES-R017.3 | Run `tests/test_spec_dashboard_states.py::test_unknown_state_renders_invalid`. |
| T-PIPE-PAGES-R018.1 | PIPE-PAGES-R018.1 | Run `tests/test_spec_delivery_nav.py::test_flag_is_env_driven` expects the `!ENV` flag and the workflow variable. |
| T-PIPE-PAGES-R018.2 | PIPE-PAGES-R018.2 | Run `tests/test_spec_delivery_nav.py::test_entry_is_root_relative_and_flag_gated` expects `base_url`, no host, and the flag guard. |
| T-PIPE-PAGES-R018.3 | PIPE-PAGES-R018.3 | Run `tests/test_spec_delivery_nav.py::test_menu_iterates_the_single_site_list` expects the loop over `extra.ecosystem.sites` and no literal repository URL in the template. |
| T-PIPE-PAGES-R018.4 | PIPE-PAGES-R018.4 | Run `tests/test_spec_delivery_nav.py::test_site_urls_match_repos` expects each site URL to equal the REPOS URL for its slug. |
| T-PIPE-PAGES-R018.5 | PIPE-PAGES-R018.5 | Run `tests/test_spec_delivery_nav.py::test_theme_sync_check_passes_with_entry` expects an empty drift list. |
| T-PIPE-PAGES-R019.1 | PIPE-PAGES-R019.1 | Run `tests/test_spec_dashboard_nav.py::test_nav_landmark_links_documentation` expects the stated result. |
| T-PIPE-PAGES-R019.2 | PIPE-PAGES-R019.2 | Run `tests/test_spec_dashboard_nav.py::test_current_page_is_marked` expects the stated result. |
| T-PIPE-PAGES-R019.3 | PIPE-PAGES-R019.3 | Run `tests/test_spec_dashboard_nav.py::test_repository_links_equal_single_source` expects the stated result. |
| T-PIPE-PAGES-R019.4 | PIPE-PAGES-R019.4 | Run `tests/test_spec_dashboard_nav.py::test_skip_link_targets_main` expects the stated result. |
| T-PIPE-PAGES-R019.5 | PIPE-PAGES-R019.5 | Run `tests/test_spec_dashboard_nav.py::test_page_keeps_existing_panels` expects the stated result. |
| T-PIPE-PAGES-R020.1 | PIPE-PAGES-R020.1 | Run `tests/hooks/test_doc_claims.py::test_doc_claim_kind_is_closed` expects a `ValueError` for any other kind. |
| T-PIPE-PAGES-R020.2 | PIPE-PAGES-R020.2 | Run `tests/hooks/test_doc_claims.py::test_resolvers_check_each_kind` expects one finding per false claim and none for true claims. |
| T-PIPE-PAGES-R020.3 | PIPE-PAGES-R020.3 | Run `tests/hooks/test_doc_claims.py::test_validate_calls_claim_findings` expects a claim finding from `validate` on a stale fixture. |
| T-PIPE-PAGES-R020.4 | PIPE-PAGES-R020.4 | Run `tests/hooks/test_doc_claims.py::test_unresolvable_claim_is_reported` expects the `claims-unchecked` finding. |
| T-PIPE-PAGES-R020.5 | PIPE-PAGES-R020.5 | Run `tests/hooks/test_doc_claims.py::test_claims_summary_line` expects the counts to equal the fixture. |
| T-PIPE-PAGES-R020.6 | PIPE-PAGES-R020.6 | Run `tests/hooks/test_public_surface_claims.py::test_public_surface_hook_fails_on_stale_claim` expects exit 1 and the finding. |
| T-PIPE-PAGES-R021.1 | PIPE-PAGES-R021.1 | Run `tests/hooks/test_test_quality.py::test_finding_rule_is_closed` expects a `ValueError` for any other rule. |
| T-PIPE-PAGES-R021.2 | PIPE-PAGES-R021.2 | Run `tests/hooks/test_test_quality.py::test_scan_flags_placeholder_and_bare_suppression` expects one finding per violation. |
| T-PIPE-PAGES-R021.3 | PIPE-PAGES-R021.3 | Run `tests/hooks/test_test_quality.py::test_test_quality_is_registered` expects the name in `GATES` and in the hook file. |
| T-PIPE-PAGES-R021.4 | PIPE-PAGES-R021.4 | Run `tests/hooks/test_test_quality.py::test_missing_coverage_report_cannot_run` expects exit 2. |
| T-PIPE-PAGES-R021.5 | PIPE-PAGES-R021.5 | Run `tests/hooks/test_test_quality.py::test_test_quality_summary_line` expects the stated fields. |
| T-PIPE-PAGES-R021.6 | PIPE-PAGES-R021.6 | Run `tests/hooks/test_test_quality_hook.py::test_test_quality_hook_fails_fixture` expects exit 1 and two findings. |
| T-PIPE-PAGES-R022.1 | PIPE-PAGES-R022.1 | Run `tests/hooks/test_mutation_gaps.py::test_policy_defaults` expects the default module list. |
| T-PIPE-PAGES-R022.2 | PIPE-PAGES-R022.2 | Run `tests/hooks/test_mutation_gaps.py::test_only_survivors_are_reported` expects survivors only. |
| T-PIPE-PAGES-R022.3 | PIPE-PAGES-R022.3 | Run `tests/hooks/test_mutation_gaps.py::test_mutation_workflow_runs_gate` expects the cron entry and the gate command. |
| T-PIPE-PAGES-R022.4 | PIPE-PAGES-R022.4 | Run `tests/hooks/test_mutation_gaps.py::test_absent_runner_fails_closed_in_ci` expects exit 2 under `CI=1`. |
| T-PIPE-PAGES-R022.5 | PIPE-PAGES-R022.5 | Run `tests/hooks/test_mutation_gaps.py::test_mutation_report_lines` expects the stated lines. |
| T-PIPE-PAGES-R022.6 | PIPE-PAGES-R022.6 | Run `tests/hooks/test_mutation_gaps_hook.py::test_mutation_gaps_hook_reports_untested_branch` expects exit 1 and the line. |
| T-PIPE-PAGES-R020.7 | PIPE-PAGES-R020.7 | Run `tests/hooks/test_public_surface_claims.py::test_located_finding_schema`; assert the stated result. |
| T-PIPE-PAGES-R020.8 | PIPE-PAGES-R020.8 | Run `tests/hooks/test_public_surface_claims.py::test_located_evidence_matches_tree`; assert the stated result. |
| T-PIPE-PAGES-R020.9 | PIPE-PAGES-R020.9 | Run `tests/hooks/test_public_surface_claims.py::test_finding_validator_is_wired`; assert the stated result. |
| T-PIPE-PAGES-R020.10 | PIPE-PAGES-R020.10 | Run `tests/hooks/test_public_surface_claims.py::test_unsupported_finding_refused`; assert the stated result. |
| T-PIPE-PAGES-R020.11 | PIPE-PAGES-R020.11 | Run `tests/hooks/test_public_surface_claims.py::test_located_evidence_export`; assert the stated result. |
| T-PIPE-PAGES-R020.12 | PIPE-PAGES-R020.12 | Run `tests/hooks/test_public_surface_claims.py::test_public_surface_located_evidence_cli`; assert the stated result. |
| T-PIPE-PAGES-R021.7 | PIPE-PAGES-R021.7 | Run `tests/hooks/test_test_quality_hook.py::test_component_contract_model`. Assert the closed edge kinds and separate runtime/type-only permissions. |
| T-PIPE-PAGES-R021.8 | PIPE-PAGES-R021.8 | Run `tests/hooks/test_test_quality_hook.py::test_component_contract_checks`. Assert allowed lazy imports preserve reachability, forbidden lazy imports fail, and type-only imports cannot prove runtime reachability. |
| T-PIPE-PAGES-R021.9 | PIPE-PAGES-R021.9 | Run `tests/hooks/test_test_quality_hook.py::test_component_checks_are_wired`. Assert the CLI boundary/orphan path consumes the static runtime graph and cycle checks retain the eager graph. |
| T-PIPE-PAGES-R021.10 | PIPE-PAGES-R021.10 | Run `tests/hooks/test_test_quality_hook.py::test_component_proof_refusals`. Assert unresolved dynamic reachability is exit 2, never a false clean or definite orphan; retain receipt refusals. |
| T-PIPE-PAGES-R021.11 | PIPE-PAGES-R021.11 | Run `tests/hooks/test_test_quality_hook.py::test_component_evidence_receipts`. Assert runtime, type-only and unresolved dynamic evidence remain distinguishable. |
| T-PIPE-PAGES-R021.12 | PIPE-PAGES-R021.12 | Run `tests/hooks/test_test_quality_hook.py::test_component_handoff_cli`. Assert CLI exit codes, exact edge locations, type-only separation and no false orphan for allowed lazy imports. |
| T-PIPE-PAGES-R023.1 | PIPE-PAGES-R023.1 | Run `tests/hooks/test_skill_grade_hook.py::test_skill_grade_model`; assert the stated result. |
| T-PIPE-PAGES-R023.2 | PIPE-PAGES-R023.2 | Run `tests/hooks/test_skill_grade_hook.py::test_skill_grade_criteria`; assert the stated result. |
| T-PIPE-PAGES-R023.3 | PIPE-PAGES-R023.3 | Run `tests/hooks/test_skill_grade_hook.py::test_skill_grade_registration`; assert the stated result. |
| T-PIPE-PAGES-R023.4 | PIPE-PAGES-R023.4 | Run `tests/hooks/test_skill_grade_hook.py::test_skill_grade_refusals`; assert the stated result. |
| T-PIPE-PAGES-R023.5 | PIPE-PAGES-R023.5 | Run `tests/hooks/test_skill_grade_hook.py::test_skill_grade_evidence`; assert the stated result. |
| T-PIPE-PAGES-R023.6 | PIPE-PAGES-R023.6 | Run `tests/hooks/test_skill_grade_hook.py::test_skill_grade_cli`; assert the stated result. |
| T-PIPE-PAGES-R024.1 | PIPE-PAGES-R024.1 | Run `tests/hooks/test_similarity_guidance_hook.py::test_similarity_report_model`; assert the stated result. |
| T-PIPE-PAGES-R024.2 | PIPE-PAGES-R024.2 | Run `tests/hooks/test_similarity_guidance_hook.py::test_similarity_threshold_boundaries`; assert the stated result. |
| T-PIPE-PAGES-R024.3 | PIPE-PAGES-R024.3 | Run `tests/hooks/test_similarity_guidance_hook.py::test_similarity_reporting_wiring`; assert the stated result. |
| T-PIPE-PAGES-R024.4 | PIPE-PAGES-R024.4 | Run `tests/hooks/test_similarity_guidance_hook.py::test_similarity_refusals`; assert the stated result. |
| T-PIPE-PAGES-R024.5 | PIPE-PAGES-R024.5 | Run `tests/hooks/test_similarity_guidance_hook.py::test_similarity_evidence`; assert the stated result. |
| T-PIPE-PAGES-R024.6 | PIPE-PAGES-R024.6 | Run `tests/hooks/test_similarity_guidance_hook.py::test_similarity_guidance_cli`; assert the stated result. |
| T-PIPE-PAGES-R021.13 | PIPE-PAGES-R021.13 | Run `tests/hooks/test_test_quality_outcomes.py::test_outcome_contract_schema`. Reject unknown outcome kinds, empty observables and missing source bindings; accept return, error and side-effect contracts. |
| T-PIPE-PAGES-R021.14 | PIPE-PAGES-R021.14 | Run `tests/hooks/test_test_quality_outcomes.py::test_outcome_counterexamples`. Reject a passing test that ignores the result; accept exact return, error and state assertions that detect their counterexamples. |
| T-PIPE-PAGES-R021.15 | PIPE-PAGES-R021.15 | Run `tests/hooks/test_test_quality_outcomes.py::test_outcome_checker_wiring`. Assert the published CLI invokes the configured runner, validates its receipts and includes outcome findings in its exit code. |
| T-PIPE-PAGES-R021.16 | PIPE-PAGES-R021.16 | Run `tests/hooks/test_test_quality_outcomes.py::test_outcome_proof_refusals`. Missing contracts and surviving counterexamples exit 1; stale, skipped, setup-failing and timed-out proofs exit 2. |
| T-PIPE-PAGES-R021.17 | PIPE-PAGES-R021.17 | Run `tests/hooks/test_test_quality_outcomes.py::test_outcome_evidence`. Assert distinct static/runtime records and digest-bound receipts; never report coverage or assertion count as outcome proof. |
| T-PIPE-PAGES-R021.18 | PIPE-PAGES-R021.18 | Run `tests/hooks/test_test_quality_outcomes.py::test_outcome_quality_cli`. Assert exit 0 for proved outcomes, exit 1 for missing observation and exit 2 for unchecked proof through the real CLI and runner. |
| T-PIPE-PAGES-R020.13 | PIPE-PAGES-R020.13 | Run `tests/hooks/test_changelog_gate.py::test_changelog_model`. Reject unknown grammar fields and duplicate releases; represent dated releases and an optional unreleased section with exact locations. |
| T-PIPE-PAGES-R020.14 | PIPE-PAGES-R020.14 | Run `tests/hooks/test_changelog_gate.py::test_changelog_grammar`. Accept dated categorized releases; independently reject invalid dates/versions, misplaced entries, duplicate headings and unknown categories. |
| T-PIPE-PAGES-R020.15 | PIPE-PAGES-R020.15 | Run `tests/hooks/test_changelog_gate.py::test_changelog_hook_wiring`. The published CLI/hook reads policy and changelog from one Git snapshot and invokes the new grammar checker. |
| T-PIPE-PAGES-R020.16 | PIPE-PAGES-R020.16 | Run `tests/hooks/test_changelog_gate.py::test_changelog_refusals`. Missing files and malformed policy exit 2; missing links and malformed release entries exit 1, with path and source line. |
| T-PIPE-PAGES-R020.17 | PIPE-PAGES-R020.17 | Run `tests/hooks/test_changelog_gate.py::test_changelog_evidence`. Bind findings to exact Git bytes and explicitly mark network reachability and change completeness as unverified. |
| T-PIPE-PAGES-R020.18 | PIPE-PAGES-R020.18 | Run `tests/hooks/test_changelog_gate.py::test_changelog_cli`. Assert valid exit 0, grammar exit 1, missing-file and initial-history exit 2, then a valid first-release repair to exit 0, exact locations, snapshot isolation and no file writes or network calls. |
| T-PIPE-PAGES-R020.19 | PIPE-PAGES-R020.19 | Run `tests/hooks/test_env_documentation.py::test_env_documentation_model`. Reject duplicate names, unknown fields, contradictory defaults and unmapped launcher bindings. |
| T-PIPE-PAGES-R020.20 | PIPE-PAGES-R020.20 | Run `tests/hooks/test_env_documentation.py::test_env_documentation_behavior`. Independently corrupt each documentation field and remove, rename or contradict each launcher binding to fail. |
| T-PIPE-PAGES-R020.21 | PIPE-PAGES-R020.21 | Run `tests/hooks/test_env_documentation.py::test_env_documentation_wiring`. Invoke CLI and configured pre-commit with all three consumer surfaces from the same indexed snapshot. |
| T-PIPE-PAGES-R020.22 | PIPE-PAGES-R020.22 | Run `tests/hooks/test_env_documentation.py::test_env_documentation_refusal`. Malformed and missing launcher JSON fails; unsupported substitutions and computed names refuse without execution. |
| T-PIPE-PAGES-R020.23 | PIPE-PAGES-R020.23 | Run `tests/hooks/test_env_documentation.py::test_env_documentation_evidence`. Check exact third-surface locations/digests, missing binding evidence, uncertainty and secret redaction. |
| T-PIPE-PAGES-R020.24 | PIPE-PAGES-R020.24 | Run `tests/hooks/test_env_documentation.py::test_env_documentation_cli`. Assert CLI/hook exits 0/1/2 for all three surfaces, exact JSON pointers, snapshot isolation and no launch/import/network execution. |
| T-PIPE-PAGES-R020.25 | PIPE-PAGES-R020.25 | Run `tests/hooks/test_config_inventory.py::test_config_inventory_model`. Require all four roles for every declared project and reject duplicate effective authorities. |
| T-PIPE-PAGES-R020.26 | PIPE-PAGES-R020.26 | Run `tests/hooks/test_config_inventory.py::test_config_inventory_behavior`. Render all roles twice byte-identically and detect missing files, sections and managed-field drift. |
| T-PIPE-PAGES-R020.27 | PIPE-PAGES-R020.27 | Run `tests/hooks/test_config_inventory.py::test_config_inventory_wiring`. The installed hook invokes check mode; an explicit scratch render runs the same templates and parsers. |
| T-PIPE-PAGES-R020.28 | PIPE-PAGES-R020.28 | Run `tests/hooks/test_config_inventory.py::test_config_inventory_refusal`. Reject traversal and overwrite, and fail a project omitted from the declared inventory. |
| T-PIPE-PAGES-R020.29 | PIPE-PAGES-R020.29 | Run `tests/hooks/test_config_inventory.py::test_config_inventory_evidence`. Prove all projects and four roles appear, and drift identifies the affected section. |
| T-PIPE-PAGES-R020.30 | PIPE-PAGES-R020.30 | Run `tests/hooks/test_config_inventory.py::test_config_inventory_cli`. Assert deterministic rendering, per-role failures, complete multi-project coverage and no check-mode writes. |
| T-PIPE-PAGES-R020.31 | PIPE-PAGES-R020.31 | Run `tests/hooks/test_validation_report.py::test_validation_report_model`. Reject unknown outcomes, duplicate record identities and counts inconsistent with records. |
| T-PIPE-PAGES-R020.32 | PIPE-PAGES-R020.32 | Run `tests/hooks/test_validation_report.py::test_validation_report_behavior`. Round-trip mixed nested outcomes and compare every field, stable ordering and recomputed metrics. |
| T-PIPE-PAGES-R020.33 | PIPE-PAGES-R020.33 | Run `tests/hooks/test_validation_report.py::test_validation_report_wiring`. Run aggregate lint-type results through JSON/Markdown and retain all three phase categories, rules and verdicts. |
| T-PIPE-PAGES-R020.34 | PIPE-PAGES-R020.34 | Run `tests/hooks/test_validation_report.py::test_validation_report_refusal`. Tampered verdict/counts, required skips and malformed/truncated JSON refuse rather than pass. |
| T-PIPE-PAGES-R020.35 | PIPE-PAGES-R020.35 | Run `tests/hooks/test_validation_report.py::test_validation_report_evidence`. Retain failure detail and skip reasons through JSON and Markdown; never leak secret payloads. |
| T-PIPE-PAGES-R020.36 | PIPE-PAGES-R020.36 | Run `tests/hooks/test_validation_report.py::test_validation_report_cli`. Assert real lint/import/type round-trip, exit 1 at unchanged health score, repaired exit 0 and required-phase skip exit 2. |
| T-PIPE-PAGES-R021.19 | PIPE-PAGES-R021.19 | Run `tests/hooks/test_lint_type_policy.py::test_lint_type_policy_model`. Reject unpinned tools, missing phases and scope omissions. |
| T-PIPE-PAGES-R021.20 | PIPE-PAGES-R021.20 | Run `tests/hooks/test_lint_type_policy.py::test_lint_type_policy_behavior`. Independent lint, import-order, type and suppression fixtures fail; a clean supported project passes. |
| T-PIPE-PAGES-R021.21 | PIPE-PAGES-R021.21 | Run `tests/hooks/test_lint_type_policy.py::test_lint_type_policy_wiring`. Configured pre-commit calls all three real tool phases and the shared report adapter. |
| T-PIPE-PAGES-R021.22 | PIPE-PAGES-R021.22 | Run `tests/hooks/test_lint_type_policy.py::test_lint_type_policy_refusal`. Unavailable type checker and an unsupported declared language must not return a clean verdict. |
| T-PIPE-PAGES-R021.23 | PIPE-PAGES-R021.23 | Run `tests/hooks/test_lint_type_policy.py::test_lint_type_policy_evidence`. Prove all three phases ran against identical source bytes and each diagnostic retains its original rule ID. |
| T-PIPE-PAGES-R021.24 | PIPE-PAGES-R021.24 | Run `tests/hooks/test_lint_type_policy.py::test_lint_type_policy_cli`. Assert real analyzer results, zero-exception enforcement, snapshot isolation and no autofix/network writes. |
| T-PIPE-PAGES-R021.25 | PIPE-PAGES-R021.25 | Run `tests/hooks/test_analyzer_health.py::test_analyzer_health_model`. Accept the five scored and three required unscored categories; reject unknown categories and invalid weights or snapshots. |
| T-PIPE-PAGES-R021.26 | PIPE-PAGES-R021.26 | Run `tests/hooks/test_analyzer_health.py::test_analyzer_health_behavior`. Stable permutations yield identical score/order; missing categories cannot inflate health. |
| T-PIPE-PAGES-R021.27 | PIPE-PAGES-R021.27 | Run `tests/hooks/test_analyzer_health.py::test_analyzer_health_wiring`. The aggregate calls the real structured lint-type runner once and exports every phase with existing health adapters. |
| T-PIPE-PAGES-R021.28 | PIPE-PAGES-R021.28 | Run `tests/hooks/test_analyzer_health.py::test_analyzer_health_refusal`. A clean score cannot mask a secret finding, skipped required adapter or stale coverage receipt. |
| T-PIPE-PAGES-R021.29 | PIPE-PAGES-R021.29 | Run `tests/hooks/test_analyzer_health.py::test_analyzer_health_evidence`. Recompute health from only scored categories; retain required lint/import/type verdicts, priority and evidence. |
| T-PIPE-PAGES-R021.30 | PIPE-PAGES-R021.30 | Run `tests/hooks/test_analyzer_health.py::test_analyzer_health_cli`. Assert real aggregate lint/import/type reachability, failing-to-repaired verdicts, stable health score and required-skip exit 2. |
| T-PIPE-PAGES-R023.7 | PIPE-PAGES-R023.7 | Run `tests/hooks/test_external_grade_rules.py::test_external_grade_rules_model`. Reject duplicate rule IDs, unsupported predicate adapters and unpinned rule packs. |
| T-PIPE-PAGES-R023.8 | PIPE-PAGES-R023.8 | Run `tests/hooks/test_external_grade_rules.py::test_external_grade_rules_behavior`. An applied external rule is identifiable; a conflicting or unmapped heuristic cannot silently alter grade. |
| T-PIPE-PAGES-R023.9 | PIPE-PAGES-R023.9 | Run `tests/hooks/test_external_grade_rules.py::test_external_grade_rules_wiring`. The real skill-grade CLI loads the declared pack and emits its exact rule ID in JSON and Markdown. |
| T-PIPE-PAGES-R023.10 | PIPE-PAGES-R023.10 | Run `tests/hooks/test_external_grade_rules.py::test_external_grade_rules_refusal`. Tampered packs and unsupported prose-only rules refuse; applicable hard failures retain exit 1. |
| T-PIPE-PAGES-R023.11 | PIPE-PAGES-R023.11 | Run `tests/hooks/test_external_grade_rules.py::test_external_grade_rules_evidence`. Round-trip per-finding rule lineage and prove unchanged baseline grading when packs are diagnostic only. |
| T-PIPE-PAGES-R023.12 | PIPE-PAGES-R023.12 | Run `tests/hooks/test_external_grade_rules.py::test_external_grade_rules_cli`. Assert installed CLI/hook integration, exact external rule evidence and stable serialized grading. |
| T-PIPE-PAGES-R020.37 | PIPE-PAGES-R020.37 | Run `tests/hooks/test_tool_mapping.py::test_tool_mapping_model`. Reject duplicate identities, missing schema fields and unbound examples. |
| T-PIPE-PAGES-R020.38 | PIPE-PAGES-R020.38 | Run `tests/hooks/test_tool_mapping.py::test_tool_mapping_behavior`. Independently remove a tool, nested method, parameter, result or example and fail. |
| T-PIPE-PAGES-R020.39 | PIPE-PAGES-R020.39 | Run `tests/hooks/test_tool_mapping.py::test_tool_mapping_wiring`. The configured docs CLI/hook consumes the real exported registry and generated mapping. |
| T-PIPE-PAGES-R020.40 | PIPE-PAGES-R020.40 | Run `tests/hooks/test_tool_mapping.py::test_tool_mapping_refusal`. Unknown schema and stale registry refuse; an omitted tool is a located failure. |
| T-PIPE-PAGES-R020.41 | PIPE-PAGES-R020.41 | Run `tests/hooks/test_tool_mapping.py::test_tool_mapping_evidence`. Locate absent nested rows and preserve the distinction between schema and runtime evidence. |
| T-PIPE-PAGES-R020.42 | PIPE-PAGES-R020.42 | Run `tests/hooks/test_tool_mapping.py::test_tool_mapping_cli`. Assert real producer-to-renderer-to-hook integration and stale-export exit 2. |
| T-PIPE-PAGES-R020.43 | PIPE-PAGES-R020.43 | Run `tests/hooks/test_guide_migration.py::test_guide_migration_model`. Reject duplicate IDs, uncovered source ranges and destinations outside canonical content roots. |
| T-PIPE-PAGES-R020.44 | PIPE-PAGES-R020.44 | Run `tests/hooks/test_guide_migration.py::test_guide_migration_behavior`. Omitting or changing an assertion without matching evidence fails; unsupported claim kinds remain unresolved. |
| T-PIPE-PAGES-R020.45 | PIPE-PAGES-R020.45 | Run `tests/hooks/test_guide_migration.py::test_guide_migration_wiring`. The real CLI materializes the declared split and the hook checks its served navigation and claim evidence. |
| T-PIPE-PAGES-R020.46 | PIPE-PAGES-R020.46 | Run `tests/hooks/test_guide_migration.py::test_guide_migration_refusal`. Unresolved assertions and unrenderable diagrams cannot produce complete migration evidence. |
| T-PIPE-PAGES-R020.47 | PIPE-PAGES-R020.47 | Run `tests/hooks/test_guide_migration.py::test_guide_migration_evidence`. A coverage total equals the original inventory and each moved claim retains its evidence kind. |
| T-PIPE-PAGES-R020.48 | PIPE-PAGES-R020.48 | Run `tests/hooks/test_guide_migration.py::test_guide_migration_cli`. Assert actual CLI/hook, renderer and served-link behavior without helper-only completion. |
| T-PIPE-PAGES-R020.49 | PIPE-PAGES-R020.49 | Run `tests/hooks/test_deployment_docs.py::test_deployment_docs_model`. Require all four records and parse configuration/command shapes without fabricated capabilities. |
| T-PIPE-PAGES-R020.50 | PIPE-PAGES-R020.50 | Run `tests/hooks/test_deployment_docs.py::test_deployment_docs_behavior`. Missing configuration, command or mismatched transport fails independently in every pattern. |
| T-PIPE-PAGES-R020.51 | PIPE-PAGES-R020.51 | Run `tests/hooks/test_deployment_docs.py::test_deployment_docs_wiring`. Configured pre-commit and docs CLI validate the same owner export, JSON and argv matrix. |
| T-PIPE-PAGES-R020.52 | PIPE-PAGES-R020.52 | Run `tests/hooks/test_deployment_docs.py::test_deployment_docs_refusal`. Unsupported patterns are explicit constraints, never false pass coverage or invented commands. |
| T-PIPE-PAGES-R020.53 | PIPE-PAGES-R020.53 | Run `tests/hooks/test_deployment_docs.py::test_deployment_docs_evidence`. Export all four patterns and distinguish docs parity from a runtime deployment receipt. |
| T-PIPE-PAGES-R020.54 | PIPE-PAGES-R020.54 | Run `tests/hooks/test_deployment_docs.py::test_deployment_docs_cli`. Assert four-pattern CLI/hook parity and independent owner runtime receipts; documentation alone cannot certify deployment. |
| T-PIPE-PAGES-R020.55 | PIPE-PAGES-R020.55 | Run `tests/hooks/test_doc_inventory.py::test_doc_inventory_model`. Require every documentation role for every project and reject duplicate canonical authorities. |
| T-PIPE-PAGES-R020.56 | PIPE-PAGES-R020.56 | Run `tests/hooks/test_doc_inventory.py::test_doc_inventory_behavior`. Missing roles, malformed config, stale managed sections and orphan navigation fail independently. |
| T-PIPE-PAGES-R020.57 | PIPE-PAGES-R020.57 | Run `tests/hooks/test_doc_inventory.py::test_doc_inventory_wiring`. The existing proposed config-inventory entry consumes both configuration and documentation roles once. |
| T-PIPE-PAGES-R020.58 | PIPE-PAGES-R020.58 | Run `tests/hooks/test_doc_inventory.py::test_doc_inventory_refusal`. Retired-path fallback and an undiscovered declared project cannot pass. |
| T-PIPE-PAGES-R020.59 | PIPE-PAGES-R020.59 | Run `tests/hooks/test_doc_inventory.py::test_doc_inventory_evidence`. Prove every role and project is checked and preserve user-owned prose during rendering. |
| T-PIPE-PAGES-R020.60 | PIPE-PAGES-R020.60 | Run `tests/hooks/test_doc_inventory.py::test_doc_inventory_cli`. Assert deterministic generation, real served navigation and whole-inventory drift failures. |
| T-PIPE-PAGES-R020.61 | PIPE-PAGES-R020.61 | Run `tests/hooks/test_readme_header.py::test_readme_header_model`. Reject missing/duplicate consumer header fields; only the exact provider identity selects non-applicable scope. |
| T-PIPE-PAGES-R020.62 | PIPE-PAGES-R020.62 | Run `tests/hooks/test_readme_header.py::test_readme_header_behavior`. Missing interface/status links, hidden badges, stale owner counts and reused wrong-project marks fail. |
| T-PIPE-PAGES-R020.63 | PIPE-PAGES-R020.63 | Run `tests/hooks/test_readme_header.py::test_readme_header_wiring`. The installed provider self-run yields declared non-applicable exit 0; known consumers still execute the shared renderer/checker. |
| T-PIPE-PAGES-R020.64 | PIPE-PAGES-R020.64 | Run `tests/hooks/test_readme_header.py::test_readme_header_refusal`. Unknown consumer, same basename under another namespace and unresolved identity exit 2; unavailable telemetry cannot become a measured success. |
| T-PIPE-PAGES-R020.65 | PIPE-PAGES-R020.65 | Run `tests/hooks/test_readme_header.py::test_readme_header_evidence`. Bind seven-owner coverage to its registry; provider skip evidence cannot count as a passed consumer or completed header check. |
| T-PIPE-PAGES-R020.66 | PIPE-PAGES-R020.66 | Run `tests/hooks/test_readme_header.py::test_readme_header_cli`. Assert real renderer/browser coverage plus provider CLI/self-run exit 0, unknown identity exit 2 and no consumer bypass through a provider flag. |
| T-PIPE-PAGES-R020.67 | PIPE-PAGES-R020.67 | Run `tests/hooks/test_image_theme.py::test_image_theme_model`. Reject omitted images, missing theme modes and ambiguous diagram edge identities. |
| T-PIPE-PAGES-R020.68 | PIPE-PAGES-R020.68 | Run `tests/hooks/test_image_theme.py::test_image_theme_behavior`. Missing dark variant, invisible labels, wrong diagram arrow endpoints and unaccounted images fail. |
| T-PIPE-PAGES-R020.69 | PIPE-PAGES-R020.69 | Run `tests/hooks/test_image_theme.py::test_image_theme_wiring`. The production docs check evaluates the actual served artifact under both browser media settings. |
| T-PIPE-PAGES-R020.70 | PIPE-PAGES-R020.70 | Run `tests/hooks/test_image_theme.py::test_image_theme_refusal`. An image lacking trustworthy theme evidence cannot silently pass or disappear from inventory. |
| T-PIPE-PAGES-R020.71 | PIPE-PAGES-R020.71 | Run `tests/hooks/test_image_theme.py::test_image_theme_evidence`. Every image has two bound render results with exact failure locations and reasons. |
| T-PIPE-PAGES-R020.72 | PIPE-PAGES-R020.72 | Run `tests/hooks/test_image_theme.py::test_image_theme_cli`. Assert real served dual-media coverage for every image, failed adversarial probes and stale-receipt exit 2. |
| T-PIPE-PAGES-R020.73 | PIPE-PAGES-R020.73 | Run `tests/hooks/test_spec_artifacts.py::test_spec_artifacts_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.74 | PIPE-PAGES-R020.74 | Run `tests/hooks/test_spec_artifacts.py::test_spec_artifacts_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.75 | PIPE-PAGES-R020.75 | Run `tests/hooks/test_spec_artifacts.py::test_spec_artifacts_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.76 | PIPE-PAGES-R020.76 | Run `tests/hooks/test_spec_artifacts.py::test_spec_artifacts_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.77 | PIPE-PAGES-R020.77 | Run `tests/hooks/test_spec_artifacts.py::test_spec_artifacts_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.78 | PIPE-PAGES-R020.78 | Run `tests/hooks/test_spec_artifacts.py::test_spec_artifacts_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.8 | PIPE-PAGES-R012.8 | Run `tests/hooks/test_spec_bundle_compatibility.py::test_spec_bundle_compatibility_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.9 | PIPE-PAGES-R012.9 | Run `tests/hooks/test_spec_bundle_compatibility.py::test_spec_bundle_compatibility_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.10 | PIPE-PAGES-R012.10 | Run `tests/hooks/test_spec_bundle_compatibility.py::test_spec_bundle_compatibility_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.11 | PIPE-PAGES-R012.11 | Run `tests/hooks/test_spec_bundle_compatibility.py::test_spec_bundle_compatibility_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.12 | PIPE-PAGES-R012.12 | Run `tests/hooks/test_spec_bundle_compatibility.py::test_spec_bundle_compatibility_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.13 | PIPE-PAGES-R012.13 | Run `tests/hooks/test_spec_bundle_compatibility.py::test_spec_bundle_compatibility_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.31 | PIPE-PAGES-R021.31 | Run `tests/hooks/test_skill_dependency_audit.py::test_skill_dependency_audit_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.32 | PIPE-PAGES-R021.32 | Run `tests/hooks/test_skill_dependency_audit.py::test_skill_dependency_audit_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.33 | PIPE-PAGES-R021.33 | Run `tests/hooks/test_skill_dependency_audit.py::test_skill_dependency_audit_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.34 | PIPE-PAGES-R021.34 | Run `tests/hooks/test_skill_dependency_audit.py::test_skill_dependency_audit_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.35 | PIPE-PAGES-R021.35 | Run `tests/hooks/test_skill_dependency_audit.py::test_skill_dependency_audit_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.36 | PIPE-PAGES-R021.36 | Run `tests/hooks/test_skill_dependency_audit.py::test_skill_dependency_audit_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.13 | PIPE-PAGES-R023.13 | Run `tests/hooks/test_aggregate_skill_grade.py::test_aggregate_skill_grade_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.14 | PIPE-PAGES-R023.14 | Run `tests/hooks/test_aggregate_skill_grade.py::test_aggregate_skill_grade_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.15 | PIPE-PAGES-R023.15 | Run `tests/hooks/test_aggregate_skill_grade.py::test_aggregate_skill_grade_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.16 | PIPE-PAGES-R023.16 | Run `tests/hooks/test_aggregate_skill_grade.py::test_aggregate_skill_grade_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.17 | PIPE-PAGES-R023.17 | Run `tests/hooks/test_aggregate_skill_grade.py::test_aggregate_skill_grade_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R023.18 | PIPE-PAGES-R023.18 | Run `tests/hooks/test_aggregate_skill_grade.py::test_aggregate_skill_grade_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.14 | PIPE-PAGES-R012.14 | Run `tests/hooks/test_capability_inventory.py::test_capability_inventory_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.15 | PIPE-PAGES-R012.15 | Run `tests/hooks/test_capability_inventory.py::test_capability_inventory_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.16 | PIPE-PAGES-R012.16 | Run `tests/hooks/test_capability_inventory.py::test_capability_inventory_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.17 | PIPE-PAGES-R012.17 | Run `tests/hooks/test_capability_inventory.py::test_capability_inventory_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.18 | PIPE-PAGES-R012.18 | Run `tests/hooks/test_capability_inventory.py::test_capability_inventory_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R012.19 | PIPE-PAGES-R012.19 | Run `tests/hooks/test_capability_inventory.py::test_capability_inventory_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.37 | PIPE-PAGES-R021.37 | Run `tests/hooks/test_structural_limits.py::test_structural_limits_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.38 | PIPE-PAGES-R021.38 | Run `tests/hooks/test_structural_limits.py::test_structural_limits_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.39 | PIPE-PAGES-R021.39 | Run `tests/hooks/test_structural_limits.py::test_structural_limits_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.40 | PIPE-PAGES-R021.40 | Run `tests/hooks/test_structural_limits.py::test_structural_limits_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.41 | PIPE-PAGES-R021.41 | Run `tests/hooks/test_structural_limits.py::test_structural_limits_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.42 | PIPE-PAGES-R021.42 | Run `tests/hooks/test_structural_limits.py::test_structural_limits_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.49 | PIPE-PAGES-R021.49 | Run `tests/hooks/test_coverage_closure.py::test_coverage_closure_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.50 | PIPE-PAGES-R021.50 | Run `tests/hooks/test_coverage_closure.py::test_coverage_closure_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.51 | PIPE-PAGES-R021.51 | Run `tests/hooks/test_coverage_closure.py::test_coverage_closure_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.52 | PIPE-PAGES-R021.52 | Run `tests/hooks/test_coverage_closure.py::test_coverage_closure_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.53 | PIPE-PAGES-R021.53 | Run `tests/hooks/test_coverage_closure.py::test_coverage_closure_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.54 | PIPE-PAGES-R021.54 | Run `tests/hooks/test_coverage_closure.py::test_coverage_closure_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.79 | PIPE-PAGES-R020.79 | Run `tests/hooks/test_validation_behavior_inventory.py::test_validation_behavior_inventory_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.80 | PIPE-PAGES-R020.80 | Run `tests/hooks/test_validation_behavior_inventory.py::test_validation_behavior_inventory_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.81 | PIPE-PAGES-R020.81 | Run `tests/hooks/test_validation_behavior_inventory.py::test_validation_behavior_inventory_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.82 | PIPE-PAGES-R020.82 | Run `tests/hooks/test_validation_behavior_inventory.py::test_validation_behavior_inventory_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.83 | PIPE-PAGES-R020.83 | Run `tests/hooks/test_validation_behavior_inventory.py::test_validation_behavior_inventory_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.84 | PIPE-PAGES-R020.84 | Run `tests/hooks/test_validation_behavior_inventory.py::test_validation_behavior_inventory_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.55 | PIPE-PAGES-R021.55 | Run `tests/hooks/test_offline_unit_profile.py::test_offline_unit_profile_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.56 | PIPE-PAGES-R021.56 | Run `tests/hooks/test_offline_unit_profile.py::test_offline_unit_profile_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.57 | PIPE-PAGES-R021.57 | Run `tests/hooks/test_offline_unit_profile.py::test_offline_unit_profile_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.58 | PIPE-PAGES-R021.58 | Run `tests/hooks/test_offline_unit_profile.py::test_offline_unit_profile_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.59 | PIPE-PAGES-R021.59 | Run `tests/hooks/test_offline_unit_profile.py::test_offline_unit_profile_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.60 | PIPE-PAGES-R021.60 | Run `tests/hooks/test_offline_unit_profile.py::test_offline_unit_profile_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.85 | PIPE-PAGES-R020.85 | Run `tests/hooks/test_ontology_governance_hook.py::test_ontology_governance_hook_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.86 | PIPE-PAGES-R020.86 | Run `tests/hooks/test_ontology_governance_hook.py::test_ontology_governance_hook_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.87 | PIPE-PAGES-R020.87 | Run `tests/hooks/test_ontology_governance_hook.py::test_ontology_governance_hook_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.88 | PIPE-PAGES-R020.88 | Run `tests/hooks/test_ontology_governance_hook.py::test_ontology_governance_hook_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.89 | PIPE-PAGES-R020.89 | Run `tests/hooks/test_ontology_governance_hook.py::test_ontology_governance_hook_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R020.90 | PIPE-PAGES-R020.90 | Run `tests/hooks/test_ontology_governance_hook.py::test_ontology_governance_hook_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.67 | PIPE-PAGES-R021.67 | Run `tests/hooks/test_solution_size_evidence.py::test_solution_size_evidence_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.68 | PIPE-PAGES-R021.68 | Run `tests/hooks/test_solution_size_evidence.py::test_solution_size_evidence_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.69 | PIPE-PAGES-R021.69 | Run `tests/hooks/test_solution_size_evidence.py::test_solution_size_evidence_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.70 | PIPE-PAGES-R021.70 | Run `tests/hooks/test_solution_size_evidence.py::test_solution_size_evidence_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.71 | PIPE-PAGES-R021.71 | Run `tests/hooks/test_solution_size_evidence.py::test_solution_size_evidence_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.72 | PIPE-PAGES-R021.72 | Run `tests/hooks/test_solution_size_evidence.py::test_solution_size_evidence_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.73 | PIPE-PAGES-R021.73 | Run `tests/hooks/test_graph_workflow_receipt.py::test_graph_workflow_receipt_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.74 | PIPE-PAGES-R021.74 | Run `tests/hooks/test_graph_workflow_receipt.py::test_graph_workflow_receipt_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.75 | PIPE-PAGES-R021.75 | Run `tests/hooks/test_graph_workflow_receipt.py::test_graph_workflow_receipt_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.76 | PIPE-PAGES-R021.76 | Run `tests/hooks/test_graph_workflow_receipt.py::test_graph_workflow_receipt_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.77 | PIPE-PAGES-R021.77 | Run `tests/hooks/test_graph_workflow_receipt.py::test_graph_workflow_receipt_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R021.78 | PIPE-PAGES-R021.78 | Run `tests/hooks/test_graph_workflow_receipt.py::test_graph_workflow_receipt_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-PAGES-R042 | PIPE-PAGES-R042 | `tests/test_architecture_explorer.py` places fixture rows, proves a deleted row disappears, reconciles discovery, fits the connector fleet, checks the stamp and builds the page and redirect variants offline; `tests/test_architecture_canonical.py` proves a family renamed through a spec alias still maps, an exact row alias never renames a spec directory, a refused build names its snapshot errors and its unmapped `repo:FAMILY` groups with the fix, and `model.json` uses no prefix retired in any repository's alias map; `tests/test_pages_pipeline_contract.py` and `tests/test_spec_delivery_nav.py` check the workflow step, the dispatch and the theme link; `tests/test_sync_mkdocs_theme.py::test_check_requires_the_diagram_to_link_the_explorer` checks the diagram link. |
| T-PIPE-PAGES-R042.1 | PIPE-PAGES-R042.1 | `tests/test_architecture_explorer.py::test_search_index_covers_every_row_and_maps_it_to_a_node` and `tests/test_architecture_explorer.py::test_search_index_carries_repository_aliases`. |
| T-PIPE-PAGES-R042.2 | PIPE-PAGES-R042.2 | `tests/test_architecture_explorer.py::test_a_capability_search_ranks_the_owning_row_first` and `tests/test_architecture_explorer.py::test_an_id_search_is_exact`. |
| T-PIPE-PAGES-R042.3 | PIPE-PAGES-R042.3 | `tests/test_architecture_explorer.py::test_deep_links_parse`. |
| T-PIPE-PAGES-R042.4 | PIPE-PAGES-R042.4 | `tests/test_architecture_explorer.py::test_a_q_deep_link_lands_on_the_owning_part_in_a_browser` loads the page in a headless Chromium when one is installed. |
| T-PIPE-PAGES-R042.5 | PIPE-PAGES-R042.5 | `tests/test_architecture_explorer.py::test_the_map_fills_the_viewport_with_full_screen_and_panel_toggle`. |
| T-PIPE-PAGES-R042.6 | PIPE-PAGES-R042.6 | `tests/test_architecture_explorer.py::test_description_is_the_first_plain_sentence_capped_at_160`, `tests/test_architecture_explorer.py::test_page_rows_carry_desc_and_never_the_full_text`, `tests/test_architecture_explorer.py::test_page_size_grows_by_a_bounded_amount_per_row` and `tests/test_architecture_explorer.py::test_search_matches_a_description_only_after_title_and_id_matches`. |
| T-PIPE-PAGES-R042.7 | PIPE-PAGES-R042.7 | `tests/test_architecture_explorer.py::test_one_family_json_is_written_per_family_with_full_row_detail`, `tests/test_architecture_explorer.py::test_a_row_whose_family_has_no_plan_still_gets_detail` and `tests/test_architecture_explorer.py::test_expanding_a_row_fetches_its_family_once_and_renders_it_safely`. |
| T-PIPE-PAGES-R042.8 | PIPE-PAGES-R042.8 | `tests/test_architecture_explorer.py::test_markdown_escapes_raw_html_and_drops_unsafe_links` and `tests/test_architecture_explorer.py::test_page_never_assigns_markup_and_exposes_the_expand_controls`. |
| T-PIPE-PAGES-R042.9 | PIPE-PAGES-R042.9 | `tests/test_architecture_explorer.py::test_every_registered_repository_has_a_part_and_its_rows_place_without_the_allowlist`. |
| T-PIPE-PAGES-R042.10 | PIPE-PAGES-R042.10 | `tests/test_architecture_explorer.py::test_header_carries_the_agent_strip_and_the_page_has_no_footer`. |
| T-PIPE-PAGES-R042.11 | PIPE-PAGES-R042.11 | `tests/test_architecture_explorer.py::test_contribution_path_is_in_the_header_head_and_llms_txt` and `tests/test_architecture_explorer.py::test_a_build_writes_llms_txt_beside_the_page`. |

## Agent-readiness and static delivery

| ID | Requirement | Test and expected result |
|---|---|---|
| T-PIPE-PAGES-R043.1 | PIPE-PAGES-R043.1 | Run `tests/test_pages_readiness.py::test_second_build_and_offline_tck_are_idempotent`. |
| T-PIPE-PAGES-R043.2 | PIPE-PAGES-R043.2 | Run `tests/test_pages_readiness.py::test_build_publishes_source_markdown_and_served_mime`. |
| T-PIPE-PAGES-R043.3 | PIPE-PAGES-R043.3 | Run `tests/test_pages_pipeline_contract.py::test_enabled_path_checks_strict_build_and_runs_owned_tck`. |
| T-PIPE-PAGES-R043.4 | PIPE-PAGES-R043.4 | Run `tests/test_pages_readiness.py::test_stale_source_digest_fails_closed`. |
| T-PIPE-PAGES-R043.5 | PIPE-PAGES-R043.5 | Run `tests/test_pages_readiness.py::test_cli_failure_result_is_versioned`. |
| T-PIPE-PAGES-R043.6 | PIPE-PAGES-R043.6 | Run `tests/test_pages_readiness.py::test_direct_entry_requires_and_loads_the_sparse_readiness_package`. |

## Entries added for rows without a prior entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-PAGES-R051.1 | PIPE-PAGES-R051.1 | `tests/test_architecture_explorer.py::test_family_files_carry_every_spec_document_with_an_outline` and `tests/test_architecture_explorer.py::test_the_page_stays_within_ten_percent_and_inlines_no_document`. |
| T-PIPE-PAGES-R051.2 | PIPE-PAGES-R051.2 | `tests/test_architecture_explorer.py::test_a_repository_constitution_is_written_versioned_and_linked`. |
| T-PIPE-PAGES-R051.3 | PIPE-PAGES-R051.3 | `tests/test_architecture_explorer.py::test_delivery_cards_carry_title_phase_task_progress_and_document_bits` and `tests/test_architecture_explorer.py::test_the_node_panel_renders_own_cards_and_links_each_document`. |
| T-PIPE-PAGES-R051.4 | PIPE-PAGES-R051.4 | `tests/test_architecture_explorer.py::test_the_node_panel_renders_own_cards_and_links_each_document`. |
| T-PIPE-PAGES-R051.5 | PIPE-PAGES-R051.5 | `tests/test_architecture_explorer.py::test_doc_deep_links_parse_and_round_trip`, `tests/test_architecture_explorer.py::test_outline_anchors_every_plan_heading` and `tests/test_architecture_explorer.py::test_the_reader_opens_a_plan_section_and_links_row_ids_in_a_browser`. |
| T-PIPE-PAGES-R051.6 | PIPE-PAGES-R051.6 | `tests/test_architecture_explorer.py::test_the_program_view_has_a_toggle_and_five_phase_columns`. |
| T-PIPE-PAGES-R051.7 | PIPE-PAGES-R051.7 | `tests/test_architecture_explorer.py::test_a_failing_principle_in_the_constitution_check_warns`. |
| T-PIPE-PAGES-R051.8 | PIPE-PAGES-R051.8 | `tests/test_architecture_explorer.py::test_search_extras_hold_task_lines_and_plan_headings_and_rank_last`. |
| T-PIPE-PAGES-R051.9 | PIPE-PAGES-R051.9 | `tests/test_architecture_explorer.py::test_the_page_stays_within_ten_percent_and_inlines_no_document` and `tests/test_architecture_explorer.py::test_new_panels_use_glass_levels_and_respect_reduced_motion`. |
| T-PIPE-PAGES-R052 | PIPE-PAGES-R052 | `tests/test_architecture_explorer.py::test_canopy_is_a_part_inside_pipelines_and_owns_its_rows`. |

## Entries added for rows without a prior entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-PAGES-R001 | PIPE-PAGES-R001 | Run `tests/test_spec_delivery_nav.py::test_site_urls_match_repos`. A parity check confirms the switcher's repository list matches the declared core-repository set and release receipt, and a source scan confirms the obsolete standalone deployment generator no longer exists. |
| T-PIPE-PAGES-R002 | PIPE-PAGES-R002 | Run `tests/test_skill_graph_registry_comparison.py::test_all_public_skill_graph_tiers_project_one_corpus`. A navigation-depth and link-structure audit confirms each tier, introduction, component, and reference, exists and links progressively into the next. |
| T-PIPE-PAGES-R003 | PIPE-PAGES-R003 | Run `tests/test_sync_mkdocs_theme.py::test_theme_components_use_accessible_native_controls`. Strict documentation build, theme, accessibility, and content-diff checks confirm the README order, embedded start, shared visuals, and present-tense wording. |
| T-PIPE-PAGES-R007 | PIPE-PAGES-R007 | Run `tests/test_sync_mkdocs_theme.py::test_all_seven_product_logo_assets_remain_canonical`. Focused theme rendering tests plus a changed-file documentation build confirm the diagram's flow, project titles, and logo marks render correctly. |
| T-PIPE-PAGES-R008 | PIPE-PAGES-R008 | Run `tests/test_pages_fleet_parity.py::test_six_exact_refs_stable_receipts_and_no_mutation`. A multi-page render, link, and accessibility audit plus a changed-file build check confirm ownership statements, the quick start, and accessible navigation on the consumer site. |
| T-PIPE-PAGES-R011 | PIPE-PAGES-R011 | Run `tests/test_sync_mkdocs_theme.py::test_shared_ecosystem_links_use_canonical_repository_urls`. Strict MkDocs render, accessibility, theme, and privacy gates, together with the documentation build run, confirm the home page's content and that it passes without regressions. |
| T-PIPE-PAGES-R025.3 | PIPE-PAGES-R025.3 | Run `tests/hooks/test_packaging_roles.py::test_packaging_role_closure_cli`. |
| T-PIPE-PAGES-R032.1 | PIPE-PAGES-R032.1 | Run export-import model test. |
| T-PIPE-PAGES-R032.2 | PIPE-PAGES-R032.2 | Run round-trip behavior test. |
| T-PIPE-PAGES-R032.3 | PIPE-PAGES-R032.3 | Run export wiring test. |
| T-PIPE-PAGES-R032.4 | PIPE-PAGES-R032.4 | Run version refusal test. |
| T-PIPE-PAGES-R032.5 | PIPE-PAGES-R032.5 | Run version comparison evidence test. |
| T-PIPE-PAGES-R032.6 | PIPE-PAGES-R032.6 | Run `test_eg56_export_import_cli`. |
| T-PIPE-PAGES-R040.1 | PIPE-PAGES-R040.1 | Proposal must carry coverage baseline and candidate measurements. |
| T-PIPE-PAGES-R040.2 | PIPE-PAGES-R040.2 | Gate compares candidate metrics against baseline deterministically. |
| T-PIPE-PAGES-R040.3 | PIPE-PAGES-R040.3 | Baseline and candidate evidence bind to revision. |
| T-PIPE-PAGES-R040.4 | PIPE-PAGES-R040.4 | Unmeasured coverage proposals fail rather than pass. |
| T-PIPE-PAGES-R040.5 | PIPE-PAGES-R040.5 | Evidence preserves graph authorization and materialization receipt. |
| T-PIPE-PAGES-R040.6 | PIPE-PAGES-R040.6 | Test planted coverage decrease in candidate revision. |
| T-PIPE-PAGES-R044 | PIPE-PAGES-R044 | Test: `tests/test_architecture_explorer.py::test_verified_and_delivered_counts_are_separate`. |
| T-PIPE-PAGES-R046 | PIPE-PAGES-R046 | Test: `tests/test_architecture_explorer.py::test_section_panel_counts_own_rows_and_shares_fade`. |
| T-PIPE-PAGES-R047 | PIPE-PAGES-R047 | Test: `tests/test_architecture_explorer.py::test_edges_carry_type_rows_and_legend`. |
| T-PIPE-PAGES-R048 | PIPE-PAGES-R048 | `tests/test_architecture_explorer.py::test_code_view_reclusters_only_changed_items_and_links_rows`. |
| T-PIPE-PAGES-R053 | PIPE-PAGES-R053 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R053.1 | PIPE-PAGES-R053.1 | Run `tests/test_canopy_drawer.py::test_row_drawer_model_has_excerpts_tasks_checklist_and_unblocks`. |
| T-PIPE-PAGES-R053.2 | PIPE-PAGES-R053.2 | Run `tests/test_canopy_drawer.py::test_excerpts_hold_only_paragraphs_that_name_the_row`. |
| T-PIPE-PAGES-R053.3 | PIPE-PAGES-R053.3 | Run `tests/test_canopy_drawer.py::test_a_row_click_opens_the_drawer_and_sets_the_row_hash`. |
| T-PIPE-PAGES-R053.4 | PIPE-PAGES-R053.4 | Run `tests/test_canopy_drawer.py::test_missing_row_and_failed_family_load_are_reported_in_the_drawer`. |
| T-PIPE-PAGES-R053.5 | PIPE-PAGES-R053.5 | Run `tests/test_canopy_drawer.py::test_drawer_lists_exact_paths_and_evidence_links`. |
| T-PIPE-PAGES-R053.6 | PIPE-PAGES-R053.6 | Run `tests/test_canopy_drawer.py::test_the_drawer_opens_in_a_browser_with_tasks_and_unblocks`. |
| T-PIPE-PAGES-R054 | PIPE-PAGES-R054 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R054.1 | PIPE-PAGES-R054.1 | Run `tests/test_canopy_modes.py::test_sdd_phase_enum_orders_six_phases`. |
| T-PIPE-PAGES-R054.2 | PIPE-PAGES-R054.2 | Run `tests/test_canopy_modes.py::test_each_phase_predicate_holds_only_on_its_artifacts`. |
| T-PIPE-PAGES-R054.3 | PIPE-PAGES-R054.3 | Run `tests/test_canopy_modes.py::test_mode_switch_changes_node_style_without_moving_nodes`. |
| T-PIPE-PAGES-R054.4 | PIPE-PAGES-R054.4 | Run `tests/test_canopy_modes.py::test_empty_nodes_stay_neutral_and_unknown_mode_falls_back`. |
| T-PIPE-PAGES-R054.5 | PIPE-PAGES-R054.5 | Run `tests/test_canopy_modes.py::test_dependency_edges_match_the_next_up_prerequisites`. |
| T-PIPE-PAGES-R054.6 | PIPE-PAGES-R054.6 | Run `tests/test_canopy_modes.py::test_sdd_mode_legend_counts_match_the_computed_phases_in_a_browser`. |
| T-PIPE-PAGES-R055 | PIPE-PAGES-R055 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R055.1 | PIPE-PAGES-R055.1 | Run `tests/test_canopy_filters.py::test_next_step_maps_phase_and_state_to_one_chip`. |
| T-PIPE-PAGES-R055.2 | PIPE-PAGES-R055.2 | Run `tests/test_canopy_filters.py::test_chip_rules_follow_the_documented_order`. |
| T-PIPE-PAGES-R055.3 | PIPE-PAGES-R055.3 | Run `tests/test_canopy_filters.py::test_chips_combine_with_status_and_release_filters`. |
| T-PIPE-PAGES-R055.4 | PIPE-PAGES-R055.4 | Run `tests/test_canopy_filters.py::test_empty_chips_are_disabled_and_unknown_names_are_ignored`. |
| T-PIPE-PAGES-R055.5 | PIPE-PAGES-R055.5 | Run `tests/test_canopy_filters.py::test_chip_counts_and_export_next_step_agree`. |
| T-PIPE-PAGES-R055.6 | PIPE-PAGES-R055.6 | Run `tests/test_canopy_filters.py::test_the_ready_filter_lists_only_next_up_rows_in_a_browser`. |
| T-PIPE-PAGES-R056 | PIPE-PAGES-R056 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R056.1 | PIPE-PAGES-R056.1 | Run `tests/test_canopy_releases.py::test_phase_line_in_plan_wins_over_release_phase_and_part_progress_counts`. |
| T-PIPE-PAGES-R056.2 | PIPE-PAGES-R056.2 | Run `tests/test_canopy_releases.py::test_selecting_a_release_dims_other_nodes_and_shows_part_progress`. |
| T-PIPE-PAGES-R056.3 | PIPE-PAGES-R056.3 | Run `tests/test_canopy_releases.py::test_github_mode_refuses_a_missing_releases_directory`. |
| T-PIPE-PAGES-R056.4 | PIPE-PAGES-R056.4 | Run `tests/test_canopy_releases.py::test_empty_state_explains_manifests_and_bad_phase_fails_the_build`. |
| T-PIPE-PAGES-R056.5 | PIPE-PAGES-R056.5 | Run `tests/test_canopy_releases.py::test_release_card_links_manifest_and_unscheduled_count_matches_rows`. |
| T-PIPE-PAGES-R056.6 | PIPE-PAGES-R056.6 | Run `tests/test_canopy_releases.py::test_release_hash_filters_the_map_in_a_browser`. |
| T-PIPE-PAGES-R057 | PIPE-PAGES-R057 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R057.1 | PIPE-PAGES-R057.1 | Run `tests/test_canopy_export.py::test_export_row_carries_every_present_artifact_path`. |
| T-PIPE-PAGES-R057.2 | PIPE-PAGES-R057.2 | Run `tests/test_canopy_export.py::test_hash_round_trips_row_part_mode_filter_release`. |
| T-PIPE-PAGES-R057.3 | PIPE-PAGES-R057.3 | Run `tests/test_canopy_export.py::test_a_build_writes_rows_json_and_markdown_beside_the_page`. |
| T-PIPE-PAGES-R057.4 | PIPE-PAGES-R057.4 | Run `tests/test_canopy_export.py::test_unknown_view_values_are_refused_and_unsafe_paths_fail_the_build`. |
| T-PIPE-PAGES-R057.5 | PIPE-PAGES-R057.5 | Run `tests/test_canopy_export.py::test_export_header_digest_is_stable_and_markdown_lists_paths`. |
| T-PIPE-PAGES-R057.6 | PIPE-PAGES-R057.6 | Run `tests/test_canopy_export.py::test_a_hash_restores_the_view_and_the_export_paths_exist`. |
| T-PIPE-PAGES-R057.7 | PIPE-PAGES-R057.7 | Run `tests/test_canopy_export.py::test_page_without_scripts_lists_parts_and_links_exports`. |
| T-PIPE-PAGES-R058 | PIPE-PAGES-R058 | The rollup is the minimum state of its children. |
| T-PIPE-PAGES-R058.1 | PIPE-PAGES-R058.1 | Run `tests/test_canopy_research.py::test_open_questions_find_markers_and_unchecked_research_items`. |
| T-PIPE-PAGES-R058.2 | PIPE-PAGES-R058.2 | Run `tests/test_canopy_research.py::test_counts_follow_the_own_rows_rule_and_zero_shows_no_badge`. |
| T-PIPE-PAGES-R058.3 | PIPE-PAGES-R058.3 | Run `tests/test_canopy_research.py::test_badges_render_on_node_card_and_row_with_screen_reader_text`. |
| T-PIPE-PAGES-R058.4 | PIPE-PAGES-R058.4 | Run `tests/test_canopy_research.py::test_unreadable_research_marks_the_family_without_failing_the_build`. |
| T-PIPE-PAGES-R058.5 | PIPE-PAGES-R058.5 | Run `tests/test_canopy_research.py::test_drawer_and_export_list_the_questions_with_document_and_line`. |
| T-PIPE-PAGES-R058.6 | PIPE-PAGES-R058.6 | Run `tests/test_canopy_research.py::test_research_badge_and_drawer_list_in_a_browser`. |
