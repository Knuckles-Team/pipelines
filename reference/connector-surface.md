# Connector surface standard (connector-surface)

Every connector accounts for its whole MCP surface. The platform builds agents, plans and routes from that surface, so a missing part is a missing capability. This standard names the parts. The `connector-surface-audit` gate checks them from the package alone. The `surface` member of `connector-standard` runs it in strict mode in every connector repository. Rows: `PIPE-GATES-R014` and its children.

The Scion SDK owns the shared machinery (`SCION-CONNECTOR-CONTROL-R916`). A connector declares its parts as data and writes no Turtle, pack builder or serving code. The mcp-builder scaffold generates every part for a new connector and backfills an existing one (`US-MCP-BUILDER-R011.15` to `R011.18`).

## Required parts

| Part | Requirement | Where it lives |
|---|---|---|
| Entry point | Exactly one `scion_sdk.connector` entry point. No `skill_providers`, `ontology_providers` or `source_connector_providers` group, and no plugin group outside the SDK namespace. | `pyproject.toml` |
| Tools | One typed tool per upstream operation. No tool takes an `action` argument that routes to several operations. No registration passes `action_dispatch=True`. | `Connector(api=...)` client methods, or `@<server>.tool` |
| Resources | At least one declared data resource. | `source_meta(...)` in `<package>/connector_sources.py`, or `@<server>.resource` |
| Skills | At least one skill. Every tool is named by a packaged skill or prompt. No `SKILL.md` outside the package skills directory. | `<package>/skills/<name>/SKILL.md` |
| Prompts | At least one operator-agent prompt, and one business-role prompt per declared business role. Each prompt is a complete agent definition (below). | `<package>/prompts/<name>.json` |
| Served | The package hands its content to the SDK, which serves skills, prompts, ontology and shapes over MCP. | `Connector(...)` |
| Ontology | Packaged Turtle with at least one class. Every class reaches a core class (`https://knuckles-team.github.io/ontology/core#`) through `rdfs:subClassOf`. No `owl:imports` of the core ontology. | `<package>/ontology/*.ttl` |
| Tool-use contracts | At least one contract. Each contract names a task and its ordered steps. Each step names its tool, params and result fields. The steps declare at least one refusal shape. Every tool is called by a contract step. | `CONTRACTS` in `<package>/connector_contracts.py` |
| Links | Every prompt and skill is linked to the task it serves and the tools it uses. A contributor skill (`<name>-development`) is exempt. Every tool is named by a link that carries a prompt or skill. | `LINKS` |
| Data locations | At least one location. Each names the classes it holds, the instance or store that holds them, and the tool that reads them. A route parameter and a federation key name how a request reaches that instance. | `LOCATIONS` |
| Business roles | At least one business role the connector serves. | `ROLES` |

## Prompts are agent definitions

The platform builds an agent from each connector prompt, so each prompt is a system-prompt candidate. A prompt file states the whole agent:

```json
{
  "title": "Incident dispatcher",
  "identity": {"role": "Incident dispatcher", "goal": "Close resolved incidents within one day."},
  "instructions": {"core_directive": "You are the incident dispatcher. ..."},
  "agent": {
    "kind": "business-role",
    "business_role": "dispatcher",
    "tools": ["demo_list_incidents", "demo_close_incident"],
    "skills": ["demo-read"],
    "data": {"reads": ["incidents"], "writes": ["incidents"]},
    "guardrails": {"approval_required": ["demo_close_incident"], "never": ["Close an incident without a reason."]},
    "outputs": ["A closed incident with its reason."]
  }
}
```

- `kind` is `operator` or `business-role`. A business-role prompt names its `business_role`.
- `tools` are tools that the connector's tool-use contracts call.
- `skills` are packaged skill directory names.
- `data.reads` and `data.writes` are declared data location names.
- `guardrails.never` holds at least one rule. Destructive tools belong in `approval_required`.
- `outputs` holds at least one expected output.
- A link names the prompt with its task, skills and tools.

## Declaration module

```python
from scion_sdk.surface_contracts import BusinessRole, DataLocation, Refusal, SurfaceLink, ToolStep, ToolUseContract

CONTRACTS = (
    ToolUseContract(
        "close-incident",
        (
            ToolStep("demo_list_incidents", params=("status",), result=("id", "title")),
            ToolStep(
                "demo_close_incident",
                params=("incident_id",),
                result=("id", "state"),
                refusals=(Refusal("NOT_FOUND", "no incident has the id"),),
            ),
        ),
    ),
)
LINKS = (
    SurfaceLink(
        "close-incident",
        tools=("demo_list_incidents", "demo_close_incident"),
        prompts=("demo-operator", "demo-dispatcher"),
        skills=("demo-read",),
    ),
)
LOCATIONS = (DataLocation("incidents", ("Incident",), "DEMO_URL", "demo_list_incidents", federation_key="id"),)
ROLES = (BusinessRole("dispatcher", tasks=("close-incident",)),)
```

The SDK renders the declarations as the served resource `ontology://<connector>/contracts.ttl`. Its classes extend core classes. The engine imports them with the connector pack. It answers "how do I execute task X" from the contracts and resolves routing from the data locations. A packaged Turtle file that types individuals with the same vocabulary also counts.

## The gate

```bash
pipelines-hook connector-surface-audit [--root DIR] [--strict] [--markdown]
pipelines-hook connector-surface-audit --fleet DIR --ref origin/main --markdown   # census
```

- It reads the checkout only. It imports no connector and writes no file.
- In a connector repository the `surface` member, and `connector-api-parity`, build the server in the connector's own interpreter and count the tools it registers, so SDK-derived tools count. A server that does not build fails closed in CI. The interpreter is `$PIPELINES_CONNECTOR_PYTHON`, else `.venv`, else `uv run --frozen python`. The fleet census reads source only, so its tool names are a static estimate.
- `--fleet` reads each repository at the ref through `git archive`, so shared checkouts stay unchanged.
- Each gap starts with its part name, for example `contracts:` or `prompts:`. Per-tool gaps list every tool name.
- `--markdown` prints totals, a per-part count and one fix checklist per failing connector.
- The SDK self-check (`python -m scion_sdk.testing.surface_check <package>`) proves the same parts against the live server. It also checks that every named tool, prompt and skill is served.
- The gate exits 0 when clean, 1 on a gap in strict mode, and 2 when it cannot run. It has no baseline and no suppression.
