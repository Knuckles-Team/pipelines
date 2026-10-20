"""The gate set runner (PIPE-GATES-R001): one set, one source, recorded verdicts.

The runner dispatches each gate of the declared set through its execution
binding, times it, captures the evidence and aggregates the verdicts. A
gate without a binding fails the run closed, named, before any gate
starts.
"""

from __future__ import annotations

import pytest
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.gate_runner import Executor, evidence_digest, main, run_gate_on, run_set
from pipelines_hooks.gate_sets import published_sets


def _executor_map(
    *gates: tuple[str, int], output_for: dict[str, str] | None = None
) -> tuple[dict[str, Executor], list[str]]:
    calls: list[str] = []
    output_for = output_for or {}

    def bound(gate: str, status: int) -> Executor:
        def run(source) -> tuple[int, str]:
            calls.append(gate)
            return status, output_for.get(gate, f"{gate}: clean\n")

        return run

    return {gate: bound(gate, status) for gate, status in gates}, calls


def test_the_set_runs_its_members_in_declaration_order(tmp_path) -> None:
    # spec: PIPE-GATES-R001
    sets = published_sets()
    executors, calls = _executor_map(*[(gate, 0) for gate in sets.fast])
    run = run_set("fast", tmp_path, executors, sets=sets)
    assert calls == list(sets.fast)
    assert [verdict.gate for verdict in run.verdicts] == list(sets.fast)
    assert run.set_name == "fast"
    assert run.source == str(tmp_path)


def test_a_verdict_carries_the_status_and_the_evidence_digest(tmp_path) -> None:
    # spec: PIPE-GATES-R001
    executors, _ = _executor_map(("secrets", 1), output_for={"secrets": "finding a\nfinding b\n"})
    verdict = run_gate_on("secrets", tmp_path, executors["secrets"])
    assert verdict.gate == "secrets"
    assert verdict.status == 1
    assert verdict.evidence_digest == evidence_digest("finding a\nfinding b\n")
    assert verdict.seconds >= 0.0


def test_identical_evidence_digests_identically_and_different_evidence_differs() -> None:
    # spec: PIPE-GATES-R001
    assert evidence_digest("same\n") == evidence_digest("same\n")
    assert evidence_digest("same\n") != evidence_digest("other\n")
    assert evidence_digest("evidence").startswith("sha256:")


def test_the_set_status_is_the_worst_member_status(tmp_path) -> None:
    # spec: PIPE-GATES-R001
    sets = published_sets()
    for overrides, expected in (({}, 0), ({"types": 1}, 1), ({"secrets": 2}, 2), ({"tests-fast": 2, "types": 1}, 2)):
        statuses = {gate: 0 for gate in sets.fast}
        statuses.update(overrides)
        executors, _ = _executor_map(*statuses.items())
        assert run_set("fast", tmp_path, executors, sets=sets).status == expected


def test_a_gate_without_a_binding_fails_the_run_before_any_gate_starts(tmp_path) -> None:
    # spec: PIPE-GATES-R001
    sets = published_sets()
    bound = {gate: 0 for gate in sets.fast if gate != "types"}
    executors, calls = _executor_map(*bound.items())
    with pytest.raises(CannotRun, match="no execution binding for types"):
        run_set("fast", tmp_path, executors, sets=sets)
    assert calls == []


def test_an_unknown_set_name_is_rejected(tmp_path) -> None:
    # spec: PIPE-GATES-R001
    with pytest.raises(CannotRun, match="unknown set 'medium'"):
        run_set("medium", tmp_path, {})


def test_the_cli_fails_closed_on_the_unbound_consumer_side_gates(capsys) -> None:
    # spec: PIPE-GATES-R001
    assert main(["fast"]) == 2
    error = capsys.readouterr().err
    assert "no execution binding for format, hygiene, types" in error
    assert main(["full"]) == 2
    assert "no execution binding for tests" in capsys.readouterr().err


def test_the_cli_reports_each_member_verdict_and_the_set_verdict(tmp_path, monkeypatch, capsys) -> None:
    # spec: PIPE-GATES-R001
    sets = published_sets()
    called: list[str] = []

    def bound(gate: str) -> Executor:
        def run(source) -> tuple[int, str]:
            called.append(gate)
            return (0 if gate != "tests" else 1, f"{gate}: output\n")

        return run

    monkeypatch.setattr(
        "pipelines_hooks.gate_runner.published_executors", lambda: {gate: bound(gate) for gate in sets.full}
    )
    assert main(["full", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert called == ["spec", "tests", "supply-chain"]
    assert "tests: exit 1" in out
    assert "gate-set full: exit 1" in out


def test_the_cli_rejects_an_unknown_set(tmp_path, capsys) -> None:
    # spec: PIPE-GATES-R001
    with pytest.raises(SystemExit) as raised:
        main(["medium", "--root", str(tmp_path)])
    assert raised.value.code == 2
    assert "medium" in capsys.readouterr().err
