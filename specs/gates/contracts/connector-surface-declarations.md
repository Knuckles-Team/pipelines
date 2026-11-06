# Contract — connector-surface-declarations

Provider: scion-sdk SCION-CONNECTOR-CONTROL-R916.2
Consumer: pipelines PIPE-GATES-R014.5

The same declarations feed `PIPE-GATES-R014.6` and `PIPE-GATES-R014.7`, the SDK rollup `SCION-CONNECTOR-CONTROL-R916` and the scaffold row `US-MCP-BUILDER-R011.15`.

## Wire shape

A connector module `<package>/connector_contracts.py` holds the module-level names `CONTRACTS`, `LINKS`, `LOCATIONS` and `ROLES`. Each holds calls of the SDK builders. The gate reads each call by keyword, or by position in this field order:

| Builder | Fields in order |
|---|---|
| `Refusal` | `code`, `when` |
| `ToolStep` | `tool`, `params`, `result`, `refusals` |
| `ToolUseContract` | `task`, `steps`, `description` |
| `SurfaceLink` | `task`, `tools`, `prompts`, `skills` |
| `DataLocation` | `name`, `holds`, `instance`, `read_tool`, `store`, `route_param`, `federation_key` |
| `BusinessRole` | `name`, `tasks`, `description` |

The SDK serves the rendered Turtle as `ontology://<connector>/contracts.ttl` in the namespace `https://knuckles-team.github.io/scion-sdk/contract#`. Individuals use the IRI `urn:scion:<connector>:<kind>:<name>`.

## Refusal codes

The gate reports gaps, not refusal codes. A builder call with a non-literal argument reads as absent, so the gate names the missing field. The SDK loader raises on a declaration that names an unserved tool.

## Authoritative types

The builders live in `scion_sdk/surface_contracts.py` in scion-sdk. The static reader is `pipelines_hooks/hygiene/connector_surface_contracts.py`.

## Test vectors

`tests/hooks/test_connector_surface.py` holds the declaration vectors of this repository. The SDK tests of `SCION-CONNECTOR-CONTROL-R916.2` render the same declarations.
