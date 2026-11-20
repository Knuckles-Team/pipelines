"""Only explicit declarations provide new landing evidence."""

import json

import pytest

from tests.hooks.conftest import Repo


@pytest.mark.parametrize(
    "declaration",
    [
        "Spec: TEST-R001.1",
        "ship vocabulary\n\nSpec: TEST-R001.1",
    ],
)
def test_pending_sibling_in_prose_does_not_land(repo: Repo, declaration: str) -> None:
    # spec: PIPE-CONNSPEC-R001
    repo.commit(
        {
            "specs/demo/requirements.md": (
                "| ID | Requirement |\n|---|---|\n| TEST-R001.1 | Vocabulary. |\n| TEST-R001.2 | Integration. |\n"
            )
        },
        "spec",
    )
    sha = repo.commit(
        {"pkg/a.py": "value = 1\n"}, (declaration + "\n\nKeep integration open as TEST-R001.2.\n\nSpec: TEST-R001.1")
    )
    assert repo.run("spec-status", "--write") == 0
    rows = json.loads((repo.root / "specs/demo/status.json").read_text())["requirements"]
    assert rows[0]["delivery_state"] == "LANDED"
    assert rows[0]["landed_in"] == [sha[:12]]
    assert rows[1]["delivery_state"] == "SPECIFIED"
    assert rows[1]["landed_in"] == []


@pytest.mark.parametrize(
    "message",
    [
        "Discuss TEST-R001 without implementing it",
        "maintenance\n\nSpec: none (TEST-R001 remains pending)",
    ],
)
def test_prose_and_none_reason_are_not_landings(repo: Repo, message: str) -> None:
    # spec: PIPE-CONNSPEC-R001
    repo.commit({"specs/demo/requirements.md": ("| ID | Requirement |\n|---|---|\n| TEST-R001 | Pending. |\n")}, "spec")
    repo.commit({"pkg/a.py": "value = 1\n"}, message)
    assert repo.run("spec-status", "--write") == 0
    row = json.loads((repo.root / "specs/demo/status.json").read_text())["requirements"][0]
    assert row["delivery_state"] == "SPECIFIED"
    assert row["landed_in"] == []


def test_multiple_trailers_keep_ranges_and_shorthand(repo: Repo) -> None:
    # spec: PIPE-CONNSPEC-R001
    from pipelines_hooks.specs.git_log import landing_commits
    from pipelines_hooks.specs.records import mentioned_tokens

    sha = repo.commit({"pkg/a.py": "value = 1\n"}, ("ship\n\nSpec: TEST-R001..R003\nSpec: TEST-R004.1, R004.2"))
    assert mentioned_tokens(landing_commits(repo.root, "HEAD")) == {
        rid: {sha} for rid in ("TEST-R001", "TEST-R002", "TEST-R003", "TEST-R004.1", "TEST-R004.2")
    }


@pytest.mark.spec("PIPE-CONNSPEC-R001")
def test_github_squash_message_keeps_source_spec_trailers(repo: Repo) -> None:
    """A squash commit's embedded source trailers remain landing evidence."""
    from pipelines_hooks.specs.git_log import landing_commits
    from pipelines_hooks.specs.records import mentioned_tokens

    message = """feat: admitted child lineage (#370)

* feat: admitted child lineage

Spec: TEST-R001
Co-Authored-By: Codex <codex@example.invalid>

* fix: refuse unbound lineage children

Spec: TEST-R001
Co-Authored-By: Codex <codex@example.invalid>

* chore(spec): refresh generated delivery evidence

Spec: none (generated status refresh)
Co-Authored-By: Codex <codex@example.invalid>

---------

Co-authored-by: Codex <codex@example.invalid>
"""
    sha = repo.commit({"pkg/lineage.py": "lineage = True\n"}, message)

    assert mentioned_tokens(landing_commits(repo.root, "HEAD")) == {"TEST-R001": {sha}}


_ATTR_SPEC = "| ID | Requirement |\n|---|---|\n| TEST-R001 | Delivered. |\n"
_ATTR_FILE = ".config/spec-landing-attributions.json"


def _attribution_repo(repo: Repo, product: dict[str, str] | None = None) -> str:
    """A repo whose marker commit carries no trailer; returns that commit's sha."""
    repo.commit({"specs/demo/requirements.md": _ATTR_SPEC}, "spec")
    return repo.commit(product or {"tests/test_a.py": "# spec: TEST-R001\ndef test_a():\n    pass\n"}, "add test")


def _attribute(repo: Repo, sha: str, rid: str = "TEST-R001") -> int:
    repo.write(_ATTR_FILE, json.dumps({rid: sha}))
    return repo.run("spec-status", "--write")


def _state(repo: Repo) -> dict:
    return json.loads((repo.root / "specs/demo/status.json").read_text())["requirements"][0]


def test_attribution_credits_the_commit_that_added_the_marker(repo: Repo) -> None:
    # spec: PIPE-CONNSPEC-R017
    sha = _attribution_repo(repo)
    assert _attribute(repo, sha) == 0
    assert _state(repo)["delivery_state"] == "VERIFIED"
    assert _state(repo)["landed_in"] == [sha[:12]]


def test_without_attribution_the_row_stays_specified(repo: Repo) -> None:
    # spec: PIPE-CONNSPEC-R017
    _attribution_repo(repo)
    assert repo.run("spec-status", "--write") == 0
    assert _state(repo)["delivery_state"] == "SPECIFIED"


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("not-hex", "not a 40-hex sha"),
        ("unknown", "is not reachable"),
        ("no-marker", "does not add a spec marker for TEST-R001"),
        ("docs-only", "touches no product path"),
        ("marker-removed", "no marker for TEST-R001 remains"),
        ("reverted", "is reverted"),
    ],
)
def test_an_invalid_attribution_is_refused_by_name(
    repo: Repo, capsys: pytest.CaptureFixture[str], case, reason
) -> None:
    # spec: PIPE-CONNSPEC-R017
    sha = _attribution_repo(repo)
    if case == "not-hex":
        sha = "xyz"
    elif case == "unknown":
        sha = "a" * 40
    elif case == "no-marker":
        sha = repo.commit({"pkg/b.py": "x = 1\n"}, "other")
    elif case == "docs-only":
        sha = repo.commit({"docs/a.md": "# spec: TEST-R001\n"}, "docs")
    elif case == "marker-removed":
        repo.commit({"tests/test_a.py": "def test_a():\n    pass\n"}, "drop marker")
    elif case == "reverted":
        repo.git("revert", "--no-edit", sha)
    assert _attribute(repo, sha) == 1
    out = capsys.readouterr().out
    assert "TEST-R001: " in out and reason in out
    assert _state(repo)["delivery_state"] == "SPECIFIED"


def test_an_attribution_only_adds_to_a_trailer_landing(repo: Repo) -> None:
    # spec: PIPE-CONNSPEC-R017
    sha = _attribution_repo(repo)
    trailer = repo.commit({"pkg/f.py": "x = 1\n"}, "feature\n\nSpec: TEST-R001")
    assert _attribute(repo, sha) == 0
    assert set(_state(repo)["landed_in"]) == {sha[:12], trailer[:12]}
