"""PIPE-PAGES-R021.19 to R021.24: lint, import-order and type diagnostics with zero exceptions."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.code import lint_type
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.pinned_tools import pinned_ruff  # noqa: F401
from tests.hooks.conftest import PYPROJECT, Repo

CLEAN = "import os\nimport sys\n\nVALUE: int = 1\nprint(os, sys)\n"


def _repo(tmp_path: Path, mod: str = CLEAN, pyproject: str = PYPROJECT) -> Repo:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.stage({"pyproject.toml": pyproject, "pkg/__init__.py": "", "pkg/mod.py": mod})
    return repo


def _failures(repo: Repo) -> dict[str, set[str]]:
    return {c.category: {r.rule for r in c.rules if r.outcome == "fail"} for c in lint_type.analyze(repo.root)}


# spec: PIPE-PAGES-R021.19
def test_lint_type_policy_model(tmp_path: Path) -> None:
    ok = dict(language="python", source_roots=("pkg",), test_roots=(), tools=dict(lint_type.DEFAULT_TOOLS))
    policy = lint_type.CodeQualityPolicy(**ok)  # type: ignore[arg-type]
    assert [policy.invocation(p).tool for p in lint_type.PHASES] == ["ruff", "ruff", "mypy"]
    assert policy.invocation("type").argv[-1] == "pkg"
    with pytest.raises(CannotRun):
        lint_type.CodeQualityPolicy(**{**ok, "tools": {"ruff": "0.15.22"}})  # type: ignore[arg-type]
    with pytest.raises(CannotRun):
        lint_type.CodeQualityPolicy(**{**ok, "tools": {"ruff": "latest", "mypy": "2.4.0"}})  # type: ignore[arg-type]
    with pytest.raises(CannotRun):
        lint_type.CodeQualityPolicy(**{**ok, "source_roots": ()})  # type: ignore[arg-type]
    with pytest.raises(CannotRun):
        lint_type.CodeQualityPolicy(**{**ok, "language": "rust"})  # type: ignore[arg-type]


# spec: PIPE-PAGES-R021.20
def test_lint_type_policy_behavior(tmp_path: Path) -> None:
    assert _failures(_repo(tmp_path)) == {"lint": set(), "import-order": set(), "type": set()}
    assert _failures(_repo(tmp_path / "a", "import os\nVALUE: int = 1\n"))["lint"] == {"F401"}
    assert _failures(_repo(tmp_path / "b", "import sys\nimport os\nprint(os, sys)\n"))["import-order"] == {"I001"}
    assert _failures(_repo(tmp_path / "c", "VALUE: int = 'x'\n"))["type"] == {"assignment"}
    hidden = _failures(_repo(tmp_path / "d", "import os  # noqa: F401\nVALUE: int = 1\n"))
    assert hidden["lint"] == {"suppression"}
    cfg = PYPROJECT + '\n[tool.ruff.lint]\nignore = ["F401"]\n'
    assert _failures(_repo(tmp_path / "e", CLEAN, cfg))["lint"] == {"suppression"}
    mypy_cfg = PYPROJECT + "\n[tool.mypy]\nignore_errors = true\n"
    assert _failures(_repo(tmp_path / "f", CLEAN, mypy_cfg))["lint"] == {"suppression"}


# spec: PIPE-PAGES-R021.21
def test_lint_type_policy_wiring(tmp_path: Path) -> None:
    assert GATES["lint-type"] == "pipelines_hooks.code.lint_type"
    hooks = (Path(__file__).resolve().parents[2] / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "id: lint-type" in hooks and "entry: pipelines-hook lint-type" in hooks
    repo = _repo(tmp_path, "import os\n")
    assert repo.run("lint-type") == 1
    assert [c.category for c in lint_type.analyze(repo.root)] == ["lint", "import-order", "type"]


# spec: PIPE-PAGES-R021.22
def test_lint_type_policy_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        lint_type, "_tool_path", lambda name: None if name == "mypy" else str(__import__("shutil").which(name))
    )
    assert repo.run("lint-type") == 2
    monkeypatch.undo()
    foreign = _repo(tmp_path / "x")
    foreign.stage({"pkg/app.js": "1\n"})
    assert foreign.run("lint-type") == 2
    outside = _repo(tmp_path / "y")
    outside.stage({"scripts/tool.py": "VALUE = 1\n"})
    assert outside.run("lint-type") == 2
    pin = _repo(tmp_path / "z", pyproject=PYPROJECT + '\n[tool.pipelines_hooks.lint_type]\nlanguage = "go"\n')
    assert pin.run("lint-type") == 2


# spec: PIPE-PAGES-R021.23
def test_lint_type_policy_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, "import os\nVALUE: int = 'x'\n")
    records = lint_type.analyze(repo.root)
    assert len({r.source_digest for r in records}) == 1 and records[0].source_digest
    assert all(r.status == "complete" and r.command and r.policy_digest and r.scope == ("pkg",) for r in records)
    assert records[0].identity == "ruff==0.15.22" and records[2].identity == "mypy==2.4.0"
    evidence = records[0].rules[0].evidence[0]
    assert (evidence.path, evidence.line, evidence.observed) == ("pkg/mod.py", 1, "F401")
    assert repo.run("lint-type") == 1
    printed = capsys.readouterr().out
    assert "pkg/mod.py:1 F401" in printed and "pkg/mod.py:2 assignment" in printed


# spec: PIPE-PAGES-R021.24
def test_lint_type_policy_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, "import os\nimport sys\nVALUE: int = 'x'\n")
    assert repo.run("lint-type") == 1
    out = capsys.readouterr().out
    assert "F401" in out and "assignment" in out
    repo.write("pkg/mod.py", CLEAN)  # an unstaged repair cannot hide the indexed defects
    assert repo.run("lint-type") == 1
    repo.stage({"pkg/mod.py": CLEAN})
    assert repo.run("lint-type") == 0
    repo.stage({"pkg/mod.py": CLEAN + "VALUE2: int = 2  # type: ignore\n"})
    assert repo.run("lint-type") == 1
    assert not list(repo.root.glob("**/*.orig")) and (repo.root / "pkg/mod.py").read_text().endswith("ignore\n")
