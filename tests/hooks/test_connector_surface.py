"""connector-surface-audit: the connector surface standard, read from the package (PIPE-GATES-R014)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.connector import served_tools, standard, surface
from pipelines_hooks.core.errors import Unavailable
from pipelines_hooks.hygiene import connector_surface as audit

pytestmark = pytest.mark.spec("PIPE-GATES-R014")

PARENT = """@prefix : <http://knuckles.team/kg#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://knuckles.team/kg/core> a owl:Ontology ; rdfs:comment "parent # not a comment ." .
:Document a owl:Class ; rdfs:label "Document" .
:Ticket a owl:Class .
"""

LINKED = """@prefix : <http://knuckles.team/kg#> .
@prefix d: <http://example.org/demo#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://example.org/demo> a owl:Ontology .
d:Incident a owl:Class ; rdfs:comment \"\"\"A ticket.
Spans lines.\"\"\" ; rdfs:subClassOf :Ticket .
d:MajorIncident a owl:Class ; rdfs:subClassOf d:Incident .
"""

IMPORTS_CORE = LINKED.replace(
    "<http://example.org/demo> a owl:Ontology .",
    "<http://example.org/demo> a owl:Ontology ; owl:imports <http://knuckles.team/kg> .",
)

ORPHAN = """@prefix d: <http://example.org/demo#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
d:Widget a owl:Class .
"""

PYPROJECT = """[project]
name = "demo-mcp"
[project.entry-points."scion_sdk.connector"]
demo-mcp = "demo_mcp:connector"
"""

INIT = """from scion_sdk.connector import Connector
from demo_mcp.api_client import Api
connector = Connector(api=Api, tools="demo_mcp.mcp_server")
"""

API = """class ApiBase:
    def request(self): ...
class Api(ApiBase):
    def list_incidents(self, status: str = "open"): ...
    def close_incident(self, incident_id: str): ...
    def _private(self): ...
"""

SOURCES = """from scion_sdk.ingest.live_declaration import source_meta
SOURCES = [source_meta(tool="demo_list_incidents", source_id="incidents", record_type="Incident")]
"""

CONTRACTS = """from scion_sdk.surface_contracts import BusinessRole, DataLocation, Refusal, SurfaceLink, ToolStep, ToolUseContract
CONTRACTS = (
    ToolUseContract(
        task="close-incident",
        steps=(
            ToolStep("demo_list_incidents", params=("status",), result=("id", "title")),
            ToolStep(tool="demo_close_incident", params=["incident_id"], result=["id", "state"],
                     refusals=[Refusal("NOT_FOUND", "no incident has the id")]),
        ),
    ),
)
LINKS = (
    SurfaceLink("close-incident", tools=("demo_list_incidents", "demo_close_incident"),
                prompts=("demo-operator", "demo-dispatcher"), skills=("demo-read",)),
)
LOCATIONS = (DataLocation("incidents", ("Incident",), "DEMO_URL", "demo_list_incidents", federation_key="id"),)
ROLES = (BusinessRole("dispatcher", tasks=("close-incident",)),)
"""

SKILL = "---\nname: demo-read\n---\nUse demo_list_incidents, then demo_close_incident.\n"


def _prompt(kind: str = "operator", **agent: object) -> str:
    body: dict[str, object] = {
        "kind": kind,
        "tools": ["demo_list_incidents", "demo_close_incident"],
        "skills": ["demo-read"],
        "data": {"reads": ["incidents"], "writes": ["incidents"]},
        "guardrails": {"approval_required": ["demo_close_incident"], "never": ["Close an incident without a reason."]},
        "outputs": ["A closed incident with its reason."],
    }
    if kind == "business-role":
        body["business_role"] = "dispatcher"
    body.update(agent)
    return json.dumps(
        {
            "title": f"Demo {kind}",
            "identity": {"role": "Incident operator", "goal": "Close resolved incidents."},
            "instructions": {"core_directive": "Operate demo incidents."},
            "agent": body,
        }
    )


def _connector(root: Path, *, ontology: str = LINKED, contracts: str | None = CONTRACTS, **files: str) -> Path:
    pkg = root / "demo_mcp"
    (pkg / "skills" / "demo-read").mkdir(parents=True)
    (pkg / "skills" / "demo-read" / "SKILL.md").write_text(SKILL)
    (pkg / "prompts").mkdir()
    (pkg / "prompts" / "demo-operator.json").write_text(_prompt())
    (pkg / "prompts" / "demo-dispatcher.json").write_text(_prompt("business-role"))
    (pkg / "ontology" / "shapes").mkdir(parents=True)
    (pkg / "ontology" / "demo.ttl").write_text(ontology)
    (pkg / "ontology" / "shapes" / "demo.shacl.ttl").write_text("")
    (pkg / "__init__.py").write_text(INIT)
    (pkg / "api_client.py").write_text(API)
    (pkg / "mcp_server.py").write_text("")
    (pkg / "connector_sources.py").write_text(SOURCES)
    if contracts is not None:
        (pkg / "connector_contracts.py").write_text(contracts)
    for name, text in files.items():
        (pkg / name.replace("__", ".")).write_text(text)
    (root / "pyproject.toml").write_text(PYPROJECT)
    return root


def _parents(tmp_path: Path) -> set[str]:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "core-v1.ttl").write_text(PARENT)
    return audit.parent_terms(parent)


def _gaps(record: dict, part: str) -> list[str]:
    return [g for g in record["gaps"] if g.startswith(part + ":")]


def test_parser_keeps_hash_iris_and_ignores_literals(tmp_path: Path) -> None:
    assert _parents(tmp_path) == {"http://knuckles.team/kg#Document", "http://knuckles.team/kg#Ticket"}


@pytest.mark.spec("PIPE-GATES-R014.1")
def test_complete_connector_has_no_gaps(tmp_path: Path) -> None:
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp"), _parents(tmp_path))
    assert record["gaps"] == []
    assert record["complete"] and record["served"] and record["parent_linked"]
    assert record["tools"]["names"] == ["demo_close_incident", "demo_list_incidents"]
    assert record["declarations"]["contracts"] == 1 and record["declarations"]["roles"] == 1
    assert record["prompts"]["kinds"] == {"demo-dispatcher": "business-role", "demo-operator": "operator"}


@pytest.mark.spec("PIPE-GATES-R014.2")
def test_action_routed_tools_and_action_dispatch_are_gaps(tmp_path: Path) -> None:
    server = (
        "@mcp.tool(tags={'x'})\nasync def demo_incidents(action: str, params_json: str = '{}'): ...\n"
        "register_tool_surface(mcp, action_dispatch=True)\n"
    )
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp", mcp_server__py=server), _parents(tmp_path))
    tools = _gaps(record, "tools")
    assert "tools: action-routed tool demo_incidents (demo_mcp/mcp_server.py)" in tools
    assert "tools: action_dispatch=True in demo_mcp/mcp_server.py" in tools


@pytest.mark.spec("PIPE-GATES-R014.2")
def test_no_tools_and_no_resources_are_gaps(tmp_path: Path) -> None:
    root = _connector(tmp_path / "demo-mcp")
    (root / "demo_mcp" / "__init__.py").write_text("")
    (root / "demo_mcp" / "connector_sources.py").unlink()
    record = audit.audit_connector(root, _parents(tmp_path))
    assert _gaps(record, "tools")[0].startswith("tools: no tool registered")
    assert _gaps(record, "resources")[0].startswith("resources: no data resource")
    assert _gaps(record, "served")


@pytest.mark.spec("PIPE-GATES-R014.3")
def test_prompts_must_be_complete_agent_definitions(tmp_path: Path) -> None:
    root = _connector(tmp_path / "demo-mcp")
    prompts = root / "demo_mcp" / "prompts"
    (prompts / "demo-operator.json").write_text(
        _prompt(tools=["demo_unknown"], skills=[], data={}, guardrails={"never": []}, outputs=[])
    )
    (prompts / "loose.json").write_text(json.dumps({"instructions": {"core_directive": "Do it."}}))
    record = audit.audit_connector(root, _parents(tmp_path))
    gaps = _gaps(record, "prompts")
    for expected in (
        "prompts: demo-operator: names no skills",
        "prompts: demo-operator: names no data read or written",
        "prompts: demo-operator: states no never-do guardrail",
        "prompts: demo-operator: states no outputs",
        "prompts: demo-operator: tools no tool-use contract calls: demo_unknown",
        "prompts: loose: not an agent definition (no agent object)",
    ):
        assert expected in gaps


@pytest.mark.spec("PIPE-GATES-R014.3")
def test_a_connector_needs_an_operator_prompt(tmp_path: Path) -> None:
    root = _connector(tmp_path / "demo-mcp")
    (root / "demo_mcp" / "prompts" / "demo-operator.json").unlink()
    record = audit.audit_connector(root, _parents(tmp_path))
    assert "prompts: no operator-agent prompt" in record["gaps"]


@pytest.mark.spec("PIPE-GATES-R014.3")
def test_every_business_role_needs_a_business_role_prompt(tmp_path: Path) -> None:
    contracts = CONTRACTS.replace(
        'ROLES = (BusinessRole("dispatcher"', 'ROLES = (BusinessRole("auditor"), BusinessRole("dispatcher"'
    )
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp", contracts=contracts), _parents(tmp_path))
    assert _gaps(record, "prompts") == ["prompts: business role auditor has no business-role prompt"]


@pytest.mark.spec("PIPE-GATES-R014.4")
def test_orphans_and_imports_of_core_are_ontology_gaps(tmp_path: Path) -> None:
    orphan = audit.audit_connector(_connector(tmp_path / "a" / "demo-mcp", ontology=ORPHAN), _parents(tmp_path))
    assert _gaps(orphan, "ontology") == [
        "ontology: demo_mcp/ontology/demo.ttl: 1 class(es) do not roll up to a core class: Widget"
    ]
    imports = audit.audit_connector(
        _connector(tmp_path / "b" / "demo-mcp", ontology=IMPORTS_CORE), _parents(tmp_path / "b")
    )
    assert _gaps(imports, "ontology") == [
        "ontology: demo_mcp/ontology/demo.ttl: owl:imports of the core ontology (extend core classes instead)"
    ]
    assert not imports["parent_linked"]


@pytest.mark.spec("PIPE-GATES-R014.4")
def test_without_parent_files_the_core_namespace_is_the_parent(tmp_path: Path) -> None:
    assert audit.audit_connector(_connector(tmp_path / "demo-mcp"))["gaps"] == []


@pytest.mark.spec("PIPE-GATES-R014.5")
def test_missing_contract_parts_are_gaps(tmp_path: Path) -> None:
    contracts = CONTRACTS.replace('result=("id", "title")', "").replace(
        'refusals=[Refusal("NOT_FOUND", "no incident has the id")]', ""
    )
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp", contracts=contracts), _parents(tmp_path))
    assert _gaps(record, "contracts") == [
        "contracts: step ['demo_list_incidents'] of contract 1 declares no result fields",
        "contracts: no refusal shape declared on any step (Refusal)",
    ]


@pytest.mark.spec("PIPE-GATES-R014.5")
def test_no_declarations_lists_every_missing_part_and_tool(tmp_path: Path) -> None:
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp", contracts=None), _parents(tmp_path))
    assert record["missing"] == ["prompts", "contracts", "links", "locations"]
    assert "contracts: 2 tool(s) with no tool-use contract: demo_close_incident, demo_list_incidents" in record["gaps"]
    assert "links: 2 tool(s) no skill or prompt links: demo_close_incident, demo_list_incidents" in record["gaps"]


@pytest.mark.spec("PIPE-GATES-R014.6")
def test_unlinked_prompt_skill_and_tool_are_link_gaps(tmp_path: Path) -> None:
    contracts = CONTRACTS.replace(
        'prompts=("demo-operator", "demo-dispatcher"), skills=("demo-read",)', 'prompts=("demo-operator",)'
    )
    contracts = contracts.replace(
        'tools=("demo_list_incidents", "demo_close_incident")', 'tools=("demo_list_incidents",)'
    )
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp", contracts=contracts), _parents(tmp_path))
    assert _gaps(record, "links") == [
        "links: prompt demo-dispatcher is linked to no task",
        "links: skill demo-read is linked to no task",
        "links: 1 tool(s) no skill or prompt links: demo_close_incident",
    ]


@pytest.mark.spec("PIPE-GATES-R014.6")
def test_contracts_declared_as_turtle_count(tmp_path: Path) -> None:
    turtle = (
        LINKED
        + """@prefix sc: <https://knuckles-team.github.io/scion-sdk/contract#> .
<urn:scion:demo-mcp:contract:close> a sc:ToolUseContract ; sc:forTask <urn:scion:demo-mcp:task:close> ;
    :hasStep <urn:scion:demo-mcp:step:1> , <urn:scion:demo-mcp:step:2> .
<urn:scion:demo-mcp:step:1> a sc:ToolStep ; sc:callsTool <urn:scion:demo-mcp:tool:demo_list_incidents> ; sc:resultField "id" .
<urn:scion:demo-mcp:step:2> a sc:ToolStep ; sc:callsTool <urn:scion:demo-mcp:tool:demo_close_incident> ; sc:resultField "id" ;
    sc:refusal <urn:scion:demo-mcp:refusal:1> .
<urn:scion:demo-mcp:prompt:demo-operator> sc:servesTask <urn:scion:demo-mcp:task:close> .
<urn:scion:demo-mcp:prompt:demo-dispatcher> sc:servesTask <urn:scion:demo-mcp:task:close> .
<urn:scion:demo-mcp:skill:demo-read> sc:servesTask <urn:scion:demo-mcp:task:close> .
<urn:scion:demo-mcp:tool:demo_list_incidents> sc:servesTask <urn:scion:demo-mcp:task:close> .
<urn:scion:demo-mcp:tool:demo_close_incident> sc:servesTask <urn:scion:demo-mcp:task:close> .
<urn:scion:demo-mcp:location:incidents> a sc:DataLocation ; sc:holdsClass d:Incident ; sc:instance "DEMO_URL" ;
    sc:readTool "demo_list_incidents" .
"""
    )
    contracts = 'from scion_sdk.surface_contracts import BusinessRole, DataLocation\nLOCATIONS = (DataLocation("incidents", ("Incident",), "DEMO_URL", "demo_list_incidents"),)\nROLES = (BusinessRole("dispatcher"),)\n'
    record = audit.audit_connector(
        _connector(tmp_path / "demo-mcp", ontology=turtle, contracts=contracts), _parents(tmp_path)
    )
    assert _gaps(record, "contracts") == [] and _gaps(record, "links") == []


@pytest.mark.spec("PIPE-GATES-R014.7")
def test_incomplete_data_location_is_a_gap(tmp_path: Path) -> None:
    contracts = CONTRACTS.replace(
        'DataLocation("incidents", ("Incident",), "DEMO_URL", "demo_list_incidents", federation_key="id")',
        'DataLocation("incidents", (), "")',
    )
    record = audit.audit_connector(_connector(tmp_path / "demo-mcp", contracts=contracts), _parents(tmp_path))
    assert _gaps(record, "locations") == [
        "locations: location incidents names no held class",
        "locations: location incidents names no instance",
        "locations: location incidents names no read tool",
    ]


def fake_python(tmp_path: Path, tools: list[dict]) -> Path:
    """An interpreter stand-in that answers the served-tools probe with ``tools``."""
    script = tmp_path / "fake-python"
    script.write_text(f"#!/bin/sh\necho '{served_tools.MARKER}{json.dumps(tools)}'\n")
    script.chmod(0o755)
    return script


SERVED = [
    {"name": "demo_close_incident", "properties": ["incident_id"]},
    {"name": "demo_list_incidents", "properties": ["status"]},
]


@pytest.mark.spec("PIPE-GATES-R014.8")
def test_connector_standard_runs_the_surface_member(tmp_path: Path, monkeypatch, capsys) -> None:
    assert standard.MEMBERS["surface"] is surface
    monkeypatch.setenv("PIPELINES_CONNECTOR_PYTHON", str(fake_python(tmp_path, SERVED)))
    monkeypatch.chdir(_connector(tmp_path / "ok" / "demo-mcp"))
    assert surface.main([]) == 0
    monkeypatch.chdir(_connector(tmp_path / "bad" / "demo-mcp", contracts=None))
    assert surface.main([]) == 1
    assert "- [ ] **contracts**: no tool-use contract" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R014.11")
def test_the_surface_member_checks_the_served_tool_list(tmp_path: Path, monkeypatch) -> None:
    served = [
        *SERVED,
        {"name": "demo_export", "properties": ["format"]},
        {"name": "demo_route", "properties": ["action"]},
    ]
    monkeypatch.setenv("PIPELINES_CONNECTOR_PYTHON", str(fake_python(tmp_path, served)))
    root = _connector(tmp_path / "demo-mcp")
    record = audit.audit_connector(root, served=served_tools.served_tools(root))
    assert record["tools"]["source"] == "served"
    assert record["tools"]["names"] == ["demo_close_incident", "demo_export", "demo_list_incidents", "demo_route"]
    assert "tools: action-routed tool demo_route (served)" in record["gaps"]
    assert "contracts: 2 tool(s) with no tool-use contract: demo_export, demo_route" in record["gaps"]


@pytest.mark.spec("PIPE-GATES-R014.11")
def test_a_server_that_does_not_build_is_unavailable_not_empty(tmp_path: Path, monkeypatch) -> None:
    broken = tmp_path / "broken-python"
    broken.write_text("#!/bin/sh\necho 'ImportError: no scion_sdk' >&2\nexit 1\n")
    broken.chmod(0o755)
    monkeypatch.setenv("PIPELINES_CONNECTOR_PYTHON", str(broken))
    with pytest.raises(Unavailable, match="did not build: ImportError: no scion_sdk"):
        served_tools.served_tools(_connector(tmp_path / "demo-mcp"))
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.chdir(tmp_path / "demo-mcp")
    assert standard._run("surface", surface, []) == 0
    monkeypatch.setenv("CI", "true")
    assert standard._run("surface", surface, []) == 2


@pytest.mark.spec("PIPE-GATES-R014.9")
def test_fleet_census_reads_refs_without_touching_worktrees(tmp_path: Path, capsys) -> None:
    fleet = tmp_path / "fleet"
    for name, contracts in (("demo-mcp", CONTRACTS), ("bare-mcp", None)):
        repo = _connector(fleet / name, contracts=contracts)
        for cmd in (
            ["init", "-q", "-b", "main"],
            ["add", "."],
            ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
        ):
            subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    assert audit.main(["--fleet", str(fleet), "--ref", "main", "--markdown", "--strict"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("Connectors: 2. Pass: 1. Fail: 1.")
    assert "| bare-mcp | FAIL |" in out and "| demo-mcp | PASS |" in out
    assert "### bare-mcp — FAIL" in out and "### demo-mcp" not in out
    worktrees = subprocess.run(
        ["git", "worktree", "list"], cwd=fleet / "demo-mcp", capture_output=True, text=True
    ).stdout
    assert len(worktrees.strip().splitlines()) == 1


def test_output_is_deterministic(tmp_path: Path, capsys) -> None:
    root = _connector(tmp_path / "demo-mcp")
    assert audit.main(["--root", str(root), "--strict"]) == 0
    first = capsys.readouterr().out
    assert audit.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == first


@pytest.mark.spec("PIPE-GATES-R014.10")
def test_the_published_standard_names_every_checked_part() -> None:
    text = (Path(__file__).resolve().parents[2] / "reference" / "connector-surface.md").read_text(encoding="utf-8")
    for part in (
        "Entry point",
        "Tools",
        "Resources",
        "Skills",
        "Prompts",
        "Served",
        "Ontology",
        "Tool-use contracts",
        "Links",
        "Data locations",
        "Business roles",
    ):
        assert f"| {part} |" in text
    for field in ("kind", "business_role", "tools", "skills", "data.reads", "guardrails.never", "outputs"):
        assert f"`{field}`" in text
