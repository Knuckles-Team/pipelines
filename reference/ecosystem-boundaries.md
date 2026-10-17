# Ecosystem boundaries (ecosystem-boundaries)

This standard routes every feature of the Arbora ecosystem to the repository that owns it. It is the one source of truth. Each repository links here from its `AGENTS.md` and its development skill. No repository keeps a copy of these tables.

Every package installs from the public package index. A source checkout, a git dependency, or a path dependency is a development aid only.

## Repository table

| Repository | Owns | Never owns (route it to) | ID prefix | Allowed dependencies |
|---|---|---|---|---|
| epistemic-graph (EG) | Facts, records, vocabulary and durable state. Storage, query (UQL and natural language), retrieval and ingest. Reasoning, decisions and choices. Code is native Rust. Each row sets latency and memory budgets and names a benchmark. | Served operations, admission and auth (arbora); connector contracts and transports (SDK); run mechanics (AU); views (UIs). | `EG-` | Rust crates; its own Python client and bindings. No ecosystem Python package. |
| arbora | The one door. Admission, auth, approvals and served operations. The MCP server and multiplexer. A2A serving and routing. The tool and operation registry. Platform config at `~/.config/arbora`. The EG methods served as `eg.*`. | Facts, stores, policy tables and decisions (EG); protocol libraries (SDK); the run loop (AU). | `ARBORA-` | epistemic-graph, agent-connector-sdk, and only `agent_utilities.host_ports`, `.harness`, `.runtime` and `.core.paths`. |
| agent-connector-sdk (SDK) | Connector contracts. Transports: REST, GraphQL, gRPC, MCP, the A2A protocol library and the others. The EG client adapter. Connector ontology pack generation. | Serving and routing (arbora); facts, storage and pushdown planning (EG). | `SDK-` | epistemic-graph client; protocol libraries. |
| agent-utilities (AU) | The in-run harness. The run loop, context assembly, fan-out, sandbox runs and replay. Trace event emission. Enforcement of a limit it receives. | An MCP server, server, gateway, API or A2A (arbora). A store, planner, selector, router, retriever or policy (EG). Contracts (SDK). | `AU-` | agent-connector-sdk; the model client library. No MCP, web server or storage package. |
| agent-webui | What a person sees in the browser. | Data access other than through arbora; decisions (EG). | `WEBUI-` | `arbora.client`; agent-connector-sdk. |
| agent-terminal-ui (TUI) | What a person sees in the terminal. | Data access other than through arbora; decisions (EG). | `TUI-` | `arbora.client`; agent-connector-sdk. |
| geniusbot | What a person sees in the desktop and chat client. | Data access other than through arbora; decisions (EG). | `GENIUSBOT-` | `arbora.client`; agent-connector-sdk. |
| Connectors (`*-mcp`, `*-api`, `*-agent`) | The behavior of one external system: its venue or API calls, mappings and MCP tools. | Domain maths and stores (EG); shared helpers (SDK); serving to other callers (arbora). | `CONN-<REPO>-` | agent-connector-sdk only. |
| pipelines | Gates, pages, release rules, the spec standard and this standard. | Product behavior of any repository. | `PIPE-` | No ecosystem package. |
| universal-skills | Skill content and the connector scaffold (mcp-builder). | Served operations (arbora); selection of skills (EG). | `US-` | `arbora.client` in skill scripts. |

## Routing procedure for a new feature

Route a feature before any code or spec text.

1. Split the feature into parts. Ask the questions below for each part. The first "yes" names the owner.

   | Question about the part | Owner |
   |---|---|
   | Is it a fact, record, vocabulary term, trace record, trust or provenance mark? | EG |
   | Is it a choice? Plans, routing, retrieval and ranking are choices. So are skill, tool and model selection, thresholds, budgets, stop rules and verdicts. | EG |
   | Is it a served operation, an admission check, auth, an approval, or the registry? | arbora |
   | Is it a contract, a schema, or a transport of a tool, source or connector? | SDK |
   | Is it the behavior of one external system? | That connector |
   | Does it apply a received decision inside one run? | AU |
   | Is it what a person sees or does? | webui, TUI or geniusbot |
   | Is it a gate, a page or a release rule? | pipelines |

2. Search the owner's specs first: `git grep -n "<term>" -- specs`. Extend an existing row before a new one.
3. File each part as a row in its owner's `specs/`. Link the dependent rows to each other by ID.
4. Write code only in the repository that owns the part. A part that this repository does not own stops here; its row goes to the owner.

An `AU-` row never decides. It names the decision it receives and the owner prefix that produces it. A threshold in an `AU-` row is a received value, with a fallback default. If no part is left for the harness, write no `AU-` row.

## Worked examples

| Feature | Split and owners |
|---|---|
| Capability index | The index is a fact and a selection. EG stores it and answers selection queries. arbora serves the query. |
| A2A | The SDK holds the protocol library: agent card, task and message types, client, and the server factory as the `[a2a]` extra. arbora serves and routes A2A behind admission and auth. AU has no A2A. |
| Ingest contracts | EG stores each connector's ingest contract as native OWL/RDF under the platform ontology, with SHACL validation. The SDK writes the Turtle from typed declarations. |
| Finance maths (emerald-exchange) | EG runs backtests, risk, signals and strategy maths as native Rust rows. The connector keeps venue calls, order routing and MCP tools, and reaches EG through the SDK adapter. |
| Platform config directory | arbora owns `~/.config/arbora/` and the `ARBORA_CONFIG_DIR` override. Other repositories read config through arbora. |
| Current-plan reads and tool-task dispatch (AU #302, #303) | The plan record and the work-item lease go to EG. The authorized read and the tool-task dispatch become arbora served operations. The request and snapshot models go to the SDK. AU keeps only the run that applies the plan it receives. |
| Web search | Web search is a source category. The searxng connector is the reference connector. arbora selects search tools through it; EG refreshes data through it as a virtual graph. |

## Forbidden-import matrix

This matrix is guidance for reviews and for each repository's own tests. A module prefix matches itself and its submodules. An allowed prefix stays permitted inside a forbidden prefix.

| Repository | Must not import | Except |
|---|---|---|
| epistemic-graph | `arbora`, `agent_utilities`, `agent_connector_sdk`, `agent_webui`, `agent_terminal_ui`, `geniusbot` | |
| arbora | `agent_utilities`, `agent_webui`, `agent_terminal_ui`, `geniusbot` | `agent_utilities.host_ports`, `agent_utilities.harness`, `agent_utilities.runtime`, `agent_utilities.core.paths` |
| agent-connector-sdk | `agent_utilities`, `arbora`, `agent_webui`, `agent_terminal_ui`, `geniusbot` | |
| agent-utilities | `arbora`, UI packages, `fastmcp`, `mcp`, `starlette`, `uvicorn`, `fastapi`, `a2a`, storage packages (`neo4j`, `falkordb`, `real_ladybug`, `kuzu`, `psycopg`, `asyncpg`, `sqlalchemy`, `redis`, `pymongo`, `qdrant_client`, `chromadb`, `lancedb`, `duckdb`, `aiosqlite`) | |
| agent-webui, agent-terminal-ui, geniusbot | `epistemic_graph`, `arbora`, `agent_utilities`, the other UI packages | `arbora.client` |
| Connectors | `agent_utilities`, `arbora`, `epistemic_graph`, UI packages | |
| pipelines | Every ecosystem package | |
| universal-skills | `epistemic_graph`, `arbora`, `agent_utilities`, UI packages | `arbora.client` |

No repository declares a `[tool.uv.sources]` git, path or URL entry for `epistemic-graph`.
