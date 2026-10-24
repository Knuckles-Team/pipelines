"""Central migration fixes from the batch-1 commit-hook failures: ruff and codespell options, tidy, standard, scan set.

Spec marks: pl.q PIPE-GATES-R016.94, pl.r PIPE-GATES-R016.95, pl.o PIPE-GATES-R016.92.
"""

from __future__ import annotations

import importlib.util
import shutil
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import load_rules

from pipelines_hooks.connector import codespell, standard
from pipelines_hooks.hygiene.connector_central import tidy
from pipelines_hooks.hygiene.connector_central.base import RULES, Ctx, make_ctx

PYPROJECT = """[project]
name = "demo-mcp"
version = "1.2.3"
description = "demo"
dependencies = ["agent-connector-sdk[mcp]>=0.5.4,<0.6.0"]

[project.scripts]
demo-mcp = "demo_mcp.mcp_server:main"

[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_mcp:connector"
"""
RUFF_HOOKS = """repos:
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.17.1
  hooks:
  - id: ruff-check
    args: ["--fix", "--ignore=E402,B008"]
    exclude: {exclude}
  - id: ruff-format
    exclude: {exclude}
"""


load_rules()  # registers every rule when this file runs alone


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    pkg = tmp_path / "demo_mcp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path


def run(root: Path, *ids: str) -> Ctx:
    ctx = make_ctx(root)
    assert ctx is not None
    for rid in ids:
        RULES[rid](ctx)
    return ctx


def toml(root: Path) -> dict:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


def precommit(root: Path, text: str) -> None:
    (root / ".pre-commit-config.yaml").write_text(text, encoding="utf-8")


def blocking(ctx: Ctx, needle: str) -> list[dict]:
    return [i for i in ctx.review.items if i["blocking"] and needle in i["detail"]]


# --- pl.q: ruff -------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.94")
@pytest.mark.parametrize(
    "exclude",
    ["^(tests/|test/|scripts/|script/)", "'^(\\./test/|\\./tests/)'", "tests"],
)
def test_q_every_plain_exclude_form_is_ported(repo: Path, exclude: str) -> None:
    (repo / "tests").mkdir()
    precommit(repo, RUFF_HOOKS.format(exclude=exclude))
    run(repo, "pl.q")
    assert toml(repo)["tool"]["ruff"]["extend-exclude"] == ["tests"]


@pytest.mark.spec("PIPE-GATES-R016.94")
def test_q_config_wide_exclude_and_file_path_are_ported(repo: Path) -> None:
    (repo / "gitlab_api").mkdir()
    (repo / "gitlab_api" / "gitlab_gql.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    precommit(repo, "exclude: 'dotnet|node_modules'\n" + RUFF_HOOKS.format(exclude="^(gitlab_api/gitlab_gql\\.py$)"))
    run(repo, "pl.q")
    assert toml(repo)["tool"]["ruff"]["extend-exclude"] == ["gitlab_api/gitlab_gql.py", "node_modules"]


@pytest.mark.spec("PIPE-GATES-R016.94")
def test_q_exclude_that_is_not_a_path_list_is_blocking(repo: Path) -> None:
    precommit(repo, RUFF_HOOKS.format(exclude="'.*generated.*'"))
    ctx = run(repo, "pl.q")
    assert blocking(ctx, "not a plain list of paths")
    assert "extend-exclude" not in repo.joinpath("pyproject.toml").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.94")
def test_q_ruff_ignore_args_become_lint_ignore_and_nothing_more(repo: Path) -> None:
    precommit(repo, RUFF_HOOKS.format(exclude="tests"))
    run(repo, "pl.q")
    assert toml(repo)["tool"]["ruff"]["lint"]["ignore"] == ["E402", "B008"]


@pytest.mark.spec("PIPE-GATES-R016.94")
def test_q_existing_lint_ignore_is_extended_only_by_missing_codes(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        PYPROJECT + '\n[tool.ruff.lint]\nselect = ["E", "F"]\nignore = [ "E402", "E501",]\n', encoding="utf-8"
    )
    precommit(repo, RUFF_HOOKS.format(exclude="tests"))
    run(repo, "pl.q")
    lint = toml(repo)["tool"]["ruff"]["lint"]
    assert lint["ignore"] == ["E402", "E501", "B008"] and lint["select"] == ["E", "F"]
    before = (repo / "pyproject.toml").read_text(encoding="utf-8")
    precommit(repo, RUFF_HOOKS.format(exclude="tests"))
    run(repo, "pl.q")
    assert (repo / "pyproject.toml").read_text(encoding="utf-8") == before


# --- tidy -------------------------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.94")
@pytest.mark.skipif(shutil.which("ruff") is None and shutil.which("uvx") is None, reason="needs ruff")
def test_tidy_fixes_safe_findings_and_reports_the_rest_with_rule_ids(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(PYPROJECT + '\n[tool.ruff.lint]\nselect = ["E", "F", "I", "UP"]\n')
    (repo / "demo_mcp" / "a.py").write_text(
        "import os\nfrom typing import Optional\n\n\ndef f(x: Optional[int]):\n    unused = 1\n    return x\n"
    )
    ctx = make_ctx(repo)
    assert ctx is not None
    ctx.changed.add("demo_mcp/a.py")
    tidy(ctx)
    text = (repo / "demo_mcp" / "a.py").read_text(encoding="utf-8")
    assert "import os" not in text and "int | None" in text
    items = [i for i in ctx.review.items if i["blocking"]]
    assert len(items) == 1 and "F841" in items[0]["detail"] and items[0]["path"] == "demo_mcp/a.py"


# --- pl.q / pl.r: codespell -------------------------------------------------------------------------------------
SPELL_HOOK = """repos:
- repo: https://github.com/codespell-project/codespell
  rev: v2.4.1
  hooks:
  - id: codespell
    args: ["-L", "ans,nam,tread,ot,tyes", "--ignore-words=.codespellignore"]
    exclude: ^(tests/|test/|scripts/|script/|.*lock.*|\\.specify/)
"""


@pytest.mark.spec("PIPE-GATES-R016.95")
def test_r_old_words_and_excludes_go_to_the_repo_table_not_the_defaults(repo: Path) -> None:
    (repo / ".specify").mkdir()
    precommit(repo, SPELL_HOOK)
    (repo / ".codespellignore").write_text("# c\nnam\nzzword\n", encoding="utf-8")
    default_before = codespell.DEFAULT_IGNORE.read_text(encoding="utf-8")
    run(repo, "pl.q", "pl.r")
    table = toml(repo)["tool"]["pipelines"]["codespell"]
    assert table == {"ignore_words": ["tyes", "zzword"], "exclude": [".specify"]}
    assert not (repo / ".codespellignore").exists()
    assert codespell.DEFAULT_IGNORE.read_text(encoding="utf-8") == default_before


@pytest.mark.spec("PIPE-GATES-R016.95")
def test_r_words_already_central_leave_no_table(repo: Path) -> None:
    (repo / ".codespellignore").write_text("linar\nnam\n", encoding="utf-8")
    run(repo, "pl.r")
    assert "codespell" not in repo.joinpath("pyproject.toml").read_text(encoding="utf-8")
    assert not (repo / ".codespellignore").exists()


@pytest.fixture(autouse=True)
def _no_hook_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)


def _git_repo(root: Path) -> None:
    """A throwaway repository; GIT_* variables of a hook run are stripped so the real repository is never touched."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *cmd], cwd=root, check=True, capture_output=True, env=env)


@pytest.mark.spec("PIPE-GATES-R016.95")
def test_codespell_hook_honours_the_repo_words_and_excludes(repo: Path) -> None:
    from tests.hooks.conftest import REQUIRE_SCANNERS

    (repo / "demo_mcp" / "m.py").write_text("nd = 1\n# teh\n", encoding="utf-8")
    (repo / ".specify").mkdir()
    (repo / ".specify" / "r.md").write_text("updat the thing\n", encoding="utf-8")
    _git_repo(repo)
    from pipelines_hooks.core.errors import Unavailable

    try:
        lines = codespell.findings(repo)
    except Unavailable:
        if REQUIRE_SCANNERS:
            raise
        pytest.skip("codespell is not installed in this environment (a scanner-provisioned run requires it)")
    assert any("nd ==>" in ln for ln in lines) and any("teh" in ln for ln in lines)
    assert any(".specify/r.md" in ln for ln in lines)
    (repo / "pyproject.toml").write_text(
        PYPROJECT + '\n[tool.pipelines.codespell]\nignore_words = ["nd"]\nexclude = [".specify"]\n', encoding="utf-8"
    )
    lines = codespell.findings(repo)
    assert not any("nd ==>" in ln or ".specify" in ln for ln in lines) and any("teh" in ln for ln in lines)


# --- connector-standard ----------------------------------------------------------------------------------------
@pytest.mark.spec("PIPE-GATES-R016.95")
def test_standard_names_the_failed_members_and_runs_all(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    class Member:
        def __init__(self, name: str, code: int) -> None:
            self.name, self.code = name, code

        def main(self, argv: list[str]) -> int:
            calls.append(self.name)
            print(f"{self.name} output")
            return self.code

    monkeypatch.setattr(
        standard,
        "MEMBERS",
        {"files": Member("files", 0), "codespell": Member("codespell", 1), "security": Member("security", 1)},
    )
    assert standard.main([]) == 1
    out = capsys.readouterr()
    assert calls == ["files", "codespell", "security"] and "codespell output" in out.out
    assert out.err.strip() == "connector-standard: FAILED members: codespell, security"
    monkeypatch.setattr(standard, "MEMBERS", {"files": Member("files", 0)})
    assert standard.main([]) == 0 and capsys.readouterr().err == ""


# --- generations script ----------------------------------------------------------------------------------------
def _script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "connector_central_generations.py"
    spec = importlib.util.spec_from_file_location("connector_central_generations", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["connector_central_generations"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_generations_scan_set_is_the_drivers_set_not_the_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script()
    for name in ("alpha-mcp", "stale-mcp"):
        (tmp_path / name / ".git").mkdir(parents=True)
    paths = script.repo_paths(tmp_path, ["alpha-mcp", "gone-mcp"])
    assert [p.name for p in paths] == ["alpha-mcp"]
    assert "no checkout of gone-mcp" in capsys.readouterr().err


@pytest.mark.spec("PIPE-GATES-R016.92")
def test_generations_recorded_entries_survive_while_one_repo_carries_them(tmp_path: Path) -> None:
    script = _script()
    manual = next(m for m in script.MANUAL if m["id"] == "compose-env-file")
    text = "services:\n  x:\n    restart: always\n    environment:\n      A: b\n"
    scanned = {"one": {"form": None, "stubs": {}, "pairs": {manual["file"]: (text, "", "demo", "8000")}}}
    assert not [r for r in script.build(scanned, 3)["rewrites"] if r["id"] == manual["id"]]
    kept = [r for r in script.build(scanned, 3, {manual["id"]})["rewrites"] if r["id"] == manual["id"]]
    assert kept and kept[0]["repos"] == 1 and kept[0]["retained"]
    out = tmp_path / "g.json"
    out.write_text('{"rewrites": [{"id": "compose-env-file"}]}', encoding="utf-8")
    assert script.recorded_ids(out) == {"compose-env-file"} and script.recorded_ids(tmp_path / "none") == set()
