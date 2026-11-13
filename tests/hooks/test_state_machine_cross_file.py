"""PIPE-GATES-R086.5: a status enum's machine is resolved across files and crates."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks import cli
from tests.hooks.state_machine_repo import fixture_repo, git

MACHINE = """\
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum GrantState {
    Active,
    Revoked,
}

pub struct GrantRefused;

impl GrantState {
    pub fn apply(self, event: &str) -> Result<GrantState, GrantRefused> {
        match (self, event) {
            (GrantState::Active, "revoke") => Ok(GrantState::Revoked),
            _ => Err(GrantRefused),
        }
    }
}
"""
HOLDER = """\
pub struct Grant {
    pub state: GrantState,
}

impl Grant {
    pub fn revoke(&mut self) -> Result<(), GrantRefused> {
        self.state = self.state.apply("revoke")?;
        Ok(())
    }
}
"""
REFUSAL_TEST = """\
#[test]
fn an_active_grant_revoke_is_refused_when_illegal() {
    let _ = GrantRefused;
}
#[test]
fn active_revoke_moves_to_revoked() {}
"""


def _repo(tmp: Path, files: dict[str, str]) -> Path:
    root = fixture_repo(tmp, "rs/compliant")
    for name in ("src", "tests"):
        for path in (root / name).glob("*"):
            path.unlink()
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "case")
    return root


def _census(root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    cli.main(["state-machine-census", "--root", str(root)])
    return capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_a_machine_in_another_module_of_the_same_crate_gives_no_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"src/machine.rs": MACHINE, "src/grant.rs": HOLDER, "tests/grant.rs": REFUSAL_TEST})
    assert "SM-" not in _census(root, capsys)


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_a_machine_in_another_crate_gives_no_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {"src/machine.rs": MACHINE, "src/other/grant.rs": HOLDER, "tests/grant.rs": REFUSAL_TEST})
    assert "SM-NO-DECLARATION" not in _census(root, capsys)


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_a_genuinely_missing_machine_is_still_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bare = MACHINE.split("impl GrantState")[0]
    root = _repo(tmp_path, {"src/machine.rs": bare, "src/grant.rs": HOLDER})
    out = _census(root, capsys)
    assert "Grant SM-NO-DECLARATION" in out


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_a_multi_assign_in_another_file_is_still_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stray = "pub fn force(grant: &mut Grant) {\n    grant.state = GrantState::Revoked;\n}\n"
    root = _repo(
        tmp_path,
        {"src/machine.rs": MACHINE, "src/grant.rs": HOLDER, "src/stray.rs": stray, "tests/grant.rs": REFUSAL_TEST},
    )
    out = _census(root, capsys)
    assert "src/stray.rs" in out and "SM-MULTI-ASSIGN" in out and "assigned in force" in out
