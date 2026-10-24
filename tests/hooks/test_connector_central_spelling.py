"""Spelling rule of the central connector migration: safe typo fixes and identifier words (PIPE-GATES-R016.110)."""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

import pytest


from pipelines_hooks.hygiene.connector_central import spelling  # noqa: E402
from pipelines_hooks.hygiene.connector_central.base import Ctx, Review  # noqa: E402

PYPROJECT = '[project]\nname = "demo-agent"\nversion = "1.0.0"\n'


def _git_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)
    return dict(os.environ)


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str], pyproject: str = PYPROJECT) -> Ctx:
    env = _git_env(monkeypatch)
    root = tmp_path / "r"
    root.mkdir()
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
    ctx = Ctx(root=root, pkg=root / "demo_agent", fleet="demo-mcp", dist="demo-agent", review=Review())
    ctx.applied.append("earlier")
    spelling.rule_af(ctx)
    return ctx


def _left(ctx: Ctx) -> list[str]:
    from pipelines_hooks.connector import codespell

    return codespell.findings(ctx.root, extra=sorted(ctx.changed))


@pytest.fixture(autouse=True)
def _needs_codespell() -> None:
    """The rule drives the central codespell member; without the tool the run is skipped unless scanners are required."""
    import subprocess as sp
    import sys

    from tests.hooks.conftest import REQUIRE_SCANNERS

    if sp.run([sys.executable, "-m", "codespell_lib", "--version"], capture_output=True, check=False).returncode != 0:
        if REQUIRE_SCANNERS:
            pytest.fail("codespell is required in this run")
        pytest.skip("codespell is not installed in this environment (a scanner-provisioned run requires it)")


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_doc_typo_is_fixed_but_not_inside_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = "A respository here.\n\n```\nrespository = 1\n```\n\nand `respository` inline\n"
    ctx = _run(tmp_path, monkeypatch, {"README.md": doc})
    text = (ctx.root / "README.md").read_text(encoding="utf-8")
    assert text.startswith("A repository here.")
    assert "respository = 1" in text and "`respository`" in text


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_comment_and_docstring_typos_are_fixed_and_code_is_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = (
        '"""Module with a respository."""\n\n\ndef f() -> int:\n    """Returns the respository."""\n'
        "    return 1  # the respository\n"
    )
    ctx = _run(tmp_path, monkeypatch, {"demo_agent/m.py": src})
    text = (ctx.root / "demo_agent/m.py").read_text(encoding="utf-8")
    assert text == src.replace("respository", "repository")
    assert _left(ctx) == []


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_identifier_goes_to_ignore_words_sorted_lowercase_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = "respository = 1\n\n\ndef g(respository: int) -> int:\n    return respository + 1\n"
    pyproject = PYPROJECT + '\n[tool.pipelines.codespell]\nignore_words = ["zeta", "alpha"]\n'
    ctx = _run(tmp_path, monkeypatch, {"demo_agent/m.py": src}, pyproject)
    assert (ctx.root / "demo_agent/m.py").read_text(encoding="utf-8") == src
    words = tomllib.loads(ctx.read("pyproject.toml"))["tool"]["pipelines"]["codespell"]["ignore_words"]
    assert words == ["alpha", "respository", "zeta"]
    assert _left(ctx) == []
    before = ctx.read("pyproject.toml")
    spelling.rule_af(ctx)
    assert ctx.read("pyproject.toml") == before


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_ignore_words_table_is_created_when_missing() -> None:
    new = spelling.merge_ignore_words(PYPROJECT, {"Foo", "bar"})
    assert new is not None
    assert tomllib.loads(new)["tool"]["pipelines"]["codespell"]["ignore_words"] == ["bar", "foo"]
    assert spelling.merge_ignore_words(new, {"foo"}) == new


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_string_literal_stays_a_review_item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = 'NAME = "respository"\n'
    ctx = _run(tmp_path, monkeypatch, {"demo_agent/m.py": src})
    assert (ctx.root / "demo_agent/m.py").read_text(encoding="utf-8") == src
    assert any("respository" in ln for ln in _left(ctx))
    assert "string literal" in ctx.options[spelling.REASONS_KEY]["demo_agent/m.py:1:respository"]


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_multiple_suggestions_in_a_comment_stay_a_review_item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = "x = 1  # the 2nd nd place\n"
    ctx = _run(tmp_path, monkeypatch, {"demo_agent/m.py": src})
    assert (ctx.root / "demo_agent/m.py").read_text(encoding="utf-8") == src
    assert any(" nd " in f" {ln.split(': ', 1)[1]}" for ln in _left(ctx))
    assert "several suggestions" in next(iter(ctx.options[spelling.REASONS_KEY].values()))


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_other_file_types_and_generated_files_are_not_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"demo_agent/data.json": '{"a": "respository"}\n', "demo_agent/g.py": "# generated by x\n# respository\n"}
    ctx = _run(tmp_path, monkeypatch, files)
    assert "respository" in (ctx.root / "demo_agent/data.json").read_text(encoding="utf-8")
    assert "respository" in (ctx.root / "demo_agent/g.py").read_text(encoding="utf-8")
    assert len(_left(ctx)) == 2


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_second_run_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _run(tmp_path, monkeypatch, {"README.md": "respository\n", "demo_agent/m.py": "# respository\n"})
    snapshot = {p: (ctx.root / p).read_text(encoding="utf-8") for p in ("README.md", "demo_agent/m.py")}
    ctx.changed.clear()
    spelling.rule_af(ctx)
    assert ctx.changed == set()
    assert snapshot == {p: (ctx.root / p).read_text(encoding="utf-8") for p in snapshot}


@pytest.mark.spec("PIPE-GATES-R016.110")
def test_findings_in_tool_working_directories_are_excluded_not_edited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = "# Report\n\nThis teh report is generated.\n"
    ctx = _run(tmp_path, monkeypatch, {".specify/reports/r.md": report, "docs/a.md": "A teh doc.\n"})
    assert (ctx.root / ".specify/reports/r.md").read_text(encoding="utf-8") == report
    table = tomllib.loads((ctx.root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pipelines"]["codespell"]
    assert table["exclude"] == [".specify"]
    assert "teh" not in (ctx.root / "docs/a.md").read_text(encoding="utf-8")
    assert not _left(ctx)
    ctx.applied.append("again")
    spelling.rule_af(ctx)
    assert tomllib.loads((ctx.root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pipelines"]["codespell"][
        "exclude"
    ] == [".specify"]
