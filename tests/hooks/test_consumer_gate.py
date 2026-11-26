"""consumer-gate: every consumer passes against the release candidate before the producer tags (PIPE-RELEASE-R031)."""

from __future__ import annotations

import json
from pathlib import Path

from pipelines_hooks.cli import run_gate
from pipelines_hooks.release import consumer_gate as cg
from tests.hooks.conftest import Repo

CONSUMERS = [
    {"name": "sdk", "path": "sdk", "install": ["i", "{candidate}"], "test": ["t-sdk"]},
    {"name": "cli", "path": "cli", "install": ["i", "{candidate}"], "test": ["t-cli"]},
]


def _execute(failing: set[str]):
    def execute(argv, cwd: Path):
        if argv[0] in failing:
            return 1, "collected 3 items\nFAILED tests/test_x.py::test_contract - boom\n1 failed\n"
        return 0, ""

    return execute


# spec: PIPE-RELEASE-R031
def test_a_failing_consumer_blocks_the_tag(repo: Repo, capsys) -> None:
    findings = cg.run(CONSUMERS, "cand.whl", _execute({"t-cli"}), Path("."), contract_change=True)
    assert findings == ["cli: tests/test_x.py::test_contract"]
    broken_install = cg.run(CONSUMERS, "cand.whl", _execute({"i"}), Path("."), contract_change=False)
    assert len(broken_install) == 2 and "does not install" in broken_install[0]
    assert cg.run([], "cand.whl", _execute(set()), Path("."), contract_change=True) == [
        "no consumers are declared for a contract change"
    ]
    manifest = repo.write("consumers.json", json.dumps({"consumers": []}))
    assert run_gate_consumers(repo, manifest, "--contract-change") == 1
    assert "CONSUMER_FAILED" in capsys.readouterr().err


# spec: PIPE-RELEASE-R031
def test_all_consumers_green_passes(repo: Repo) -> None:
    assert cg.run(CONSUMERS, "cand.whl", _execute(set()), Path("."), contract_change=True) == []
    manifest = repo.write("consumers.json", json.dumps({"consumers": []}))
    assert run_gate_consumers(repo, manifest) == 0


def run_gate_consumers(repo: Repo, manifest: Path, *extra: str) -> int:
    return run_gate(
        "consumer-gate", ["--root", str(repo.root), "--consumers", str(manifest), "--candidate", "c.whl", *extra]
    )
