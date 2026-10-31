"""spec-standard: optional artifacts exist where they carry content."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.specs import artifacts
from pipelines_hooks.specs.standard import _fails

PLAN_NONE = "# X — Plan\n\n## Phase 0: Research\n\nno unknowns\n\n## Cross-repo seams\n\nnone\n"
PLAN_SEAM = "# X — Plan\n\n## Phase 0: Research\n\nno unknowns\n\n## Cross-repo seams\n\n- `OTHER-AREA-R004` accepts the call.\n"
CONTRACT = (
    "# Seam\n\n## Wire shape\n\nA JSON body.\n\n## Refusal codes\n\n`denied`.\n\n"
    "Provider: other `OTHER-AREA-R004`\nConsumer: this `X-R001`\n"
)


def _spec(tmp: Path) -> Path:
    spec = tmp / "specs" / "x"
    spec.mkdir(parents=True)
    (spec / "checklists").mkdir()
    (spec / "checklists" / "requirements.md").write_text("- [x] a\n")
    return spec


def _check(spec: Path, plan: str, requirements: str = "| `X-R001` | **A.** B | C |\n") -> list[str]:
    return artifacts.check_artifacts(spec, {"plan.md": plan, "requirements.md": requirements})


def test_a_spec_without_seams_needs_no_contracts(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R041
    spec = _spec(tmp_path)
    assert _check(spec, PLAN_NONE) == []
    (spec / "contracts").mkdir()
    assert any("lists no seam" in f for f in _check(spec, PLAN_NONE))


def test_a_seam_needs_one_human_written_contract_document(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R041
    spec = _spec(tmp_path)
    assert any("one per seam" in f for f in _check(spec, PLAN_SEAM))
    (spec / "contracts").mkdir()
    (spec / "contracts" / "other.md").write_text(CONTRACT)
    assert _check(spec, PLAN_SEAM) == []
    (spec / "contracts" / "other.json").write_text("{}\n")
    assert any("not a human-written .md document" in f for f in _check(spec, PLAN_SEAM))


def test_a_contract_names_wire_shape_refusals_and_both_sides(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R041
    spec = _spec(tmp_path)
    (spec / "contracts").mkdir()
    (spec / "contracts" / "other.md").write_text("# Seam\n\n## Wire shape\n\n`OTHER-AREA-R004`.\n")
    found = " ".join(_check(spec, PLAN_SEAM))
    assert "lacks the 'refusal codes' section" in found
    assert "lacks a 'Provider:" in found


def test_a_row_adding_types_or_tables_needs_a_data_model(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R042
    spec = _spec(tmp_path)
    adds = "| `X-R001` | **Ontology.** The spec adds two ontology classes and one table. | T |\n"
    assert any("data-model.md is missing" in f for f in _check(spec, PLAN_NONE, adds))
    (spec / "data-model.md").write_text("# Data model\n\n- Class A\n- Class B\n- Table C\n")
    assert _check(spec, PLAN_NONE, adds) == []
    assert _check(_spec(tmp_path / "y"), PLAN_NONE) == []


def test_a_served_behaviour_row_needs_a_quickstart(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R043
    spec = _spec(tmp_path)
    served = "| `X-R001` | **Answer.** The service gives a served answer. | T |\n"
    assert any("quickstart.md is missing" in f for f in _check(spec, PLAN_NONE, served))
    (spec / "quickstart.md").write_text("Run `uv run pytest tests/test_x.py` to see the proof.\n")
    assert _check(spec, PLAN_NONE, served) == []
    quoted = "| `X-R001` | **Word.** The word `served` is quoted. | T |\n"
    assert _check(_spec(tmp_path / "z"), PLAN_NONE, quoted) == []


def test_research_exists_only_when_the_plan_lists_unknowns(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R044
    spec = _spec(tmp_path)
    unknown = PLAN_NONE.replace("no unknowns", "- Does the store accept the key?")
    assert any("research.md is missing" in f for f in _check(spec, unknown))
    (spec / "research.md").write_text("# Research\n")
    assert _check(spec, unknown) == []
    assert any("lists no unknowns" in f for f in _check(spec, PLAN_NONE))


def test_a_checklist_is_required_before_landing(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R044
    spec = tmp_path / "specs" / "x"
    spec.mkdir(parents=True)
    assert any("checklists/requirements.md is missing" in f for f in _check(spec, PLAN_NONE))


def test_row_findings_fail_only_for_an_added_row(tmp_path: Path) -> None:
    # spec: PIPE-GATES-R044
    spec = _spec(tmp_path)
    row = "X-R001 is a served behaviour row and quickstart.md is missing"
    assert _fails(row, {"X-R001"}, set(), spec, tmp_path)
    assert not _fails(row, set(), {"specs/x/requirements.md"}, spec, tmp_path)
    wide = "checklists/requirements.md is missing"
    assert _fails(wide, set(), {"specs/x/plan.md"}, spec, tmp_path)
    assert not _fails(wide, set(), set(), spec, tmp_path)
