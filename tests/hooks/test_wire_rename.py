"""wire-rename: a renamed serialized name recomputes the files that digest it (PIPE-GATES-R067)."""

from __future__ import annotations

import pytest

from pipelines_hooks.code.wire_rename import glob_regex, renamed_identifiers
from tests.hooks.conftest import PYPROJECT, Repo

CONFIG = PYPROJECT + '\n[tool.pipelines_hooks.wire_rename]\ngolden = ["tests/golden/**", "receipts/*.json"]\n'
BASE = {
    "pyproject.toml": CONFIG,
    "pkg/wire.py": 'FIELD = "tool_call_id"\nOTHER = "plain_name"\n',
    "tests/golden/vectors.json": '{"tool_call_id": "abc", "digest": "0f"}\n',
}


@pytest.fixture
def base_repo(repo: Repo) -> Repo:
    repo.commit(BASE, "golden base")
    repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


@pytest.mark.spec("PIPE-GATES-R067")
def test_a_renamed_serialized_name_with_a_stale_golden_file_fails(
    base_repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    base_repo.commit({"pkg/wire.py": 'FIELD = "call_id"\nOTHER = "plain_name"\n'}, "rename")
    assert base_repo.run("wire-rename") == 1
    out = capsys.readouterr().out
    assert "tool_call_id" in out and "call_id" in out and "tests/golden/vectors.json" in out


@pytest.mark.spec("PIPE-GATES-R067")
def test_a_rename_with_a_recomputed_golden_file_passes(base_repo: Repo) -> None:
    base_repo.commit(
        {
            "pkg/wire.py": 'FIELD = "call_id"\nOTHER = "plain_name"\n',
            "tests/golden/vectors.json": '{"call_id": "abc", "digest": "1e"}\n',
        },
        "rename and recompute",
    )
    assert base_repo.run("wire-rename") == 0


@pytest.mark.spec("PIPE-GATES-R067")
def test_a_rename_of_an_unserialized_name_passes(base_repo: Repo) -> None:
    base_repo.commit({"pkg/wire.py": 'FIELD = "tool_call_id"\nOTHER = "plainer_name"\n'}, "rename unserialized")
    assert base_repo.run("wire-rename") == 0
    assert base_repo.run("wire-rename", "--base", "HEAD") == 0


@pytest.mark.spec("PIPE-GATES-R067")
def test_the_diff_reader_pairs_one_identifier_changes_only() -> None:
    diff = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n"
        '-A = "old_name"\n+A = "new_name"\n-b = 1 + 2\n+b = 1 + 2 + 3\n'
        "diff --git a/s.sql b/s.sql\n--- a/s.sql\n+++ b/s.sql\n@@ -1 +1 @@\n--- note\n+-- notes\n"
    )
    assert renamed_identifiers(diff) == [("s.sql", "note", "notes"), ("x.py", "old_name", "new_name")]
    assert glob_regex("tests/golden/**").fullmatch("tests/golden/a/b.json")
    assert not glob_regex("receipts/*.json").fullmatch("receipts/a/b.json")


@pytest.mark.spec("PIPE-GATES-R067")
def test_without_golden_globs_the_gate_covers_nothing(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert repo.run("wire-rename") == 0
    assert "no golden file globs" in capsys.readouterr().out
