"""Constants and regular expressions for the Pages readiness contract."""

from __future__ import annotations

import re


SCHEMA_ID = "https://agent-utilities.invalid/schemas/agent-readiness-v1.json"
SCHEMA_VERSION = "agent-readiness/v1"
MIRROR_CONTRACT = "mkdocs-static/v2"
CHECKER_VERSION = "pages-readiness-tck/v1"

MAX_ENTRIES = 512
MAX_SOURCE_BYTES = 2_000_000
MAX_TOTAL_SOURCE_BYTES = 8_000_000
MAX_GENERATED_FILE_BYTES = 500_000
MAX_TOTAL_GENERATED_BYTES = 8_000_000
MAX_HTML_BYTES = 8_000_000
MAX_MANIFEST_BYTES = 1_000_000

APPLICABILITY_KEYS = {
    "content",
    "discoverability",
    "access_policy",
    "capabilities",
    "errors",
    "provenance",
    "measurement",
    "deployment",
}
CAPABILITY_KEYS = {"api", "mcp", "a2a", "skills"}
SIGNAL_POLICIES = {"unset", "operator-reviewed"}
STANDARD_KINDS = {"rfc", "draft", "convention"}
GENERATOR_OUTPUTS = {
    "llms.txt",
    "llms-full.txt",
    "llms-sections",
    "markdown-mirror-manifest.json",
    "agent-readiness-manifest.json",
    ".well-known",
}
# The exact discovery documents the universal-skills generator is designed to
# emit (DOCUMENTATION_STANDARD_VNEXT "Source and generated artifacts").
# `.well-known` is admitted only with one of these leaves -- never as an open
# directory -- so this set and the generator's own `discovery_paths` are one
# contract.
WELL_KNOWN_OUTPUTS = {"agent-skills.json", "api-catalog", "mcp-server-card.json"}
OAUTH_METADATA_FIELDS = {
    "oauth_protected_resource": ".well-known/oauth-protected-resource",
    "oauth_authorization_server": ".well-known/oauth-authorization-server",
}
# Transports a served surface may declare. ``stdio`` exists only for MCP; an
# A2A agent is always reached over a network binding.
SURFACE_TRANSPORTS = {
    "mcp": {"stdio", "streamable-http", "sse"},
    "a2a": {"jsonrpc", "http-json", "grpc"},
}
# ``local``: a client launches the server process itself (stdio).
# ``in-cluster``: reachable only inside the deployment network under
# ``service_identity``. ``public``: reachable at a verifiable public HTTPS
# ``endpoint``.
REACHABILITY_VALUES = {"local", "in-cluster", "public"}
NON_PUBLIC_REACHABILITY = {"local", "in-cluster"}
TRANSPORT_KEYS = {"transport", "reachability", "service_identity"}
SERVICE_IDENTITY_PATTERN = re.compile(
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?){1,4}"
)
SECRET_PATTERN = re.compile(
    r"(?ix)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|"
    r"secret(?:[_-][a-z0-9]+)*|token(?:[_-][a-z0-9]+)*)"
    r"[\"'`]?\s*[:=]\s*(?!<|\$|env://|\*|redacted\b|none\b|false\b|true\b)"
    r"[\"']?[A-Za-z0-9_./+=:-]{12,}[\"']?"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")
URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")
META_TAG_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
DEPRECATED_DATA_PATTERN = re.compile(
    r"data-(?:agent-)?document-state\s*=\s*[\"']deprecated[\"']",
    re.IGNORECASE,
)
LINK_TAG_PATTERN = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
DIRECTIVE_MARKER_PATTERN = re.compile(
    r"<!--\s*agent-utilities-markdown\b", re.IGNORECASE
)
DIRECTIVE_PATTERN = re.compile(
    r"<!--\s*agent-utilities-markdown\s+"
    r'alternate="(?P<alternate>[^"]+)"\s+'
    r'llms="(?P<llms>[^"]+)"\s*-->',
    re.IGNORECASE,
)
ATTRIBUTE_PATTERN = re.compile(
    r"(?P<name>[a-z][a-z0-9:-]*)\s*=\s*(?P<quote>[\"'])(?P<value>[^\"']*)(?P=quote)",
    re.IGNORECASE,
)
PATH_CONTROL_PATTERN = re.compile(r"[\x00-\x1f]")
