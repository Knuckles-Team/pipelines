# Quickstart — PIPE-RELEASE

Run the release proofs of this specification from a clean checkout of this repository. Every command is offline and needs no cluster or secret.

1. Order and qualify a candidate set from public fixtures: `uv run python scripts/release_orchestrator.py validate --manifest <candidate.json>` and then `uv run pytest tests/test_release_orchestrator.py tests/test_release_candidate.py tests/test_release_qualification.py` (PIPE-RELEASE-R001).
2. Prove the release guards: `uv run pytest tests/test_release_version_guard.py tests/test_release_source.py` (PIPE-RELEASE-R002).
3. Prove the kernel wheel gate and the dependency loop gate: `uv run pytest tests/test_wheel_kernel_completeness.py tests/hooks/test_dependency_cycles.py` (PIPE-RELEASE-R004.6 and PIPE-RELEASE-R005.6).
4. Prove the version consistency gate end to end: `uv run pytest tests/hooks/test_project_version_sync.py tests/hooks/test_version_inventory_completeness.py` (PIPE-RELEASE-R006.6).
5. Prove the shared gates workflow and the fast subset: `uv run pytest tests/test_gates_pipeline_contract.py tests/hooks/test_fast_tests.py tests/hooks/test_change_scope.py` (PIPE-RELEASE-R007.6).
6. Check the release bundles: `uv run python scripts/release_scope.py --workspace <workspace> --check` (PIPE-RELEASE-R021).
7. Check that every merged version is published: `uv run pytest tests/test_release_drift.py` (PIPE-RELEASE-R027).

Rows marked planned in `test-spec.md` have no runnable proof yet; their first run is the proof each row names.
