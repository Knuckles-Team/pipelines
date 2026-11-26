"""Computed states publish with the verdicts (PIPE-GATES-R004.3, R004.4)."""

from __future__ import annotations

import pytest
from pipelines_hooks.cli import run_gate
from pipelines_hooks.states_publish import collect_states, publish_states, task_states
from pipelines_hooks.specs.generator import generate

from tests.hooks.arbora_loopback import Loopback, serving
from tests.hooks.conftest import Repo

_REQUIREMENTS = (
    "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R001` | **Landed only.** |\n| `TEST-R002` | **Open row.** |\n"
)
_TASKS = "# Tasks\n\n- [x] T001 [P] [US1] TEST-R001 Build the first part\n- [ ] T002 TEST-R002 Build the second part\n"


def _fixture(repo: Repo) -> None:
    repo.commit({"specs/demo/requirements.md": _REQUIREMENTS, "specs/demo/tasks.md": _TASKS}, "add spec")
    repo.commit({"pkg/feature.py": "# implements TEST-R001\n"}, "Spec: TEST-R001")


def test_task_lines_report_the_ticked_box() -> None:
    assert task_states(_TASKS) == [("T001", "TEST-R001", "done"), ("T002", "TEST-R002", "open")]


@pytest.mark.spec("PIPE-GATES-R004.3")
def test_row_and_task_states_publish_with_the_verdict(repo: Repo) -> None:
    _fixture(repo)
    generated = generate(repo.root, "HEAD")
    records = collect_states(generated, repository="demo", revision="abc123")
    with serving(Loopback()) as engine:
        assert publish_states(records, engine.endpoint, "") is True
        engine.fail = True
        assert publish_states(records, engine.endpoint, "") is False
    rows = {r["id"]: r["state"] for r in engine.states if r["kind"] == "row"}
    tasks = {r["id"]: r["state"] for r in engine.states if r["kind"] == "task"}
    assert rows == {"TEST-R001": "LANDED", "TEST-R002": "SPECIFIED"}
    assert tasks == {"demo/T001": "done", "demo/T002": "open"}
    assert all(r["repository"] == "demo" and r["revision"] == "abc123" and r["input_digest"] for r in engine.states)


@pytest.mark.spec("PIPE-GATES-R004.4")
def test_status_main_publishes_and_skips_without_endpoint(repo: Repo, monkeypatch, capsys) -> None:
    _fixture(repo)
    monkeypatch.delenv("PIPELINES_ARBORA_ENDPOINT", raising=False)
    assert repo.run("spec-status") == 0
    assert "states-publish: skipped" in capsys.readouterr().err
    with serving(Loopback()) as engine:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint)
        assert repo.run("spec-status") == 0
    head = repo.git("rev-parse", "HEAD").strip()
    assert {r["revision"] for r in engine.states} == {head}
    assert {r["id"] for r in engine.states if r["kind"] == "row"} == {"TEST-R001", "TEST-R002"}
    with serving(Loopback(fail=True)) as down:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", down.endpoint)
        assert run_gate("spec-status", ["--root", str(repo.root)]) == 0
