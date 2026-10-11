"""Incomplete history must never erase existing spec landing receipts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs.generator import generate
from tests.hooks.conftest import Repo


def _receipt(sha: str, schema: int) -> dict:
    if schema == 1:
        return {"evidence": [{"kind": "merged_head", "commit": sha}]}
    return {"landed_in": [sha[:12]]}


def _history_with_receipts(repo: Repo, schema: int) -> str:
    rows = "# demo\n\n| ID | Requirement |\n|---|---|\n"
    rows += "".join(f"| `TEST-R00{i}` | **Feature {i}.** |\n" for i in range(1, 4))
    repo.commit({"specs/demo/requirements.md": rows}, "add spec")
    live = repo.commit({"pkg/live.py": "# live\n"}, "historical live work")
    reverted = repo.commit({"pkg/reverted.py": "# removed\n"}, "historical removed work")
    repo.git("revert", "--no-edit", reverted)
    repo.git("checkout", "-q", "-b", "unmerged")
    unreachable = repo.commit({"pkg/unmerged.py": "# unmerged\n"}, "unmerged work")
    repo.git("checkout", "-q", "main")
    old = {
        "schema_version": schema,
        "requirements": [
            {"id": f"TEST-R00{i}", **_receipt(sha, schema)}
            for i, sha in enumerate((live, reverted, unreachable), 1)
        ],
    }
    repo.commit({"specs/demo/status.json": json.dumps(old)}, "record historical receipts")
    return live


def _assert_refusal_preserves_files(shallow: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert shallow.git("rev-parse", "--is-shallow-repository").strip() == "true"
    status = shallow.root / "specs/demo/status.json"
    before = status.read_bytes()
    with pytest.raises(CannotRun, match="complete Git history"):
        generate(shallow.root, "HEAD")
    for args in ((), ("--write",), ("--write", "--changed-only")):
        assert shallow.run("spec-status", *args) == 2
        assert status.read_bytes() == before
        assert shallow.git("status", "--porcelain") == ""
    assert "git fetch --unshallow" in capsys.readouterr().err


@pytest.mark.parametrize("schema", [1, 2])
def test_shallow_history_refuses_without_writes_then_full_history_validates_receipts(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str], *, schema: int
) -> None:
    # spec: PIPE-CONNSPEC-R001
    live = _history_with_receipts(repo, schema)
    shallow = Repo(tmp_path / "shallow")
    repo.git("clone", "-q", "--depth=1", repo.root.as_uri(), str(shallow.root))
    _assert_refusal_preserves_files(shallow, capsys)
    shallow.git("fetch", "-q", "--unshallow")
    assert shallow.git("rev-parse", "--is-shallow-repository").strip() == "false"
    # Hosted PR jobs auto-scope to a base; the clone's origin/main is already HEAD.
    assert shallow.run("spec-status", "--write", "--base-ref", live) == 0
    status = shallow.root / "specs/demo/status.json"
    rows = json.loads(status.read_text(encoding="utf-8"))["requirements"]
    assert rows[0]["landed_in"] == [live[:12]]
    assert rows[0]["delivery_state"] == "LANDED"
    assert all(row["landed_in"] == [] for row in rows[1:])
    assert all(row["delivery_state"] == "SPECIFIED" for row in rows[1:])
    assert shallow.run("spec-status", "--base-ref", live) == 0


def test_shallow_repository_without_specs_is_a_clean_pass(repo: Repo, tmp_path: Path) -> None:
    # spec: PIPE-CONNSPEC-R001
    shallow = Repo(tmp_path / "shallow")
    repo.git("clone", "-q", "--depth=1", repo.root.as_uri(), str(shallow.root))
    assert shallow.run("spec-status", "--write") == 0
    assert not (shallow.root / "specs").exists()
