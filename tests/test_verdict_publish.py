"""Gate verdicts publish to the engine through arbora (PIPE-GATES-R004.1, R004.2)."""

from __future__ import annotations

import pytest
from pipelines_hooks.gate_runner import evidence_digest, run_gate_on, run_set
from pipelines_hooks.gate_sets import published_sets
from pipelines_hooks.source_provider import tree_digest
from pipelines_hooks.verdict_publish import publish_verdict

from tests.hooks.arbora_loopback import Loopback, serving


def _tree(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


@pytest.mark.spec("PIPE-GATES-R004.1")
def test_gate_run_posts_one_verdict(tmp_path, monkeypatch) -> None:
    source = _tree(tmp_path)
    with serving(Loopback()) as engine:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint)
        monkeypatch.setenv("PIPELINES_ARBORA_TOKEN", "t0ken")
        verdict = run_gate_on("secrets", source, lambda _: (1, "finding\n"))
    assert [call[0] for call in engine.calls] == ["source.gate_verdict"]
    assert engine.calls[0][2] == "Bearer t0ken"
    (record,) = engine.verdicts
    assert record["gate_id"] == "secrets"
    assert record["verdict"] == "fail"
    assert record["evidence_digest"] == verdict.evidence_digest == evidence_digest("finding\n")
    assert record["input_digest"] == tree_digest(source)
    assert record["duration_ms"] >= 0


@pytest.mark.spec("PIPE-GATES-R004.1")
def test_without_an_endpoint_the_publish_is_skipped_and_logged(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("PIPELINES_ARBORA_ENDPOINT", raising=False)
    verdict = run_gate_on("secrets", _tree(tmp_path), lambda _: (0, "clean\n"))
    assert verdict.status == 0
    assert "verdict-publish: skipped secrets" in capsys.readouterr().err
    assert publish_verdict(verdict, "", "") is False


@pytest.mark.spec("PIPE-GATES-R004.2")
def test_fast_set_publishes_and_survives_endpoint_error(tmp_path, monkeypatch, capsys) -> None:
    source = _tree(tmp_path)
    sets = published_sets()
    executors = {gate: (lambda _s, gate=gate: (0, f"{gate}: clean\n")) for gate in sets.fast}
    with serving(Loopback()) as engine:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint)
        run = run_set("fast", source, executors, sets=sets)
        published = list(engine.verdicts)
        engine.fail = True
        failing = run_set("fast", source, executors, sets=sets)
    assert [record["gate_id"] for record in published] == list(sets.fast)
    assert {record["input_digest"] for record in published} == {tree_digest(source)}
    assert run.status == 0
    assert failing.verdicts == tuple(
        type(v)(gate=v.gate, status=v.status, evidence_digest=v.evidence_digest, seconds=v.seconds)
        for v in failing.verdicts
    )
    assert [v.status for v in failing.verdicts] == [0] * len(sets.fast)
    assert [v.evidence_digest for v in failing.verdicts] == [v.evidence_digest for v in run.verdicts]
    assert "could not publish" in capsys.readouterr().err
