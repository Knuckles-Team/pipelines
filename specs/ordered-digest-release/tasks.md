# Tasks — PIPE-RELEASE

- [ ] Agree public candidate schema and integrity mechanism; document deployment-owner handoff fields.
- [ ] Implement strict candidate, digest, source, and dependency validation before publication effects.
- [ ] Add deterministic topological order, exact-revision qualification, and stage receipts using existing actions.
- [ ] Bind source verification and registry digests to builds; emit idempotent versioned handoff.
- [ ] Check declared consumer manifest references without editing those manifests.
- [ ] Add P-1–P-5 and N-1–N-6 fixture/workflow tests; run YAML, pytest, CCCC, jscpd, Dupehound, and KISS.
- [ ] Execute reviewed release, link hosted CI/digest receipts, obtain deployment evidence, update delivery and acceptance independently.

No task above cites a `requirements.md` ID by name. PIPE-RELEASE-R001 (dependency-ordered digest
publication) is closed by tasks 2-4 above (candidate validation, ordered publication, digest
handoff). PIPE-RELEASE-R002 (release tag matches the qualified commit) is closed by task 2 above
(candidate/source/digest validation) together with task 7 (release evidence linking the tag to its
commit).
- [ ] Quote and properly escape every environment value the release build job sources locally
      (including compiler flags such as CFLAGS) so a multi-token value is never misinterpreted as a
      shell command, and verify the build produces byte-identical, reproducible wheels. Closes
      PIPE-RELEASE-R003, which no functional requirement or existing task above covers.
- [ ] Add `kernels.py` with the kernel matrix, call it from `aggregate`, record `kernel_cells` in the receipt, and prove a release bundle with a missing platform wheel fails. Closes PIPE-RELEASE-R004.
- [ ] Add `dependency_cycles.py`, call it from `dependency_findings`, emit `SC-DEP-LOOP`, and prove `pipelines-hook supply-chain` fails on a group loop. Closes PIPE-RELEASE-R005.
- [ ] PIPE-RELEASE-R006: Deliver all six children and retain separate consistency and release authorization.
- [ ] PIPE-RELEASE-R006.1: Model: Accept a complete three-role inventory; reject unknown roles, duplicate locations and missing role coverage. Implement and bind `test_project_version_inventory` in `tests/hooks/test_project_version_sync.py`.
- [ ] PIPE-RELEASE-R006.2: Behavior: Equal values pass; independently changing metadata, source, documentation or canonical current version fails at the exact location. Implement and bind `test_project_version_values` in `tests/hooks/test_project_version_sync.py`.
- [ ] PIPE-RELEASE-R006.3: Wiring: The installed CLI and published hook select the same snapshot and fail on an inconsistent unchanged declared surface. Implement and bind `test_project_version_hook_wiring` in `tests/hooks/test_project_version_sync.py`.
- [ ] PIPE-RELEASE-R006.4: Refusal: Missing, malformed or competing configs and ambiguous extraction exit 2; mismatches exit 1 and cannot produce a passing receipt. Implement and bind `test_project_version_refusals` in `tests/hooks/test_project_version_sync.py`.
- [ ] PIPE-RELEASE-R006.5: Evidence: Evidence identifies the exact checked Git bytes and all three roles; unchecked cases have no successful verdict. Implement and bind `test_project_version_evidence` in `tests/hooks/test_project_version_sync.py`.
- [ ] PIPE-RELEASE-R006.6: Hot-path proof: Assert real dispatcher/hook exit codes, exact locations, snapshot isolation, all-surface bumping and unchanged caller files during gate checks. Implement and bind `test_project_version_sync_cli` in `tests/hooks/test_project_version_sync.py`.
- [ ] PIPE-RELEASE-R005.7: Model. Implement this contract and bind `test_role_extra_closure_model` in `tests/hooks/test_role_extra_closure.py`.
- [ ] PIPE-RELEASE-R005.8: Behavior. Implement this contract and bind `test_role_extra_closure_behavior` in `tests/hooks/test_role_extra_closure.py`.
- [ ] PIPE-RELEASE-R005.9: Wiring. Implement this contract and bind `test_role_extra_closure_wiring` in `tests/hooks/test_role_extra_closure.py`.
- [ ] PIPE-RELEASE-R005.10: Refusal. Implement this contract and bind `test_role_extra_closure_refusal` in `tests/hooks/test_role_extra_closure.py`.
- [ ] PIPE-RELEASE-R005.11: Evidence. Implement this contract and bind `test_role_extra_closure_evidence` in `tests/hooks/test_role_extra_closure.py`.
- [ ] PIPE-RELEASE-R005.12: Hot-path proof. Implement this contract and bind `test_role_extra_closure_cli` in `tests/hooks/test_role_extra_closure.py`.
- [ ] PIPE-RELEASE-R001.1: Model. Implement this contract and bind `test_release_phase_progress_model` in `tests/hooks/test_release_phase_progress.py`.
- [ ] PIPE-RELEASE-R001.2: Behavior. Implement this contract and bind `test_release_phase_progress_behavior` in `tests/hooks/test_release_phase_progress.py`.
- [ ] PIPE-RELEASE-R001.3: Wiring. Implement this contract and bind `test_release_phase_progress_wiring` in `tests/hooks/test_release_phase_progress.py`.
- [ ] PIPE-RELEASE-R001.4: Refusal. Implement this contract and bind `test_release_phase_progress_refusal` in `tests/hooks/test_release_phase_progress.py`.
- [ ] PIPE-RELEASE-R001.5: Evidence. Implement this contract and bind `test_release_phase_progress_evidence` in `tests/hooks/test_release_phase_progress.py`.
- [ ] PIPE-RELEASE-R001.6: Hot-path proof. Implement this contract and bind `test_release_phase_progress_cli` in `tests/hooks/test_release_phase_progress.py`.
- [ ] PIPE-RELEASE-R006.7: Model. Implement this contract and bind `test_version_inventory_completeness_model` in `tests/hooks/test_version_inventory_completeness.py`.
- [ ] PIPE-RELEASE-R006.8: Behavior. Implement this contract and bind `test_version_inventory_completeness_behavior` in `tests/hooks/test_version_inventory_completeness.py`.
- [ ] PIPE-RELEASE-R006.9: Wiring. Implement this contract and bind `test_version_inventory_completeness_wiring` in `tests/hooks/test_version_inventory_completeness.py`.
- [ ] PIPE-RELEASE-R006.10: Refusal. Implement this contract and bind `test_version_inventory_completeness_refusal` in `tests/hooks/test_version_inventory_completeness.py`.
- [ ] PIPE-RELEASE-R006.11: Evidence. Implement this contract and bind `test_version_inventory_completeness_evidence` in `tests/hooks/test_version_inventory_completeness.py`.
- [ ] PIPE-RELEASE-R006.12: Hot-path proof. Implement this contract and bind `test_version_inventory_completeness_cli` in `tests/hooks/test_version_inventory_completeness.py`.
- [ ] PIPE-RELEASE-R001.7: Model. Implement this contract and bind `test_major_upgrade_pre_pin_model` in `tests/hooks/test_major_upgrade_pre_pin.py`.
- [ ] PIPE-RELEASE-R001.8: Behavior. Implement this contract and bind `test_major_upgrade_pre_pin_behavior` in `tests/hooks/test_major_upgrade_pre_pin.py`.
- [ ] PIPE-RELEASE-R001.9: Wiring. Implement this contract and bind `test_major_upgrade_pre_pin_wiring` in `tests/hooks/test_major_upgrade_pre_pin.py`.
- [ ] PIPE-RELEASE-R001.10: Refusal. Implement this contract and bind `test_major_upgrade_pre_pin_refusal` in `tests/hooks/test_major_upgrade_pre_pin.py`.
- [ ] PIPE-RELEASE-R001.11: Evidence. Implement this contract and bind `test_major_upgrade_pre_pin_evidence` in `tests/hooks/test_major_upgrade_pre_pin.py`.
- [ ] PIPE-RELEASE-R001.12: Hot-path proof. Implement this contract and bind `test_major_upgrade_pre_pin_cli` in `tests/hooks/test_major_upgrade_pre_pin.py`.
- [ ] PIPE-RELEASE-R007: Deliver all six children; keep every new input optional.
- [ ] PIPE-RELEASE-R007.1: Model. Implement this contract and bind `test_gates_workflow_inputs_all_default` in `tests/test_gates_pipeline_contract.py`.
- [ ] PIPE-RELEASE-R007.2: Behavior. Implement this contract and bind `test_gates_workflow_scopes_to_the_diff_and_caps_time` in `tests/test_gates_pipeline_contract.py`.
- [ ] PIPE-RELEASE-R007.3: Wiring. Implement this contract and bind `test_require_tag_defaults_off_and_guards_the_publish_step` in `tests/test_gates_pipeline_contract.py`.
- [ ] PIPE-RELEASE-R007.4: Refusal. Implement this contract and bind `test_require_tag_refuses_a_branch_ref_and_names_it` in `tests/test_gates_pipeline_contract.py`.
- [ ] PIPE-RELEASE-R007.5: Evidence. Implement this contract and bind `test_fast_tests_reports_no_affected_tests` in `tests/hooks/test_fast_tests.py`.
- [ ] PIPE-RELEASE-R007.6: Hot-path proof. Implement this contract and bind `test_fast_tests_runs_only_the_affected_subset` in `tests/hooks/test_fast_tests.py`.
- [ ] PIPE-RELEASE-R008: Publish the source distribution with the wheel. Implement this contract and bind `tests/test_python_sdist_output.py`.
