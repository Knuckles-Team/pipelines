"""PIPE-PAGES-R020.31 to R020.36: the shared ValidationReport and repository-validation export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.validation_report import (
    CheckRecord,
    Evidence,
    RuleRecord,
    SkillInventory,
    ValidationReport,
)
from tests.hooks.pinned_tools import pinned_ruff  # noqa: F401
from tests.hooks.conftest import PYPROJECT, Repo

PASS = RuleRecord(rule="a-ok", outcome="pass", reason="clean")
FAIL = RuleRecord(
    rule="F401",
    outcome="fail",
    reason="unused import",
    evidence=(Evidence(path="pkg/mod.py", line=1, observed="F401", expected="none", detail="os unused"),),
)
SKIP = RuleRecord(rule="b-skip", outcome="skip", reason="not applicable", required=False)


def _mixed() -> ValidationReport:
    checks = [
        CheckRecord(category="lint", identity="ruff==1", command=("ruff", "check"), duration_ms=7, rules=(FAIL, PASS)),
        CheckRecord(category="type", identity="mypy==2", rules=(SKIP,)),
    ]
    return ValidationReport.build(repository="demo", snapshot="index", checks=checks)


# spec: PIPE-PAGES-R020.31
def test_validation_report_model() -> None:
    with pytest.raises(ValueError):
        RuleRecord(rule="x", outcome="maybe", reason="r")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RuleRecord(rule="x", outcome="fail", reason="no evidence")
    with pytest.raises(ValueError):
        CheckRecord(category="lint", identity="t", rules=(PASS, PASS))
    with pytest.raises(ValueError):
        CheckRecord(category="lint", identity="t", status="cannot-run")
    with pytest.raises(CannotRun):
        ValidationReport.build(
            repository="r",
            snapshot="s",
            checks=[CheckRecord(category="c", identity="i"), CheckRecord(category="c", identity="i")],
        )
    report = _mixed()
    with pytest.raises(ValueError):
        ValidationReport.model_validate({**report.model_dump(), "counts": {}})
    assert report.schema_version == "validation-report-v1"
    assert report.counts["lint"].failed == 1 and report.counts["type"].skipped == 1


# spec: PIPE-PAGES-R020.32
def test_validation_report_behavior() -> None:
    report = _mixed()
    again = ValidationReport.from_json(report.to_json())
    assert again == report and again.to_json() == report.to_json()
    assert [r.rule for r in again.checks[0].rules] == ["F401", "a-ok"]
    assert again.checks[0].rules[0].evidence[0].detail == "os unused"
    assert again.counts == report.counts and again.verdict == "fail"
    empty = ValidationReport.build(
        repository="demo", snapshot="s", skills=SkillInventory(roots=("skills",), applicable=False, reason="none found")
    )
    assert (
        empty.skills is not None
        and not empty.skills.applicable
        and empty.counts["skill"].passed == 0
        and empty.full_coverage is False
    )
    assert "# validation-report-v1" in report.to_markdown()


# spec: PIPE-PAGES-R020.34
def test_validation_report_refusal() -> None:
    doc = json.loads(_mixed().to_json())
    tampered = {**doc, "verdict": "pass"}
    with pytest.raises(CannotRun):
        ValidationReport.from_json(json.dumps(tampered))
    with pytest.raises(CannotRun):
        ValidationReport.from_json(json.dumps({**doc, "counts": {"lint": {"passed": 9, "failed": 0, "skipped": 0}}}))
    with pytest.raises(CannotRun):
        ValidationReport.from_json(json.dumps({**doc, "schema_version": "validation-report-v0"}))
    with pytest.raises(CannotRun):
        ValidationReport.from_json(_mixed().to_json()[:-40])
    required_skip = ValidationReport.build(
        repository="d",
        snapshot="s",
        checks=[
            CheckRecord(category="lint", identity="t", rules=(FAIL, RuleRecord(rule="s", outcome="skip", reason="r")))
        ],
    )
    assert required_skip.exit_code == 2  # cannot-run takes precedence over the failure
    assert _mixed().exit_code == 1 and _mixed().full_coverage is False


# spec: PIPE-PAGES-R020.35
def test_validation_report_evidence() -> None:
    secret = RuleRecord(
        rule="S1",
        outcome="fail",
        reason="leak",
        evidence=(Evidence(path="a.py", line=2, detail="password=hunter2 and <b>x</b> | y"),),
    )
    report = ValidationReport.build(
        repository="d",
        snapshot="s",
        checks=[CheckRecord(category="lint", identity="ruff", duration_ms=12, rules=(secret,))],
    )
    for text in (report.to_json(), report.to_markdown()):
        assert "hunter2" not in text and "[REDACTED]" in text or "REDACTED" in text
    assert "<b>" not in report.to_markdown() and "\\|" in report.to_markdown()
    assert "12 ms" in report.to_markdown()
    with pytest.raises(ValueError):
        Evidence(path="/abs/path.py")
    with pytest.raises(ValueError):
        Evidence(path="../up.py")
    assert len(Evidence(path="a", detail="x" * 5000).detail) < 1100
    with pytest.raises(CannotRun):
        ValidationReport.from_json(" " * (5 * 1024 * 1024))


def _fixture(tmp_path: Path, mod: str, extra: str = "") -> Repo:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.stage({"pyproject.toml": PYPROJECT + extra, "pkg/__init__.py": "", "pkg/mod.py": mod})
    return repo


CLEAN = "VALUE: int = 1\n"
SKILLS_OFF = '\n[tool.pipelines_hooks.repository_validation]\nrequired = ["lint", "import-order", "type"]\n'


# spec: PIPE-PAGES-R020.33
def test_validation_report_wiring(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert GATES["repository-validation"] == "pipelines_hooks.code.repository_validation"
    hooks = (Path(__file__).resolve().parents[2] / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "entry: pipelines-hook repository-validation" in hooks
    repo = _fixture(tmp_path, "import os\nimport sys\nVALUE: int = 'x'\n", SKILLS_OFF)
    out = tmp_path.parent / (tmp_path.name + "-report.json")
    assert repo.run("repository-validation", "--report-json", str(out)) == 1
    report = ValidationReport.from_json(out.read_text(encoding="utf-8"))
    assert {c.category for c in report.checks} == {"lint", "import-order", "type"}
    capsys.readouterr()


# spec: PIPE-PAGES-R020.36
def test_validation_report_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _fixture(tmp_path, "import sys\nimport os\nVALUE: int = 'x'\nprint(os, sys)\n", SKILLS_OFF)
    out_json = tmp_path.parent / (tmp_path.name + ".json")
    out_md = tmp_path.parent / (tmp_path.name + ".md")
    assert repo.run("repository-validation", "--report-json", str(out_json), "--report-markdown", str(out_md)) == 1
    report = ValidationReport.from_json(out_json.read_text(encoding="utf-8"))
    by_category = {c.category: {r.rule for r in c.rules if r.outcome == "fail"} for c in report.checks}
    assert by_category["import-order"] == {"I001"} and by_category["type"] == {"assignment"}
    assert report.verdict == "fail" and "I001" in out_md.read_text(encoding="utf-8")
    repo.stage({"pkg/mod.py": "import os\nimport sys\n\nVALUE: int = 1\nprint(os, sys)\n"})
    assert repo.run("repository-validation") == 0
    pinned = SKILLS_OFF + '\n[tool.pipelines_hooks.lint_type.tools]\nmypy = "0.0.1"\n'
    repo.stage({"pyproject.toml": PYPROJECT + pinned})
    assert repo.run("repository-validation") == 2
    optional = SKILLS_OFF.replace('"type"', "").replace(", ]", "]").replace('"import-order", ]', '"import-order"]')
    repo.stage({"pyproject.toml": PYPROJECT + optional + '\n[tool.pipelines_hooks.lint_type.tools]\nmypy = "0.0.1"\n'})
    assert repo.run("repository-validation", "--report-json", str(out_json)) == 0
    optional_report = ValidationReport.from_json(out_json.read_text(encoding="utf-8"))
    assert optional_report.full_coverage is False and optional_report.counts["type"].skipped == 1
    capsys.readouterr()
