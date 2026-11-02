# Test contract — PIPE-RELEASE

Use public synthetic candidate manifests and CI/registry responses. Unit and workflow tests require no cluster or secrets; a real release supplies separate exact-run evidence.

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-001 | Valid A → B → C manifest validates source/digest fields. |
| N-1 | FR-001 | Duplicate, missing dependency, self edge, or cycle fails before publication. |
| N-2 | FR-001 | Floating tag, malformed digest, or provenance mismatch fails closed. |
| P-2 | FR-002 | Required exact-commit checks pass and mark only that candidate eligible. |
| N-3 | FR-002 | Missing, skipped, failed, or wrong-commit check blocks candidate and descendants. |
| P-3 | FR-003 | Stable order publishes A then B then C and records hosted CI. |
| N-4 | FR-003 | Failed predecessor CI prevents next push and retains partial receipt. |
| N-5 | FR-003 | Same-digest retry is idempotent; changed commit/digest cannot resume old receipt. |
| P-4 | FR-004 | Digest-pinned manifest exactly matches qualified mapping. |
| N-6 | FR-004 | Wrong or floating workload reference names workload and blocks readiness. |
| P-5 | FR-005 | Dry-run, parser, ordering, and negative tests run without infrastructure secrets. |

Contract tests inspect immutable workflow/action pins, source binding, least-privilege permissions, exact CI polling, and digest handoff. Real acceptance also records registry digest, hosted run IDs, reviewed consumer manifest commit, and deployment-owner runtime evidence. Run YAML, pytest, CCCC, jscpd, Dupehound, and KISS on implementation. Mocked tests never imply a green release.

## Kernel wheel completeness and dependency loops

`tests/test_wheel_kernel_completeness.py::test_release_bundle_blocks_missing_kernel_wheel` must fail the bundle when a platform wheel is absent. `tests/hooks/test_dependency_cycles.py::test_supply_chain_hook_blocks_dependency_loop` must exit 1 on a group loop.

## Project version consistency

| ID | Requirement | Test and expected result |
|---|---|---|
| T-PIPE-RELEASE-R006.1 | PIPE-RELEASE-R006.1 | Run `tests/hooks/test_project_version_sync.py::test_project_version_inventory`. Accept a complete three-role inventory; reject unknown roles, duplicate locations and missing role coverage. |
| T-PIPE-RELEASE-R006.2 | PIPE-RELEASE-R006.2 | Run `tests/hooks/test_project_version_sync.py::test_project_version_values`. Equal values pass; independently changing metadata, source, documentation or canonical current version fails at the exact location. |
| T-PIPE-RELEASE-R006.3 | PIPE-RELEASE-R006.3 | Run `tests/hooks/test_project_version_sync.py::test_project_version_hook_wiring`. The installed CLI and published hook select the same snapshot and fail on an inconsistent unchanged declared surface. |
| T-PIPE-RELEASE-R006.4 | PIPE-RELEASE-R006.4 | Run `tests/hooks/test_project_version_sync.py::test_project_version_refusals`. Missing, malformed or competing configs and ambiguous extraction exit 2; mismatches exit 1 and cannot produce a passing receipt. |
| T-PIPE-RELEASE-R006.5 | PIPE-RELEASE-R006.5 | Run `tests/hooks/test_project_version_sync.py::test_project_version_evidence`. Evidence identifies the exact checked Git bytes and all three roles; unchecked cases have no successful verdict. |
| T-PIPE-RELEASE-R006.6 | PIPE-RELEASE-R006.6 | Run `tests/hooks/test_project_version_sync.py::test_project_version_sync_cli`. Assert real dispatcher/hook exit codes, exact locations, snapshot isolation, all-surface bumping and unchanged caller files during gate checks. |
| T-PIPE-RELEASE-R005.7 | PIPE-RELEASE-R005.7 | Planned test (the file does not exist yet): Run `tests/hooks/test_role_extra_closure.py::test_role_extra_closure_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.8 | PIPE-RELEASE-R005.8 | Planned test (the file does not exist yet): Run `tests/hooks/test_role_extra_closure.py::test_role_extra_closure_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.9 | PIPE-RELEASE-R005.9 | Planned test (the file does not exist yet): Run `tests/hooks/test_role_extra_closure.py::test_role_extra_closure_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.10 | PIPE-RELEASE-R005.10 | Planned test (the file does not exist yet): Run `tests/hooks/test_role_extra_closure.py::test_role_extra_closure_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.11 | PIPE-RELEASE-R005.11 | Planned test (the file does not exist yet): Run `tests/hooks/test_role_extra_closure.py::test_role_extra_closure_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.12 | PIPE-RELEASE-R005.12 | Planned test (the file does not exist yet): Run `tests/hooks/test_role_extra_closure.py::test_role_extra_closure_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.1 | PIPE-RELEASE-R001.1 | Planned test (the file does not exist yet): Run `tests/hooks/test_release_phase_progress.py::test_release_phase_progress_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.2 | PIPE-RELEASE-R001.2 | Planned test (the file does not exist yet): Run `tests/hooks/test_release_phase_progress.py::test_release_phase_progress_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.3 | PIPE-RELEASE-R001.3 | Planned test (the file does not exist yet): Run `tests/hooks/test_release_phase_progress.py::test_release_phase_progress_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.4 | PIPE-RELEASE-R001.4 | Planned test (the file does not exist yet): Run `tests/hooks/test_release_phase_progress.py::test_release_phase_progress_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.5 | PIPE-RELEASE-R001.5 | Planned test (the file does not exist yet): Run `tests/hooks/test_release_phase_progress.py::test_release_phase_progress_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.6 | PIPE-RELEASE-R001.6 | Planned test (the file does not exist yet): Run `tests/hooks/test_release_phase_progress.py::test_release_phase_progress_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.7 | PIPE-RELEASE-R006.7 | Run `tests/hooks/test_version_inventory_completeness.py::test_version_inventory_completeness_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.8 | PIPE-RELEASE-R006.8 | Planned test (the file exists, the test does not yet): Run `tests/hooks/test_version_inventory_completeness.py::test_version_inventory_completeness_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.9 | PIPE-RELEASE-R006.9 | Planned test (the file exists, the test does not yet): Run `tests/hooks/test_version_inventory_completeness.py::test_version_inventory_completeness_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.10 | PIPE-RELEASE-R006.10 | Planned test (the file exists, the test does not yet): Run `tests/hooks/test_version_inventory_completeness.py::test_version_inventory_completeness_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.11 | PIPE-RELEASE-R006.11 | Planned test (the file exists, the test does not yet): Run `tests/hooks/test_version_inventory_completeness.py::test_version_inventory_completeness_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.12 | PIPE-RELEASE-R006.12 | Planned test (the file exists, the test does not yet): Run `tests/hooks/test_version_inventory_completeness.py::test_version_inventory_completeness_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.7 | PIPE-RELEASE-R001.7 | Planned test (the file does not exist yet): Run `tests/hooks/test_major_upgrade_pre_pin.py::test_major_upgrade_pre_pin_model`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.8 | PIPE-RELEASE-R001.8 | Planned test (the file does not exist yet): Run `tests/hooks/test_major_upgrade_pre_pin.py::test_major_upgrade_pre_pin_behavior`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.9 | PIPE-RELEASE-R001.9 | Planned test (the file does not exist yet): Run `tests/hooks/test_major_upgrade_pre_pin.py::test_major_upgrade_pre_pin_wiring`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.10 | PIPE-RELEASE-R001.10 | Planned test (the file does not exist yet): Run `tests/hooks/test_major_upgrade_pre_pin.py::test_major_upgrade_pre_pin_refusal`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.11 | PIPE-RELEASE-R001.11 | Planned test (the file does not exist yet): Run `tests/hooks/test_major_upgrade_pre_pin.py::test_major_upgrade_pre_pin_evidence`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.12 | PIPE-RELEASE-R001.12 | Planned test (the file does not exist yet): Run `tests/hooks/test_major_upgrade_pre_pin.py::test_major_upgrade_pre_pin_cli`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.1 | PIPE-RELEASE-R007.1 | Run `tests/test_gates_pipeline_contract.py::test_gates_workflow_inputs_all_default`. Assert the stated contract through its declared boundary. `test_gates_workflow_forwards_optional_uv_cache_path` checks the empty default and the setup action input. |
| T-PIPE-RELEASE-R007.2 | PIPE-RELEASE-R007.2 | Run `tests/test_gates_pipeline_contract.py::test_gates_workflow_scopes_to_the_diff_and_caps_time`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.3 | PIPE-RELEASE-R007.3 | Run `tests/test_gates_pipeline_contract.py::test_require_tag_defaults_off_and_guards_the_publish_step`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.4 | PIPE-RELEASE-R007.4 | Run `tests/test_gates_pipeline_contract.py::test_require_tag_refuses_a_branch_ref_and_names_it`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.5 | PIPE-RELEASE-R007.5 | Run `tests/hooks/test_fast_tests.py::test_fast_tests_reports_no_affected_tests`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.6 | PIPE-RELEASE-R007.6 | Run `tests/hooks/test_fast_tests.py::test_fast_tests_runs_only_the_affected_subset`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.7 | PIPE-RELEASE-R007.7 | Run `test_a_release_version_bump_forces_no_crate_sweep`, `test_a_registry_dependency_bump_still_forces_the_full_sweep` and `tests/hooks/test_pr_test_scope.py::test_a_member_manifest_change_beyond_versions_maps_to_its_crate`. |
| T-PIPE-RELEASE-R007.8 | PIPE-RELEASE-R007.8 | Run `test_change_scope_classifies_each_fixture_diff` and `tests/hooks/test_change_scope.py::test_change_scope_writes_step_outputs_and_the_spec_skip_list`. Each fixture diff maps to its classes and scope. |
| T-PIPE-RELEASE-R007.9 | PIPE-RELEASE-R007.9 | Run `tests/test_gates_pipeline_contract.py::test_gates_workflow_routes_each_change_scope_to_its_gates` and `tests/hooks/test_change_scope.py::test_change_scope_keeps_every_hook_for_code_and_full_runs`. |
| T-PIPE-RELEASE-R007.10 | PIPE-RELEASE-R007.10 | Run `tests/hooks/test_change_scope.py::test_change_scope_refuses_and_falls_back_conservatively`. Each refusal exits 2. |
| T-PIPE-RELEASE-R007.11 | PIPE-RELEASE-R007.11 | Run `tests/test_gates_pipeline_contract.py::test_docs_only_paths_is_removed_for_the_default_scope`. |
| T-PIPE-RELEASE-R007.12 | PIPE-RELEASE-R007.12 | Run `tests/test_gates_pipeline_contract.py::test_gates_workflow_names_each_not_applicable_gate`. |
| T-PIPE-RELEASE-R008 | PIPE-RELEASE-R008 | Run `tests/test_python_sdist_output.py`; observe the sdist built, proven and uploaded with the wheel, the maturin sdist job covering its package, and the documented readiness rule. |

## Release records published to the engine

| Row | Proving test |
|---|---|
| `PIPE-RELEASE-R009` | See each child. |
| `PIPE-RELEASE-R009.1` | Planned test (the file does not exist yet): `tests/test_release_record_step.py::test_workflow_has_record_step_after_publish` |
| `PIPE-RELEASE-R009.2` | Planned test (the file does not exist yet): `tests/test_release_record_step.py::test_step_posts_release_with_digests` |
| T-PIPE-RELEASE-R010 | PIPE-RELEASE-R010 | Run the `test_source_build_allowance_*` and `test_published_package_cannot_be_its_own_source_build` tests in `tests/test_wheel_readiness.py`; observe the empty default, the named list, the refusals and the recorded receipt list. |
| T-PIPE-RELEASE-R011 | PIPE-RELEASE-R011 | Run `tests/test_connector_release_pipeline.py::test_connector_pr_workflow_is_fast_commit_stage_and_never_publishes`. Assert the commit-stage-only, 10-minute, no-publish contract. |
| T-PIPE-RELEASE-R012 | PIPE-RELEASE-R012 | Run `tests/test_connector_release_pipeline.py::test_verification_fails_naming_the_missing_artifact`. Assert the step fails naming the missing tag or version. |
| T-PIPE-RELEASE-R013 | PIPE-RELEASE-R013 | Run `tests/hooks/test_release_standard.py`. Assert warn, strict generated-render and custom-path acceptance, disabled-job and exempt behavior. |
| T-PIPE-RELEASE-R014 | PIPE-RELEASE-R014 | Run the two bound tests in `tests/test_wheel_readiness.py`. Assert profiles overlap in time, the evidence keeps declared order, and the install command carries `--no-compile` beside `--no-cache-dir`. |
| T-PIPE-RELEASE-R015 | PIPE-RELEASE-R015 | Run `test_release_builds_use_one_persistent_builder`. Assert no per-job builder create or remove, every build attempt names the builder, and the cache arguments are unchanged. |
| T-PIPE-RELEASE-R016 | PIPE-RELEASE-R016 | Run `test_publish_action_persists_uv_cache_in_tool_cache`. Assert the step precedes every uv use and writes both variables under the tool cache. |

| T-PIPE-RELEASE-R012.1 | PIPE-RELEASE-R012.1 | Run `tests/test_public_wheel_guard.py` and `tests/test_container_pipeline_contract.py`; require exact committed and deterministic release-generated package inventory, bytes and public digest, stale pin refusal before network, nonconnector/custom-path refusal, and a main-release preflight before the builder/login/build while preserving the default release guard. Also require the explicit boolean repair input and original source SHA/epoch inputs to default false/empty, refuse non-dispatch/non-main/non-current-HEAD, missing or non-ancestor source, epoch mismatch, nonconnector or unpublished-wheel cases, build from the immutable source checkout, and keep PyPI verification read-only while the guarded repair may publish the container. |

## Entries added for rows without a prior entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-RELEASE-R003 | PIPE-RELEASE-R003 | Verified by a build run whose steps complete via the real product build path rather than aborting early from an environment-sourcing error, and whose reproducibility check confirms byte-identical wheels across independent builds. |
| T-PIPE-RELEASE-R022 | PIPE-RELEASE-R022 | Planned test (the file does not exist yet): Test: `tests/test_delivered.py::test_each_failing_condition_blocks_delivered`. |
| T-PIPE-RELEASE-R023 | PIPE-RELEASE-R023 | Planned test (the file exists, the test does not yet): Test: `tests/test_release_scope.py::test_p5_names_the_cross_source_scenario`. |
| T-PIPE-RELEASE-R024 | PIPE-RELEASE-R024 | Planned test (the file does not exist yet): Test: `tests/test_release_consumer_import.py::test_removed_symbol_fails_and_is_named` and `::test_missing_ceiling_is_reported`. |

## Entries added for rows without a prior entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-RELEASE-R019 | PIPE-RELEASE-R019 | Test: a workflow fixture run asserts the step order and that an unsigned build fails. |
| T-PIPE-RELEASE-R020 | PIPE-RELEASE-R020 | Planned test (the file does not exist yet): Test: `tests/test_release_bundle_gate.py::test_bundle_with_open_rows_or_failed_scenario_stops`. |
| T-PIPE-RELEASE-R025.1 | PIPE-RELEASE-R025.1 | Planned test (the file exists, the test does not yet): Test: `tests/test_release_scope.py::test_closure_follows_depends_on_and_contract_edges`. |
| T-PIPE-RELEASE-R025.2 | PIPE-RELEASE-R025.2 | Planned test (the file exists, the test does not yet): Test: `tests/test_release_scope.py::test_train_order_is_topological_and_not_hard_coded`. |
| T-PIPE-RELEASE-R025.3 | PIPE-RELEASE-R025.3 | Planned test (the file exists, the test does not yet): Test: `tests/test_release_scope.py::test_cycle_across_bundles_refuses_with_bundle_cycle`. |
| T-PIPE-RELEASE-R025.4 | PIPE-RELEASE-R025.4 | Planned test (the file does not exist yet): Test: `tests/test_release_plan.py::test_plan_is_deterministic_and_lists_rows_order_scenario_and_open_tasks`. |
| T-PIPE-RELEASE-R025.5 | PIPE-RELEASE-R025.5 | Planned test (the file does not exist yet): Test: `tests/test_release_plan.py::test_publish_posts_bundle_facts_and_plan_and_skips_without_endpoint`. |
| T-PIPE-RELEASE-R025.6 | PIPE-RELEASE-R025.6 | Planned test (the file does not exist yet): Test: `tests/test_release_bundle_gate.py::test_release_job_stops_on_bundle_cycle`. |
| T-PIPE-RELEASE-R025.7 | PIPE-RELEASE-R025.7 | Planned test (the file does not exist yet): Test: `tests/test_release_plan_served.py::test_published_plan_answers_rows_per_repository_through_ask` (L3, served). |
| T-PIPE-RELEASE-R026.1 | PIPE-RELEASE-R026.1 | Planned test (the file does not exist yet): Test: `tests/test_release_exit_gates.py::test_gate_table_with_a_missing_row_or_phase_fails`. |
| T-PIPE-RELEASE-R026.2 | PIPE-RELEASE-R026.2 | Planned test (the file does not exist yet): Test: `tests/test_release_exit_gates.py::test_final_gate_lists_open_connector_rows_and_unready_services`. |
| T-PIPE-RELEASE-R026.3 | PIPE-RELEASE-R026.3 | Planned test (the file does not exist yet): Test: `tests/test_release_exit_gates.py::test_final_gate_needs_a_passing_run_for_each_channel`. |
| T-PIPE-RELEASE-R026.4 | PIPE-RELEASE-R026.4 | Planned test (the file does not exist yet): Test: `tests/test_release_exit_gates.py::test_program_exit_gates_table_resolves_against_the_workspace` (L3, served). |
| T-PIPE-RELEASE-R027 | PIPE-RELEASE-R027 | Test: `tests/test_release_drift.py::test_an_unpublished_old_version_is_reported_with_a_normalized_name` and the three further tests of that file. |

## Entries added for rows without an entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-RELEASE-R002 | PIPE-RELEASE-R002 | Run `tests/test_release_version_guard.py::test_stale_version_under_new_tag_is_refused` and `tests/test_release_source.py::test_existing_tag_is_compared_to_frozen_source`. A stale version under a new tag, or a tag that points elsewhere than the frozen source, is refused before the build. |
| T-PIPE-RELEASE-R004 | PIPE-RELEASE-R004 | Rollup. The proof is its children `PIPE-RELEASE-R004.1` to `PIPE-RELEASE-R004.6`. |
| T-PIPE-RELEASE-R004.1 | PIPE-RELEASE-R004.1 | Run `tests/test_wheel_kernel_completeness.py::test_kernel_matrix_model_is_closed`. One cell per target and tag. |
| T-PIPE-RELEASE-R004.2 | PIPE-RELEASE-R004.2 | Run `tests/test_wheel_kernel_completeness.py::test_wheel_without_binary_is_missing`. The pure-Python wheel counts as missing. |
| T-PIPE-RELEASE-R004.3 | PIPE-RELEASE-R004.3 | Run `tests/test_wheel_kernel_completeness.py::test_aggregate_calls_kernel_gate`. `aggregate` raises on a missing cell. |
| T-PIPE-RELEASE-R004.4 | PIPE-RELEASE-R004.4 | Run `tests/test_wheel_kernel_completeness.py::test_missing_cell_refusal_lists_all_pairs`. Every absent pair is named. |
| T-PIPE-RELEASE-R004.5 | PIPE-RELEASE-R004.5 | Run `tests/test_wheel_kernel_completeness.py::test_receipt_records_kernel_cells`. `kernel_cells` equals the required set. |
| T-PIPE-RELEASE-R004.6 | PIPE-RELEASE-R004.6 | Run `tests/test_wheel_kernel_completeness.py::test_release_bundle_blocks_missing_kernel_wheel`. Exit 1 and no receipt file. |
| T-PIPE-RELEASE-R005.1 | PIPE-RELEASE-R005.1 | Run `tests/hooks/test_dependency_cycles.py::test_group_graph_model`. One node per group. |
| T-PIPE-RELEASE-R005.2 | PIPE-RELEASE-R005.2 | Run `tests/hooks/test_dependency_cycles.py::test_include_group_cycle_found`. A two-group loop is reported. |
| T-PIPE-RELEASE-R005.3 | PIPE-RELEASE-R005.3 | Run `tests/hooks/test_dependency_cycles.py::test_dependency_findings_include_loops`. A loop finding appears. |
| T-PIPE-RELEASE-R005.4 | PIPE-RELEASE-R005.4 | Run `tests/hooks/test_dependency_cycles.py::test_unparseable_manifest_is_not_a_pass`. A parse finding, not an empty pass. |
| T-PIPE-RELEASE-R005.5 | PIPE-RELEASE-R005.5 | Run `tests/hooks/test_dependency_cycles.py::test_loop_finding_lists_sorted_members`. Members are sorted. The loop count in the gate summary has no test yet (planned with the summary). |
| T-PIPE-RELEASE-R005.6 | PIPE-RELEASE-R005.6 | Run `tests/hooks/test_dependency_cycles.py::test_supply_chain_hook_blocks_dependency_loop`. Exit 1 and the rule name `SC-DEP-LOOP`. |
| T-PIPE-RELEASE-R001.13 | PIPE-RELEASE-R001.13 | Run `tests/hooks/test_connector_central.py::test_render_is_deterministic_and_driven_by_the_table` and the further render tests named in the row. Equal inputs give equal bytes and invalid tables refuse. |
| T-PIPE-RELEASE-R001.14 | PIPE-RELEASE-R001.14 | Run `tests/hooks/test_connector_central.py::test_container_workflow_renders_and_tags_by_sdk_version`. The SDK version reaches the build argument and the tag. |
| T-PIPE-RELEASE-R017 | PIPE-RELEASE-R017 | Run `tests/test_connector_release_pipeline.py::test_connector_pr_builds_the_image_only_when_a_container_input_changes`. The image check runs only for a container input change. |
| T-PIPE-RELEASE-R018 | PIPE-RELEASE-R018 | Run `tests/test_connector_pipeline.py::test_nothing_publishes_on_a_main_push_and_a_v_tag_publishes`. A main push never publishes and a `v*` tag does. |
| T-PIPE-RELEASE-R018.1 | PIPE-RELEASE-R018.1 | Run `tests/test_public_wheel_guard.py::test_public_wheel_verifies_the_tag_version_the_build_stamps`. The guard checks the version the tag stamps. |
| T-PIPE-RELEASE-R021 | PIPE-RELEASE-R021 | Run `tests/test_release_scope.py::test_scope_closure_and_single_release_per_row`. Each row is in one release and the closure holds its dependencies. |
