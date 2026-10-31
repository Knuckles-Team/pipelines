"""The spec templates sit at the upstream location, are vended by a script and cannot drift."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.cli import main as cli_main
from pipelines_hooks.specs import placement, templates_sync
from scripts import check_public_specs, sync_spec_templates
from tests.git_fixture_environment import fixture_git_environment

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".specify" / "templates"
NAMES = (
    "spec-template.md",
    "plan-template.md",
    "tasks-template.md",
    "checklist-template.md",
    "constitution-template.md",
    "requirements-template.md",
    "test-spec-template.md",
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=fixture_git_environment(), check=True)
    return tmp_path


def test_the_seven_templates_sit_in_the_upstream_location() -> None:
    # spec: PIPE-GATES-R035
    assert sorted(p.name for p in SOURCE.iterdir()) == sorted(NAMES)
    assert not (ROOT / "specs" / "_template").exists()
    assert check_public_specs._template_errors(ROOT) == []


def test_a_specs_template_directory_is_a_finding(repo: Path) -> None:
    # spec: PIPE-GATES-R035
    (repo / "specs" / "_template").mkdir(parents=True)
    (repo / "specs" / "_template" / "spec.md").write_text("x\n")
    found = " ".join(f for _, f in placement.check_placement(repo))
    assert "templates live only in .specify/templates/" in found


def test_the_sync_script_writes_and_check_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # spec: PIPE-GATES-R036
    assert sync_spec_templates.main(["--root", str(repo), "--check"]) == 1
    assert sync_spec_templates.main(["--root", str(repo)]) == 0
    assert sorted(p.name for p in (repo / ".specify" / "templates").iterdir()) == sorted(NAMES)
    assert sync_spec_templates.main(["--root", str(repo), "--check"]) == 0


def test_check_fails_on_drift_and_writes_nothing(repo: Path) -> None:
    # spec: PIPE-GATES-R036
    sync_spec_templates.main(["--root", str(repo)])
    changed = repo / ".specify" / "templates" / "spec-template.md"
    changed.write_text("drift\n")
    assert sync_spec_templates.main(["--root", str(repo), "--check"]) == 1
    assert changed.read_text() == "drift\n"


def test_missing_changed_and_unknown_files_are_findings(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R037
    destination = tmp_path / "t"
    templates_sync.write(SOURCE, destination)
    assert templates_sync.mismatches(SOURCE, destination) == []
    (destination / "plan-template.md").unlink()
    (destination / "spec-template.md").write_text("drift\n")
    (destination / "extra.md").write_text("x\n")
    found = templates_sync.mismatches(SOURCE, destination)
    assert any("plan-template.md is missing" in f for f in found)
    assert any("spec-template.md differs" in f for f in found)
    assert any("extra.md is not a vended template" in f for f in found)


def test_the_gate_is_a_published_hook_that_fails_on_drift(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # spec: PIPE-GATES-R037
    hooks = yaml.safe_load((ROOT / ".pre-commit-hooks.yaml").read_text())
    assert {h["id"]: h["entry"] for h in hooks}["spec-templates"] == "pipelines-hook spec-templates"
    config = yaml.safe_load((ROOT / ".config" / "pre-commit.yaml").read_text())
    local = {h["id"] for r in config["repos"] if r["repo"] == "local" for h in r["hooks"]}
    assert "spec-templates" in local
    consumer = yaml.safe_load((ROOT / "templates" / "pre-commit.yaml").read_text())
    assert "spec-templates" in {h["id"] for r in consumer["repos"] for h in r.get("hooks", [])}
    assert cli_main(["spec-templates", "--root", str(repo)]) == 1
    assert "spec-templates: FAIL" in capsys.readouterr().err


def test_the_wheel_ships_the_templates_and_every_package() -> None:
    # spec: PIPE-GATES-R037
    setuptools = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]
    assert setuptools["package-dir"]["pipelines_hooks.spec_templates"] == ".specify/templates"
    assert setuptools["package-data"]["pipelines_hooks.spec_templates"] == ["*.md"]
    on_disk = {".".join(p.parent.relative_to(ROOT).parts) for p in (ROOT / "pipelines_hooks").rglob("__init__.py")}
    assert set(setuptools["packages"]) == on_disk | {"pipelines_hooks.spec_templates"}
