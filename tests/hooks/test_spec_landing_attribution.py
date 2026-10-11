"""Only explicit declarations provide new landing evidence."""

import json

import pytest

from tests.hooks.conftest import Repo


@pytest.mark.parametrize("declaration", [
    "Spec: TEST-R001.1",
    "ship vocabulary\n\nSpec: TEST-R001.1",
])
def test_pending_sibling_in_prose_does_not_land(repo: Repo, declaration: str) -> None:
    # spec: PIPE-CONNSPEC-R001
    repo.commit({"specs/demo/requirements.md": (
        "| ID | Requirement |\n|---|---|\n"
        "| TEST-R001.1 | Vocabulary. |\n| TEST-R001.2 | Integration. |\n"
    )}, "spec")
    sha = repo.commit({"pkg/a.py": "value = 1\n"}, (
        declaration + "\n\nKeep integration open as TEST-R001.2.\n\n"
        "Spec: TEST-R001.1"
    ))
    assert repo.run("spec-status", "--write") == 0
    rows = json.loads((repo.root / "specs/demo/status.json").read_text())["requirements"]
    assert rows[0]["delivery_state"] == "LANDED"
    assert rows[0]["landed_in"] == [sha[:12]]
    assert rows[1]["delivery_state"] == "SPECIFIED"
    assert rows[1]["landed_in"] == []


@pytest.mark.parametrize("message", [
    "Discuss TEST-R001 without implementing it",
    "maintenance\n\nSpec: none (TEST-R001 remains pending)",
])
def test_prose_and_none_reason_are_not_landings(repo: Repo, message: str) -> None:
    # spec: PIPE-CONNSPEC-R001
    repo.commit({"specs/demo/requirements.md": (
        "| ID | Requirement |\n|---|---|\n| TEST-R001 | Pending. |\n"
    )}, "spec")
    repo.commit({"pkg/a.py": "value = 1\n"}, message)
    assert repo.run("spec-status", "--write") == 0
    row = json.loads((repo.root / "specs/demo/status.json").read_text())["requirements"][0]
    assert row["delivery_state"] == "SPECIFIED"
    assert row["landed_in"] == []


def test_multiple_trailers_keep_ranges_and_shorthand(repo: Repo) -> None:
    # spec: PIPE-CONNSPEC-R001
    from pipelines_hooks.specs.git_log import landing_commits
    from pipelines_hooks.specs.records import mentioned_tokens

    sha = repo.commit({"pkg/a.py": "value = 1\n"}, (
        "ship\n\nSpec: TEST-R001..R003\nSpec: TEST-R004.1, R004.2"
    ))
    assert mentioned_tokens(landing_commits(repo.root, "HEAD")) == {
        rid: {sha} for rid in (
            "TEST-R001", "TEST-R002", "TEST-R003", "TEST-R004.1", "TEST-R004.2"
        )
    }
