"""spec-standard passes a clean spec and fires once per check kind."""

from __future__ import annotations

from tests.git_fixture_environment import fixture_git_environment

import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.specs.standard import main

FILES = (
    "spec.md",
    "plan.md",
    "requirements.md",
    "tasks.md",
    "test-spec.md",
    "status.json",
)


NARRATIVE = """# {id} — Title

### User Story 1 - Read (Priority: P1)

1. **Given** a spec, **When** the gate runs, **Then** it passes.

### Edge Cases

- A missing file.

- **FR-001**: The gate passes. Rows: `{id}-R001`.
- **SC-001**: One run. Rows: `{id}-R001`.

## Assumptions

- None.
"""


def _stage(root: Path, *names: str) -> None:
    subprocess.run(["git", "-C", str(root), "add", "--", *names], env=fixture_git_environment(), check=True)


def _spec(root: Path, name: str = "foo", spec_id: str = "FOO") -> Path:
    d = root / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        (d / f).write_text(f'{{"spec_id": "{spec_id}"}}\n' if f.endswith(".json") else "x\n")
    (d / "spec.md").write_text(NARRATIVE.format(id=spec_id))
    (d / "requirements.md").write_text(f"| `{spec_id}-R001` | req |\n")
    (root / "specs" / "README.md").write_text(f"- [x]({name}/spec.md)\n")
    constitution = root / ".specify" / "memory" / "constitution.md"
    constitution.parent.mkdir(parents=True, exist_ok=True)
    constitution.write_text("# Constitution\n")
    return d


@pytest.fixture
def root(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], env=fixture_git_environment(), check=True)
    return tmp_path


def _run(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(["--root", str(root)])
    return code, capsys.readouterr().out


def test_clean(root, capsys):
    _spec(root)
    assert _run(root, capsys) == (0, "spec-standard: clean (1 spec(s) checked)\n")


def test_template_skipped(root, capsys):
    _spec(root)
    (root / "specs" / "_template").mkdir()
    (root / "specs" / "_template" / "spec.md").write_text("junk\n")
    assert _run(root, capsys)[0] == 0


def test_file_set(root, capsys):
    d = _spec(root)
    (d / "plan.md").unlink()
    (d / "design.md").write_text("x")
    code, out = _run(root, capsys)
    assert code == 1
    assert "missing required file plan.md" in out and "forbidden file design.md" in out


def test_title(root, capsys):
    d = _spec(root)
    (d / "spec.md").write_text("# FOO - Title\n")
    assert "line 1 must match" in _run(root, capsys)[1]


def test_id_suffix_and_rows(root, capsys):
    d = _spec(root, "foo", "FOO-001")
    (d / "requirements.md").write_text("| `BAR-R001` | req |\n")
    out = _run(root, capsys)[1]
    assert "numeric suffix" in out and "does not start with FOO-001-R" in out


def test_names(root, capsys):
    _spec(root, "foo-audit", "FOO-FIX")
    out = _run(root, capsys)[1]
    assert "directory name contains forbidden word 'audit'" in out
    assert "spec ID contains forbidden word 'fix'" in out


def test_index(root, capsys):
    _spec(root)
    (root / "specs" / "README.md").write_text("nothing\n")
    assert "not listed in specs/README.md" in _run(root, capsys)[1]


@pytest.mark.parametrize("bad", ["DS-01", "FOO-01", "FOO-R01", "FOO-R0001", "foo-R001", "FOO-R001.", "FOO-001"])
def test_nonstandard_row_id_is_a_finding(root, capsys, bad):
    req = _spec(root) / "requirements.md"
    req.write_text(req.read_text() + f"| `{bad}` | A nonconforming row ID. |\n")
    code, out = _run(root, capsys)
    assert code == 1
    assert f"row {bad} does not match <PREFIX>-R<nnn>[.n]" in out


def test_child_and_nested_prefix_row_ids_pass(root, capsys):
    req = _spec(root) / "requirements.md"
    req.write_text(req.read_text() + "| `FOO-R001.2` | child |\n| `FOO-R002.1.3` | grandchild |\n")
    assert _run(root, capsys)[0] == 0


@pytest.mark.parametrize(
    "title, expected",
    [
        ("**RETIRED: replaced by FOO-R001.**", 0),
        ("Active row; RETIRED is discussed only.", 1),
        ("**Active row.** RETIRED: replaced by FOO-R001.", 1),
    ],
)
def test_moved_retired_identity_uses_shared_status_parser(root, capsys, title, expected):
    # spec: PIPE-CONNSPEC-R006
    req = _spec(root) / "requirements.md"
    req.write_text(req.read_text() + f"| `OLD-R001` | {title} | preserved |\n")
    assert _run(root, capsys)[0] == expected


def test_retired_duplicate_does_not_hide_active_wrong_prefix(root, capsys):
    # spec: PIPE-CONNSPEC-R006
    req = _spec(root) / "requirements.md"
    req.write_text(
        req.read_text() + "| `OLD-R001` | **RETIRED: replaced by FOO-R001.** | |\n"
        "| `OLD-R001` | **Active duplicate.** | |\n"
    )
    assert main(["--root", str(root), "--tombstones"]) == 1


def test_tombstone_row_is_a_finding(root, capsys):
    req = _spec(root) / "requirements.md"
    req.write_text(req.read_text() + "| `FOO-R002` | RETIRED: replaced by BAR-R001 |\n")
    out = _run(root, capsys)[1]
    assert "requirements.md row FOO-R002 is a tombstone for a moved row; delete it" in out


def test_tombstone_row_is_advisory_by_default(root, capsys):
    req = _spec(root) / "requirements.md"
    req.write_text(req.read_text() + "| `FOO-R002` | RETIRED: replaced by BAR-R001 |\n")
    code, out = _run(root, capsys)
    assert code == 0 and "ADV spec-standard:" in out


def test_optional_artifacts_are_accepted(root, capsys):
    # spec: PIPE-GATES-R022
    d = _spec(root)
    for name in ("research.md", "data-model.md", "quickstart.md"):
        (d / name).write_text("x\n")
    for name in ("contracts", "checklists"):
        (d / name).mkdir()
        (d / name / "a.md").write_text("x\n")
    assert _run(root, capsys) == (0, "spec-standard: clean (1 spec(s) checked)\n")


def test_optional_artifact_of_the_wrong_kind_is_a_finding(root, capsys):
    # spec: PIPE-GATES-R022
    d = _spec(root)
    (d / "contracts").write_text("x\n")
    (d / "research.md").mkdir()
    code, out = _run(root, capsys)
    assert code == 1 and "contracts/ must be a directory" in out and "research.md must be a file" in out


@pytest.mark.parametrize("name", ["design.md", "architecture.md", "coverage.md", "cross-repo.md"])
def test_forbidden_files_stay_forbidden(root, capsys, name):
    # spec: PIPE-GATES-R022
    (_spec(root) / name).write_text("x\n")
    code, out = _run(root, capsys)
    assert code == 1 and f"forbidden file {name}" in out


def test_missing_constitution_is_advisory(root, capsys):
    # spec: PIPE-GATES-R023
    _spec(root)
    (root / ".specify" / "memory" / "constitution.md").unlink()
    code, out = _run(root, capsys)
    assert code == 0 and "ADV spec-standard: .specify/memory/constitution.md is missing" in out


def test_constitution_present_is_clean(root, capsys):
    # spec: PIPE-GATES-R023
    _spec(root)
    assert _run(root, capsys) == (0, "spec-standard: clean (1 spec(s) checked)\n")


def test_narrative_sections_fail_for_a_touched_spec(root, capsys):
    # spec: PIPE-GATES-R024
    d = _spec(root)
    (d / "spec.md").write_text("# FOO — Title\n\nNo sections.\n")
    _stage(root, "specs/foo/spec.md")
    code, out = _run(root, capsys)
    assert code == 1
    for part in ("User Story N", "Given/When/Then", "'Edge Cases'", "'Assumptions'"):
        assert part in out
    assert not [line for line in out.splitlines() if "specs/foo: spec.md" in line and "advisory" in line]


def test_narrative_sections_are_advisory_for_an_untouched_spec(root, capsys):
    # spec: PIPE-GATES-R024
    d = _spec(root)
    (d / "spec.md").write_text("# FOO — Title\n\nNo sections.\n")
    code, out = _run(root, capsys)
    assert code == 0
    assert "ADV spec-standard: specs/foo: spec.md has no 'Assumptions' section (advisory: spec not touched)" in out


def test_label_must_name_existing_rows(root, capsys):
    # spec: PIPE-GATES-R024
    d = _spec(root)
    text = (d / "spec.md").read_text()
    (d / "spec.md").write_text(text + "- **FR-002**: No rows.\n- **FR-003**: Bad row. Rows: `FOO-R009`.\n")
    _stage(root, "specs/foo/spec.md")
    code, out = _run(root, capsys)
    assert code == 1 and "FR-002 names no -R row" in out and "names FOO-R009, which requirements.md lacks" in out


def test_complete_narrative_is_clean(root, capsys):
    # spec: PIPE-GATES-R024
    _spec(root)
    _stage(root, "specs/foo/spec.md")
    assert _run(root, capsys) == (0, "spec-standard: clean (1 spec(s) checked)\n")


def test_clarification_marker_is_a_finding(root, capsys):
    # spec: PIPE-GATES-R025
    d = _spec(root)
    (d / "spec.md").write_text((d / "spec.md").read_text() + "\n[NEEDS CLARIFICATION: which store?]\n")
    code, out = _run(root, capsys)
    assert code == 1 and "spec.md:" in out and "open [NEEDS CLARIFICATION: ...] marker" in out
    (d / "spec.md").write_text(NARRATIVE.format(id="FOO"))
    (d / "requirements.md").write_text("| `FOO-R001` | req [NEEDS CLARIFICATION: scope] |\n")
    assert "requirements.md:1 holds an open" in _run(root, capsys)[1]


def test_marker_in_code_is_ignored(root, capsys):
    # spec: PIPE-GATES-R025
    d = _spec(root)
    (d / "spec.md").write_text(
        (d / "spec.md").read_text()
        + "\nWrite `[NEEDS CLARIFICATION: q]` in prose.\n\n```\n[NEEDS CLARIFICATION: q]\n```\n"
    )
    assert _run(root, capsys)[0] == 0


def _tasks(root: Path, body: str) -> None:
    (root / "specs" / "foo" / "tasks.md").write_text(body)


def test_numbered_task_line_is_clean(root, capsys):
    # spec: PIPE-GATES-R026
    _spec(root)
    _tasks(
        root, "- [ ] T001 [P] [US1] FOO-R001 Do it.\n- [x] T002 FOO-R001 Do more.\n- [ ] T003 [US2] FOO-R001 Next.\n"
    )
    _stage(root, "specs/foo/tasks.md")
    assert _run(root, capsys) == (0, "spec-standard: clean (1 spec(s) checked)\n")


def test_task_line_needs_a_row_id(root, capsys):
    # spec: PIPE-GATES-R026
    _spec(root)
    _tasks(root, "- [ ] T001 Do it without a row.\n- [ ] Free text.\n")
    _stage(root, "specs/foo/tasks.md")
    code, out = _run(root, capsys)
    assert code == 1 and out.count("must read '- [ ] T001") == 2


def test_task_line_with_unknown_row_is_a_finding(root, capsys):
    # spec: PIPE-GATES-R026
    _spec(root)
    _tasks(root, "- [ ] T001 FOO-R009 Do it.\n")
    _stage(root, "specs/foo/tasks.md")
    code, out = _run(root, capsys)
    assert code == 1 and "names FOO-R009, which requirements.md lacks" in out


def test_task_lines_are_advisory_for_an_untouched_spec(root, capsys):
    # spec: PIPE-GATES-R026
    _spec(root)
    _tasks(root, "- [ ] Free text.\n")
    code, out = _run(root, capsys)
    assert (
        code == 0
        and "ADV spec-standard: specs/foo: tasks.md:1 must read" in out
        and "(advisory: spec not touched)" in out
    )


def test_status_header_is_a_finding(root, capsys):
    # spec: PIPE-GATES-R027
    d = _spec(root)
    (d / "plan.md").write_text("# FOO — Plan\n\n**Status**: Draft\n")
    code, out = _run(root, capsys)
    assert code == 0 and "plan.md:3 writes a Status line" in out and "ADV" in out
    _stage(root, "specs/foo/plan.md")
    code, out = _run(root, capsys)
    assert code == 1 and "ADV spec-standard: specs/foo: plan.md:3" not in out


def test_a_change_against_the_base_revision_counts_as_touched(root, capsys):
    # spec: PIPE-GATES-R024
    d = _spec(root)
    env = fixture_git_environment()
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "add", "--", "."], env=env, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "base"], env=env, check=True)
    (d / "spec.md").write_text("# FOO — Title\n\nNo sections.\n")
    assert main(["--root", str(root), "--base", "HEAD"]) == 1
    capsys.readouterr()
    assert main(["--root", str(root)]) == 0
