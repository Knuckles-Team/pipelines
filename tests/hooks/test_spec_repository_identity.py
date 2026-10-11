"""Spec ownership follows repository identity, while landing receipts survive."""

import json

import pytest

from tests.hooks.conftest import Repo

_ROWS = "| ID | Requirement |\n|---|---|\n| TEST-R001 | Legacy landing. |\n"
_STATUS = "specs/demo/status.json"


@pytest.mark.parametrize("remote", [
    "https://github.com/Knuckles-Team/graph-os.git",
    "git@github.com:Knuckles-Team/graph-os.git",
    "ssh://git@gitlab.arpa:2222/team/graph-os.git/",
    "file:///srv/git/graph-os.git",
])
def test_new_owner_comes_from_remote(repo: Repo, remote: str) -> None:
    # spec: PIPE-CONNSPEC-R001
    repo.git("remote", "add", "origin", remote)
    repo.commit({"specs/demo/requirements.md": _ROWS}, "add spec")
    assert repo.run("spec-status", "--write") == 0
    assert json.loads((repo.root / _STATUS).read_text())["owner_repo"] == "graph-os"


@pytest.mark.parametrize("version", [1, 2])
def test_worktree_owner_repair_preserves_legacy_receipts(repo: Repo, version: int) -> None:
    # spec: PIPE-CONNSPEC-R001
    repo.git("remote", "add", "origin", "https://github.com/Knuckles-Team/graph-os.git")
    repo.commit({"specs/demo/requirements.md": _ROWS}, "add spec")
    sha = repo.commit({"pkg/legacy.py": "value = 1\n"}, "old implementation without ID")
    receipt = ({"evidence": [{"kind": "merged_head", "commit": sha}]} if version == 1
               else {"landed_in": [sha[:12]]})
    old = {"schema_version": version, "spec_id": "stable-spec", "owner_repo": "spec-standard-conform",
           "requirements": [{"id": "TEST-R001", "delivery_state": "LANDED", **receipt}]}
    repo.commit({_STATUS: json.dumps(old)}, "record historical evidence")
    worktree = repo.root.parent / "spec-standard-conform"
    repo.git("worktree", "add", "--detach", str(worktree), "HEAD")
    lane = Repo(worktree)
    assert lane.run("spec-status", "--write") == 0
    first = (worktree / _STATUS).read_text()
    status = json.loads(first)
    assert status["owner_repo"] == "graph-os"
    assert status["spec_id"] == "stable-spec"
    assert status["requirements"][0]["landed_in"] == [sha[:12]]
    assert status["requirements"][0]["delivery_state"] == "LANDED"
    assert lane.run("spec-status", "--write") == 0
    assert (worktree / _STATUS).read_text() == first
    assert lane.run("spec-status") == 0


@pytest.mark.parametrize("old_owner", [None, "stable-repository"])
@pytest.mark.parametrize("remotes", [[], ["https://github.com/"], ["/a/one.git", "/b/two.git"]])
def test_unavailable_identity_keeps_safe_fallback(repo: Repo, old_owner: str | None, remotes: list[str]) -> None:
    # spec: PIPE-CONNSPEC-R001
    for index, remote in enumerate(remotes):
        repo.git("remote", "add", f"remote-{index}", remote)
    repo.commit({"specs/demo/requirements.md": _ROWS, _STATUS: json.dumps({"owner_repo": old_owner})}, "add spec")
    assert repo.run("spec-status", "--write") == 0
    assert json.loads((repo.root / _STATUS).read_text())["owner_repo"] == (old_owner or repo.root.name)


@pytest.mark.parametrize("use_origin", [False, True])
def test_remote_selection_is_unambiguous(repo: Repo, use_origin: bool) -> None:
    # spec: PIPE-CONNSPEC-R001
    repo.git("remote", "add", "upstream", "git@github.com:team/upstream-repo.git")
    if use_origin:
        repo.git("remote", "add", "origin", "git@github.com:team/origin-repo.git")
    repo.commit({"specs/demo/requirements.md": _ROWS}, "add spec")
    assert repo.run("spec-status", "--write") == 0
    expected = "origin-repo" if use_origin else "upstream-repo"
    assert json.loads((repo.root / _STATUS).read_text())["owner_repo"] == expected
