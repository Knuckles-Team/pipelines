"""dupehound-changed and jscpd-differential fire on planted clones; the register rots."""

from __future__ import annotations

import pytest

from pathlib import Path

from pipelines_hooks.clones.ledger import DistinctPair, partition
from pipelines_hooks.clones.ledger_text import digest_of, normalized_function_text
from tests.hooks.conftest import Repo


def _worker(name: str) -> str:
    return (
        f"def {name}(records, threshold):\n"
        "    totals = {}\n"
        "    for record in records:\n"
        "        key = record.get('group', 'none')\n"
        "        if record['score'] > threshold:\n"
        "            totals[key] = totals.get(key, 0) + record['score']\n"
        "        else:\n"
        "            totals[key] = totals.get(key, 0) - 1\n"
        "    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)\n"
        "    return [name for name, value in ranked if value > 0]\n"
    )


def _distinct(name: str) -> str:
    return (
        f"def {name}(path, mode):\n"
        "    with open(path, mode) as handle:\n"
        "        payload = handle.read()\n"
        "    lines = payload.splitlines()\n"
        "    longest = max(lines, key=len) if lines else ''\n"
        "    return len(lines), longest.strip().upper()\n"
    )


# spec: PIPE-GATES-R081
@pytest.mark.scanner("dupehound")
def test_dupehound_fires_on_a_staged_structural_clone(repo: Repo) -> None:
    repo.commit({"pkg/original.py": _worker("summarise")})
    repo.stage({"pkg/copy.py": _worker("tally").replace("records", "rows").replace("totals", "sums")})
    assert repo.run("dupehound-changed") == 1


@pytest.mark.scanner("dupehound")
def test_dupehound_passes_distinct_changed_source(repo: Repo) -> None:
    repo.commit({"pkg/original.py": _worker("summarise")})
    repo.stage({"pkg/other.py": "def other(value):\n    return str(value).upper()\n"})
    assert repo.run("dupehound-changed") == 0


# spec: PIPE-GATES-R078
@pytest.mark.scanner("jscpd")
def test_jscpd_differential_fires_only_on_a_new_pair(repo: Repo) -> None:
    block = "".join(_worker(f"variant_{index}") for index in range(1))
    base = repo.commit({"pkg/original.py": block})
    repo.commit({"pkg/unrelated.py": _distinct("unrelated")})
    assert repo.run("jscpd-differential", "--base-ref", base) == 0
    repo.commit({"pkg/copied.py": "# copy\n" + block})
    assert repo.run("jscpd-differential", "--base-ref", base) == 1
    assert repo.run("jscpd-census") == 0


def _in_class(name: str) -> str:
    return f"class {name}:\n" + "".join(f"    {line}\n" for line in _worker("run").splitlines()) + "\n"


# spec: PIPE-GATES-R078
@pytest.mark.scanner("jscpd")
def test_jscpd_same_file_pair_survives_a_line_shift_but_not_a_new_copy(repo: Repo) -> None:
    pair = _in_class("First") + _in_class("Second")
    base = repo.commit({"pkg/both.py": pair})
    shifted = "".join(f"LIMIT_{index} = {index}\n" for index in range(6)) + "\n" + pair
    repo.commit({"pkg/both.py": shifted})
    assert repo.run("jscpd-differential", "--base-ref", base) == 0
    repo.commit({"pkg/both.py": shifted + _in_class("Third")})
    assert repo.run("jscpd-differential", "--base-ref", base) == 1


# spec: PIPE-GATES-R081
def test_the_register_rots_when_a_reviewed_function_changes(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def left():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def right():\n    return 2\n", encoding="utf-8")
    left = digest_of(normalized_function_text(tmp_path / "a.py", 1, "left"))
    right = digest_of(normalized_function_text(tmp_path / "b.py", 1, "right"))
    pair = DistinctPair(
        "a.py", "left", left, "b.py", "right", right, "reviewed: " + "semantically unrelated " * 6, "2026-09-13"
    )
    finding = {
        "file": "a.py",
        "line": 1,
        "name": "left",
        "original_file": "b.py",
        "original_line": 1,
        "original_name": "right",
    }
    assert partition([finding], [pair], tmp_path)["unregistered"] == []
    (tmp_path / "b.py").write_text("def right():\n    return 3\n", encoding="utf-8")
    assert partition([finding], [pair], tmp_path)["changed"] == [finding]


def test_generated_spec_status_is_outside_the_jscpd_universe() -> None:
    # specs/*/status.json is generator output (pipelines-hook spec-status); two specs with
    # similar requirement rows produce structurally identical JSON that no author can dedupe.
    from pipelines_hooks.clones.contract import is_jscpd_path

    assert not is_jscpd_path("specs/portable-deployment/status.json")
    assert is_jscpd_path("arbora/api/ops/identity.py")


# spec: PIPE-GATES-R079
@pytest.mark.scanner("jscpd")
def test_a_comment_only_change_is_refused_not_passed(repo: Repo) -> None:
    base = repo.commit({"pkg/original.py": _distinct("original")})
    repo.commit({"pkg/notes.py": "".join(f"# a note about the module, line {index}\n" for index in range(12))})
    assert repo.run("jscpd-differential", "--base-ref", base) == 2
    repo.commit({"pkg/notes.py": "def real():\n    return 1\n"})  # a small file the scanner also reads nothing of
    assert repo.run("jscpd-differential", "--base-ref", base) == 2
    repo.commit({"pkg/other.py": _distinct("other_name").replace("path", "location")})
    assert repo.run("jscpd-differential", "--base-ref", base) == 0


# spec: PIPE-GATES-R079
@pytest.mark.scanner("jscpd")
def test_a_deletion_only_change_is_refused_not_passed(repo: Repo) -> None:
    repo.commit({"pkg/original.py": _distinct("original"), "pkg/extra.py": _distinct("extra")})
    base = repo.commit({"pkg/keep.py": _distinct("keep")})
    repo.git("rm", "-q", "--", "pkg/extra.py")
    repo.git("commit", "-q", "-m", "delete")
    assert repo.run("jscpd-differential", "--base-ref", base) == 2


# spec: PIPE-GATES-R080
@pytest.mark.scanner("jscpd")
def test_a_split_file_reports_zero_new_pairs_against_the_base(repo: Repo) -> None:
    first, second = _distinct("reader"), _worker("summarise")
    base = repo.commit({"pkg/both.py": first + "\n" + second})
    repo.commit({"pkg/both.py": first, "pkg/second.py": second})
    assert repo.run("jscpd-differential", "--base-ref", base) == 0


# spec: PIPE-GATES-R080
@pytest.mark.scanner("jscpd")
def test_a_moved_duplicate_is_not_new_but_a_further_copy_is(repo: Repo) -> None:
    block = _worker("summarise")
    repo.commit({"pkg/a.py": block, "pkg/b.py": "# b\n" + block})
    base = repo.commit({"pkg/keep.py": _distinct("keep")})
    repo.commit({"pkg/b.py": "x = 1\n", "pkg/c.py": "# c\n" + block})  # the copy moved from b to c
    assert repo.run("jscpd-differential", "--base-ref", base) == 0
    repo.commit({"pkg/d.py": "# d\n" + block})  # a third copy is new duplication
    assert repo.run("jscpd-differential", "--base-ref", base) == 1
