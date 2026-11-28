"""PIPE-GATES-R086.12 to R086.15: the census reads declared machines by structure, skips values and generated code."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.code import state_machine
from tests.hooks.state_machine_repo import git, POLICY


def _census(tmp_path: Path, files: dict[str, str]) -> list[str]:
    """The finding lines of a census over a throwaway repository holding ``files``."""
    root = tmp_path / "repo"
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    (root / "pyproject.toml").write_text(POLICY.format(mode="blocking", extra=""), encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    return [f.render() for f in state_machine.run(root, census=True).findings]


def _codes(lines: list[str]) -> set[str]:
    return {line.split()[2] for line in lines}


LAMP_RS = """\
pub struct Edge<S, E> { pub id: &'static str, pub from: S, pub event: E, pub to: S }
pub struct MachineDef<S, E> { pub name: &'static str, pub states: &'static [S], pub initial: S, pub edges: &'static [Edge<S, E>] }
pub struct Blocked;
pub fn fire<S, E>(def: &MachineDef<S, E>, from: S, event: E) -> Result<S, Blocked> { Err(Blocked) }
"""
LAMP_STATIC_RS = """\
use crate::def::{Edge, MachineDef};
use crate::lamp::LampState;
pub enum LampState { Off, On }
pub enum Press { Toggle }
pub static LAMP: MachineDef<LampState, Press> = MachineDef {
    name: "Lamp",
    states: &[LampState::Off, LampState::On],
    initial: LampState::Off,
    edges: &[
        Edge { id: "L1", from: LampState::Off, event: Press::Toggle, to: LampState::On },
        Edge { id: "L2", from: LampState::On, event: Press::Toggle, to: LampState::Off },
    ],
};
"""
LAMP_HOLDER_RS = """\
use crate::lamp::LampState;
pub struct Bulb { pub state: LampState }
impl Bulb {
    pub fn commit(&mut self, next: LampState) { self.state = next; }
}
"""


@pytest.mark.spec("PIPE-GATES-R086.12")
def test_a_machine_definition_static_declares_the_machine_of_its_state_enum(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"src/def.rs": LAMP_RS, "src/lamp.rs": LAMP_STATIC_RS, "src/bulb.rs": LAMP_HOLDER_RS})
    assert not [line for line in lines if "SM-NO-DECLARATION" in line], lines
    assert not [line for line in lines if "SM-MULTI-ASSIGN" in line], lines
    # declared, so the rules for a declared machine apply: no test names an edge.
    assert "SM-UNTESTED-EDGE" in _codes(lines)


FLOW_PY = """\
from enum import StrEnum


class Stage(StrEnum):
    OPEN = "open"
    SHUT = "shut"


class Step(StrEnum):
    CLOSE = "close"
    REOPEN = "reopen"


_S, _E = Stage, Step
FLOW: dict[tuple[Stage, Step], Stage] = {
    (_S.OPEN, _E.CLOSE): _S.SHUT,
    (_S.SHUT, _E.REOPEN): _S.OPEN,
}


class Blocked(RuntimeError):
    pass


def move(stage: Stage, step: Step) -> Stage:
    target = FLOW.get((stage, step))
    if target is None:
        raise Blocked(stage, step)
    return target


class Door:
    stage: Stage

    def toggle(self, step: Step) -> None:
        self.stage = move(self.stage, step)
"""


@pytest.mark.spec("PIPE-GATES-R086.12")
def test_an_oddly_named_edge_table_declares_the_machine_of_its_enum(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/door.py": FLOW_PY})
    assert "SM-NO-DECLARATION" not in _codes(lines), lines
    assert "SM-UNTESTED-EDGE" in _codes(lines)  # declared: edges need tests


@pytest.mark.spec("PIPE-GATES-R086.12")
def test_the_refusal_is_the_error_the_transition_function_raises(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/door.py": FLOW_PY})
    assert [line for line in lines if "SM-NO-REFUSAL-TEST" in line and "refusal Blocked" in line], lines


@pytest.mark.spec("PIPE-GATES-R086.12")
def test_an_edge_table_over_other_things_declares_nothing(tmp_path: Path) -> None:
    source = (
        FLOW_PY.replace("FLOW: dict[tuple[Stage, Step], Stage] = {", "PALETTE = {")
        .replace("(_S.OPEN, _E.CLOSE): _S.SHUT", '("red", "blue"): "green"')
        .replace("(_S.SHUT, _E.REOPEN): _S.OPEN", '("blue", "red"): "green"')
    )
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/door.py": source})
    assert "SM-NO-DECLARATION" in _codes(lines), lines


TUPLES_RS = """\
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Gate { Shut, Open }
pub struct Refused;
pub const WIRING: &[(Gate, &str, Gate)] = &[(Gate::Shut, "lift", Gate::Open), (Gate::Open, "drop", Gate::Shut)];
pub struct Door { pub status: Gate }
impl Door {
    pub fn commit(&mut self, next: Gate) { self.status = next; }
}
"""


@pytest.mark.spec("PIPE-GATES-R086.12")
def test_a_rust_tuple_table_under_any_name_declares_the_machine(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"src/door.rs": TUPLES_RS})
    assert "SM-NO-DECLARATION" not in _codes(lines), lines


FROZEN_PY = """\
from dataclasses import dataclass, replace
from enum import StrEnum


class Outcome(StrEnum):
    OK = "ok"
    FAILED = "failed"


@dataclass(frozen=True)
class Result:
    status: Outcome
    finished_at: float | None = None
    is_final: bool = True


@dataclass(frozen=True)
class Verdict:
    status: str


def report(result: Result) -> str:
    return "bad" if result.status == "failed" else "fine"


def seen(verdict: Verdict) -> bool:
    return verdict.status == "ok"
"""


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_frozen_result_with_a_status_is_not_a_lifecycle(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/result.py": FROZEN_PY})
    codes = _codes(lines)
    assert not codes & {"SM-NO-DECLARATION", "SM-LIFECYCLE-FLAGS", "SM-STRING-STATUS", "SM-MULTI-ASSIGN"}, lines


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_string_status_on_a_value_is_the_soft_code(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/result.py": FROZEN_PY})
    value = [line for line in lines if "Verdict" in line]
    assert value and {line.split()[2] for line in value} == {"SM-STRING-VALUE"}, lines
    assert all(line.endswith("rule 2") or "rule 2:" in line for line in value)


REPLACED_PY = (
    FROZEN_PY
    + """

def finish(result: Result) -> Result:
    return replace(result, status=Outcome.FAILED)
"""
)


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_replaced_status_stays_a_lifecycle(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/result.py": REPLACED_PY})
    assert "SM-NO-DECLARATION" in _codes(lines), lines


VALUE_RS = """\
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Outcome { Ok, Failed }
pub struct Receipt { pub status: Outcome, pub finished_at: Option<u64>, pub is_final: bool }
pub fn failed(receipt: &Receipt) -> bool { receipt.status == Outcome::Failed }
pub struct Label { pub status: String }
pub fn shown(label: &Label) -> bool { label.status == "ok" }
"""


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_rust_struct_never_mutated_is_a_value(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"src/receipt.rs": VALUE_RS})
    assert not _codes(lines) & {"SM-NO-DECLARATION", "SM-LIFECYCLE-FLAGS", "SM-STRING-STATUS"}, lines
    assert "SM-STRING-VALUE" in _codes(lines)


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_mut_borrow_of_the_status_is_an_assignment(tmp_path: Path) -> None:
    source = (
        VALUE_RS + "pub fn reset(receipt: &mut Receipt) { poke(&mut receipt.status); }\nfn poke(_: &mut Outcome) {}\n"
    )
    lines = _census(tmp_path, {"src/receipt.rs": source})
    assert "SM-NO-DECLARATION" in _codes(lines), lines


SESSION_PY = """\
from dataclasses import dataclass


@dataclass
class SessionState:
    token: str
    open: bool


@dataclass
class Session:
    state: SessionState
"""


@pytest.mark.spec("PIPE-GATES-R086.14")
def test_a_dataclass_with_a_state_suffix_is_not_a_state_type(tmp_path: Path) -> None:
    source = SESSION_PY + "\n\ndef close(session: Session) -> None:\n    session.state = SessionState('', False)\n"
    assert _census(tmp_path, {"pkg/__init__.py": "", "pkg/session.py": source}) == []


@pytest.mark.spec("PIPE-GATES-R086.14")
def test_a_rust_struct_with_a_state_suffix_is_not_a_state_type(tmp_path: Path) -> None:
    source = (
        "pub struct ApprovalState { pub asked: bool }\npub struct Gate { pub state: ApprovalState }\n"
        "impl Gate { pub fn reset(&mut self) { self.state = ApprovalState { asked: false }; } }\n"
    )
    assert _census(tmp_path, {"src/gate.rs": source}) == []


@pytest.mark.spec("PIPE-GATES-R086.14")
def test_a_literal_union_is_a_state_type(tmp_path: Path) -> None:
    source = (
        "from typing import Literal\n\nMood = Literal['up', 'down']\n\n\nclass Pet:\n    status: Mood\n\n"
        "    def set_a(self) -> None:\n        self.status = 'up'\n\n    def set_b(self) -> None:\n        self.status = 'down'\n"
    )
    assert "SM-MULTI-ASSIGN" in _codes(_census(tmp_path, {"pkg/__init__.py": "", "pkg/pet.py": source}))


@pytest.mark.spec("PIPE-GATES-R086.14")
def test_an_enum_with_a_state_suffix_is_still_a_state_type(tmp_path: Path) -> None:
    source = (
        "from enum import Enum\n\n\nclass JobState(Enum):\n    A = 1\n    B = 2\n\n\nclass Job:\n    state: JobState\n\n"
        "    def go(self) -> None:\n        self.state = JobState.B\n"
    )
    assert "SM-NO-DECLARATION" in _codes(_census(tmp_path, {"pkg/__init__.py": "", "pkg/job.py": source}))


@pytest.mark.spec("PIPE-GATES-R086.15")
def test_a_generated_file_is_not_read(tmp_path: Path) -> None:
    body = "class Row:\n    status: str\n\n    def go(self) -> None:\n        self.status = 'x'\n"
    lines = _census(
        tmp_path,
        {"pkg/__init__.py": "", "pkg/made.py": "# @generated by the schema tool\n" + body, "pkg/own.py": body},
    )
    assert lines and all(line.startswith("pkg/own.py") for line in lines), lines


@pytest.mark.spec("PIPE-GATES-R086.15")
def test_a_marker_outside_a_comment_does_not_exclude_a_file(tmp_path: Path) -> None:
    body = (
        "TEXT = 'DO NOT EDIT'\n\nclass Row:\n    status: str\n\n    def go(self) -> None:\n        self.status = 'x'\n"
    )
    assert _census(tmp_path, {"pkg/__init__.py": "", "pkg/row.py": body})


@pytest.mark.spec("PIPE-GATES-R086.15")
def test_a_marker_below_the_header_does_not_exclude_a_file(tmp_path: Path) -> None:
    body = (
        "\n" * 12
        + "# generated by hand\nclass Row:\n    status: str\n\n    def go(self) -> None:\n        self.status = 'x'\n"
    )
    assert _census(tmp_path, {"pkg/__init__.py": "", "pkg/row.py": body})


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_an_integer_status_on_a_value_is_a_protocol_code_and_reports_nothing(tmp_path: Path) -> None:
    source = "from dataclasses import dataclass\n\n\n@dataclass(frozen=True)\nclass Problem:\n    status: int\n"
    assert _census(tmp_path, {"pkg/__init__.py": "", "pkg/problem.py": source}) == []


DEFECT_RS = """\
pub struct TransitionRefused;
pub enum TransitionRefusalReason { Illegal }
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum DefectStatus { New, Fixed }
pub const TRANSITIONS: &[(DefectStatus, &str, DefectStatus)] = &[(DefectStatus::New, "fix", DefectStatus::Fixed)];
pub struct Defect { pub status: DefectStatus }
impl Defect {
    pub fn apply(&mut self, event: &str) -> Result<(), TransitionRefused> {
        self.status = DefectStatus::Fixed;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn illegal_pairs() -> Vec<(DefectStatus, &'static str)> {
        let machine = &TRANSITIONS;
        let mut out = Vec::new();
        for state in [DefectStatus::New, DefectStatus::Fixed] {
            for event in ["fix"] {
                if !machine.iter().any(|e| e.0 == state && e.1 == event) {
                    out.push((state, event));
                }
            }
        }
        out
    }

    #[test]
    fn new_fix_is_legal() {}

    #[test]
    fn every_illegal_pair_is_refused() {
        for (state, event) in illegal_pairs() {
            let refused = Defect { status: state }.apply(event).unwrap_err();
            let _ = TransitionRefusalReason::Illegal;
        }
    }
}
"""


@pytest.mark.spec("PIPE-GATES-R086.16")
def test_a_refusal_test_that_loops_a_helper_over_the_table_binds_every_missing_cell(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"src/defect.rs": DEFECT_RS})
    assert "SM-UNTESTED-REFUSAL" not in _codes(lines), lines
    assert "SM-NO-REFUSAL-TEST" not in _codes(lines), lines


REBUILT_PY = """\
from dataclasses import dataclass
from enum import StrEnum


class Phase(StrEnum):
    LIVE = "live"
    GONE = "gone"


@dataclass(frozen=True)
class Record:
    state: Phase


def retire(record: Record, key: str) -> Record:
    if record.state != Phase.LIVE:
        raise ValueError(key)
    return Record(state=Phase.GONE)
"""


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_record_rebuilt_with_a_new_status_in_a_function_that_reads_it_is_a_lifecycle(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/record.py": REBUILT_PY})
    assert "SM-NO-DECLARATION" in _codes(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_rust_record_rebuilt_in_a_function_that_reads_its_status_is_a_lifecycle(tmp_path: Path) -> None:
    source = (
        "#[derive(Clone, Copy, PartialEq, Eq)]\npub enum Phase { Live, Gone }\npub struct Record { pub state: Phase }\n"
        "pub fn retire(record: &Record) -> Record {\n    if record.state != Phase::Live { return Record { state: Phase::Live }; }\n"
        "    Record { state: Phase::Gone }\n}\n"
    )
    assert "SM-NO-DECLARATION" in _codes(_census(tmp_path, {"src/record.rs": source}))


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_record_built_where_a_status_is_only_read_is_not_a_transition(tmp_path: Path) -> None:
    source = REBUILT_PY.replace(
        "if record.state != Phase.LIVE:", "if True:\n        print(record.state)\n    if not key:"
    )
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/record.py": source})
    assert "SM-NO-DECLARATION" not in _codes(lines), lines


CATALOG_PY = """\
from dataclasses import dataclass
from enum import StrEnum


class Phase(StrEnum):
    LIVE = "live"
    GONE = "gone"


@dataclass(frozen=True)
class Record:
    state: Phase


class Catalog:
    def __init__(self) -> None:
        self.records: dict[str, Record] = {}

    def retire(self, key: str) -> Record:
        record = self.records.get(key)
        if record.state != Phase.LIVE:
            raise ValueError(key)
        return Record(state=Phase.GONE)
"""


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_record_read_from_a_typed_container_field_resolves_to_its_element_type(tmp_path: Path) -> None:
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/catalog.py": CATALOG_PY})
    assert "SM-NO-DECLARATION" in _codes(lines), lines
    assert "SM-UNRESOLVED-RECEIVER" not in _codes(lines), lines


@pytest.mark.spec("PIPE-GATES-R086.13")
def test_a_record_built_where_an_unresolved_status_is_compared_is_not_a_transition(tmp_path: Path) -> None:
    source = REBUILT_PY.replace("def retire(record: Record, key: str)", "def retire(key: str)").replace(
        "    if record.state", "    record = lookup(key)\n    if record.state"
    )
    lines = _census(tmp_path, {"pkg/__init__.py": "", "pkg/record.py": source})
    assert "SM-NO-DECLARATION" not in _codes(lines), lines
