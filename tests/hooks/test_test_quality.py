"""PIPE-PAGES-R021.1-.6: the test quality gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.cli import GATES
from pipelines_hooks.code.test_quality import TestQualityFinding, scan
from tests.hooks.conftest import HOOK_REPOSITORY, Repo

BAD = (
    "import pytest\n\n\n"
    "def test_placeholder():\n    pass\n\n\n"
    "def test_always_true():\n    assert True\n\n\n"
    "def test_real():\n    assert 1 + 1 == 2\n\n\n"
    "x = 1  # noqa: E501\n"
    "y = 2  # noqa: E501 -- a long literal kept verbatim\n\n\n"
    "@pytest.mark.skip\ndef test_skipped():\n    assert 2 == 2\n"
)


def coverage(percent: float) -> str:
    return json.dumps({"totals": {"percent_covered": percent}})


def _repo(tmp_path: Path, percent: float | None, tests: str = BAD) -> Repo:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    files = {"tests/test_sample.py": tests}
    if percent is not None:
        files["coverage.json"] = coverage(percent)
    repo.commit(files)
    return repo


# spec: PIPE-PAGES-R021.1
def test_finding_rule_is_closed() -> None:
    assert TestQualityFinding("a.py", 1, "placeholder-test").render() == "a.py:1 placeholder-test"
    with pytest.raises(ValueError):
        TestQualityFinding("a.py", 1, "made-up-rule")


# spec: PIPE-PAGES-R021.2
def test_scan_flags_placeholder_and_bare_suppression(tmp_path: Path) -> None:
    _repo(tmp_path, 95)
    result = scan(tmp_path, 80)
    assert [(f.line, f.rule) for f in result.findings] == [
        (4, "placeholder-test"),
        (8, "placeholder-test"),
        (16, "unjustified-suppression"),
        (20, "unjustified-suppression"),
    ]
    clean = tmp_path / "clean"
    clean.mkdir()
    _repo(clean, 95, "def test_real():\n    assert 1 == 1\n")
    assert scan(clean, 80).findings == ()
    assert [f.rule for f in scan(tmp_path, 95).findings].count("coverage-below-threshold") == 0
    assert [f.rule for f in scan(tmp_path, 95.5).findings].count("coverage-below-threshold") == 1


# spec: PIPE-PAGES-R021.3
def test_test_quality_is_registered() -> None:
    assert GATES["test-quality"] == "pipelines_hooks.code.test_quality"
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    assert "pipelines-hook test-quality" in {hook["entry"] for hook in hooks}


# spec: PIPE-PAGES-R021.4
def test_missing_coverage_report_cannot_run(tmp_path: Path) -> None:
    repo = _repo(tmp_path, None, "def test_real():\n    assert 1 == 1\n")
    assert repo.run("test-quality") == 2
    repo.commit({"coverage.json": "{not json"})
    assert repo.run("test-quality") == 2


# spec: PIPE-PAGES-R021.5
def test_test_quality_summary_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, 70)
    assert repo.run("test-quality") == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "test-quality: files 1, placeholders 2, coverage 70%, threshold 80%"
    assert "  tests/test_sample.py:4 placeholder-test" in lines
    assert "  coverage.json:1 coverage-below-threshold" in lines


# spec: PIPE-PAGES-R021.6
def test_test_quality_hook_fails_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, 70, "def test_placeholder():\n    ...\n")
    assert repo.run("test-quality") == 1
    out = capsys.readouterr().out
    assert "tests/test_sample.py:1 placeholder-test" in out and "coverage-below-threshold" in out
    repo.commit({"tests/test_sample.py": "def test_real():\n    assert 1 == 1\n", "coverage.json": coverage(90)})
    assert repo.run("test-quality") == 0
