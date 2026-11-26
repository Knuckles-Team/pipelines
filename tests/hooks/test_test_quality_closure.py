"""PIPE-PAGES-R021.49-.54: coverage closure over every declared project."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pipelines_hooks.code import coverage_closure
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo

#: A fixture-side coverage producer in coverage.py's JSON shape: line tracing of ``pkg`` under pytest.
PRODUCER = """\
import ast, json, sys
from pathlib import Path

import pytest

hit = {}


def tracer(frame, event, arg):
    name = frame.f_code.co_filename
    if "/pkg/" in name:
        hit.setdefault(name, set()).add(frame.f_lineno)
        return tracer
    return tracer if event == "call" else None


sys.settrace(tracer)
code = pytest.main(["-q", "-p", "no:cacheprovider", "-p", "no:xdist", "--rootdir=.", "tests"])
sys.settrace(None)
files = {}
for path in sorted(Path("pkg").rglob("*.py")):
    tree = ast.parse(path.read_text())
    lines = sorted({n.lineno for n in ast.walk(tree) if isinstance(n, ast.stmt) and not isinstance(n, (ast.FunctionDef, ast.ClassDef))} | {n.lineno for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)})
    seen = next((v for k, v in hit.items() if k.endswith(str(path.resolve()))), set())
    files[path.as_posix()] = {"executed_lines": [l for l in lines if l in seen], "missing_lines": [l for l in lines if l not in seen]}
Path("coverage.json").write_text(json.dumps({"files": files}))
raise SystemExit(0 if code == 0 else 1)
"""
LIB = "def a(x):\n    if x:\n        return 1\n    return 2\n"
LIB_TEST = "from pkg.lib import a\n\n\ndef test_a():\n    assert a(1) == 1\n    assert a(0) == 2\n"
POLICY = """version = 1
[[projects]]
name = "alpha"
root = "alpha"
runner = ["{py}", "../producer.py"]
sources = ["pkg"]
[[projects]]
name = "beta"
root = "beta"
runner = ["{py}", "../producer.py"]
sources = ["pkg"]
"""


def project(repo_files: dict[str, str], name: str, lib: str, test: str) -> None:
    repo_files[f"{name}/pkg/__init__.py"] = ""
    repo_files[f"{name}/pkg/lib.py"] = lib
    repo_files[f"{name}/tests/test_lib.py"] = test
    repo_files[f"{name}/pytest.ini"] = "[pytest]\npythonpath = .\n"


def build(tmp_path: Path, beta_test: str = LIB_TEST, policy: str = POLICY) -> Repo:
    files = {
        "producer.py": PRODUCER,
        ".pipelines/closure.toml": policy.format(py=sys.executable),
        "coverage.json": json.dumps({"totals": {"percent_covered": 99}}),
    }
    project(files, "alpha", LIB, LIB_TEST)
    project(files, "beta", LIB, beta_test)
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.commit(files)
    return repo


PARTIAL = "from pkg.lib import a\n\n\ndef test_a():\n    assert a(1) == 1\n"


# spec: PIPE-PAGES-R021.49
def test_policy_models_projects_and_receipt(tmp_path: Path) -> None:
    build(tmp_path)
    result = coverage_closure.check(tmp_path, tmp_path / ".pipelines/closure.toml")
    assert [p["project"] for p in result.projects] == ["alpha", "beta"]
    assert all(len(str(p["policy_digest"])) == 64 and len(str(p["source_digest"])) == 64 for p in result.projects)
    assert result.projects[0]["zero_line"] == ["alpha/pkg/__init__.py"]


# spec: PIPE-PAGES-R021.50
def test_closure_requires_zero_uncovered_lines_not_the_threshold(tmp_path: Path) -> None:
    build(tmp_path, PARTIAL)  # the aggregate percentage is high, the closure is not
    result = coverage_closure.check(tmp_path, tmp_path / ".pipelines/closure.toml")
    assert result.findings == [("beta/pkg/lib.py", 4, "coverage-below-threshold")]


# spec: PIPE-PAGES-R021.51
def test_closure_mode_runs_the_declared_runner(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    assert repo.run("test-quality", "--closure", ".pipelines/closure.toml") == 0
    repo.commit({"beta/tests/test_lib.py": PARTIAL})
    assert repo.run("test-quality", "--closure", ".pipelines/closure.toml") == 1
    assert "beta/pkg/lib.py:4 coverage-below-threshold" in capsys.readouterr().out
    assert not (tmp_path / "beta/.pytest_cache").exists()


# spec: PIPE-PAGES-R021.52
def test_refusals_and_exclusions(tmp_path: Path) -> None:
    repo = build(tmp_path)
    skipped = POLICY.format(py=sys.executable).replace(
        'runner = ["' + sys.executable + '", "../producer.py"]\nsources = ["pkg"]\n', 'sources = ["pkg"]\n', 1
    )
    repo.commit({".pipelines/closure.toml": skipped})
    assert repo.run("test-quality", "--closure", ".pipelines/closure.toml") == 2
    failing = POLICY.format(py=sys.executable).replace("../producer.py", "../missing.py")
    repo.commit({".pipelines/closure.toml": failing})
    with pytest.raises(CannotRun, match="runner exited"):
        coverage_closure.check(tmp_path, tmp_path / ".pipelines/closure.toml")
    repo.commit({".pipelines/closure.toml": "version = 1\n"})
    assert repo.run("test-quality", "--closure", ".pipelines/closure.toml") == 2


# spec: PIPE-PAGES-R021.53
def test_evidence_lists_files_lines_and_zero_line_scope(tmp_path: Path) -> None:
    build(tmp_path, PARTIAL)
    beta = coverage_closure.check(tmp_path, tmp_path / ".pipelines/closure.toml").projects[1]
    assert beta["files"]["beta/pkg/lib.py"] == {"executed": 3, "uncovered": [4]}  # type: ignore[index]
    assert beta["zero_line"] == ["beta/pkg/__init__.py"]


# spec: PIPE-PAGES-R021.54
def test_hot_path_uncovered_branch_refuses_until_tested(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path, PARTIAL)
    assert repo.run("test-quality", "--closure", ".pipelines/closure.toml") == 1
    assert "beta/pkg/lib.py:4" in capsys.readouterr().out
    repo.commit({"beta/tests/test_lib.py": LIB_TEST})
    assert repo.run("test-quality", "--closure", ".pipelines/closure.toml") == 0
    stale = json.dumps({"files": {}})
    repo.commit({"producer.py": f"from pathlib import Path\nPath('coverage.json').write_text({stale!r})\n"})
    assert repo.run("test-quality", "--closure", ".pipelines/closure.toml") == 1  # omitted files are findings
