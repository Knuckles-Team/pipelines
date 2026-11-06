# Contract — prompt-agent-definitions

Provider: scion-sdk SCION-CONNECTOR-CONTROL-R916.8
Consumer: pipelines PIPE-GATES-R014.3

## Wire shape

A prompt file `<package>/prompts/<name>.json` holds `identity.role`, `identity.goal`, `instructions.core_directive` and an `agent` object. The object holds `kind` (`operator` or `business-role`), `business_role`, `tools`, `skills`, `data.reads`, `data.writes`, `guardrails.approval_required`, `guardrails.never` and `outputs`. The SDK carries `agent` in the prompt metadata under `team.knuckles/prompt`.

## Refusal codes

The gate reports one `prompts:` gap per missing field or unknown name. The SDK self-check reports the same items against the live server.

## Authoritative types

The SDK validator is `prompt_agent_findings` in `scion_sdk/surface_contracts.py`. The static checker is `pipelines_hooks/hygiene/connector_surface_prompts.py`.

## Test vectors

`tests/hooks/test_connector_surface.py` builds an operator prompt and a business-role prompt.
