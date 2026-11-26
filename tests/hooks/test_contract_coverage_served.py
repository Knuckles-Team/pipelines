"""PIPE-GATES-R034.5: the hook refuses an uncovered seam; the engine reads the covered one.

The engine half is a loopback of the spec'd seam-graph shape (MEDULLA-SDLC-R014.4): one Contract
record per contract file and a ``crossesSeam`` edge from each named row. The fixture answers like the
served ask operation; the same ``parse_contract`` feeds the gate and the loopback ingest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipelines_hooks.specs.contracts import Contract, parse_contract
from tests.hooks.test_contract_coverage import CONTRACT, OTHER, OWN, Repo


@dataclass
class LoopbackSeamEngine:
    """Seam-graph shape: ``contracts`` keyed by path and ``crossesSeam`` edges keyed by row."""

    contracts: dict[str, Contract] = field(default_factory=dict)
    crosses_seam: dict[str, set[str]] = field(default_factory=dict)

    def ingest(self, path: str, text: str) -> None:
        contract = parse_contract(text, path)
        self.contracts[path] = contract
        for _repository, row in (*contract.provider, *contract.consumer):
            self.crosses_seam.setdefault(row, set()).add(path)

    def ask(self, row: str) -> list[dict[str, object]]:
        return [
            {"contract": p, "provider": self.contracts[p].provider, "consumer": self.contracts[p].consumer}
            for p in sorted(self.crosses_seam.get(row, ()))
        ]


# spec: PIPE-GATES-R034.5
def test_hook_refuses_uncovered_seam_and_engine_reads_the_covered_one(repo: Repo, capsys) -> None:
    repo.stage({"specs/demo/requirements.md": OWN, "specs/other/requirements.md": OTHER})
    assert repo.run("contract-coverage", "--base", "HEAD") == 1
    assert "DEMO-R001 cites ENG-DEMO-R001 without a contract" in capsys.readouterr().out
    repo.stage({"specs/demo/contracts/seam.md": CONTRACT})
    assert repo.run("contract-coverage", "--base", "HEAD") == 0
    engine = LoopbackSeamEngine()
    assert engine.ask("DEMO-R001") == []  # nothing is read before the ingest
    engine.ingest("specs/demo/contracts/seam.md", CONTRACT)
    (answer,) = engine.ask("DEMO-R001")
    assert answer["provider"] == (("engine", "ENG-DEMO-R001"),) and answer["consumer"] == (("demo", "DEMO-R001"),)
    assert engine.ask("ENG-DEMO-R001") == engine.ask("DEMO-R001")
    assert engine.ask("UNKNOWN-R001") == []  # a foreign row answers exactly like an absent one
