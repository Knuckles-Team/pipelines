"""A spec row names an existing path or marks it planned (PIPE-GATES-R093)."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.specs.row_paths import check_row_paths
from pipelines_hooks.specs.standard import ADVISORY_TAG, _fails


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.rs").write_text("")
    return tmp_path


def _check(tmp_path: Path, text: str) -> list[str]:
    return check_row_paths(_repo(tmp_path), {"requirements.md": text})


def test_a_missing_path_is_a_finding(tmp_path: Path) -> None:
    found = _check(tmp_path, "| `FOO-R001` | uses `src/gone.rs:12` | x |")
    assert len(found) == 1
    assert "FOO-R001" in found[0] and "src/gone.rs" in found[0] and "requirements.md:1" in found[0]


def test_an_existing_path_and_a_test_suffix_pass(tmp_path: Path) -> None:
    assert _check(tmp_path, "| `FOO-R001` | `src/real.rs::t::x` and `src/real.rs:3` | x |") == []


def test_a_planned_row_passes_including_continuation_lines(tmp_path: Path) -> None:
    text = "- `FOO-R001`: `src/later.rs::t`\n  (planned, L1): the change adds it.\n- `FOO-R002`: `src/gone.rs`\n"
    found = _check(tmp_path, text)
    assert len(found) == 1 and "FOO-R002" in found[0]


def test_urls_and_unknown_roots_are_not_repository_paths(tmp_path: Path) -> None:
    assert _check(tmp_path, "| `FOO-R001` | `https://x.io/a/b.rs` `elsewhere/a.rs` `src/*.rs` | x |") == []


def test_only_an_added_row_fails(tmp_path: Path) -> None:
    message = "analyze: " + _check(tmp_path, "| `FOO-R001` | `src/gone.rs` | x |")[0]
    spec_dir = tmp_path / "specs" / "foo"
    assert _fails(message, {"FOO-R001"}, set(), spec_dir, tmp_path) is True
    assert _fails(message, set(), {"specs/foo/requirements.md"}, spec_dir, tmp_path) is False
    assert ADVISORY_TAG
