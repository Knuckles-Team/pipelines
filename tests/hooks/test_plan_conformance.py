"""plan-conformance: a plan.md follows the plan template, names real rows and links real files."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipelines_hooks import cli
from pipelines_hooks.ci_replica.change_scope import SPEC_GATES
from pipelines_hooks.specs import plan_conformance as gate

TEMPLATE = (Path(__file__).resolve().parents[2] / ".specify" / "templates" / "plan-template.md").read_text()
HEADINGS = gate.required_headings(TEMPLATE)
REQUIREMENTS = "# DEMO-AREA — Demo\n\n| `DEMO-AREA-R001` | **A.** B | C |\n| `DEMO-AREA-R001.1` | **D.** E | F |\n"


def build(*, drop=(), swap=False, extra="", ident="DEMO-AREA", body="Real content.") -> str:
    heads = [h for h in HEADINGS if h not in drop]
    if swap:
        heads[0], heads[1] = heads[1], heads[0]
    parts = [f"# {ident} — Implementation plan\n"]
    parts += [f"{h}\n\n{body}\n" for h in heads]
    return "\n".join(parts) + extra


def run(tmp_path: Path, plan: str, capsys) -> tuple[int, str]:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    spec = tmp_path / "specs" / "demo"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "requirements.md").write_text(REQUIREMENTS)
    (spec / "notes.md").write_text("notes\n")
    (spec / "plan.md").write_text(plan)
    code = gate.main(["--root", str(tmp_path), str(spec / "plan.md")])
    return code, capsys.readouterr().out


@pytest.fixture(autouse=True)
def _template(tmp_path: Path) -> None:
    target = tmp_path / ".specify" / "templates"
    target.mkdir(parents=True)
    (target / "plan-template.md").write_text(TEMPLATE)


@pytest.mark.spec("PIPE-GATES-R046")
def test_a_conforming_plan_is_clean(tmp_path: Path, capsys) -> None:
    ok = build(extra="\nSee `DEMO-AREA-R001.1` and [notes](notes.md).\n")
    assert run(tmp_path, ok, capsys) == (0, "plan-conformance: clean (1 plan(s) checked)\n")


@pytest.mark.spec("PIPE-GATES-R046")
@pytest.mark.parametrize(
    ("plan", "message"),
    [
        (build(drop=("## Build contract",)), "missing heading '## Build contract'"),
        (build(swap=True), "is out of order"),
        (build(extra="\n## Extra\n\nText.\n"), "unexpected heading '## Extra'"),
        (build(body=""), "is empty"),
        (build(ident="[ID]"), "first line must read"),
        (build(ident="OTHER-AREA"), "must equal the spec ID DEMO-AREA"),
        (build(body="[NEEDS CLARIFICATION: which store?]"), "unresolved placeholder"),
        (build(body="[The primary requirement, in a sentence.]"), "bracketed line"),
        (build(extra="\n- **Storage**: [store, or N/A]\n"), "field value left in brackets"),
        (build(extra="\nSee `DEMO-AREA-R099`.\n"), "DEMO-AREA-R099 is not defined"),
        (build(extra="\nSee [gone](missing.md).\n"), "fix the relative path"),
    ],
    ids=[
        "missing",
        "order",
        "unexpected",
        "empty",
        "title",
        "title-id",
        "marker",
        "bracket-line",
        "field",
        "unknown-id",
        "link",
    ],
)
def test_each_failure_type_is_a_path_line_message(tmp_path: Path, capsys, plan: str, message: str) -> None:
    code, out = run(tmp_path, plan, capsys)
    assert code == 1
    lines = [ln for ln in out.splitlines() if message in ln]
    assert lines and lines[0].startswith("specs/demo/plan.md:") and lines[0].split(":")[1].isdigit()
    assert out.rstrip().endswith("plan(s)")


@pytest.mark.spec("PIPE-GATES-R046")
def test_foreign_seam_ids_are_allowed_only_in_the_seams_section(tmp_path: Path, capsys) -> None:
    plan = build().replace(
        "## Cross-repo seams\n\nReal content.", "## Cross-repo seams\n\n- `OTHER-AREA-R004` accepts it."
    )
    assert run(tmp_path, plan, capsys)[0] == 0
    elsewhere = build().replace("## Summary\n\nReal content.", "## Summary\n\nSee `OTHER-AREA-R004`.", 1)
    assert "OTHER-AREA-R004 is not defined" in run(tmp_path, elsewhere, capsys)[1]


@pytest.mark.spec("PIPE-GATES-R046")
def test_headings_come_from_the_template_at_run_time(tmp_path: Path, capsys) -> None:
    template = tmp_path / ".specify" / "templates" / "plan-template.md"
    template.write_text(TEMPLATE + "\n## Rollout\n\n[Steps.]\n")
    code, out = run(tmp_path, build(), capsys)
    assert code == 1 and "missing heading '## Rollout'" in out


@pytest.mark.spec("PIPE-GATES-R046")
def test_the_gate_joins_the_spec_group_and_spec_gate_set() -> None:
    assert "plan-conformance" in cli.GATES and "plan-conformance" in cli.GROUPS["spec"]
    assert "plan-conformance" in SPEC_GATES
