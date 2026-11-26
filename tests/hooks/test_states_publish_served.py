"""Verdicts and states reach the engine through a served endpoint (PIPE-GATES-R004.6).

This journey runs the ``spec`` group against a loopback arbora endpoint backed by a
loopback engine, as the row's hot-path proof names.
"""

from __future__ import annotations

from pipelines_hooks import cli
from pipelines_hooks.gate_runner import run_gate_on
from pipelines_hooks.verdict_publish import post_operation

from tests.hooks.arbora_loopback import Loopback, serving
from tests.hooks.conftest import Repo

_REQUIREMENTS = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R001` | **One.** |\n| `TEST-R002` | **Two.** |\n"
_TASKS = "# Tasks\n\n- [x] T001 TEST-R001 First\n- [ ] T002 TEST-R002 Second\n"


# spec: PIPE-GATES-R004.6
def test_spec_hook_publishes_states_through_arbora_to_the_engine(repo: Repo, monkeypatch) -> None:
    repo.commit({"specs/demo/requirements.md": _REQUIREMENTS, "specs/demo/tasks.md": _TASKS}, "add spec")
    repo.commit({"pkg/feature.py": "# implements TEST-R001\n"}, "Spec: TEST-R001")
    monkeypatch.chdir(repo.root)
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)

    def spec_hook(_source) -> tuple[int, str]:
        return cli.main(["spec"]), "spec group output\n"

    with serving(Loopback()) as engine:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint)
        verdict = run_gate_on("spec", repo.root, spec_hook)
        served = post_operation(engine.endpoint, "", "spec.status", {"repository": repo.root.name})
    assert [record["gate_id"] for record in engine.verdicts] == ["spec"]
    assert engine.verdicts[0]["evidence_digest"] == verdict.evidence_digest
    assert sorted(record["id"] for record in engine.states if record["kind"] == "row") == ["TEST-R001", "TEST-R002"]
    assert sorted(record["id"] for record in engine.states if record["kind"] == "task") == ["demo/T001", "demo/T002"]
    assert {row["id"]: row["state"] for row in served["rows"]} == {
        record["id"]: record["state"] for record in engine.states if record["kind"] == "row"
    }
