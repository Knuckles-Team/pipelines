"""The hydration journey gate (PIPE-GATES-R019): harness, ingest, readback, digest comparison."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pipelines_hooks.gate_runner import evidence_digest
from scripts import hydration_journey as journey

from tests.hooks.arbora_loopback import Loopback, serving

OUTPUT = "hydrated 3 documents\n"
EXPECTED = ({"id": "doc:1", "content_digest": "sha256:" + "1" * 64, "revision": 1},)


def _receipt(output: str = OUTPUT) -> journey.HarnessReceipt:
    return journey.HarnessReceipt(
        workflow_revision=4,
        plan_digest="sha256:" + "a" * 64,
        output=output,
        ingest_request={"documents": ["doc:1"]},
        expected=EXPECTED,
    )


class Engine:
    """A fixture engine: stores what is ingested, binds the claim it is given, compares on readback."""

    def __init__(self, *, stored: tuple[dict[str, Any], ...] = EXPECTED, bind: str | None = None) -> None:
        self.stored, self.bind, self.calls = stored, bind, []

    def __call__(self, operation: str, params: dict[str, Any]) -> Any:
        self.calls.append(operation)
        if operation == journey.INGEST_OPERATION:
            return {"write_receipt_digest": "sha256:" + "b" * 64, "graph_revision": 9}
        request = params["request"]
        matched = [dict(item) for item in request["results"]] == [dict(item) for item in self.stored]
        claim = request["hydration_run"]
        return {
            "verdict": "matched" if matched else "mismatched",
            "hydration_run": {"run_output_digest": self.bind or claim["run_output_digest"]},
        }


@pytest.mark.spec("PIPE-GATES-R019")
def test_a_matching_readback_passes() -> None:
    engine = Engine()
    verdict = journey.run_journey("skill-compilation:abc", lambda _w: _receipt(), engine)
    assert verdict.findings == () and verdict.status == 0
    assert engine.calls == [journey.INGEST_OPERATION, journey.READBACK_OPERATION]


@pytest.mark.spec("PIPE-GATES-R019")
def test_a_tampered_output_fails() -> None:
    stored = ({**EXPECTED[0], "content_digest": "sha256:" + "2" * 64},)
    verdict = journey.run_journey("skill-compilation:abc", lambda _w: _receipt(), Engine(stored=stored))
    assert verdict.status == 1
    assert any("not 'matched'" in finding for finding in verdict.findings)
    rebound = journey.run_journey(
        "skill-compilation:abc", lambda _w: _receipt(), Engine(bind=evidence_digest("something else\n"))
    )
    assert rebound.status == 1
    assert any("differs from the run output digest" in finding for finding in rebound.findings)


def _harness_script(tmp_path: Path, body: dict[str, Any] | None, *, exit_code: int = 0) -> str:
    script = tmp_path / "harness.py"
    script.write_text(f"import json,sys\nprint(json.dumps({body!r}))\nsys.exit({exit_code})\n", encoding="utf-8")
    return f"{sys.executable} {script}"


def test_the_script_runs_the_harness_command_and_posts_through_the_endpoint(tmp_path, monkeypatch, capsys) -> None:
    receipt = {
        "workflow_revision": 4,
        "plan_digest": "sha256:" + "a" * 64,
        "output": OUTPUT,
        "ingest_request": {"documents": ["doc:1"]},
        "expected": list(EXPECTED),
    }
    state = Loopback()
    state.answer = lambda operation, params: Engine()(operation, params)  # type: ignore[method-assign]
    with serving(state) as engine:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint)
        status = journey.main(
            ["--workflow", "skill-compilation:abc", "--harness-command", _harness_script(tmp_path, receipt)]
        )
    assert status == 0
    assert [call[0] for call in state.calls] == [journey.INGEST_OPERATION, journey.READBACK_OPERATION]
    assert json.loads(json.dumps(state.calls[1][1]))["request"]["hydration_run"][
        "run_output_digest"
    ] == evidence_digest(OUTPUT)
    assert "OK" in capsys.readouterr().out


def test_the_journey_cannot_run_without_a_harness_an_endpoint_or_a_served_operation(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("PIPELINES_ARBORA_ENDPOINT", raising=False)
    assert journey.main(["--workflow", "w", "--harness-command", "true"]) == 2
    assert "no arbora endpoint" in capsys.readouterr().err
    with serving(Loopback(fail=True)) as engine:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint)
        good = {
            "workflow_revision": 1,
            "plan_digest": "sha256:" + "a" * 64,
            "output": OUTPUT,
            "ingest_request": {},
            "expected": [],
        }
        assert journey.main(["--workflow", "w", "--harness-command", _harness_script(tmp_path, good)]) == 2
        assert "could not answer" in capsys.readouterr().err
        assert journey.main(["--workflow", "w", "--harness-command", _harness_script(tmp_path, None, exit_code=3)]) == 2
        assert "harness exited 3" in capsys.readouterr().err
        assert journey.main(["--workflow", "w", "--harness-command", _harness_script(tmp_path, {"output": "x"})]) == 2
        assert "no usable receipt" in capsys.readouterr().err
