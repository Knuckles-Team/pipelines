"""PIPE-GATES-R086.11: a use is counted against the type its receiver resolves to."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks import cli
from pipelines_hooks.code.state_machine_model import CODES, UNRESOLVED_TYPE
from tests.hooks.state_machine_repo import fixture_repo, git

TWO_TYPES = """\
from enum import StrEnum


class Phase(StrEnum):
    NEW = "new"
    DONE = "done"


class TransitionRefused(Exception):
    pass


class Tenant:
    lifecycle: Phase

    def apply(self, event: str) -> None:
        if event != "close":
            raise TransitionRefused(event)
        self.lifecycle = Phase.DONE


class Catalog:
    lifecycle: Phase

    def apply(self, event: str) -> None:
        if event != "close":
            raise TransitionRefused(event)
        self.lifecycle = Phase.DONE
"""
ASSIGN_TENANT = "\n\ndef force(tenant: Tenant) -> None:\n    tenant.lifecycle = Phase.NEW\n"
ASSIGN_UNKNOWN = "\n\ndef force(thing) -> None:\n    thing.lifecycle = Phase.NEW\n"
COMPARE_UNKNOWN = 'def is_done(thing) -> bool:\n    return thing.lifecycle == "done"\n'
CONSTRUCTED = "\n\ndef build() -> None:\n    made = Catalog()\n    made.lifecycle = Phase.NEW\n"
COPIED = (
    "\n\ndef reopen(tenant: Tenant) -> Tenant:\n"
    "    again = tenant.model_copy()\n    again.lifecycle = Phase.NEW\n    return again\n"
)
RETURNED = "\n\ndef make() -> Catalog:\n    return Catalog()\n\n\ndef use() -> None:\n    got = make()\n    got.lifecycle = Phase.NEW\n"


def _census(tmp: Path, extra: str, capsys: pytest.CaptureFixture[str], other: str = "") -> list[str]:
    root = fixture_repo(tmp, "py/compliant")
    for path in (root / "pkg").glob("*.py"):
        path.unlink()
    (root / "pkg" / "models.py").write_text(TWO_TYPES + extra, encoding="utf-8")
    (root / "pkg" / "other.py").write_text(other or "X = 1\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "case")
    cli.main(["state-machine-census", "--root", str(root)])
    return [line for line in capsys.readouterr().out.splitlines() if ".py:" in line]


@pytest.mark.spec("PIPE-GATES-R086.11")
def test_two_types_sharing_a_field_only_the_assigned_one_is_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = _census(tmp_path, ASSIGN_TENANT, capsys)
    multi = [line for line in lines if "SM-MULTI-ASSIGN" in line]
    assert len(multi) == 1 and multi[0].split()[1] == "Tenant" and "assigned in force" in multi[0]
    assert not any(line.split()[1] == "Catalog" and "SM-MULTI-ASSIGN" in line for line in lines)
    assert not any(UNRESOLVED_TYPE in line for line in lines)


@pytest.mark.spec("PIPE-GATES-R086.11")
@pytest.mark.parametrize("case", [CONSTRUCTED, COPIED, RETURNED])
def test_a_constructor_a_copy_and_a_return_type_resolve_the_receiver(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    lines = _census(tmp_path, case, capsys)
    stray = [line for line in lines if "SM-MULTI-ASSIGN" in line]
    expected = "Tenant" if case is COPIED else "Catalog"
    assert [line.split()[1] for line in stray] == [expected]
    assert not any(UNRESOLVED_TYPE in line for line in lines)


@pytest.mark.spec("PIPE-GATES-R086.11")
def test_an_unresolvable_receiver_gives_one_unresolved_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = _census(tmp_path, ASSIGN_UNKNOWN, capsys)
    unresolved = [line for line in lines if UNRESOLVED_TYPE in line]
    assert len(unresolved) == 1
    assert "SM-UNRESOLVED-RECEIVER rule 7" in unresolved[0] and "assign of .lifecycle in force" in unresolved[0]
    assert not any("assigned in force" in line for line in lines)


@pytest.mark.spec("PIPE-GATES-R086.11")
def test_an_unresolvable_string_compare_is_one_unresolved_finding_not_one_per_type(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = _census(tmp_path, "", capsys, other=COMPARE_UNKNOWN)
    assert len([line for line in lines if UNRESOLVED_TYPE in line]) == 1
    assert not any("SM-STRING-STATUS" in line and "is_done" in line for line in lines)


@pytest.mark.spec("PIPE-GATES-R086.11")
def test_the_unresolved_code_belongs_to_rule_seven() -> None:
    assert int(CODES["SM-UNRESOLVED-RECEIVER"]) == 7


@pytest.mark.spec("PIPE-GATES-R086.11")
def test_staged_mode_reports_an_unresolved_finding_only_for_a_changed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pipelines_hooks.code import state_machine

    root = fixture_repo(tmp_path, "py/compliant")
    (root / "pkg" / "models.py").write_text(TWO_TYPES, encoding="utf-8")
    (root / "pkg" / "poke.py").write_text("def poke(thing) -> None:\n    thing.lifecycle = 1\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "case")
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    state_machine.main(["--root", str(root)])
    assert UNRESOLVED_TYPE not in capsys.readouterr().out
    (root / "pkg" / "poke.py").write_text("def poke(thing) -> None:\n    thing.lifecycle = 2\n", encoding="utf-8")
    git(root, "add", "pkg/poke.py")
    state_machine.main(["--root", str(root)])
    assert f"pkg/poke.py:2 {UNRESOLVED_TYPE} SM-UNRESOLVED-RECEIVER" in capsys.readouterr().out


RS_TYPES = """\
pub enum Phase { New, Done }
pub struct Tenant { pub lifecycle: Phase }
pub struct Catalog { pub lifecycle: Phase }
pub fn force(tenant: &mut Tenant) { tenant.lifecycle = Phase::New; }
pub fn unknown(thing: &mut Opaque) { thing.lifecycle = Phase::New; }
pub fn guess(thing: &mut T) { thing.lifecycle = Phase::Done; }
"""


@pytest.mark.spec("PIPE-GATES-R086.11")
def test_rust_parameter_types_resolve_and_an_unknown_receiver_is_unresolved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = fixture_repo(tmp_path, "rs/compliant")
    for name in ("src", "tests"):
        for path in (root / name).glob("*"):
            path.unlink()
    (root / "src" / "lib.rs").write_text(RS_TYPES.replace("thing: &mut T", "thing"), encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "case")
    cli.main(["state-machine-census", "--root", str(root)])
    out = capsys.readouterr().out
    assert "src/lib.rs:4 Tenant SM-MULTI-ASSIGN" not in out  # one assigning function is not a stray
    assert out.count(UNRESOLVED_TYPE) == 1 and "src/lib.rs:6" in out
    assert "Catalog SM-MULTI-ASSIGN" not in out
