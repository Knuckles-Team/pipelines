"""commit-identity (commit-time, pending) check: FR-2 (P-2, N-2).

Every identity here is an obviously synthetic ``*.invalid`` fixture, never a
real contributor.
"""

from __future__ import annotations

import pytest

from tests.hooks.conftest import Repo, set_local_identity, stage_file, write_identity_allowlist

ALLOWED = {"name": "Example Author", "email": "author@example.invalid"}
OTHER = {"name": "Example Reviewer", "email": "reviewer@example.invalid"}
OUTSIDE_NAME = "Outside Contributor"
OUTSIDE_EMAIL = "outside@example.invalid"


def test_p2_commit_time_accepts_an_allowlisted_author_and_committer(repo: Repo) -> None:
    write_identity_allowlist(repo.root, [ALLOWED, OTHER])
    set_local_identity(repo.root, name=ALLOWED["name"], email=ALLOWED["email"])
    stage_file(repo.root)
    assert repo.run("commit-identity") == 0


def test_n2_commit_time_rejects_an_identity_outside_the_allowlist_naming_only_the_field(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    write_identity_allowlist(repo.root, [ALLOWED, OTHER])
    set_local_identity(repo.root, name=OUTSIDE_NAME, email=OUTSIDE_EMAIL)
    stage_file(repo.root)
    assert repo.run("commit-identity") == 1
    output = capsys.readouterr().out
    assert "author" in output
    assert OUTSIDE_NAME not in output
    assert ALLOWED["name"] not in output
    assert OTHER["name"] not in output


def test_commit_time_with_nothing_staged_is_a_no_op_pass(repo: Repo) -> None:
    """No allowlist is even required: there is no commit being formed yet."""
    assert repo.run("commit-identity") == 0
