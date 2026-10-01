"""commit-identity-range (push-time and CI re-verification): FR-3, FR-4 (P-3/N-3, P-4/N-4).

Every identity here is an obviously synthetic ``*.invalid`` fixture, never a
real contributor. Each test pins ``--base`` to the fixture's own starting
commit so only the commits a test makes are ever in scope.
"""

from __future__ import annotations

import pytest

from tests.hooks.conftest import Repo, commit_as, write_identity_allowlist

ALLOWED = {"name": "Example Author", "email": "author@example.invalid"}
OTHER = {"name": "Example Reviewer", "email": "reviewer@example.invalid"}
OUTSIDE_NAME = "Outside Contributor"
OUTSIDE_EMAIL = "outside@example.invalid"


def test_p3_a_fully_matching_outgoing_range_succeeds(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    write_identity_allowlist(repo.root, [ALLOWED, OTHER])
    commit_as(repo.root, name=ALLOWED["name"], email=ALLOWED["email"], message="one")
    commit_as(repo.root, name=OTHER["name"], email=OTHER["email"], message="two")
    assert repo.run("commit-identity-range", "--base", base) == 0


def test_n3_one_non_matching_commit_anywhere_in_range_is_refused_even_when_the_tip_matches(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    write_identity_allowlist(repo.root, [ALLOWED, OTHER])
    commit_as(repo.root, name=OUTSIDE_NAME, email=OUTSIDE_EMAIL, message="buried-bad")
    commit_as(repo.root, name=ALLOWED["name"], email=ALLOWED["email"], message="tip-is-fine")
    assert repo.run("commit-identity-range", "--base", base) == 1


OUTSIDE = {"name": OUTSIDE_NAME, "email": OUTSIDE_EMAIL}


@pytest.mark.parametrize(
    ("committer", "author", "expect_named", "expect_silent"),
    [
        (ALLOWED, OUTSIDE, "author", "committer"),
        (OUTSIDE, ALLOWED, "committer", "author"),
    ],
    ids=["mismatched-author", "mismatched-committer"],
)
def test_n3_names_only_the_one_mismatched_field_for_a_split_identity(
    repo: Repo,
    capsys: pytest.CaptureFixture[str],
    committer: dict[str, str],
    author: dict[str, str],
    expect_named: str,
    expect_silent: str,
) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    write_identity_allowlist(repo.root, [ALLOWED])
    commit_as(repo.root, name=committer["name"], email=committer["email"], message="split", author=f"{author['name']} <{author['email']}>")
    assert repo.run("commit-identity-range", "--base", base) == 1
    output = capsys.readouterr().out
    assert expect_named in output
    assert expect_silent not in output
    assert OUTSIDE_NAME not in output


def test_p4_ci_reverification_accepts_a_fully_matching_range(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    write_identity_allowlist(repo.root, [ALLOWED])
    commit_as(repo.root, name=ALLOWED["name"], email=ALLOWED["email"], message="ci-good")
    monkeypatch.setenv("CI", "true")
    assert repo.run("commit-identity-range", "--base", base) == 0


def test_n4_ci_reverification_rejects_a_range_even_when_the_local_check_was_bypassed(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    write_identity_allowlist(repo.root, [ALLOWED])
    # No commit-identity invocation ever ran for this commit: it simulates a
    # skipped or bypassed local commit-time hook. Only the range re-check (what
    # CI re-runs) examines it.
    commit_as(repo.root, name=OUTSIDE_NAME, email=OUTSIDE_EMAIL, message="ci-bad")
    monkeypatch.setenv("CI", "true")
    assert repo.run("commit-identity-range", "--base", base) == 1


def test_a_malformed_base_revision_cannot_run(repo: Repo) -> None:
    write_identity_allowlist(repo.root, [ALLOWED])
    assert repo.run("commit-identity-range", "--base", "not-a-real-revision") == 2
