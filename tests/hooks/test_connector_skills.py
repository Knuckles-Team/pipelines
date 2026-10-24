"""The skill gates are a connector-standard member: atomicity, frontmatter portability, path portability."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.connector import skills, standard

SKILL = """---
name: demo-skill
description: Look up one demo record. Use when the agent must find a demo record. Do NOT use for writing records.
skill_type: skill
---

# Demo skill

Reads one record.
"""


def _repo(root: Path, skill: str | None = SKILL, extra_toml: str = "") -> Path:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo-mcp"\nversion = "1.0.0"\n' + extra_toml, encoding="utf-8"
    )
    if skill is not None:
        folder = root / "demo_mcp" / "skills" / "demo-skill"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(skill, encoding="utf-8")
    return root


@pytest.mark.spec("PIPE-GATES-R016.115")
def test_a_connector_without_skills_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_repo(tmp_path, skill=None))
    assert skills.main([]) == 0


@pytest.mark.spec("PIPE-GATES-R016.115")
def test_a_conforming_skill_passes_all_three_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(_repo(tmp_path))
    assert skills.main([]) == 0
    assert "OK" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R016.115")
def test_a_non_portable_frontmatter_fails_and_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = SKILL.replace("skill_type: skill", "skill_type: gadget")
    monkeypatch.chdir(_repo(tmp_path, skill=bad))
    assert skills.main([]) == 1
    captured = capsys.readouterr()
    assert "frontmatter-portability" in captured.out + captured.err


@pytest.mark.spec("PIPE-GATES-R016.115")
def test_a_long_path_fails_unless_its_directory_is_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path)
    deep = root / "demo_mcp" / "skills" / "demo-skill" / "reference"
    deep.mkdir()
    (deep / ("x" * 150 + ".md")).write_text("x\n", encoding="utf-8")
    (deep / "more").mkdir()
    (deep / "more" / ("y" * 90 + ".md")).write_text("y\n", encoding="utf-8")
    monkeypatch.chdir(root)
    assert skills.main([]) == 1
    (root / "pyproject.toml").write_text(
        (root / "pyproject.toml").read_text(encoding="utf-8")
        + '\n[tool.pipelines.skills]\npath_exclude = ["demo_mcp/skills/demo-skill/reference"]\n',
        encoding="utf-8",
    )
    assert skills.main([]) == 0


@pytest.mark.spec("PIPE-GATES-R016.115")
def test_connector_standard_runs_the_skills_member() -> None:
    assert standard.MEMBERS["skills"] is skills
