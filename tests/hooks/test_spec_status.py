"""spec-status: generated specs/*/status.json (SPEC-STATUS-LIFECYCLE.md)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.hooks.conftest import Repo

_LANDED_ROW = (
    "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R001` | **Landed only.** |\n"
)
_RETIRED_ROW = (
    "# demo\n\n| ID | Requirement |\n|---|---|\n"
    "| `TEST-R002` | **RETIRED: superseded by TEST-R003.** |\n"
)
_ROLLUP_ROWS = (
    "# demo\n\n| ID | Requirement |\n|---|---|\n"
    "| `TEST-R010` | **Parent.** |\n"
    "| `TEST-R010.1` | **Child one.** |\n"
    "| `TEST-R010.2` | **Child two.** |\n"
)
_REVERT_ROW = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R030` | **Reverted feature.** |\n"
_STALE_ROW = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R040` | **Needs regeneration.** |\n"


def _status(repo: Repo) -> dict:
    return json.loads(
        (repo.root / "specs/demo/status.json").read_text(encoding="utf-8")
    )


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
        {
            "tests/test_feature.py": "# spec: TEST-R001\ndef test_feature() -> None:\n    assert True\n"
        },
        "add bound test",
    )

    assert repo.run("spec-status", "--write") == 0
    row = _by_id(repo)["TEST-R001"]
    assert row["delivery_state"] == "VERIFIED"
    assert row["verified_by"] == ["tests/test_feature.py:1"]


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
        {
            "tests/test_a.py": "# spec: TEST-R010.1\ndef test_a() -> None:\n    assert True\n"
        },
        "verify child one",
    )

    assert repo.run("spec-status", "--write") == 0
    by_id = _by_id(repo)
    assert by_id["TEST-R010.1"]["delivery_state"] == "VERIFIED"
    assert by_id["TEST-R010.2"]["delivery_state"] == "LANDED"
    assert by_id["TEST-R010"]["delivery_state"] == "LANDED"
    assert by_id["TEST-R010"]["rollup_of"] == ["TEST-R010.1", "TEST-R010.2"]


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


def test_check_mode_fails_on_a_stale_status_json(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _STALE_ROW}, "add spec")

    assert repo.run("spec-status") == 1

    assert repo.run("spec-status", "--write") == 0
    assert repo.run("spec-status") == 0

    repo.commit({"pkg/c.py": "# c\n"}, "Spec: TEST-R040")
    assert repo.run("spec-status") == 1


def test_no_specs_directory_is_a_clean_pass(repo: Repo) -> None:
    assert repo.run("spec-status") == 0
    assert not (Path(repo.root) / "specs").exists()


def test_same_line_shorthand_inherits_prefix() -> None:
    from pipelines_hooks.specs.ids import expand_ranges

    out = expand_ranges("Spec: TUI-RUNTIME-R001.1, R001.2, R001.3\nR009 alone")
    assert "TUI-RUNTIME-R001.2" in out and "TUI-RUNTIME-R001.3" in out
    assert "-R009" not in out


_LEGACY_ROW = (
    "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R050` | **Legacy landing.** |\n"
)


def test_regeneration_is_idempotent_and_keeps_legacy_landings(repo: Repo) -> None:
    """v1 merged_head evidence becomes v2 landed_in; regenerating must carry it forward."""
    repo.commit({"specs/demo/requirements.md": _LEGACY_ROW}, "add spec")
    sha = repo.commit({"pkg/legacy.py": "# old work\n"}, "old work without an ID")
    v1 = {
        "schema_version": 1,
        "spec_id": "demo",
        "owner_repo": "demo",
        "requirements": [
            {
                "id": "TEST-R050",
                "delivery_state": "LANDED",
                "evidence": [
                    {"kind": "merged_head", "result": "passed", "commit": sha}
                ],
            }
        ],
    }
    repo.commit({"specs/demo/status.json": json.dumps(v1)}, "v1 status")

    assert repo.run("spec-status", "--write") == 0
    first = (repo.root / "specs/demo/status.json").read_text(encoding="utf-8")
    assert _by_id(repo)["TEST-R050"]["delivery_state"] == "LANDED"
    repo.commit({"specs/demo/status.json": first}, "v2 status")

    assert repo.run("spec-status", "--write") == 0
    assert (repo.root / "specs/demo/status.json").read_text(encoding="utf-8") == first
    assert repo.run("spec-status") == 0


_LANDED_ROW_A = (
    "# a\n\n| ID | Requirement |\n|---|---|\n| `A-R001` | **Landed only.** |\n"
)
_LANDED_ROW_B = (
    "# b\n\n| ID | Requirement |\n|---|---|\n| `B-R001` | **Landed only.** |\n"
)


def test_changed_only_skips_an_untouched_stale_dir(repo: Repo) -> None:
    """A PR touching spec A passes under --changed-only even while B is stale."""
    repo.commit(
        {
            "specs/a/requirements.md": _LANDED_ROW_A,
            "specs/b/requirements.md": _LANDED_ROW_B,
        },
        "add specs a and b",
    )
    assert repo.run("spec-status", "--write") == 0
    repo.commit(
        {
            "specs/a/status.json": (repo.root / "specs/a/status.json").read_text(
                encoding="utf-8"
            ),
            "specs/b/status.json": (repo.root / "specs/b/status.json").read_text(
                encoding="utf-8"
            ),
        },
        "commit generated status",
    )

    # main advances on spec b without this PR: hand-drift b's committed status.json.
    drifted = json.loads(
        (repo.root / "specs/b/status.json").read_text(encoding="utf-8")
    )
    drifted["delivery_state"] = "LANDED"
    repo.commit(
        {"specs/b/status.json": json.dumps(drifted)}, "simulate b drift on main"
    )

    base = repo.git("rev-parse", "HEAD").strip()

    # This PR only lands and regenerates spec a.
    repo.commit({"pkg/a.py": "# a\n"}, "land a\n\nSpec: A-R001")
    assert repo.run("spec-status", "--base-ref", base, "--changed-only", "--write") == 0
    repo.commit(
        {
            "specs/a/status.json": (repo.root / "specs/a/status.json").read_text(
                encoding="utf-8"
            )
        },
        "regenerate a status",
    )

    # The scoped --write never touched b: it is still drifted.
    assert (
        json.loads((repo.root / "specs/b/status.json").read_text(encoding="utf-8"))[
            "delivery_state"
        ]
        == "LANDED"
    )

    assert repo.run("spec-status") == 1  # full-repo mode still catches b's staleness
    assert repo.run("spec-status", "--base-ref", base, "--changed-only") == 0


def test_changed_only_still_fails_when_the_touched_dir_is_stale(repo: Repo) -> None:
    """A PR touching spec A fails under --changed-only when A itself is stale."""
    repo.commit({"specs/a/requirements.md": _LANDED_ROW_A}, "add spec a")
    assert repo.run("spec-status", "--write") == 0
    repo.commit(
        {
            "specs/a/status.json": (repo.root / "specs/a/status.json").read_text(
                encoding="utf-8"
            )
        },
        "commit generated status",
    )

    base = repo.git("rev-parse", "HEAD").strip()
    # Lands A-R001 (via the Spec: trailer) without regenerating status.json.
    repo.commit({"pkg/a.py": "# a\n"}, "land a\n\nSpec: A-R001")

    assert repo.run("spec-status", "--base-ref", base, "--changed-only") == 1


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
