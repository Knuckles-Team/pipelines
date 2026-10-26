"""Focused proof for the opt-in KISS structural adapter.

The shared gate portion is tested here.  Arbora adoption and its build receipt
remain a separate cross-repository acceptance task and are intentionally not
claimed by these fixtures.
"""

from __future__ import annotations

import json

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.kiss import structural
from pipelines_hooks.kiss.staged import staged_structural_report
from tests.hooks.conftest import Repo


def _policy(*, arguments: int = 6, try_statements: int = 2) -> structural.StructuralPolicy:
    return structural.StructuralPolicy(
        version=1,
        max_function_arguments=arguments,
        max_try_body_statements=try_statements,
        config_digest="sha256:fixture-policy",
    )


def _adopted_pyproject() -> str:
    return (
        '[project]\nname = "fixture"\nversion = "0"\n\n'
        '[tool.pipelines_hooks]\npackages = ["pkg"]\n\n'
        '[tool.pipelines_hooks.kiss]\npaths = ["pkg"]\nstructural = true\n'
    )


def _adopted_kiss_config(repo: Repo, *, arguments: int = 6, try_statements: int = 2) -> str:
    return (
        (repo.root / ".config/kiss.toml").read_text(encoding="utf-8")
        + "\n[structural]\n"
        + f"version = 1\nmax_function_arguments = {arguments}\n"
        + f"max_try_body_statements = {try_statements}\n"
    )


@pytest.mark.spec("PIPE-PAGES-R021.37")
def test_structural_limits_model() -> None:
    policy = _policy()
    policy.validate()
    source = """
class Workout:
    def run(self, /, exercise, sets=1, *extra, intensity, **options):
        try:
            value = exercise
            return value
        except Exception:
            return None
"""
    report = structural.inspect_sources({"pkg/workout.py": source}, policy)
    function = report.functions[0]
    assert function.qualified_name == "Workout.run"
    assert function.count == 6  # self, 2 positional, *extra, keyword-only, **options
    assert [item.count for item in report.try_bodies] == [2]
    assert report.clean
    with pytest.raises(CannotRun, match="nonnegative integer"):
        structural.StructuralPolicy(1, -1, 2, "sha256:x").validate()
    with pytest.raises(CannotRun, match="unsupported.*version"):
        structural.StructuralPolicy(2, 6, 2, "sha256:x").validate()


@pytest.mark.spec("PIPE-PAGES-R021.38")
def test_structural_limits_behavior() -> None:
    source = """
def over_args(first, second, third, *rest, keyword, **options):
    try:
        one = first
        two = second
        try:
            return one
        except Exception:
            return two
    except Exception:
        return three
"""
    report = structural.inspect_sources({"pkg/over.py": source}, _policy(arguments=5, try_statements=3))
    assert [item.count for item in report.try_bodies] == [3, 1]
    assert {(item.kind, item.qualified_name, item.measured, item.limit) for item in report.violations} == {
        ("function-arguments", "over_args", 6, 5),
    }
    # Equality passes for the outer body; the nested try is measured separately.
    equality = structural.inspect_sources({"pkg/over.py": source}, _policy(arguments=6, try_statements=4))
    assert equality.clean
    stricter = structural.inspect_sources({"pkg/over.py": source}, _policy(arguments=6, try_statements=2))
    assert {(item.kind, item.qualified_name, item.measured, item.limit) for item in stricter.violations} == {
        ("try-body-statements", "over_args", 3, 2),
    }


def test_structural_limits_wiring(repo: Repo) -> None:
    repo.commit(
        {
            "pyproject.toml": _adopted_pyproject(),
            ".config/kiss.toml": _adopted_kiss_config(repo, arguments=5),
            "pkg/source.py": "def clean(value):\n    return value\n",
        },
        "adopt structural policy",
    )
    repo.stage({"pkg/source.py": "def changed(first, second, third, *, fourth, fifth, sixth):\n    return first\n"})
    report = staged_structural_report(repo.root, ("pkg",), ["pkg/source.py"])
    assert report is not None
    assert report.source_snapshot == repo.git("write-tree").strip()
    assert [item.qualified_name for item in report.functions] == ["changed"]
    assert report.violations[0].kind == "function-arguments"


def test_structural_limits_refusal(repo: Repo) -> None:
    repo.commit({"pyproject.toml": _adopted_pyproject()}, "opt in without policy")
    with pytest.raises(CannotRun, match=r"requires a \[structural\] table"):
        structural.adopted_policy(repo.root)
    with pytest.raises(CannotRun, match="no versioned adapter"):
        structural.inspect_sources({"pkg/source.rs": "fn main() {}\n"}, _policy())
    with pytest.raises(CannotRun, match="nonnegative integer"):
        structural.inspect_sources(
            {"pkg/source.py": "VALUE = 1\n"},
            structural.StructuralPolicy(1, True, 2, "sha256:x"),
        )


def test_structural_limits_evidence() -> None:
    report = structural.inspect_sources(
        {"pkg/source.py": "def work(value):\n    return value\n"},
        _policy(),
        source_snapshot="fixture-revision",
    )
    evidence = report.as_dict()
    assert evidence["schema"] == "kiss-structural/v1"
    assert evidence["source_snapshot"] == "fixture-revision"
    assert evidence["checked_sources"] == ["pkg/source.py"]
    assert evidence["checked_source_count"] == 1
    assert evidence["scanner"]["version"] == "python-ast/v1"
    assert evidence["scanner"]["digest"].startswith("sha256:")
    assert evidence["policy"]["digest"].startswith("sha256:")
    assert len(evidence["functions"]) == 1
    assert evidence["functions"][0]["count"] == 1
    assert json.loads(json.dumps(evidence))["violations"] == []
    assert any("source_snapshot=fixture-revision" in line for line in structural.render(report))


@pytest.mark.scanner("kiss")
def test_structural_limits_cli(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit(
        {
            "pyproject.toml": _adopted_pyproject(),
            ".config/kiss.toml": _adopted_kiss_config(repo, arguments=5, try_statements=2),
            "pkg/source.py": "def clean(value):\n    return value\n",
        },
        "adopt structural policy",
    )
    repo.stage(
        {
            "pkg/source.py": """def changed(first, second, third, *, fourth, fifth, sixth):
    try:
        one = first
        two = second
        three = third
    except Exception:
        return first
"""
        }
    )
    assert repo.run("kiss-staged") == 1
    output = capsys.readouterr().out
    assert "STRUCTURAL VIOLATION function-arguments pkg/source.py" in output
    assert "STRUCTURAL VIOLATION try-body-statements pkg/source.py" in output
    repo.stage({"pkg/source.py": "def repaired(value):\n    return value\n"})
    assert repo.run("kiss-staged") == 0
