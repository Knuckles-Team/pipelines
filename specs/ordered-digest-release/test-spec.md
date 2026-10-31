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
| T-PIPE-RELEASE-R006.1 | PIPE-RELEASE-R006.1 | Run `test_project_version_inventory` in `tests/hooks/test_project_version_sync.py`. Accept a complete three-role inventory; reject unknown roles, duplicate locations and missing role coverage. |
| T-PIPE-RELEASE-R006.2 | PIPE-RELEASE-R006.2 | Run `test_project_version_values` in `tests/hooks/test_project_version_sync.py`. Equal values pass; independently changing metadata, source, documentation or canonical current version fails at the exact location. |
| T-PIPE-RELEASE-R006.3 | PIPE-RELEASE-R006.3 | Run `test_project_version_hook_wiring` in `tests/hooks/test_project_version_sync.py`. The installed CLI and published hook select the same snapshot and fail on an inconsistent unchanged declared surface. |
| T-PIPE-RELEASE-R006.4 | PIPE-RELEASE-R006.4 | Run `test_project_version_refusals` in `tests/hooks/test_project_version_sync.py`. Missing, malformed or competing configs and ambiguous extraction exit 2; mismatches exit 1 and cannot produce a passing receipt. |
| T-PIPE-RELEASE-R006.5 | PIPE-RELEASE-R006.5 | Run `test_project_version_evidence` in `tests/hooks/test_project_version_sync.py`. Evidence identifies the exact checked Git bytes and all three roles; unchecked cases have no successful verdict. |
| T-PIPE-RELEASE-R006.6 | PIPE-RELEASE-R006.6 | Run `test_project_version_sync_cli` in `tests/hooks/test_project_version_sync.py`. Assert real dispatcher/hook exit codes, exact locations, snapshot isolation, all-surface bumping and unchanged caller files during gate checks. |
| T-PIPE-RELEASE-R005.7 | PIPE-RELEASE-R005.7 | Run `test_role_extra_closure_model` in `tests/hooks/test_role_extra_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.8 | PIPE-RELEASE-R005.8 | Run `test_role_extra_closure_behavior` in `tests/hooks/test_role_extra_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.9 | PIPE-RELEASE-R005.9 | Run `test_role_extra_closure_wiring` in `tests/hooks/test_role_extra_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.10 | PIPE-RELEASE-R005.10 | Run `test_role_extra_closure_refusal` in `tests/hooks/test_role_extra_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.11 | PIPE-RELEASE-R005.11 | Run `test_role_extra_closure_evidence` in `tests/hooks/test_role_extra_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R005.12 | PIPE-RELEASE-R005.12 | Run `test_role_extra_closure_cli` in `tests/hooks/test_role_extra_closure.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.1 | PIPE-RELEASE-R001.1 | Run `test_release_phase_progress_model` in `tests/hooks/test_release_phase_progress.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.2 | PIPE-RELEASE-R001.2 | Run `test_release_phase_progress_behavior` in `tests/hooks/test_release_phase_progress.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.3 | PIPE-RELEASE-R001.3 | Run `test_release_phase_progress_wiring` in `tests/hooks/test_release_phase_progress.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.4 | PIPE-RELEASE-R001.4 | Run `test_release_phase_progress_refusal` in `tests/hooks/test_release_phase_progress.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.5 | PIPE-RELEASE-R001.5 | Run `test_release_phase_progress_evidence` in `tests/hooks/test_release_phase_progress.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.6 | PIPE-RELEASE-R001.6 | Run `test_release_phase_progress_cli` in `tests/hooks/test_release_phase_progress.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.7 | PIPE-RELEASE-R006.7 | Run `test_version_inventory_completeness_model` in `tests/hooks/test_version_inventory_completeness.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.8 | PIPE-RELEASE-R006.8 | Run `test_version_inventory_completeness_behavior` in `tests/hooks/test_version_inventory_completeness.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.9 | PIPE-RELEASE-R006.9 | Run `test_version_inventory_completeness_wiring` in `tests/hooks/test_version_inventory_completeness.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.10 | PIPE-RELEASE-R006.10 | Run `test_version_inventory_completeness_refusal` in `tests/hooks/test_version_inventory_completeness.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.11 | PIPE-RELEASE-R006.11 | Run `test_version_inventory_completeness_evidence` in `tests/hooks/test_version_inventory_completeness.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R006.12 | PIPE-RELEASE-R006.12 | Run `test_version_inventory_completeness_cli` in `tests/hooks/test_version_inventory_completeness.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.7 | PIPE-RELEASE-R001.7 | Run `test_major_upgrade_pre_pin_model` in `tests/hooks/test_major_upgrade_pre_pin.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.8 | PIPE-RELEASE-R001.8 | Run `test_major_upgrade_pre_pin_behavior` in `tests/hooks/test_major_upgrade_pre_pin.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.9 | PIPE-RELEASE-R001.9 | Run `test_major_upgrade_pre_pin_wiring` in `tests/hooks/test_major_upgrade_pre_pin.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.10 | PIPE-RELEASE-R001.10 | Run `test_major_upgrade_pre_pin_refusal` in `tests/hooks/test_major_upgrade_pre_pin.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.11 | PIPE-RELEASE-R001.11 | Run `test_major_upgrade_pre_pin_evidence` in `tests/hooks/test_major_upgrade_pre_pin.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R001.12 | PIPE-RELEASE-R001.12 | Run `test_major_upgrade_pre_pin_cli` in `tests/hooks/test_major_upgrade_pre_pin.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.1 | PIPE-RELEASE-R007.1 | Run `test_gates_workflow_inputs_all_default` in `tests/test_gates_pipeline_contract.py`. Assert the stated contract through its declared boundary. `test_gates_workflow_forwards_optional_uv_cache_path` checks the empty default and the setup action input. |
| T-PIPE-RELEASE-R007.2 | PIPE-RELEASE-R007.2 | Run `test_gates_workflow_scopes_to_the_diff_and_caps_time` in `tests/test_gates_pipeline_contract.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.3 | PIPE-RELEASE-R007.3 | Run `test_require_tag_defaults_off_and_guards_the_publish_step` in `tests/test_gates_pipeline_contract.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.4 | PIPE-RELEASE-R007.4 | Run `test_require_tag_refuses_a_branch_ref_and_names_it` in `tests/test_gates_pipeline_contract.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.5 | PIPE-RELEASE-R007.5 | Run `test_fast_tests_reports_no_affected_tests` in `tests/hooks/test_fast_tests.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.6 | PIPE-RELEASE-R007.6 | Run `test_fast_tests_runs_only_the_affected_subset` in `tests/hooks/test_fast_tests.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.7 | PIPE-RELEASE-R007.7 | Run `test_a_release_version_bump_forces_no_crate_sweep`, `test_a_registry_dependency_bump_still_forces_the_full_sweep` and `test_a_member_manifest_change_beyond_versions_maps_to_its_crate` in `tests/hooks/test_pr_test_scope.py`. |
| T-PIPE-RELEASE-R007.8 | PIPE-RELEASE-R007.8 | Run `test_change_scope_classifies_each_fixture_diff` and `test_change_scope_writes_step_outputs_and_the_spec_skip_list` in `tests/hooks/test_change_scope.py`. Each fixture diff maps to its classes and scope. |
| T-PIPE-RELEASE-R007.9 | PIPE-RELEASE-R007.9 | Run `test_gates_workflow_routes_each_change_scope_to_its_gates` in `tests/test_gates_pipeline_contract.py` and `test_change_scope_keeps_every_hook_for_code_and_full_runs` in `tests/hooks/test_change_scope.py`. |
| T-PIPE-RELEASE-R007.10 | PIPE-RELEASE-R007.10 | Run `test_change_scope_refuses_and_falls_back_conservatively` in `tests/hooks/test_change_scope.py`. Each refusal exits 2. |
| T-PIPE-RELEASE-R007.11 | PIPE-RELEASE-R007.11 | Run `test_docs_only_paths_is_removed_for_the_default_scope` in `tests/test_gates_pipeline_contract.py`. |
| T-PIPE-RELEASE-R007.12 | PIPE-RELEASE-R007.12 | Run `test_gates_workflow_names_each_not_applicable_gate` in `tests/test_gates_pipeline_contract.py`. |
| T-PIPE-RELEASE-R008 | PIPE-RELEASE-R008 | Run `tests/test_python_sdist_output.py`; observe the sdist built, proven and uploaded with the wheel, the maturin sdist job covering its package, and the documented readiness rule. |

## Release records published to the engine

| Row | Proving test |
|---|---|
| `PIPE-RELEASE-R009` | See each child. |
| `PIPE-RELEASE-R009.1` | `tests/test_release_record_step.py::test_workflow_has_record_step_after_publish` |
| `PIPE-RELEASE-R009.2` | `tests/test_release_record_step.py::test_step_posts_release_with_digests` |
| T-PIPE-RELEASE-R010 | PIPE-RELEASE-R010 | Run the `test_source_build_allowance_*` and `test_published_package_cannot_be_its_own_source_build` tests in `tests/test_wheel_readiness.py`; observe the empty default, the named list, the refusals and the recorded receipt list. |
| T-PIPE-RELEASE-R011 | PIPE-RELEASE-R011 | Run `test_connector_pr_workflow_is_fast_commit_stage_and_never_publishes` in `tests/test_connector_release_pipeline.py`. Assert the commit-stage-only, 10-minute, no-publish contract. |
| T-PIPE-RELEASE-R012 | PIPE-RELEASE-R012 | Run `test_verification_fails_naming_the_missing_artifact` in `tests/test_connector_release_pipeline.py`. Assert the step fails naming the missing tag or version. |
| T-PIPE-RELEASE-R013 | PIPE-RELEASE-R013 | Run `tests/hooks/test_release_standard.py`. Assert warn, strict generated-render and custom-path acceptance, disabled-job and exempt behavior. |
| T-PIPE-RELEASE-R014 | PIPE-RELEASE-R014 | Run the two bound tests in `tests/test_wheel_readiness.py`. Assert profiles overlap in time, the evidence keeps declared order, and the install command carries `--no-compile` beside `--no-cache-dir`. |
| T-PIPE-RELEASE-R015 | PIPE-RELEASE-R015 | Run `test_release_builds_use_one_persistent_builder`. Assert no per-job builder create or remove, every build attempt names the builder, and the cache arguments are unchanged. |
| T-PIPE-RELEASE-R016 | PIPE-RELEASE-R016 | Run `test_publish_action_persists_uv_cache_in_tool_cache`. Assert the step precedes every uv use and writes both variables under the tool cache. |

| T-PIPE-RELEASE-R012.1 | PIPE-RELEASE-R012.1 | Run `tests/test_public_wheel_guard.py` and `tests/test_container_pipeline_contract.py`; require exact committed and deterministic release-generated package inventory, bytes and public digest, stale pin refusal before network, nonconnector/custom-path refusal, and a main-release preflight before the builder/login/build while preserving the default release guard. Also require the explicit boolean repair input and original source SHA/epoch inputs to default false/empty, refuse non-dispatch/non-main/non-current-HEAD, missing or non-ancestor source, epoch mismatch, nonconnector or unpublished-wheel cases, build from the immutable source checkout, and keep PyPI verification read-only while the guarded repair may publish the container. |

## Entries added for rows without a prior entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-RELEASE-R003 | PIPE-RELEASE-R003 | Verified by a build run whose steps complete via the real product build path rather than aborting early from an environment-sourcing error, and whose reproducibility check confirms byte-identical wheels across independent builds. |
| T-PIPE-RELEASE-R022 | PIPE-RELEASE-R022 | Test: `tests/test_delivered.py::test_each_failing_condition_blocks_delivered`. |
| T-PIPE-RELEASE-R023 | PIPE-RELEASE-R023 | Test: `tests/test_release_scope.py::test_p5_names_the_cross_source_scenario`. |
| T-PIPE-RELEASE-R024 | PIPE-RELEASE-R024 | Test: `tests/test_release_consumer_import.py::test_removed_symbol_fails_and_is_named` and `::test_missing_ceiling_is_reported`. |

## Entries added for rows without a prior entry

| Test ID | Requirement | Expected observation |
|---|---|---|
| T-PIPE-RELEASE-R019 | PIPE-RELEASE-R019 | Test: a workflow fixture run asserts the step order and that an unsigned build fails. |
| T-PIPE-RELEASE-R020 | PIPE-RELEASE-R020 | Test: `tests/test_release_bundle_gate.py::test_bundle_with_open_rows_or_failed_scenario_stops`. |
| T-PIPE-RELEASE-R025.1 | PIPE-RELEASE-R025.1 | Test: `tests/test_release_scope.py::test_closure_follows_depends_on_and_contract_edges`. |
| T-PIPE-RELEASE-R025.2 | PIPE-RELEASE-R025.2 | Test: `tests/test_release_scope.py::test_train_order_is_topological_and_not_hard_coded`. |
| T-PIPE-RELEASE-R025.3 | PIPE-RELEASE-R025.3 | Test: `tests/test_release_scope.py::test_cycle_across_bundles_refuses_with_bundle_cycle`. |
| T-PIPE-RELEASE-R025.4 | PIPE-RELEASE-R025.4 | Test: `tests/test_release_plan.py::test_plan_is_deterministic_and_lists_rows_order_scenario_and_open_tasks`. |
| T-PIPE-RELEASE-R025.5 | PIPE-RELEASE-R025.5 | Test: `tests/test_release_plan.py::test_publish_posts_bundle_facts_and_plan_and_skips_without_endpoint`. |
| T-PIPE-RELEASE-R025.6 | PIPE-RELEASE-R025.6 | Test: `tests/test_release_bundle_gate.py::test_release_job_stops_on_bundle_cycle`. |
| T-PIPE-RELEASE-R025.7 | PIPE-RELEASE-R025.7 | Test: `tests/test_release_plan_served.py::test_published_plan_answers_rows_per_repository_through_ask` (L3, served). |
| T-PIPE-RELEASE-R026.1 | PIPE-RELEASE-R026.1 | Test: `tests/test_release_exit_gates.py::test_gate_table_with_a_missing_row_or_phase_fails`. |
| T-PIPE-RELEASE-R026.2 | PIPE-RELEASE-R026.2 | Test: `tests/test_release_exit_gates.py::test_final_gate_lists_open_connector_rows_and_unready_services`. |
| T-PIPE-RELEASE-R026.3 | PIPE-RELEASE-R026.3 | Test: `tests/test_release_exit_gates.py::test_final_gate_needs_a_passing_run_for_each_channel`. |
| T-PIPE-RELEASE-R026.4 | PIPE-RELEASE-R026.4 | Test: `tests/test_release_exit_gates.py::test_program_exit_gates_table_resolves_against_the_workspace` (L3, served). |
