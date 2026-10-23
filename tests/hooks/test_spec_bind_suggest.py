"""spec-bind-suggest: ranked, repeatable test candidates for unverified rows."""

from __future__ import annotations

import json
from pathlib import Path

from pipelines_hooks.specs.bind_suggest import suggest
import pytest

from tests.hooks.conftest import Repo

_ROWS = (
    "# demo\n\n| ID | Requirement | Acceptance |\n|---|---|---|\n"
    "| `TEST-R001` | **Named test proves it.** | `tests/test_a.py::test_exact` asserts it. |\n"
    "| `TEST-R002` | **Docstring cites it.** | tbd |\n"
    "| `TEST-R003` | **Cache eviction honours capacity limit.** | tbd |\n"
    "| `TEST-R004` | **Unrelated widget.** | tbd |\n"
)
_TESTS = (
    "def test_exact() -> None:\n    assert True\n\n"
    'def test_other() -> None:\n    """Covers TEST-R002."""\n\n'
    "def test_cache_eviction_honours_capacity() -> None:\n    assert True\n\n"
    "def test_noise() -> None:\n    assert True\n"
)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    fixture = Repo(tmp_path / "repo")
    fixture.root.mkdir()
    fixture.git("init", "-q", "-b", "main")
    return fixture


def _fixture(repo: Repo) -> Path:
    repo.commit({"specs/demo/requirements.md": _ROWS, "tests/test_a.py": _TESTS}, "add spec and tests")
    return repo.root


# spec: PIPE-CONNSPEC-R010
def test_ranks_named_test_first_and_is_repeatable(repo: Repo) -> None:
    root = _fixture(repo)
    result = suggest(root)
    by_row = {c["row"]: c for c in result["candidates"]}

    assert by_row["TEST-R001"]["test"] == "tests/test_a.py::test_exact"
    assert by_row["TEST-R001"]["score"] == 100
    assert by_row["TEST-R002"]["score"] == 90
    assert by_row["TEST-R003"]["test"] == "tests/test_a.py::test_cache_eviction_honours_capacity"
    assert 0 < by_row["TEST-R003"]["score"] < 60
    assert "TEST-R004" not in by_row
    scores = [c["score"] for c in result["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert json.dumps(suggest(root)) == json.dumps(result)


def test_bound_row_and_binding_lines_are_not_suggested(repo: Repo) -> None:
    root = _fixture(repo)
    repo.commit({"pkg/x.py": "x = 1\n"}, "Spec: TEST-R001")
    repo.commit({"tests/test_b.py": "# spec: TEST-R001\ndef test_bound() -> None:\n    assert True\n"}, "bind")
    result = suggest(root)

    assert result["states"].get("VERIFIED") == 1
    assert all(c["row"] != "TEST-R001" for c in result["candidates"])
    assert all("test_bound" not in c["test"] for c in result["candidates"])


def test_cli_writes_markdown(repo: Repo, tmp_path: Path) -> None:
    root = _fixture(repo)
    out = tmp_path / "out.md"
    assert repo.run("spec-bind-suggest", "--format", "markdown", "--out", str(out)) == 0
    assert "`TEST-R001`" in out.read_text(encoding="utf-8")
    assert root.exists()
