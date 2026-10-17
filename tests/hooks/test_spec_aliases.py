"""Spec ID prefix aliases (.config/spec-aliases.toml): historical evidence counts for the new ID."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs.aliases import (
    canonical_id,
    canonical_lists,
    canonical_sets,
    load_aliases,
)
from tests.hooks.conftest import Repo

_ALIASES = '"OLD-" = "NEW-"\n'


def _rows(*ids: str) -> str:
    body = "".join(f"| `{rid}` | **Row {rid}.** |\n" for rid in ids)
    return "# demo\n\n| ID | Requirement |\n|---|---|\n" + body


def _by_id(repo: Repo) -> dict[str, dict]:
    status = json.loads((repo.root / "specs/demo/status.json").read_text(encoding="utf-8"))
    return {row["id"]: row for row in status["requirements"]}


def _states(repo: Repo) -> dict[str, str]:
    return {rid: row["delivery_state"] for rid, row in _by_id(repo).items()}


def test_canonical_id_replaces_only_a_retired_prefix() -> None:
    aliases = {"OLD-": "NEW-"}
    assert canonical_id("OLD-RUNTIME-R001.2", aliases) == "NEW-RUNTIME-R001.2"
    assert canonical_id("NEW-R001", aliases) == "NEW-R001"
    assert canonical_id("XOLD-R001", aliases) == "XOLD-R001"


def test_canonical_maps_merge_old_and_new_evidence() -> None:
    aliases = {"OLD-": "NEW-"}
    assert canonical_sets({"OLD-R001": {"a"}, "NEW-R001": {"b"}}, aliases) == {"NEW-R001": {"a", "b"}}
    assert canonical_lists({"OLD-R001": ["x"], "NEW-R001": ["y"]}, aliases) == {"NEW-R001": ["x", "y"]}


def test_missing_alias_file_means_no_aliases(tmp_path: Path) -> None:
    assert load_aliases(tmp_path) == {}


@pytest.mark.parametrize(
    "text",
    ['"old-" = "NEW-"\n', '"OLD" = "NEW-"\n', '"OLD-" = 3\n', '"OLD-" = "OLD-"\n', '"A-" = "B-"\n"B-" = "C-"\n', "not toml ="],
)
def test_malformed_alias_file_cannot_run(tmp_path: Path, text: str) -> None:
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config/spec-aliases.toml").write_text(text, encoding="utf-8")
    with pytest.raises(CannotRun):
        load_aliases(tmp_path)


def test_rename_keeps_every_row_state(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _rows("OLD-R001", "OLD-R002", "OLD-R003")}, "add spec")
    repo.commit({"pkg/a.py": "# a\n"}, "land\n\nSpec: OLD-R001, OLD-R002")
    repo.commit({"tests/test_a.py": "# spec: OLD-R001\n"}, "bind")
    assert repo.run("spec-status", "--write") == 0
    before = {canonical_id(k, {"OLD-": "NEW-"}): v for k, v in _states(repo).items()}
    assert before == {"NEW-R001": "VERIFIED", "NEW-R002": "LANDED", "NEW-R003": "SPECIFIED"}
    repo.commit({"specs/demo/status.json": (repo.root / "specs/demo/status.json").read_text()}, "status")

    repo.commit(
        {
            ".config/spec-aliases.toml": _ALIASES,
            "specs/demo/requirements.md": _rows("NEW-R001", "NEW-R002", "NEW-R003"),
        },
        "rename\n\nSpec: none (rename)",
    )
    assert repo.run("spec-status", "--write") == 0
    assert _states(repo) == before


def test_old_status_landings_carry_forward_under_the_new_id(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _rows("OLD-R001")}, "add spec")
    sha = repo.commit({"pkg/a.py": "# a\n"}, "land\n\nSpec: OLD-R001")
    assert repo.run("spec-status", "--write") == 0
    repo.commit({"specs/demo/status.json": (repo.root / "specs/demo/status.json").read_text()}, "status")
    repo.commit(
        {".config/spec-aliases.toml": _ALIASES, "specs/demo/requirements.md": _rows("NEW-R001")},
        "rename\n\nSpec: none (rename)",
    )
    assert repo.run("spec-status", "--write") == 0
    assert _by_id(repo)["NEW-R001"]["landed_in"] == [sha[:12]]


def test_without_aliases_old_trailers_do_not_count(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _rows("NEW-R001")}, "add spec")
    repo.commit({"pkg/a.py": "# a\n"}, "land\n\nSpec: OLD-R001")
    assert repo.run("spec-status", "--write") == 0
    assert _states(repo) == {"NEW-R001": "SPECIFIED"}


def test_trailers_accept_a_retired_prefix_with_a_warning(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit(
        {
            ".config/spec-aliases.toml": _ALIASES,
            "specs/demo/requirements.md": _rows("NEW-R001"),
            "tests/test_a.py": "# spec: OLD-R001\n",
        },
        "add spec",
    )
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"pkg/a.py": "# a\n"}, "land\n\nSpec: OLD-R001")
    assert repo.run("spec-trailers", "--base-ref", base) == 0
    out = capsys.readouterr().out
    assert "WARN" in out and "NEW-R001" in out


def test_trailers_new_prefix_is_clean(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit(
        {
            ".config/spec-aliases.toml": _ALIASES,
            "specs/demo/requirements.md": _rows("NEW-R001"),
            "tests/test_a.py": "# spec: NEW-R001\n",
        },
        "add spec",
    )
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"pkg/a.py": "# a\n"}, "land\n\nSpec: NEW-R001")
    assert repo.run("spec-trailers", "--base-ref", base) == 0
    assert "WARN" not in capsys.readouterr().out


def test_decomposition_matches_old_status_rows_to_new_requirements(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _rows("OLD-R001")}, "add spec")
    assert repo.run("spec-status", "--write") == 0
    repo.commit(
        {".config/spec-aliases.toml": _ALIASES, "specs/demo/requirements.md": _rows("NEW-R001")},
        "rename",
    )
    assert repo.run("spec-decomposition") == 0
