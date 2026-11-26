"""The graph and the page agree (PIPE-GATES-R004.5).

The row stays unbound: arbora does not serve ``spec.status`` yet, so these
tests run against a loopback engine and pin the unavailable state.
"""

from __future__ import annotations

from pipelines_hooks.specs.generator import generate
from pipelines_hooks.states_publish import collect_states, publish_states

from tests.hooks.arbora_loopback import Loopback, serving
from tests.hooks.conftest import Repo

_REQUIREMENTS = "# demo\n\n| ID | Requirement |\n|---|---|\n| `TEST-R001` | **One.** |\n| `TEST-R002` | **Two.** |\n"


def _repo(repo: Repo) -> str:
    repo.commit({"specs/demo/requirements.md": _REQUIREMENTS}, "add spec")
    return repo.commit({"pkg/feature.py": "# implements TEST-R001\n"}, "Spec: TEST-R001")


def _publish(repo: Repo, revision: str, engine: Loopback, *, tamper: dict[str, str] | None = None) -> None:
    records = collect_states(generate(repo.root, "HEAD"), repository=repo.root.name, revision=revision)
    for record in records:
        if tamper and record["id"] in tamper:
            record["state"] = tamper[record["id"]]
    assert publish_states(records, engine.endpoint, "")


def test_mismatch_names_each_row_and_side(repo: Repo, monkeypatch, capsys) -> None:
    revision = _repo(repo)
    with serving(Loopback()) as engine:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint)
        _publish(repo, revision, engine)
        assert repo.run("states-agree") == 0
        assert "OK" in capsys.readouterr().out
        engine.states.clear()
        _publish(repo, revision, engine, tamper={"TEST-R001": "VERIFIED"})
        assert repo.run("states-agree") == 1
    out = capsys.readouterr().out
    assert "TEST-R001: generator says LANDED, engine says VERIFIED" in out
    assert "TEST-R002" not in out


def test_an_unreachable_engine_is_an_advisory_finding(repo: Repo, monkeypatch, capsys) -> None:
    _repo(repo)
    with serving(Loopback(fail=True)) as engine:
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint)
        assert repo.run("states-agree") == 0
    assert "ADVISORY" in capsys.readouterr().out


def test_an_operation_the_endpoint_does_not_serve_is_an_advisory_finding(repo: Repo, monkeypatch, capsys) -> None:
    _repo(repo)
    with serving(Loopback(fail=True)) as engine:
        engine.fail = True
        monkeypatch.setenv("PIPELINES_ARBORA_ENDPOINT", engine.endpoint + "/missing")
        assert repo.run("states-agree") == 0
    assert "the graph was not compared" in capsys.readouterr().out
