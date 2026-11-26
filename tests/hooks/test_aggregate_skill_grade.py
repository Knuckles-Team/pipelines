"""PIPE-PAGES-R023.13 to R023.18: skill grading inside the repository-validation aggregate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.cli import GATES
from pipelines_hooks.code import repository_validation
from pipelines_hooks.core.validation_report import ValidationReport
from tests.hooks.conftest import PYPROJECT, Repo
from tests.hooks.test_external_grade_rules import PACK_BODY, _policy
from tests.hooks.test_skill_grade_hook import VALID_SKILL

SKILL_ONLY = PYPROJECT + '\n[tool.pipelines_hooks.repository_validation]\nrequired = ["skill"]\n'
BAD_SKILL = VALID_SKILL.replace("## Usage", "## FAQ")


def _repo(tmp_path: Path, second: str = VALID_SKILL, extra: dict[str, str] | None = None) -> Repo:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = Repo(tmp_path)
    repo.git("init", "-q", "-b", "main")
    repo.stage(
        {
            "pyproject.toml": SKILL_ONLY,
            "README.md": "# fixture\n",
            "skills/one/SKILL.md": VALID_SKILL,
            "skills/one/guide.md": "# Guide\n",
            "skills/two/SKILL.md": second,
            "skills/two/guide.md": "# Guide\n",
            "rules/pack.yaml": PACK_BODY,
            ".config/grade.yaml": yaml.safe_dump(_policy()),
            **(extra or {}),
        }
    )
    return repo


def _report(repo: Repo, tmp_path: Path, *args: str) -> tuple[int, ValidationReport | None]:
    out = tmp_path.parent / (tmp_path.name + ".json")
    out.unlink(missing_ok=True)
    code = repo.run("repository-validation", "--report-json", str(out), *args)
    return code, ValidationReport.from_json(out.read_text(encoding="utf-8")) if out.exists() else None


POLICY = ("--skill-policy", ".config/grade.yaml")


# spec: PIPE-PAGES-R023.13
def test_aggregate_skill_grade_model(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r")
    inventory, identity = repository_validation.skill_inventory(repo.root, None, Path(".config/grade.yaml"))
    assert inventory.roots == ("skills",) and [r.skill_path for r in inventory.results] == [
        "skills/one/SKILL.md",
        "skills/two/SKILL.md",
    ]
    first = inventory.results[0]
    assert first.snapshot == identity and first.skill_digest and first.policy_digest and first.lineage
    assert first.lineage[0].startswith("reviewed-pack@1.0.0:no-faq:")
    with pytest.raises(Exception):
        repository_validation.skill_inventory(repo.root, (Path("missing-root"),), None)


# spec: PIPE-PAGES-R023.14
def test_aggregate_skill_grade_behavior(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r", BAD_SKILL)
    code, report = _report(repo, tmp_path / "r", *POLICY)
    assert code == 1 and report is not None and report.skills is not None
    assert {r.skill_path: r.status for r in report.skills.results} == {
        "skills/one/SKILL.md": "pass",
        "skills/two/SKILL.md": "fail",
    }
    assert report.counts["skill"].passed == 1 and report.counts["skill"].failed == 1
    empty = Repo(tmp_path / "e")
    empty.root.mkdir()
    empty.git("init", "-q")
    empty.stage({"pyproject.toml": SKILL_ONLY, "README.md": "# x\n"})
    code, report = _report(empty, tmp_path / "e")
    assert code == 0 and report is not None and report.skills is not None
    assert not report.skills.applicable and report.skills.reason and report.full_coverage is False


# spec: PIPE-PAGES-R023.15
def test_aggregate_skill_grade_wiring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert GATES["repository-validation"] == "pipelines_hooks.code.repository_validation"
    calls: list[str] = []
    real = repository_validation.skill_grade.grade_document
    monkeypatch.setattr(
        repository_validation.skill_grade, "grade_document", lambda *a, **k: calls.append("g") or real(*a, **k)
    )
    repo = _repo(tmp_path / "r")
    assert repo.run("repository-validation", *POLICY) == 0
    assert calls == ["g", "g"]


# spec: PIPE-PAGES-R023.16
def test_aggregate_skill_grade_refusal(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r", BAD_SKILL)
    assert repo.run("repository-validation", *POLICY) == 1  # hard external failure
    missing = _repo(tmp_path / "m")
    assert missing.run("repository-validation", "--skill-policy", ".config/absent.yaml") == 2
    stale = _repo(tmp_path / "s", extra={"rules/pack.yaml": PACK_BODY + "# tampered\n"})
    assert stale.run("repository-validation", *POLICY) == 2
    escaping = _repo(tmp_path / "x")
    assert escaping.run("repository-validation", "--skills-root", "../outside") == 2


# spec: PIPE-PAGES-R023.17
def test_aggregate_skill_grade_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path / "r", BAD_SKILL)
    code, report = _report(repo, tmp_path / "r", *POLICY)
    assert code == 1 and report is not None and report.skills is not None
    bad = report.skills.results[1]
    external = [f for f in bad.findings if f.observed == "external-rule"]
    assert external and external[0].line and external[0].detail.startswith("reviewed-pack:no-faq")
    assert bad.lineage and bad.criteria["structure"] is not None and bad.grade is not None
    assert len({r.snapshot for r in report.skills.results}) == 1 == len({report.snapshot})
    assert "reviewed-pack@1.0.0:no-faq" in report.to_markdown().replace("\\", "")
    assert "reviewed-pack@1.0.0:no-faq" in capsys.readouterr().out
    assert json.loads(report.to_json())["skills"]["results"][1]["status"] == "fail"


# spec: PIPE-PAGES-R023.18
def test_aggregate_skill_grade_cli(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "r", BAD_SKILL)
    assert repo.run("repository-validation", *POLICY) == 1
    repo.stage({"skills/two/SKILL.md": VALID_SKILL})
    assert repo.run("repository-validation", *POLICY) == 0
    assert repo.run("repository-validation", "--skill-policy", ".config/none.yaml") == 2
    assert repo.run("repository-validation", "--skills-root", "../etc") == 2
    code, report = _report(repo, tmp_path / "r", "--skills-root", "docs")
    assert code == 2 and report is None
