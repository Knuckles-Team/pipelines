"""One idempotent generator brings a repository to the spec-driven standard."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest

from pipelines_hooks.connector import spec_templates
from pipelines_hooks.connector import standard as connector_standard
from pipelines_hooks.specs import sdd_scaffold, templates_sync
from scripts import standardize_sdd
from tests.git_fixture_environment import fixture_git_environment

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".specify" / "templates"
TODAY = date(2026, 10, 31)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=fixture_git_environment(), check=True)
    return tmp_path


def test_the_generator_writes_every_part_and_a_second_run_changes_nothing(repo: Path) -> None:
    # spec: PIPE-GATES-R046
    (repo / "AGENTS.md").write_text("# Agent\n\nIntro.\n\n## Build\n\nRun it.\n")
    written = sdd_scaffold.standardize(repo, "demo-mcp", SOURCE, TODAY)
    assert written == [".specify/memory/constitution.md", ".specify/templates", "CONTRIBUTING.md", "AGENTS.md"]
    constitution = (repo / sdd_scaffold.CONSTITUTION).read_text()
    assert constitution.startswith("# demo-mcp constitution")
    assert "[" + "date]" not in constitution and "[Title" not in constitution and "| [Limit]" not in constitution
    assert "**Ratified**: 2026-10-31" in constitution
    assert templates_sync.mismatches(SOURCE, repo / templates_sync.TEMPLATES) == []
    contributing = (repo / "CONTRIBUTING.md").read_text()
    section = contributing.split(sdd_scaffold.CONTRIBUTING_HEADING, 1)[1].strip().splitlines()
    assert len(section) <= 8
    agents = (repo / "AGENTS.md").read_text()
    assert agents.index(sdd_scaffold.AGENTS_HEADING) < agents.index("## Build")
    assert "`speckit-specify`" in agents
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert sdd_scaffold.standardize(repo, "demo-mcp", SOURCE, TODAY) == []
    assert {p: p.read_bytes() for p in before} == before


def test_an_existing_constitution_and_sections_are_kept(repo: Path) -> None:
    # spec: PIPE-GATES-R046
    (repo / sdd_scaffold.CONSTITUTION).parent.mkdir(parents=True)
    (repo / sdd_scaffold.CONSTITUTION).write_text("# Own constitution\n")
    (repo / "CONTRIBUTING.md").write_text(f"# C\n\n{sdd_scaffold.CONTRIBUTING_SECTION}")
    assert sdd_scaffold.standardize(repo, "x", SOURCE, TODAY) == [".specify/templates"]
    assert (repo / sdd_scaffold.CONSTITUTION).read_text() == "# Own constitution\n"
    assert not (repo / "AGENTS.md").exists()


def test_the_script_check_mode_writes_nothing_then_passes_after_a_run(repo: Path) -> None:
    # spec: PIPE-GATES-R046
    assert standardize_sdd.main(["--root", str(repo), "--name", "x", "--check"]) == 1
    assert not (repo / ".specify").exists()
    assert standardize_sdd.main(["--root", str(repo), "--name", "x"]) == 0
    assert standardize_sdd.main(["--root", str(repo), "--name", "x", "--check"]) == 0


def test_connector_standard_checks_the_vended_templates(repo: Path) -> None:
    # spec: PIPE-GATES-R046
    assert connector_standard.MEMBERS["spec-templates"] is spec_templates
    assert spec_templates.main(["--root", str(repo)]) == 0
    sdd_scaffold.standardize(repo, "x", SOURCE, TODAY)
    assert spec_templates.main(["--root", str(repo)]) == 0
    (repo / templates_sync.TEMPLATES / "plan-template.md").write_text("drift\n")
    assert spec_templates.main(["--root", str(repo)]) == 1


def test_the_stack_profile_lookup_is_one_pluggable_function(tmp_path: Path, repo: Path) -> None:
    # spec: PIPE-GATES-R046
    assert sdd_scaffold.stack_profile(tmp_path, repo) is None
    (tmp_path / "reference").mkdir()
    (tmp_path / sdd_scaffold.STACK_PROFILES).write_text("profiles:\n  python:\n    pre_commit: [hygiene]\n")
    assert sdd_scaffold.stack_profile(tmp_path, repo) == {"pre_commit": ["hygiene"]}
