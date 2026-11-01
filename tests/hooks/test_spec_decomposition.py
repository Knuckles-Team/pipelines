"""spec-decomposition (over computed status) fires on each malformed decomposition kind and passes a clean spec."""

from __future__ import annotations

from tests.hooks.conftest import Repo

REQ_CLEAN = "# FOO-001 requirements\n\n| ID | Requirement | Verification |\n|---|---|---|\n| `FOO-001` | **Root.** Does the thing. | Verified by a test. |\n"


def _clean(repo: Repo) -> None:
    repo.commit(
        {
            "specs/foo/requirements.md": REQ_CLEAN,
        }
    )


def test_clean_spec_passes(repo: Repo) -> None:
    _clean(repo)
    assert repo.run("spec-decomposition") == 0


def test_duplicate_id_in_requirements_fires(repo: Repo) -> None:
    _clean(repo)
    repo.commit({"specs/foo/requirements.md": REQ_CLEAN + "| `FOO-001` | **Root again.** Dup row. | Verified. |\n"})
    assert repo.run("spec-decomposition") == 1


def test_referenced_child_with_no_requirement_row_fires(repo: Repo) -> None:
    _clean(repo)
    repo.commit(
        {
            "specs/foo/tasks.md": "- [ ] **FOO-001.1:** a slice with no requirements row\n",
        }
    )
    assert repo.run("spec-decomposition") == 1


def test_child_with_no_parent_row_at_all_fires(repo: Repo) -> None:
    req = "# requirements\n\n| ID | Requirement | Verification |\n|---|---|---|\n| `FOO-001.1` | **Orphan slice.** No parent row anywhere. | Verified. |\n"
    repo.commit({"specs/foo/requirements.md": req})
    assert repo.run("spec-decomposition") == 1


def test_v2_landed_parent_with_verified_child_is_consistent() -> None:
    from pipelines_hooks.specs.decomposition_checks import STATE_RANK

    assert STATE_RANK["VERIFIED"] >= STATE_RANK["LANDED"]


def test_local_test_case_numbers_are_not_requirement_children() -> None:
    from pipelines_hooks.specs.decomposition import _referenced_child_ids

    texts = {"test-spec.md": "| F-07.1 | case |\n| MEDULLA-FIN-R005.2 | real child |"}
    assert _referenced_child_ids(texts, {"MEDULLA-FIN-R005"}) == {"MEDULLA-FIN-R005.2"}
