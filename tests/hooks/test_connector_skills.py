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

## Steps

1. Read the record with `demo get <id>`. Verify the output names the record.

| Failure | Cause | Recovery |
|---|---|---|
| Not found | Wrong id | Run `demo list` and pick an id from it |
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


@pytest.mark.spec("PIPE-GATES-R014.15")
def test_vendored_paths_leave_the_path_check_and_codespell(tmp_path: Path, monkeypatch, capsys) -> None:
    from pipelines_hooks.connector import codespell

    vendored = tmp_path / "demo_mcp" / "upstream" / ("v" * 120)
    vendored.mkdir(parents=True)
    (vendored / "x.md").write_text("x\n", encoding="utf-8")
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    assert skills.main([]) == 1
    capsys.readouterr()
    (root / "pyproject.toml").write_text(
        (root / "pyproject.toml").read_text(encoding="utf-8")
        + '[tool.pipelines.connector]\nvendored = ["demo_mcp/upstream"]\n',
        encoding="utf-8",
    )
    assert skills.main([]) == 0
    assert codespell.extra_excludes(root) == ["demo_mcp/upstream"]
    assert codespell.excluded("demo_mcp/upstream/" + "v" * 120 + "/x.md", codespell.extra_excludes(root))


def _skill_with(body: str) -> str:
    return SKILL.split("## Steps")[0] + body


@pytest.mark.spec("PIPE-GATES-R016.120")
@pytest.mark.parametrize(
    ("body", "code"),
    [
        (
            "## Steps\n\n1. Read the record and then delete it with `demo rm`. Verify it is gone.\n",
            "STEP_MULTI_OBJECTIVE",
        ),
        ("## Steps\n\n1. Read the record. Verify the output.\n", "STEP_NO_COMMAND"),
        ("## Steps\n\n1. Read the record with `demo get`.\n", "STEP_NO_VERIFY"),
        ("## Steps\n\n1. Read the record with `demo get`. Verify it.\n", "RECOVERY_TABLE_MISSING"),
        (
            "## Steps\n\n1. Read with `demo get`. Verify it.\n\n| Failure | Cause | Recovery |\n|---|---|---|\n| x | y | Try again |\n",
            "RECOVERY_VAGUE",
        ),
    ],
)
def test_a_skill_without_a_verified_step_fails_and_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], body: str, code: str
) -> None:
    monkeypatch.chdir(_repo(tmp_path, skill=_skill_with(body)))
    assert skills.main([]) == 1
    assert code in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R016.120")
@pytest.mark.parametrize(
    ("edit", "code"),
    [
        (
            lambda s: s.replace("Look up one demo record.", "Look up one demo record. " + "x" * 400),
            "DESCRIPTION_TOO_LONG",
        ),
        (lambda s: s + "line\n" * 501, "BODY_TOO_LONG"),
        (lambda s: s + "\nSee [notes](NOTES.md).\n", "REFERENCE_NOT_STAGED"),
    ],
)
def test_each_budget_code_fires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], edit, code: str
) -> None:
    root = _repo(tmp_path, skill=edit(SKILL))
    (root / "demo_mcp" / "skills" / "demo-skill" / "NOTES.md").write_text("n\n", encoding="utf-8")
    monkeypatch.chdir(root)
    assert skills.main([]) == 1
    assert code in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R016.120")
def test_a_connector_file_in_a_skill_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    (root / "demo_mcp" / "skills" / "demo-skill" / ".mcp.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(root)
    assert skills.main([]) == 1
    assert "SKILL_HAS_CONNECTOR_FILE" in capsys.readouterr().out


SPEC = """goal: Look up one demo record.
outputs: [the record]
required_tool_actions: [demo_get]
forbidden_tool_actions: [demo_delete]
target_agents: [claude]
target_models: [standard-model]
steps:
  - objective: Read the record.
    command: demo get <id>
    verify: The output names the record.
    on_failure: Run `demo list` and pick an id from it.
"""


def _compiled_repo(root: Path) -> Path:
    from pipelines_hooks.connector.skill_checks import compile as skill_compile

    _repo(root)
    folder = root / "demo_mcp" / "skills" / "demo-skill"
    (folder / "skill.spec.yml").write_text(SPEC, encoding="utf-8")
    compiled = skill_compile.compile_skill(
        skill_compile.parse_spec(SPEC), "demo-skill", (folder / "SKILL.md").read_text(encoding="utf-8")
    )
    (folder / "SKILL.md").write_text(compiled.skill_md, encoding="utf-8")
    (folder / "evals").mkdir()
    (folder / "evals" / "prompts.jsonl").write_text(compiled.prompts_jsonl, encoding="utf-8")
    return folder


@pytest.mark.spec("PIPE-GATES-R016.121")
def test_a_stale_compiled_skill_fails_and_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _compiled_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert skills.main([]) == 0
    (folder / "skill.spec.yml").write_text(SPEC.replace("Look up one", "Find one"), encoding="utf-8")
    assert skills.main([]) == 1
    assert "SKILL_COMPILE_STALE: demo-skill" in capsys.readouterr().out
