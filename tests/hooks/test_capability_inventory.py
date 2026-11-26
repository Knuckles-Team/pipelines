"""capability-coverage: every function, test and MCP tool carries a capability that the registry knows."""

from __future__ import annotations

import json

import pytest
import yaml

from pipelines_hooks.cli import GATES
from pipelines_hooks.specs import capability_inventory as inventory
from tests.hooks.conftest import HOOK_REPOSITORY, Repo

_PY = '''"""Fixture service."""


# capability: graph.query
def query(text):
    # capability: graph.query
    def inner():
        return text

    return inner()


class Store:
    # capability: graph.store
    def put(self, key):
        return key
'''
_PY_TEST = """# capability: graph.query
def test_query():
    assert True
"""
_RUST = """// capability: graph.store
pub fn save(key: &str) -> usize {
    let label = "} brace in a string {";
    label.len() + key.len()
}

struct Engine;

impl Engine {
    // capability: graph.query
    pub fn run(&self) -> u8 {
        // capability: graph.query
        fn helper() -> u8 { 1 }
        helper()
    }
}

#[cfg(test)]
mod tests {
    #[test]
    // capability: graph.store
    fn saves() {
        assert_eq!(super::save("a"), 1);
    }
}
"""
_REGISTRY = {"revision": "reg-1", "capabilities": ["graph.query", "graph.store"]}
_TOOLS = {
    "complete": True,
    "tools": [{"name": "query_tool", "path": "pkg/service.py", "symbol": "query", "capability": "graph.query"}],
}


def _config(**tools: object) -> str:
    return json.dumps(
        {
            "repository": "fixture",
            "registry": "registry.json",
            "roots": ["pkg", "crates"],
            "tools": tools or {"scope": "inventory", "inventory": "tools.json"},
        }
    )


@pytest.fixture
def covered(repo: Repo) -> Repo:
    repo.commit(
        {
            ".config/capability-coverage.json": _config(),
            "registry.json": json.dumps(_REGISTRY),
            "tools.json": json.dumps(_TOOLS),
            "pkg/service.py": _PY,
            "pkg/test_service.py": _PY_TEST,
            "crates/engine/src/lib.rs": _RUST,
        },
        "covered",
    )
    return repo


def _receipt(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(next(line for line in capsys.readouterr().out.splitlines() if line.startswith("{")))


# spec: PIPE-PAGES-R012.14
def test_capability_inventory_model(covered: Repo) -> None:
    items = inventory.python_items("pkg/service.py", _PY, False)
    assert [(i.symbol, i.capabilities) for i in items] == [
        ("query", ("graph.query",)),
        ("query.inner", ("graph.query",)),
        ("Store.put", ("graph.store",)),
    ]
    assert len({i.sha256 for i in items}) == 3 and all(len(i.sha256) == 64 for i in items)
    assert items[0].identity == "pkg/service.py::query"
    assert not inventory.CAPABILITY_ID.match("PIPE-PAGES-R012.14")  # a requirement ID is never a capability ID
    covered.commit({"pkg/service.py": _PY.replace("# capability: graph.store", "# capability: PIPE-PAGES-R012.14")})
    assert covered.run("capability-coverage") == 1


# spec: PIPE-PAGES-R012.15
def test_capability_inventory_behavior(covered: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    rust = inventory.rust_items("crates/engine/src/lib.rs", _RUST, False)
    assert [(i.kind, i.symbol, i.capabilities) for i in rust] == [
        ("function", "save", ("graph.store",)),
        ("function", "Engine.run", ("graph.query",)),
        ("function", "Engine.run.helper", ("graph.query",)),
        ("test", "tests.saves", ("graph.store",)),
    ]
    assert covered.run("capability-coverage") == 0
    receipt = _receipt(capsys)
    assert receipt["counts"] == {"function": 6, "test": 2, "tool": 1}
    assert receipt["capabilities"]["graph.query"] == {"function": 4, "test": 1, "tool": 1}
    assert receipt["capabilities"]["graph.store"] == {"function": 2, "test": 1, "tool": 0}
    assert receipt["uncovered"] == {"graph.store": ["tool"]}


# spec: PIPE-PAGES-R012.16
def test_capability_inventory_wiring() -> None:
    assert GATES["capability-coverage"] == "pipelines_hooks.specs.capability_inventory"
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    assert [h["entry"] for h in hooks if h["id"] == "capability-coverage"] == ["pipelines-hook capability-coverage"]


# spec: PIPE-PAGES-R012.17
def test_capability_inventory_refusal(covered: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    covered.commit({"pkg/service.py": _PY.replace("    # capability: graph.store\n", "")})
    assert covered.run("capability-coverage") == 1
    assert "pkg/service.py:14: function Store.put: no capability binding" in capsys.readouterr().out
    covered.commit({"pkg/service.py": _PY.replace("graph.store", "graph.unknown")})
    assert covered.run("capability-coverage") == 1
    assert "capability graph.unknown is not in the registry export" in capsys.readouterr().out
    covered.commit({"pkg/service.py": _PY.replace("def query(text)", "def query(text, extra=None)")})
    covered.commit({"tools.json": json.dumps({**_TOOLS, "tools": [{**_TOOLS["tools"][0], "sha256": "0" * 64}]})})
    assert covered.run("capability-coverage") == 1
    assert "source digest does not match" in capsys.readouterr().out
    covered.commit({"tools.json": json.dumps({"tools": _TOOLS["tools"]})})  # incomplete inventory
    assert covered.run("capability-coverage") == 2
    covered.commit({"tools.json": json.dumps(_TOOLS), "registry.json": json.dumps({"capabilities": []})})  # no revision
    assert covered.run("capability-coverage") == 2
    covered.commit({"registry.json": json.dumps(_REGISTRY), "pkg/ui.ts": "export const a = 1\n"})  # no adapter
    assert covered.run("capability-coverage") == 2


# spec: PIPE-PAGES-R012.18
def test_capability_inventory_evidence(covered: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert covered.run("capability-coverage") == 0
    receipt = _receipt(capsys)
    assert receipt["adapters"] == {"inventory": "1", "python": "1", "rust": "1"}
    assert receipt["registry_revision"] == "reg-1" and len(receipt["source_snapshot"]) == 64
    assert receipt["identities"]["tool"] == ["query_tool"]
    assert "pkg/service.py::Store.put" in receipt["identities"]["function"]
    assert "pkg/test_service.py::test_query" in receipt["identities"]["test"]
    assert receipt["unmatched"] == []
    # zero tools is an explicit scope fact, never an omitted column
    covered.commit({".config/capability-coverage.json": _config(scope="none")})
    assert covered.run("capability-coverage") == 0
    receipt = _receipt(capsys)
    assert receipt["scope"]["tools"] == "none" and receipt["counts"]["tool"] == 0
    assert receipt["identities"]["tool"] == []


# spec: PIPE-PAGES-R012.19
def test_capability_inventory_cli(covered: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert covered.run("capability-coverage") == 0
    capsys.readouterr()
    covered.commit(
        {"crates/engine/src/lib.rs": _RUST.replace("    // capability: graph.query\n    pub fn run", "    pub fn run")}
    )
    assert covered.run("capability-coverage") == 1
    assert "crates/engine/src/lib.rs:10: function Engine.run: no capability binding" in capsys.readouterr().out
    covered.commit({"crates/engine/src/lib.rs": _RUST})
    covered.commit(
        {
            "tools.json": json.dumps(
                {"complete": True, "tools": [{k: v for k, v in _TOOLS["tools"][0].items() if k != "capability"}]}
            )
        }
    )
    assert covered.run("capability-coverage") == 1
    assert "tool query_tool: no capability binding" in capsys.readouterr().out
    covered.commit({"tools.json": json.dumps(_TOOLS)})
    assert covered.run("capability-coverage") == 0  # repair passes
    covered.commit({"crates/engine/src/main.go": "package main\n"})
    assert covered.run("capability-coverage") == 2  # an unsupported language refuses exhaustive coverage
