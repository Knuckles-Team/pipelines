"""The release CLI runs portably: no network call, no hosted credential (FR-5: P-5).

Acceptance scenario 4: a public contributor runs parsing, ordering, and
negative contract tests from fixtures alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release.cli import main
from scripts.release_orchestrator import main as wrapper_main

FIXTURES = Path(__file__).parent / "fixtures" / "release"


def test_validate_accepts_the_a_b_c_manifest(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["validate", "--manifest", str(FIXTURES / "candidates_abc.json")])
    assert code == 0
    assert "valid" in capsys.readouterr().out


def test_validate_rejects_a_manifest_with_a_cycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    raw = json.loads((FIXTURES / "candidates_abc.json").read_text(encoding="utf-8"))
    raw["candidates"][0]["predecessors"] = ["C"]
    manifest = tmp_path / "cyclic.json"
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    code = main(["validate", "--manifest", str(manifest)])
    assert code == 1
    assert "dependency cycle" in capsys.readouterr().err


def test_plan_reports_every_candidate_eligible(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "plan",
            "--manifest",
            str(FIXTURES / "candidates_abc.json"),
            "--checks",
            str(FIXTURES / "checks_all_pass.json"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "A: eligible" in out and "B: eligible" in out and "C: eligible" in out


def test_publish_runs_the_ordered_release_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "publish",
            "--manifest",
            str(FIXTURES / "candidates_abc.json"),
            "--checks",
            str(FIXTURES / "checks_all_pass.json"),
            "--plan",
            str(FIXTURES / "publish_plan_success.json"),
            "--receipts",
            str(tmp_path / "receipts.json"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "A: published" in out and "B: published" in out and "C: published" in out


def test_verify_consumers_reports_a_clean_handoff() -> None:
    code = main(
        [
            "verify-consumers",
            "--plan",
            str(FIXTURES / "publish_plan_success.json"),
            "--consumers",
            str(FIXTURES / "consumers_ready.json"),
        ]
    )
    assert code == 0


def test_no_command_reaches_the_network_or_a_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the portable CLI must not open a socket")

    monkeypatch.setattr("socket.socket.connect", _forbidden)
    code = main(["validate", "--manifest", str(FIXTURES / "candidates_abc.json")])
    assert code == 0


def test_the_registered_wrapper_script_exposes_the_same_cli() -> None:
    assert wrapper_main is main
