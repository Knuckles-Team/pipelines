"""Connector prompts are complete agent definitions.

The platform builds agents from connector prompts, so each prompt is a
system-prompt candidate. A prompt JSON file states the agent in full:

```json
{"title": "...", "identity": {"role": "...", "goal": "..."},
 "instructions": {"core_directive": "..."},
 "agent": {"kind": "operator" | "business-role", "business_role": "<role>",
           "tools": ["<tool>"], "skills": ["<skill>"],
           "data": {"reads": ["<location>"], "writes": ["<location>"]},
           "guardrails": {"approval_required": ["..."], "never": ["..."]},
           "outputs": ["..."]}}
```

A connector has at least one operator prompt, declares the business roles it
serves (``BusinessRole`` in ``connector_contracts.py``) and has one
business-role prompt per role. A prompt's tools are tools its connector's
tool-use contracts call; its skills are packaged skills; its data names are
declared data locations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KINDS = ("operator", "business-role")


@dataclass(frozen=True)
class Known:
    """The names a prompt may refer to."""

    contract_tools: set[str]
    skills: set[str]
    locations: set[str]
    linked: set[str]


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _load(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _structure_gaps(name: str, document: dict[str, Any], agent: dict[str, Any]) -> list[str]:
    identity = _obj(document.get("identity"))
    data = _obj(agent.get("data"))
    guardrails = _obj(agent.get("guardrails"))
    checks = (
        (_text(identity.get("role") or document.get("role")), "no role"),
        (_text(identity.get("goal") or document.get("goal")), "no goal"),
        (agent.get("kind") in KINDS, "agent.kind is not operator or business-role"),
        (agent.get("kind") != "business-role" or _text(agent.get("business_role")), "no agent.business_role"),
        (bool(_strings(agent.get("tools"))), "names no tools"),
        (bool(_strings(agent.get("skills"))), "names no skills"),
        (bool(_strings(data.get("reads")) + _strings(data.get("writes"))), "names no data read or written"),
        (bool(_strings(guardrails.get("never"))), "states no never-do guardrail"),
        (bool(_strings(agent.get("outputs"))), "states no outputs"),
    )
    return [f"prompts: {name}: {message}" for ok, message in checks if not ok]


def _reference_gaps(name: str, agent: dict[str, Any], known: Known) -> list[str]:
    data = _obj(agent.get("data"))
    gaps = []
    tools = [t for t in _strings(agent.get("tools")) if t not in known.contract_tools]
    skills = [s for s in _strings(agent.get("skills")) if s not in known.skills]
    places = [d for d in _strings(data.get("reads")) + _strings(data.get("writes")) if d not in known.locations]
    if tools:
        gaps.append(f"prompts: {name}: tools no tool-use contract calls: {', '.join(tools)}")
    if skills:
        gaps.append(f"prompts: {name}: skills not packaged: {', '.join(skills)}")
    if places:
        gaps.append(f"prompts: {name}: data locations not declared: {', '.join(places)}")
    if name not in known.linked:
        gaps.append(f"prompts: {name}: not linked to its skills and tools in the ontology (SurfaceLink)")
    return gaps


def prompt_gaps(prompts: list[Path], roles: list[str], known: Known) -> tuple[list[str], dict[str, Any]]:
    """The agent-definition gaps of a connector's prompts and a summary for the record."""
    gaps: list[str] = []
    kinds: dict[str, str] = {}
    served_roles: set[str] = set()
    for path in prompts:
        document = _load(path)
        agent = _obj(document.get("agent"))
        if not agent:
            gaps.append(f"prompts: {path.stem}: not an agent definition (no agent object)")
            continue
        gaps.extend(_structure_gaps(path.stem, document, agent))
        gaps.extend(_reference_gaps(path.stem, agent, known))
        kinds[path.stem] = str(agent.get("kind"))
        if agent.get("kind") == "business-role" and _text(agent.get("business_role")):
            served_roles.add(agent["business_role"].strip())
    if prompts and "operator" not in kinds.values():
        gaps.append("prompts: no operator-agent prompt")
    if not roles:
        gaps.append("prompts: no business role declared (BusinessRole in connector_contracts.py)")
    gaps.extend(
        f"prompts: business role {role} has no business-role prompt" for role in roles if role not in served_roles
    )
    return gaps, {"kinds": dict(sorted(kinds.items())), "roles": roles, "roles_with_prompt": sorted(served_roles)}
