"""spec-status: generated specs/*/status.json (SPEC-STATUS-LIFECYCLE.md)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.spec_dashboard_metadata import enrich_records
from scripts.spec_dashboard_sources import read_records
from tests.hooks.conftest import Repo

_LANDED_ROW = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R001` | **Landed only.** |\n"
_RETIRED_ROW = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R002` | **RETIRED: superseded by TEST-R003.** |\n"
_ROLLUP_ROWS = (
    "# demo\n\n| ID | Requirement |\n|---|---|\n"
    "| `TEST-R010` | **Parent.** |\n"
    "| `TEST-R010.1` | **Child one.** |\n"
    "| `TEST-R010.2` | **Child two.** |\n"
)
_REVERT_ROW = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R030` | **Reverted feature.** |\n"
_STALE_ROW = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R040` | **Needs regeneration.** |\n"


def _status(repo: Repo) -> dict:
    return json.loads((repo.root / "specs/demo/status.json").read_text(encoding="utf-8"))


def _by_id(repo: Repo) -> dict[str, dict]:
    return {row["id"]: row for row in _status(repo)["requirements"]}


def test_commit_naming_an_id_lands_without_a_test(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _LANDED_ROW}, "add spec")
    repo.commit({"pkg/feature.py": "# implements TEST-R001\n"}, "Spec: TEST-R001")

    assert repo.run("spec-status", "--write") == 0
    row = _by_id(repo)["TEST-R001"]
    assert row["delivery_state"] == "LANDED"
    assert row["verified_by"] == []
    assert row["landed_in"]


def test_bound_test_promotes_landed_to_verified(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _LANDED_ROW}, "add spec")
    repo.commit({"pkg/feature.py": "# implements TEST-R001\n"}, "Spec: TEST-R001")
    repo.commit(
        {"tests/test_feature.py": "# spec: TEST-R001\ndef test_feature() -> None:\n    assert True\n"},
        "add bound test",
    )

    assert repo.run("spec-status", "--write") == 0
    row = _by_id(repo)["TEST-R001"]
    assert row["delivery_state"] == "VERIFIED"
    assert row["verified_by"] == ["tests/test_feature.py:1"]


@pytest.mark.spec("PIPE-CONNSPEC-R002")
def test_json_embedded_test_source_does_not_bind_a_requirement(repo: Repo) -> None:
    """Historical provider source in JSON is data, even when decoded text is a marker."""
    repo.commit({"specs/demo/requirements.md": _LANDED_ROW}, "add spec")
    repo.commit({"pkg/feature.py": "# implements TEST-R001\n"}, "Spec: TEST-R001")

    marker = "@pytest.mark." + 'spec("TEST-R001")'
    historical_source = marker + "\ndef test_historical(): pass\n"
    expected_hash = hashlib.sha256(historical_source.encode("utf-8")).hexdigest()
    repo.commit(
        {"tests/fixtures/provider.json": json.dumps({"source": historical_source})},
        "record historical provider source",
    )

    decoded = json.loads((repo.root / "tests/fixtures/provider.json").read_text(encoding="utf-8"))["source"]
    assert decoded.encode("utf-8") == historical_source.encode("utf-8")
    assert hashlib.sha256(decoded.encode("utf-8")).hexdigest() == expected_hash

    assert repo.run("spec-status", "--write") == 0
    row = _by_id(repo)["TEST-R001"]
    assert row["delivery_state"] == "LANDED"
    assert row["verified_by"] == []

    repo.commit(
        {
            "tests/test_python.py": marker + "\ndef test_real_python_marker(): pass\n",
            "tests/test_rust.rs": "// spec: " + "TEST-R001\n#[test] fn test_real_rust_marker() {}\n",
        },
        "add executable marker sources",
    )
    assert repo.run("spec-status", "--write") == 0
    row = _by_id(repo)["TEST-R001"]
    assert row["delivery_state"] == "VERIFIED"
    assert row["verified_by"] == ["tests/test_python.py:1", "tests/test_rust.rs:1"]


def test_retired_row_is_excluded_from_rollup_and_tally(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _RETIRED_ROW}, "add spec")

    assert repo.run("spec-status", "--write") == 0
    status = _status(repo)
    row = status["requirements"][0]
    assert row["delivery_state"] == "RETIRED"
    assert row["retired_reason"] == "superseded by TEST-R003"
    assert status["delivery_state"] == "RETIRED"


def test_parent_rollup_is_the_minimum_of_its_children(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _ROLLUP_ROWS}, "add spec")
    repo.commit({"pkg/a.py": "# a\n"}, "Spec: TEST-R010.1, TEST-R010.2")
    repo.commit(
        {"tests/test_a.py": "# spec: TEST-R010.1\ndef test_a() -> None:\n    assert True\n"},
        "verify child one",
    )

    assert repo.run("spec-status", "--write") == 0
    by_id = _by_id(repo)
    assert by_id["TEST-R010.1"]["delivery_state"] == "VERIFIED"
    assert by_id["TEST-R010.2"]["delivery_state"] == "LANDED"
    assert by_id["TEST-R010"]["delivery_state"] == "LANDED"
    assert by_id["TEST-R010"]["rollup_of"] == ["TEST-R010.1", "TEST-R010.2"]
    assert by_id["TEST-R010"]["landed_in"] == by_id["TEST-R010.1"]["landed_in"]
    assert by_id["TEST-R010"]["verified_by"] == []


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_verified_rollup_carries_its_childrens_evidence(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _ROLLUP_ROWS}, "add spec")
    repo.commit({"pkg/a.py": "# a\n"}, "Spec: TEST-R010.1, TEST-R010.2")
    repo.commit(
        {
            "tests/test_a.py": "# spec: TEST-R010.1\ndef test_a() -> None:\n    assert True\n",
            "tests/test_b.py": "# spec: TEST-R010.2\ndef test_b() -> None:\n    assert True\n",
        },
        "verify both children",
    )

    assert repo.run("spec-status", "--write") == 0
    parent = _by_id(repo)["TEST-R010"]
    assert parent["delivery_state"] == "VERIFIED"
    assert parent["landed_in"], "a delivered rollup names its landing commits"
    assert parent["verified_by"] == ["tests/test_a.py:1", "tests/test_b.py:1"]


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_rollup_evidence_is_stable_across_regenerations(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _ROLLUP_ROWS}, "add spec")
    repo.commit({"pkg/b.py": "# b\n"}, "Spec: TEST-R010.2")
    repo.commit({"pkg/a.py": "# a\n"}, "Spec: TEST-R010.1")

    assert repo.run("spec-status", "--write") == 0
    first = _status(repo)
    assert len(first["requirements"][0]["landed_in"]) == 2
    assert repo.run("spec-status", "--write") == 0
    assert _status(repo) == first
    assert repo.run("spec-status") == 0


def test_reverted_commit_does_not_count_as_landed(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _REVERT_ROW}, "add spec")
    landing_sha = repo.commit({"pkg/b.py": "# b\n"}, "Spec: TEST-R030")
    repo.commit(
        {"pkg/b.py": "# b removed\n"},
        f"Revert previous change\n\nThis reverts commit {landing_sha}.",
    )

    assert repo.run("spec-status", "--write") == 0
    row = _by_id(repo)["TEST-R030"]
    assert row["delivery_state"] == "SPECIFIED"
    assert row["landed_in"] == []


def test_revert_naming_a_commit_absent_from_this_clone_is_tolerated(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _REVERT_ROW}, "add spec")
    landing_sha = repo.commit({"pkg/b.py": "# b\n"}, "Spec: TEST-R030")
    repo.commit(
        {"pkg/c.py": "# c\n"},
        f"Revert an unpushed change\n\nThis reverts commit {'0' * 39}1.",
    )

    assert repo.run("spec-status", "--write") == 0
    row = _by_id(repo)["TEST-R030"]
    assert row["delivery_state"] == "LANDED"
    assert row["landed_in"] == [landing_sha[:12]]


def test_check_mode_fails_only_on_a_tracked_status_json(repo: Repo) -> None:
    """status.json is computed, never committed: an untracked copy passes, a tracked one fails."""
    repo.commit({"specs/demo/requirements.md": _STALE_ROW}, "add spec")
    assert repo.run("spec-status") == 0
    assert repo.run("spec-status", "--write") == 0
    assert repo.run("spec-status") == 0  # the written copy is untracked

    repo.commit({"specs/demo/status.json": "{}\n"}, "track generated status")
    assert repo.run("spec-status") == 1


def test_no_specs_directory_is_a_clean_pass(repo: Repo) -> None:
    assert repo.run("spec-status") == 0
    assert not (Path(repo.root) / "specs").exists()


_MERGE_ROWS = (
    "# demo\n\n| ID | Requirement |\n|---|---|\n"
    "| `TEST-R001` | **Main-side feature.** |\n"
    "| `TEST-R002` | **Incoming-side feature.** |\n"
)


def _pending_merge_with_two_features(repo: Repo) -> tuple[str, str]:
    repo.commit({"specs/demo/requirements.md": _MERGE_ROWS}, "add merge fixture spec")
    repo.git("checkout", "-qb", "incoming")
    incoming = repo.commit({"pkg/incoming.py": "# TEST-R002\n"}, "Spec: TEST-R002")
    repo.commit({"pkg/exempt.py": "# fixture\n"}, "Spec: none (fixture exemption)")
    repo.commit(
        {"tests/test_incoming.py": "# spec: TEST-R002\ndef test_incoming() -> None:\n    assert True\n"},
        "bind incoming test",
    )
    repo.git("checkout", "-q", "main")
    main = repo.commit({"pkg/main.py": "# TEST-R001\n"}, "Spec: TEST-R001")
    repo.commit(
        {"tests/test_main.py": "# spec: TEST-R001\ndef test_main() -> None:\n    assert True\n"},
        "bind main test",
    )
    repo.git("merge", "--no-commit", "--no-ff", "incoming")
    return main, incoming


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_default_spec_status_uses_both_sides_of_pending_merge(repo: Repo) -> None:
    main_landing, incoming_landing = _pending_merge_with_two_features(repo)
    head_before = repo.git("rev-parse", "HEAD").strip()
    tree_before = repo.git("write-tree").strip()
    merge_head_before = repo.git("rev-parse", "MERGE_HEAD").strip()

    assert repo.run("spec-status", "--write") == 0

    rows = _by_id(repo)
    for spec_id, commit, binding in (
        ("TEST-R001", main_landing, "tests/test_main.py:1"),
        ("TEST-R002", incoming_landing, "tests/test_incoming.py:1"),
    ):
        assert rows[spec_id]["delivery_state"] == "VERIFIED"
        assert rows[spec_id]["landed_in"] == [commit[:12]]
        assert rows[spec_id]["verified_by"] == [binding]
    all_receipts = [sha for row in rows.values() for sha in row["landed_in"]]
    assert all_receipts == [main_landing[:12], incoming_landing[:12]]
    assert repo.git("rev-parse", "HEAD").strip() == head_before
    assert repo.git("write-tree").strip() == tree_before
    assert repo.git("rev-parse", "MERGE_HEAD").strip() == merge_head_before


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_explicit_head_keeps_requested_premerge_history(repo: Repo) -> None:
    _, incoming_landing = _pending_merge_with_two_features(repo)

    assert repo.run("spec-status", "--head", "HEAD", "--write") == 0

    rows = _by_id(repo)
    assert rows["TEST-R001"]["delivery_state"] == "VERIFIED"
    assert rows["TEST-R002"]["delivery_state"] == "SPECIFIED"
    assert rows["TEST-R002"]["landed_in"] == []
    assert incoming_landing[:12] not in rows["TEST-R001"]["landed_in"]


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_unresolved_pending_merge_fails_closed_without_status_write(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _MERGE_ROWS, "pkg/conflict.py": "base\n"}, "fixture")
    repo.git("checkout", "-qb", "incoming")
    repo.commit({"pkg/conflict.py": "incoming\n"}, "incoming edit")
    repo.git("checkout", "-q", "main")
    repo.commit({"pkg/conflict.py": "main\n"}, "main edit")
    with pytest.raises(subprocess.CalledProcessError):
        repo.git("merge", "--no-commit", "--no-ff", "incoming")

    assert repo.run("spec-status", "--write") == 2
    assert not (repo.root / "specs/demo/status.json").exists()


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_pending_merge_fails_closed_when_worktree_differs_from_index(repo: Repo) -> None:
    _pending_merge_with_two_features(repo)
    (repo.root / "pkg/main.py").write_text("# unstaged edit\n", encoding="utf-8")

    assert repo.run("spec-status", "--write") == 2
    assert not (repo.root / "specs/demo/status.json").exists()


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_explicit_head_is_honored_during_unresolved_pending_merge(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _MERGE_ROWS, "pkg/conflict.py": "base\n"}, "fixture")
    repo.git("checkout", "-qb", "incoming")
    repo.commit({"pkg/conflict.py": "incoming\n"}, "incoming edit")
    repo.git("checkout", "-q", "main")
    repo.commit({"pkg/conflict.py": "main\n"}, "main edit")
    with pytest.raises(subprocess.CalledProcessError):
        repo.git("merge", "--no-commit", "--no-ff", "incoming")

    assert repo.run("spec-status", "--head", "HEAD", "--write") == 0
    rows = _by_id(repo)
    assert rows["TEST-R001"]["delivery_state"] == "SPECIFIED"
    assert rows["TEST-R002"]["delivery_state"] == "SPECIFIED"
    assert rows["TEST-R001"]["landed_in"] == []
    assert rows["TEST-R002"]["landed_in"] == []


def test_same_line_shorthand_inherits_prefix() -> None:
    from pipelines_hooks.specs.ids import expand_ranges

    out = expand_ranges("Spec: TUI-RUNTIME-R001.1, R001.2, R001.3\nR009 alone")
    assert "TUI-RUNTIME-R001.2" in out and "TUI-RUNTIME-R001.3" in out
    assert "-R009" not in out


_LEGACY_ROW = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R050` | **Legacy landing.** |\n"


def test_frozen_legacy_landings_survive_untracking_status(repo: Repo) -> None:
    """Cutover: v1 merged_head evidence is frozen, then status.json is untracked without losing it."""
    repo.commit({"specs/demo/requirements.md": _LEGACY_ROW}, "add spec")
    sha = repo.commit({"pkg/legacy.py": "# old work\n"}, "old work without an ID")
    v1 = {
        "schema_version": 1,
        "requirements": [
            {
                "id": "TEST-R050",
                "delivery_state": "LANDED",
                "evidence": [{"kind": "merged_head", "result": "passed", "commit": sha}],
            }
        ],
    }
    repo.commit({"specs/demo/status.json": json.dumps(v1)}, "v1 status")
    assert repo.run("spec-status", "--freeze-legacy") == 0
    frozen = (repo.root / ".config/spec-legacy-landings.json").read_text(encoding="utf-8")
    repo.git("rm", "-q", "--cached", "specs/demo/status.json")
    repo.commit({".config/spec-legacy-landings.json": frozen}, "untrack status")

    assert repo.run("spec-status", "--write") == 0
    first = (repo.root / "specs/demo/status.json").read_text(encoding="utf-8")
    assert _by_id(repo)["TEST-R050"]["delivery_state"] == "LANDED"
    assert repo.run("spec-status", "--write") == 0
    assert (repo.root / "specs/demo/status.json").read_text(encoding="utf-8") == first
    assert repo.run("spec-status") == 0


@pytest.mark.spec("PIPE-PAGES-R012.2")
def test_source_declarations_survive_status_regeneration(repo: Repo) -> None:
    """Status regeneration keeps source metadata in the dashboard's source documents."""
    requirements = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R051` | **Source-backed delivery.** |\n"
    repo.commit(
        {
            "specs/demo/spec.md": "# DEMO — Source-backed delivery\n\nCode: pkg/feature.py\n",
            "specs/demo/plan.md": "# Plan\n\nCode: tests/test_feature.py\n",
            "specs/demo/requirements.md": requirements,
            "pkg/feature.py": "def feature():\n    return True\n",
            "tests/test_feature.py": "def test_feature():\n    assert True\n",
        },
        "declare source-backed delivery",
    )
    assert repo.run("spec-status", "--write") == 0
    status_path = repo.root / "specs/demo/status.json"
    first_status = json.loads(status_path.read_text(encoding="utf-8"))
    assert set(first_status) == {
        "schema_version",
        "spec_id",
        "owner_repo",
        "delivery_state",
        "requirement_ids",
        "requirements",
    }
    first_row = first_status["requirements"][0]
    assert set(first_row) == {"id", "title", "delivery_state", "landed_in", "verified_by"}

    def dashboard_refs() -> list[dict]:
        snapshot = {
            "repository": "Knuckles-Team/demo",
            "revision": repo.git("rev-parse", "HEAD").strip(),
            "records": read_records(repo.root, {"sources": [{"glob": "specs/*/status.json"}]}),
        }
        enrich_records(repo.root, snapshot)
        return snapshot["records"][0]["code_refs"]

    first_refs = dashboard_refs()
    assert {row["role"] for row in first_refs} == {"implementation", "test"}
    assert {row["declared_in"] for row in first_refs} == {"specs/demo/spec.md", "specs/demo/plan.md"}

    repo.commit({"pkg/landing.py": "# implementation\n"}, "Spec: TEST-R051")
    assert repo.run("spec-status", "--write") == 0
    second_status = json.loads(status_path.read_text(encoding="utf-8"))
    assert second_status["requirements"][0]["delivery_state"] == "LANDED"
    assert set(second_status["requirements"][0]) == set(first_row)
    second_refs = dashboard_refs()
    assert [{key: value for key, value in row.items() if key != "url"} for row in second_refs] == [
        {key: value for key, value in row.items() if key != "url"} for row in first_refs
    ]
    current_revision = repo.git("rev-parse", "HEAD").strip()
    assert all(f"/blob/{current_revision}/" in row["url"] for row in second_refs)
    assert repo.run("spec-status") == 0


def test_two_branches_landing_the_same_spec_merge_without_conflict(repo: Repo) -> None:
    """Concurrent PRs on one spec carry only source; status is derived after the merge."""
    rows = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R060` | **One.** |\n| `TEST-R061` | **Two.** |\n"
    repo.commit({"specs/demo/requirements.md": rows}, "add spec")
    base = repo.git("rev-parse", "--abbrev-ref", "HEAD").strip()
    repo.git("checkout", "-q", "-b", "lane-a")
    repo.commit({"pkg/a.py": "# a\n"}, "land a\n\nSpec: TEST-R060")
    repo.git("checkout", "-q", base)
    repo.git("checkout", "-q", "-b", "lane-b")
    repo.commit({"pkg/b.py": "# b\n"}, "land b\n\nSpec: TEST-R061")
    repo.git("checkout", "-q", base)
    repo.git("merge", "-q", "--ff-only", "lane-a")
    repo.git("rebase", "-q", base, "lane-b")  # a rebase-merge of lane-b: no conflict
    assert repo.run("spec-status", "--write") == 0
    rows_by_id = _by_id(repo)
    assert rows_by_id["TEST-R060"]["delivery_state"] == "LANDED"
    assert rows_by_id["TEST-R061"]["delivery_state"] == "LANDED"


def test_reverting_a_merge_undoes_its_member_commits(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _REVERT_ROW}, "add spec")
    base = repo.git("rev-parse", "--abbrev-ref", "HEAD").strip()
    repo.git("checkout", "-q", "-b", "feature")
    repo.commit({"pkg/r030.py": "# r030\n"}, "Spec: TEST-R030")
    repo.git("checkout", "-q", base)
    repo.git("merge", "-q", "--no-ff", "-m", "merge feature", "feature")
    merge = repo.git("rev-parse", "HEAD").strip()
    repo.git("revert", "-m", "1", "--no-edit", merge)

    assert repo.run("spec-status", "--write") == 0
    assert _by_id(repo)["TEST-R030"]["delivery_state"] == "SPECIFIED"


@pytest.mark.spec("PIPE-CONNSPEC-R008")
def test_canonical_title_controls_generated_identity(repo):
    files = {
        "specs/demo/requirements.md": _LANDED_ROW,
        "specs/demo/spec.md": "# TEST — Canonical identity\n",
    }
    repo.commit(files, "declare canonical spec identity")
    assert repo.run("spec-status", "--write") == 0
    assert _status(repo)["spec_id"] == "TEST"
    assert _status(repo)["requirement_ids"] == ["TEST-R001"]
    assert repo.run("spec-status") == 0
