"""PIPE-GATES-R034: a row that cites another repository's row is covered by a contract."""

from __future__ import annotations

import json

import pytest

from pipelines_hooks import cli
from pipelines_hooks.specs.contracts import check_dangling_and_duplicates, parse_contract
from tests.hooks.conftest import Repo

CONTRACT = """# Seam

Provider: engine ENG-DEMO-R001
Consumer: demo DEMO-R001

## Wire shape

A request and a reply.

## Refusal codes

- `seam-refused`

## Authoritative types

The reply type of `ENG-DEMO-R001`.

## Test vectors

`tests/test_seam.py`.
"""
OWN = "| ID | Requirement |\n|---|---|\n| `DEMO-R001` | **Uses the engine reply.** Depends: `ENG-DEMO-R001`. |\n"
OTHER = "| ID | Requirement |\n|---|---|\n| `ENG-DEMO-R001` | **The engine reply.** |\n"


def _spec(repo: Repo, contract: str | None = None) -> None:
    files = {"specs/demo/requirements.md": OWN}
    if contract is not None:
        files["specs/demo/contracts/seam.md"] = contract
    repo.stage(files)


# spec: PIPE-GATES-R034.1
def test_contract_without_a_required_line_or_section_is_a_finding(repo: Repo, capsys) -> None:
    whole = parse_contract(CONTRACT, "seam.md")
    assert whole.provider == (("engine", "ENG-DEMO-R001"),) and whole.consumer == (("demo", "DEMO-R001"),)
    assert whole.sections == ("Wire shape", "Refusal codes", "Authoritative types", "Test vectors")
    for broken in (
        CONTRACT.replace("Provider: engine ENG-DEMO-R001\n", ""),
        CONTRACT.replace("Consumer: demo DEMO-R001\n", "Consumer: demo\n"),
        CONTRACT.replace("## Test vectors\n\n`tests/test_seam.py`.\n", ""),
        CONTRACT.replace("## Refusal codes\n\n- `seam-refused`\n", "## Refusal codes\n"),
    ):
        _spec(repo, broken)
        assert repo.run("contract-coverage", "--base", "HEAD") == 1, broken
        assert "contract-coverage: specs/demo/contracts/seam.md: lacks" in capsys.readouterr().out
    _spec(repo, CONTRACT)
    repo.stage({"specs/other/requirements.md": OTHER})
    assert repo.run("contract-coverage", "--base", "HEAD") == 0
    # A broken contract the change does not touch is advisory.
    repo.commit({"specs/demo/contracts/seam.md": CONTRACT.replace("## Test vectors\n\n`tests/test_seam.py`.\n", "")})
    capsys.readouterr()
    assert repo.run("contract-coverage", "--base", "HEAD") == 0
    assert (
        "ADV contract-coverage: specs/demo/contracts/seam.md: lacks the 'Test vectors' section"
        in capsys.readouterr().out
    )


# spec: PIPE-GATES-R034.2
def test_uncovered_citation_fails_for_touched_spec_and_warns_for_untouched(repo: Repo, capsys) -> None:
    repo.commit({"specs/demo/requirements.md": OWN}, "old citation")
    # The citation exists at the base: advisory, exit 0.
    assert repo.run("contract-coverage", "--base", "HEAD") == 0
    assert (
        "ADV contract-coverage: specs/demo: DEMO-R001 cites ENG-DEMO-R001 without a contract" in capsys.readouterr().out
    )
    # A row that adds a citation fails and names both rows.
    repo.commit({"specs/demo/requirements.md": OWN + "| `DEMO-R002` | **Also.** Needs `ENG-DEMO-R002`. |\n"}, "new")
    base = repo.git("rev-parse", "HEAD~1").strip()
    assert repo.run("contract-coverage", "--base", base) == 1
    out = capsys.readouterr().out
    assert "contract-coverage: specs/demo: DEMO-R002 cites ENG-DEMO-R002 without a contract" in out
    assert "ADV contract-coverage: specs/demo: DEMO-R001" in out
    # A contract naming both rows covers the pair, in either direction.
    repo.write(
        "specs/demo/contracts/seam.md",
        CONTRACT.replace("ENG-DEMO-R001\nConsumer: demo DEMO-R001", "ENG-DEMO-R002\nConsumer: demo DEMO-R002"),
    )
    capsys.readouterr()
    repo.git("add", "--", "specs/demo/contracts/seam.md")
    assert repo.run("contract-coverage", "--base", base) == 0
    assert "DEMO-R002 cites" not in capsys.readouterr().out


# spec: PIPE-GATES-R034.3
def test_spec_group_runs_contract_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    assert cli.GATES["contract-coverage"] == "pipelines_hooks.specs.contracts"
    assert "contract-coverage" in cli.GROUPS["spec"]
    ran: list[str] = []
    monkeypatch.setattr(cli, "run_gate", lambda gate, argv: ran.append(gate) or 0)
    assert cli.run_group("spec", []) == 0
    assert "contract-coverage" in ran


# spec: PIPE-GATES-R034.4
def test_dangling_and_duplicate_contracts_are_findings(repo: Repo, capsys, tmp_path) -> None:
    contract = parse_contract(CONTRACT, "a.md")
    twin = parse_contract(CONTRACT, "b.md")
    rows = {"ENG-DEMO": {"ENG-DEMO-R001"}, "DEMO": {"DEMO-R001"}}
    assert check_dangling_and_duplicates([contract], rows) == []
    found = check_dangling_and_duplicates([contract, twin], rows)
    assert found == ["b.md: duplicates a.md for ENG-DEMO-R001 and DEMO-R001"]
    dangling = check_dangling_and_duplicates([contract], {"ENG-DEMO": {"ENG-DEMO-R009"}, "DEMO": {"DEMO-R001"}})
    assert dangling == ["a.md: names ENG-DEMO-R001, which engine does not define"]
    assert "unreachable" in check_dangling_and_duplicates([contract], {"DEMO": {"DEMO-R001"}})[0]
    # Through the gate: an owner index that lacks the provider row is a finding; one that has it is clean.
    _spec(repo, CONTRACT)
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"repos": {"engine": ["ENG-DEMO-R009"]}}), encoding="utf-8")
    assert repo.run("contract-coverage", "--base", "HEAD", "--id-index", str(index)) == 1
    assert "which engine does not define" in capsys.readouterr().out
    index.write_text(json.dumps({"repos": {"engine": ["ENG-DEMO-R001"]}}), encoding="utf-8")
    assert repo.run("contract-coverage", "--base", "HEAD", "--id-index", str(index)) == 0
