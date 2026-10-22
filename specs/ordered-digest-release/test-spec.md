# Test contract — PIPE-RELEASE

Use public synthetic candidate manifests and CI/registry responses. Unit and workflow tests require no cluster or secrets; a real release supplies separate exact-run evidence.

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-1 | Valid A → B → C manifest validates source/digest fields. |
| N-1 | FR-1 | Duplicate, missing dependency, self edge, or cycle fails before publication. |
| N-2 | FR-1 | Floating tag, malformed digest, or provenance mismatch fails closed. |
| P-2 | FR-2 | Required exact-commit checks pass and mark only that candidate eligible. |
| N-3 | FR-2 | Missing, skipped, failed, or wrong-commit check blocks candidate and descendants. |
| P-3 | FR-3 | Stable order publishes A then B then C and records hosted CI. |
| N-4 | FR-3 | Failed predecessor CI prevents next push and retains partial receipt. |
| N-5 | FR-3 | Same-digest retry is idempotent; changed commit/digest cannot resume old receipt. |
| P-4 | FR-4 | Digest-pinned manifest exactly matches qualified mapping. |
| N-6 | FR-4 | Wrong or floating workload reference names workload and blocks readiness. |
| P-5 | FR-5 | Dry-run, parser, ordering, and negative tests run without infrastructure secrets. |

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
| T-PIPE-RELEASE-R007.1 | PIPE-RELEASE-R007.1 | Run `test_gates_workflow_inputs_all_default` in `tests/test_gates_pipeline_contract.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.2 | PIPE-RELEASE-R007.2 | Run `test_gates_workflow_scopes_to_the_diff_and_caps_time` in `tests/test_gates_pipeline_contract.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.3 | PIPE-RELEASE-R007.3 | Run `test_require_tag_defaults_off_and_guards_the_publish_step` in `tests/test_gates_pipeline_contract.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.4 | PIPE-RELEASE-R007.4 | Run `test_require_tag_refuses_a_branch_ref_and_names_it` in `tests/test_gates_pipeline_contract.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.5 | PIPE-RELEASE-R007.5 | Run `test_fast_tests_reports_no_affected_tests` in `tests/hooks/test_fast_tests.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.6 | PIPE-RELEASE-R007.6 | Run `test_fast_tests_runs_only_the_affected_subset` in `tests/hooks/test_fast_tests.py`. Assert the stated contract through its declared boundary. |
| T-PIPE-RELEASE-R007.7 | PIPE-RELEASE-R007.7 | Run `test_a_release_version_bump_forces_no_crate_sweep`, `test_a_registry_dependency_bump_still_forces_the_full_sweep` and `test_a_member_manifest_change_beyond_versions_maps_to_its_crate` in `tests/hooks/test_pr_test_scope.py`. |
| T-PIPE-RELEASE-R008 | PIPE-RELEASE-R008 | Run `tests/test_python_sdist_output.py`; observe the sdist built, proven and uploaded with the wheel, the maturin sdist job covering its package, and the documented readiness rule. |

## Release records published to the engine

| Row | Proving test |
|---|---|
| `PIPE-RELEASE-R009` | See each child. |
| `PIPE-RELEASE-R009.1` | `tests/test_release_record_step.py::test_workflow_has_record_step_after_publish` |
| `PIPE-RELEASE-R009.2` | `tests/test_release_record_step.py::test_step_posts_release_with_digests` |
