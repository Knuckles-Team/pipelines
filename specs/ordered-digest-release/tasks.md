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
