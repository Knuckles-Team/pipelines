"""PIPE-PAGES-R020.37 to R020.42: the tool/method inventory equals the documentation rows."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs import tool_mapping as tm
from pipelines_hooks.docs.gate_io import sha
from tests.hooks.conftest import Repo
from tests.hooks.docs_support import fetch, serve

REGISTRY = "docs/registry.json"
TABLE = "docs/tools.md"


def export_registry() -> dict:
    """The owner producer's export of one fixture tool with a nested method and a void method."""
    return {
        "format": "tool-registry/1",
        "producer": "fixture-owner",
        "version": "1.2.0",
        "tools": [
            {
                "id": "store",
                "methods": [
                    {
                        "id": "store.get",
                        "parameters": [
                            {"name": "key", "type": "string", "required": True},
                            {"name": "limit", "type": "integer", "required": False, "default": 10},
                        ],
                        "result": {"type": "object", "fields": [{"name": "value", "type": "string"}]},
                        "examples": [{"request": {"key": "a"}, "result": {"value": "b"}}],
                        "methods": [
                            {
                                "id": "store.get.history",
                                "parameters": [],
                                "result": {"type": "void"},
                                "examples": [{"request": {}, "result": None}],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def build(tmp_path: Path, registry: dict | None = None, *, page: str | None = None) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir(parents=True)
    repo.git("init", "-q")
    raw = json.dumps(registry or export_registry(), indent=1)
    (tmp_path / "scratch.json").write_text(raw)
    repo.stage({REGISTRY: raw})
    decl = {"schema": 1, "registry": REGISTRY, "registry_digest": sha(raw), "table": TABLE}
    mapping, _r, _t = _load(repo, decl)
    repo.stage({tm.DECLARATION: json.dumps(decl), TABLE: page if page is not None else tm.render(mapping)})
    return repo


def _load(repo: Repo, decl: dict):
    repo.stage({tm.DECLARATION: json.dumps(decl)})
    return tm.load_registry(repo.root)


def page_of(repo: Repo) -> str:
    return (repo.root / TABLE).read_text()


# spec: PIPE-PAGES-R020.37
def test_tool_mapping_model(tmp_path: Path) -> None:
    repo = build(tmp_path)
    mapping, registry, table = tm.load_registry(repo.root)
    assert (mapping.producer, mapping.version, registry, table) == ("fixture-owner", "1.2.0", REGISTRY, TABLE)
    assert [m.id for m in mapping.inventory()] == ["store.get", "store.get.history"]
    get = mapping.inventory()[0]
    assert [(p.name, p.type, p.required, p.default) for p in get.parameters] == [
        ("key", "string", True, None),
        ("limit", "integer", False, 10),
    ]
    assert get.result == (("value", "string"),) and mapping.inventory()[1].result is None
    assert len(get.children) == 1 and get.pointer == "/tools/0/methods/0"
    dup = export_registry()
    dup["tools"][0]["methods"][0]["methods"][0]["id"] = "store.get"
    with pytest.raises(CannotRun):
        build(tmp_path / "dup", dup)
    missing = export_registry()
    del missing["tools"][0]["methods"][0]["result"]
    with pytest.raises(CannotRun):
        build(tmp_path / "missing", missing)


# spec: PIPE-PAGES-R020.38
def test_tool_mapping_behavior(tmp_path: Path) -> None:
    repo = build(tmp_path)
    assert tm.check(repo.root).findings == []
    page = page_of(repo)
    cases = {
        "tool row removed": page.split("### store.get.history")[0],
        "parameter removed": page.replace("- parameter `limit` type=integer required=false default=10\n", ""),
        "default mismatch": page.replace("default=10", "default=11"),
        "result removed": page.replace("- result field `value` type=string\n", ""),
        "void undescribed": page.replace("- result: void\n", ""),
        "empty params undescribed": page.replace("- parameters: none\n", ""),
        "example removed": page.replace('Request example:\n```json\n{"key": "a"}', 'Other:\n```json\n{"key": "a"}'),
        "example mistyped": page.replace('{"key": "a"}', '{"key": 3}'),
        "stale extra row": page + "\n### store.gone\n\n- parameters: none\n- result: void\n",
    }
    for name, broken in cases.items():
        findings = tm.check(build(tmp_path / name.replace(" ", "_"), page=broken).root).findings
        assert findings, name
    assert tm.check(build(tmp_path / "again").root).findings == []


# spec: PIPE-PAGES-R020.39
def test_tool_mapping_wiring(tmp_path: Path) -> None:
    from pipelines_hooks.cli import run_gate

    assert GATES["tool-mapping"] == "pipelines_hooks.docs.tool_mapping"
    hooks = Path(__file__).resolve().parents[2] / ".pre-commit-hooks.yaml"
    assert "entry: pipelines-hook tool-mapping" in hooks.read_text()
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/pages_pipeline.yml").read_text()
    assert workflow.index("docs.tool_mapping") < workflow.index("Upload artifact")
    repo = build(tmp_path)
    assert run_gate("tool-mapping", ["--root", str(repo.root)]) == 0 == repo.run("tool-mapping")


# spec: PIPE-PAGES-R020.40
def test_tool_mapping_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    page = page_of(repo)
    omitted = build(tmp_path / "omitted", page=page.split("### store.get.history")[0])
    assert omitted.run("tool-mapping") == 1
    out = capsys.readouterr().out
    assert "/tools/0/methods/0/methods/0: store.get.history has no row in docs/tools.md" in out
    wrong_format = export_registry() | {"format": "tool-registry/9"}
    with pytest.raises(CannotRun, match="unsupported registry format"):
        build(tmp_path / "fmt", wrong_format)
    anonymous = export_registry()
    del anonymous["producer"]
    with pytest.raises(CannotRun, match="producer evidence"):
        build(tmp_path / "anon", anonymous)
    ambiguous = copy.deepcopy(export_registry())
    ambiguous["tools"][0]["methods"][0]["result"] = {"type": "array", "fields": []}
    with pytest.raises(CannotRun, match="ambiguous"):
        build(tmp_path / "amb", ambiguous)
    stale = build(tmp_path / "stale")
    stale.stage({REGISTRY: json.dumps(export_registry() | {"version": "9"})})
    assert stale.run("tool-mapping") == 2
    unsafe = {"schema": 1, "registry": "../x", "registry_digest": "0", "table": TABLE}
    stale.stage({tm.DECLARATION: json.dumps(unsafe)})
    assert stale.run("tool-mapping") == 2


# spec: PIPE-PAGES-R020.41
def test_tool_mapping_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path)
    assert repo.run("tool-mapping") == 0
    out = capsys.readouterr().out
    assert "producer=fixture-owner version=1.2.0 digest=" in out
    assert "methods=['store.get', 'store.get.history']" in out
    assert "counts methods=2 parameters=2 result-fields=1 examples=2" in out
    assert "comparison id=store.get.history row=docs/tools.md:" in out and "anchor=#store.get.history" in out
    assert "runtime=none: schema-valid examples do not prove a deployed method succeeds" in out
    nested_gone = build(tmp_path / "n", page=page_of(repo).split("#### store.get.history")[0])
    assert nested_gone.run("tool-mapping") == 1
    gone = capsys.readouterr().out
    assert "store.get.history has no row in docs/tools.md (expected section ### store.get.history)" in gone
    assert "comparison id=store.get.history row=absent" in gone


# spec: PIPE-PAGES-R020.42
def test_tool_mapping_cli(tmp_path: Path) -> None:
    repo = build(tmp_path)
    scratch = tmp_path / "site" / "tools.md"
    assert repo.run("tool-mapping", "--render", str(scratch)) == 0
    assert repo.run("tool-mapping", "--render", str(scratch)) == 2  # never overwrites
    with serve(scratch.parent) as base:
        served = fetch(f"{base}/tools.md")
    assert served == page_of(repo) and repo.run("tool-mapping") == 0
    mutations = {
        "tool row": lambda p: p.split("### store.get")[0],
        "nested method": lambda p: p.split("#### store.get.history")[0],
        "parameter": lambda p: p.replace("- parameter `key` type=string required=true default=none\n", ""),
        "result": lambda p: p.replace("- result field `value` type=string\n", ""),
        "example": lambda p: p.replace('{"value": "b"}', '{"value": 1}'),
    }
    good = page_of(repo)
    for name, mutate in mutations.items():
        repo.stage({TABLE: mutate(good)})
        assert repo.run("tool-mapping") == 1, name
        repo.stage({TABLE: good})
        assert repo.run("tool-mapping") == 0, name
    repo.stage({REGISTRY: json.dumps(export_registry() | {"version": "2.0.0"})})
    assert repo.run("tool-mapping") == 2  # stale export
