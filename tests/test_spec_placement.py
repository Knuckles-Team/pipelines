"""spec-standard: lower-case kebab-case names and fixed artifact placement."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.specs import placement
from pipelines_hooks.specs.standard import ADVISORY_TAG, check_placement


def _tree(root: Path, *paths: str) -> None:
    for rel in paths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n")


def _found(root: Path) -> str:
    return "\n".join(f"{p}: {f}" for p, f in placement.check_placement(root))


def test_lower_case_kebab_case_names_pass(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R037
    _tree(tmp_path, "specs/README.md", "specs/gates/test-spec.md", "specs/gates/checklists/requirements.md")
    _tree(tmp_path, ".specify/memory/constitution.md", ".specify/templates/plan-template.md")
    assert placement.check_placement(tmp_path) == []


def test_an_upper_case_or_underscore_name_is_a_finding(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R037
    _tree(tmp_path, "specs/gates/DRIFT_REPORT.md", "specs/gates/Notes.md", "specs/gates/test_spec.md")
    found = _found(tmp_path)
    assert "DRIFT_REPORT.md" in found and "Notes.md" in found and "test_spec.md" in found


def test_a_tool_required_upper_case_file_is_allowed(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R037
    names = sorted(placement.UPPER_CASE_ALLOWED)
    assert names == ["AGENTS.md", "CHANGELOG.md", "CLAUDE.md", "LICENSE", "README.md", "SKILL.md"]
    _tree(tmp_path, *(f"specs/gates/{n}" for n in names))
    assert placement.check_placement(tmp_path) == []


def test_recorded_evidence_keeps_its_tool_name(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R037
    _tree(tmp_path, "specs/gates/evidence/Run_1.LOG")
    assert placement.check_placement(tmp_path) == []


def test_a_numeric_prefix_on_a_spec_directory_is_a_finding(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R038
    _tree(tmp_path, "specs/01-gates/spec.md")
    assert "no numeric prefix" in _found(tmp_path)


def test_plans_templates_and_the_constitution_have_one_place(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R038
    _tree(tmp_path, "specs/gates/plan.md", ".specify/templates/plan-template.md", ".specify/memory/constitution.md")
    assert placement.check_placement(tmp_path) == []
    _tree(tmp_path, "specs/gates/plans/a.md", "specs/migration-plan.md", "specs/gates/spec-template.md")
    _tree(tmp_path, "specs/gates/constitution.md", ".specify/constitution.md")
    found = _found(tmp_path)
    assert "plans live only in specs/<family>/plan.md" in found
    assert "migration-plan.md: plans live only" in found
    assert "spec-template.md: templates live only" in found
    assert "specs/gates/constitution.md: the constitution lives only" in found
    assert ".specify/constitution.md: the constitution lives only" in found


def test_an_untouched_path_is_advisory_and_a_touched_one_fails(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R037
    _tree(tmp_path, "specs/gates/Notes.md")
    assert check_placement(tmp_path, set())[0].endswith(ADVISORY_TAG)
    assert not check_placement(tmp_path, {"specs/gates/Notes.md"})[0].endswith(ADVISORY_TAG)
