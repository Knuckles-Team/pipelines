"""spec-decomposition fires on each malformed decomposition kind and passes a clean spec."""

from __future__ import annotations

from tests.hooks.conftest import Repo

STATUS_CLEAN = """{
  "schema_version": 1,
  "spec_id": "FOO-001",
  "owner_repo": "fixture",
  "requirement_ids": ["FOO-001"],
  "requirements": [
    {"id": "FOO-001", "title": "Root", "delivery_state": "SPECIFIED", "evidence": []}
  ]
}
"""

REQ_CLEAN = "# FOO-001 requirements\n\n| ID | Requirement | Verification |\n|---|---|---|\n| `FOO-001` | **Root.** Does the thing. | Verified by a test. |\n"


def _clean(repo: Repo) -> None:
    repo.commit(
        {
            "specs/foo/status.json": STATUS_CLEAN,
            "specs/foo/requirements.md": REQ_CLEAN,
        }
    )


def test_clean_spec_passes(repo: Repo) -> None:
    _clean(repo)
    assert repo.run("spec-decomposition") == 0


def test_duplicate_id_in_requirements_fires(repo: Repo) -> None:
    _clean(repo)
    repo.commit(
        {
            "specs/foo/requirements.md": REQ_CLEAN
            + "| `FOO-001` | **Root again.** Dup row. | Verified. |\n"
        }
    )
    assert repo.run("spec-decomposition") == 1


def test_duplicate_id_in_status_fires(repo: Repo) -> None:
    status = """{
      "requirements": [
        {"id": "FOO-001", "title": "Root", "delivery_state": "SPECIFIED", "evidence": []},
        {"id": "FOO-001", "title": "Root dup", "delivery_state": "SPECIFIED", "evidence": []}
      ]
    }
    """
    repo.commit(
        {"specs/foo/status.json": status, "specs/foo/requirements.md": REQ_CLEAN}
    )
    assert repo.run("spec-decomposition") == 1


def test_referenced_child_with_no_status_row_fires(repo: Repo) -> None:
    _clean(repo)
    repo.commit(
        {
            "specs/foo/requirements.md": REQ_CLEAN
            + "| `FOO-001.1` | **Slice.** First slice. | Verified. |\n",
        }
    )
    assert repo.run("spec-decomposition") == 1


def test_status_row_with_no_requirements_row_fires(repo: Repo) -> None:
    status = """{
      "requirements": [
        {"id": "FOO-001", "title": "Root", "delivery_state": "SPECIFIED", "evidence": []},
        {"id": "FOO-002", "title": "Untracked in docs", "delivery_state": "SPECIFIED", "evidence": []}
      ]
    }
    """
    repo.commit(
        {"specs/foo/status.json": status, "specs/foo/requirements.md": REQ_CLEAN}
    )
    assert repo.run("spec-decomposition") == 1


def test_landed_parent_with_open_child_fires(repo: Repo) -> None:
    status = """{
      "requirements": [
        {"id": "FOO-001", "title": "Root", "delivery_state": "LANDED", "evidence": []},
        {"id": "FOO-001.1", "title": "Slice", "delivery_state": "SPECIFIED", "evidence": []}
      ]
    }
    """
    req = REQ_CLEAN + "| `FOO-001.1` | **Slice.** First slice. | Verified. |\n"
    repo.commit({"specs/foo/status.json": status, "specs/foo/requirements.md": req})
    assert repo.run("spec-decomposition") == 1


def test_child_with_no_parent_row_at_all_fires(repo: Repo) -> None:
    status = """{
      "requirements": [
        {"id": "FOO-001.1", "title": "Orphan slice", "delivery_state": "SPECIFIED", "evidence": []}
      ]
    }
    """
    req = "# requirements\n\n| ID | Requirement | Verification |\n|---|---|---|\n| `FOO-001.1` | **Orphan slice.** No parent row anywhere. | Verified. |\n"
    repo.commit({"specs/foo/status.json": status, "specs/foo/requirements.md": req})
    assert repo.run("spec-decomposition") == 1


def test_v2_landed_parent_with_verified_child_is_consistent() -> None:
    from pipelines_hooks.specs.decomposition_checks import STATE_RANK

    assert STATE_RANK["VERIFIED"] >= STATE_RANK["LANDED"]


def test_local_test_case_numbers_are_not_requirement_children() -> None:
    from pipelines_hooks.specs.decomposition import _referenced_child_ids

    texts = {"test-spec.md": "| F-07.1 | case |\n| EG-FIN-R005.2 | real child |"}
    assert _referenced_child_ids(texts, {"EG-FIN-R005"}) == {"EG-FIN-R005.2"}
