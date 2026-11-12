"""The three ontology parts of a connector surface, read without importing it.

A connector declares its tool-use contracts, its prompt/skill/tool links and
its data locations once, in ``<package>/connector_contracts.py``, with the
Scion SDK builders (``ToolUseContract``, ``ToolStep``, ``Refusal``,
``SurfaceLink``, ``DataLocation``, ``UpstreamTool``). The SDK renders them as the served
``ontology://<connector>/contracts.ttl`` resource. This module reads the same
declarations statically: the call names and their literal arguments, by keyword
or by the builders' positional field order. A packaged Turtle file that types
individuals with the SDK contract vocabulary counts as well.

It imports no ecosystem package, so pipelines can run it on any checkout.
"""

from __future__ import annotations

from pipelines_hooks.core.ontology_base import CONTRACT_NS

import ast
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONTRACTS_MODULE = "connector_contracts.py"
#: A skill whose name ends with this suffix guides contributors, not an agent at work; it serves no task.
CONTRIBUTOR_SKILL_SUFFIX = "-development"
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

#: Builder name -> positional field order (the SDK dataclass field order).
FIELDS: dict[str, tuple[str, ...]] = {
    "Refusal": ("code", "when"),
    "ToolStep": ("tool", "params", "result", "refusals"),
    "ToolUseContract": ("task", "steps", "description"),
    "SurfaceLink": ("task", "tools", "prompts", "skills"),
    "DataLocation": ("name", "holds", "instance", "read_tool", "store", "route_param", "federation_key"),
    "BusinessRole": ("name", "tasks", "description"),
    "UpstreamTool": ("upstream", "tool", "description", "input_schema", "destructive"),
}


@dataclass
class Declared:
    """The contract parts one connector declares."""

    contracts: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    roles: list[dict[str, Any]] = field(default_factory=list)
    upstream_tools: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def _literal(node: ast.AST) -> Any:
    """A literal value, a builder call as a dict, or a sequence of those; else ``None``."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [_literal(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {
            key.value: _literal(value)
            for key, value in zip(node.keys, node.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    if isinstance(node, ast.Call):
        return _call(node)
    return None


def _call_name(node: ast.Call) -> str:
    return getattr(node.func, "id", getattr(node.func, "attr", ""))


def _call(node: ast.Call) -> dict[str, Any] | None:
    name = _call_name(node)
    order = FIELDS.get(name)
    if order is None:
        return None
    values: dict[str, Any] = {"kind": name}
    for key, arg in zip(order, node.args, strict=False):
        values[key] = _literal(arg)
    for keyword in node.keywords:
        if keyword.arg:
            values[keyword.arg] = _literal(keyword.value)
    return values


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _outermost_calls(tree: ast.Module) -> list[dict[str, Any]]:
    """Builder calls that are not arguments of another builder call."""
    nested: set[int] = set()
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in FIELDS:
            calls.append(node)
            for child in ast.walk(node):
                if child is not node and isinstance(child, ast.Call):
                    nested.add(id(child))
    return [value for node in calls if id(node) not in nested and (value := _call(node)) is not None]


def read_module(path: Path, declared: Declared) -> None:
    """Add the builder declarations of one Python module to ``declared``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return
    for value in _outermost_calls(tree):
        kind = value.pop("kind")
        if kind == "ToolUseContract":
            declared.contracts.append(value)
        elif kind == "SurfaceLink":
            declared.links.append(value)
        elif kind == "DataLocation":
            declared.locations.append(value)
        elif kind == "BusinessRole":
            declared.roles.append(value)
        elif kind == "UpstreamTool":
            declared.upstream_tools.append(value)
    declared.sources.append(path.name)


def read_turtle(triples: list[tuple[str, str, str]], name: str, declared: Declared) -> None:
    """Add the contract-vocabulary individuals of one Turtle file to ``declared``."""

    def objects(subject: str, local: str) -> list[str]:
        return sorted(o for s, p, o in triples if s == subject and p == CONTRACT_NS + local)

    typed = {(s, o.removeprefix(CONTRACT_NS)) for s, p, o in triples if p == _RDF_TYPE and o.startswith(CONTRACT_NS)}
    found = False
    for subject, kind in sorted(typed):
        if kind == "ToolUseContract":
            steps = [
                {
                    "tool": _local((objects(o, "callsTool") or [""])[0], "tool"),
                    "result": objects(o, "resultField"),
                    "refusals": objects(o, "refusal"),
                }
                for s, p, o in triples
                if s == subject and p.endswith("#hasStep")
            ]
            declared.contracts.append({"task": (objects(subject, "forTask") or [""])[0], "steps": steps})
            found = True
        elif kind == "DataLocation":
            declared.locations.append(
                {
                    "name": subject,
                    "holds": objects(subject, "holdsClass"),
                    "instance": (objects(subject, "instance") or [""])[0],
                    "read_tool": (objects(subject, "readTool") or [""])[0],
                }
            )
            found = True
    served = {(s, o) for s, p, o in triples if p == CONTRACT_NS + "servesTask"}
    for subject, task in sorted(served):
        tools = [_local(subject, "tool")] if ":tool:" in subject else []
        declared.links.append({"task": task, "names": [subject], "tools": tools})
        found = True
    if found:
        declared.sources.append(name)


def _local(iri: str, kind: str) -> str:
    """The name of an SDK individual IRI ``urn:scion:<connector>:<kind>:<name>``."""
    return iri.rsplit(f":{kind}:", 1)[-1]


def _step_gaps(index: int, step: Any) -> list[str]:
    if not isinstance(step, dict):
        return [f"contracts: contract {index} has a step that is not a ToolStep"]
    gaps = []
    if not _strings(step.get("tool")):
        gaps.append(f"contracts: contract {index} has a step with no tool")
    if not _strings(step.get("result")):
        gaps.append(
            f"contracts: step {_strings(step.get('tool')) or '?'} of contract {index} declares no result fields"
        )
    return gaps


def contract_gaps(declared: Declared) -> list[str]:
    """Part (a): at least one ordered tool-use contract with result and refusal shapes."""
    if not declared.contracts:
        return ["contracts: no tool-use contract (ToolUseContract in connector_contracts.py)"]
    gaps: list[str] = []
    refusals = 0
    for index, contract in enumerate(declared.contracts, start=1):
        if not _strings(contract.get("task")):
            gaps.append(f"contracts: contract {index} names no task")
        steps = contract.get("steps") or []
        if not steps:
            gaps.append(f"contracts: contract {index} has no ordered steps")
        for step in steps:
            gaps.extend(_step_gaps(index, step))
            refusals += len(step.get("refusals") or []) if isinstance(step, dict) else 0
    if not refusals:
        gaps.append("contracts: no refusal shape declared on any step (Refusal)")
    return gaps


def link_gaps(declared: Declared, prompts: list[str], skills: list[str]) -> list[str]:
    """Part (b): every packaged prompt and skill is linked to a task and to the tools it uses."""
    if not declared.links:
        return ["links: no prompt/skill/tool link (SurfaceLink in connector_contracts.py)"]
    named: set[str] = set()
    gaps: list[str] = []
    for index, link in enumerate(declared.links, start=1):
        names = _strings(link.get("prompts")) + _strings(link.get("skills")) + _strings(link.get("names"))
        named.update(names)
        if not _strings(link.get("task")):
            gaps.append(f"links: link {index} names no task")
        if "names" not in link and not _strings(link.get("tools")):
            gaps.append(f"links: link {index} names no tool")
    gaps.extend(f"links: prompt {name} is linked to no task" for name in prompts if not _linked(name, "prompt", named))
    task_skills = [name for name in skills if not name.endswith(CONTRIBUTOR_SKILL_SUFFIX)]
    gaps.extend(
        f"links: skill {name} is linked to no task" for name in task_skills if not _linked(name, "skill", named)
    )
    return gaps


def _linked(name: str, kind: str, named: set[str]) -> bool:
    return name in named or any(item.endswith(f":{kind}:{name}") for item in named)


def location_gaps(declared: Declared) -> list[str]:
    """Part (c): which instance or store holds which data, and the tool that reads it."""
    if not declared.locations:
        return ["locations: no data location (DataLocation in connector_contracts.py)"]
    gaps: list[str] = []
    for index, location in enumerate(declared.locations, start=1):
        label = _strings(location.get("name")) or [str(index)]
        for key, what in (("holds", "held class"), ("instance", "instance"), ("read_tool", "read tool")):
            if not _strings(location.get(key)):
                gaps.append(f"locations: location {label[0]} names no {what}")
    return gaps


def contract_tools(declared: Declared) -> set[str]:
    """Every tool name a contract step calls."""
    return {
        tool
        for contract in declared.contracts
        for step in contract.get("steps") or []
        if isinstance(step, dict)
        for tool in _strings(step.get("tool"))
    }


def linked_tools(declared: Declared) -> set[str]:
    """Every tool name a link that carries a prompt or a skill names."""
    return {
        tool
        for link in declared.links
        if _strings(link.get("prompts")) or _strings(link.get("skills")) or "names" in link
        for tool in _strings(link.get("tools"))
    }


def location_names(declared: Declared) -> set[str]:
    return {name for location in declared.locations for name in _strings(location.get("name"))}


def role_names(declared: Declared) -> list[str]:
    return sorted({name for role in declared.roles for name in _strings(role.get("name"))})


def upstream_name(entry: dict[str, Any]) -> str:
    """The served name ``<upstream>_<tool>`` of one declared upstream tool."""
    upstream, tool = _strings(entry.get("upstream")), _strings(entry.get("tool"))
    return f"{upstream[0]}_{tool[0]}" if upstream and tool else ""


def upstream_names(declared: Declared) -> list[str]:
    """Served names of every declared upstream tool, sorted and unique."""
    return sorted({name for entry in declared.upstream_tools if (name := upstream_name(entry))})


def upstream_gaps(declared: Declared, local: Iterable[str] = ()) -> list[str]:
    """Declared upstream tools are validated like registered ones: name, description, schema, annotation."""
    gaps: list[str] = []
    seen: set[str] = set()
    taken = set(local)
    for index, entry in enumerate(declared.upstream_tools, start=1):
        name = upstream_name(entry)
        label = name or f"#{index}"
        if not name:
            gaps.append(f"tools: upstream tool {label} names no upstream or no tool")
            continue
        if name in seen:
            gaps.append(f"tools: upstream tool {name} is declared twice")
        seen.add(name)
        if name in taken:
            gaps.append(f"tools: upstream tool {name} collides with a registered tool")
        if not _strings(entry.get("description")):
            gaps.append(f"tools: upstream tool {name} has no description")
        schema = entry.get("input_schema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            gaps.append(f"tools: upstream tool {name} has no object input schema")
        elif not isinstance(schema.get("properties", {}), dict):
            gaps.append(f"tools: upstream tool {name} has a malformed input schema")
        if "destructive" in entry and not isinstance(entry["destructive"], bool):
            gaps.append(f"tools: upstream tool {name} has no boolean destructive annotation")
    return gaps


def tool_coverage_gaps(declared: Declared, served_tools: list[str]) -> list[str]:
    """Per tool: a tool-use contract that calls it, and a skill or prompt link that names it."""
    called, linked = contract_tools(declared), linked_tools(declared)
    no_contract = [t for t in served_tools if t not in called]
    no_link = [t for t in served_tools if t not in linked]
    gaps = []
    if no_contract:
        gaps.append(f"contracts: {len(no_contract)} tool(s) with no tool-use contract: {', '.join(no_contract)}")
    if no_link:
        gaps.append(f"links: {len(no_link)} tool(s) no skill or prompt links: {', '.join(no_link)}")
    return gaps
