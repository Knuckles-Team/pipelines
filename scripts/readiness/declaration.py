"""Validation for the canonical agent-readiness declaration."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .constants import (
    APPLICABILITY_KEYS,
    CAPABILITY_KEYS,
    OAUTH_METADATA_FIELDS,
    SCHEMA_ID,
    SCHEMA_VERSION,
    SIGNAL_POLICIES,
    STANDARD_KINDS,
    SURFACE_TRANSPORTS,
    TRANSPORT_KEYS,
)
from .errors import _fail
from .privacy import _scan_safe_text
from .surfaces import _validate_surface_reachability
from .urls import _public_url


_SCHEMA_FIELDS = {
    "schema_version",
    "project",
    "applicability",
    "standards",
    "content_signals",
    "budgets",
    "capabilities",
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        _fail(code)


def _validate_schema(schema: Mapping[str, Any]) -> set[str]:
    _require(
        schema.get("$id") == SCHEMA_ID and schema.get("type") == "object",
        "schema-authority-invalid",
    )
    _require(
        schema.get("additionalProperties") is False,
        "schema-additional-properties",
    )
    properties = schema.get("properties")
    required = schema.get("required")
    _require(
        isinstance(properties, Mapping) and isinstance(required, list),
        "schema-shape-invalid",
    )
    required_set = {item for item in required if isinstance(item, str)}
    _require(
        required_set == _SCHEMA_FIELDS and set(properties) == _SCHEMA_FIELDS,
        "schema-authority-invalid",
    )
    version = properties.get("schema_version")
    _require(
        isinstance(version, Mapping) and version.get("const") == SCHEMA_VERSION,
        "schema-authority-invalid",
    )
    return required_set


def _validate_project_and_applicability(value: Mapping[str, Any]) -> str:
    project = value.get("project")
    _require(
        isinstance(project, Mapping)
        and set(project) == {"name", "kind"}
        and isinstance(project.get("name"), str)
        and bool(project["name"])
        and project.get("kind") in {"library", "package", "service", "docs-only"},
        "readiness-project-invalid",
    )
    applicability = value.get("applicability")
    _require(
        isinstance(applicability, Mapping), "readiness-applicability-invalid"
    )
    _require(
        set(applicability) == APPLICABILITY_KEYS,
        "readiness-applicability-invalid",
    )
    _require(
        all(type(applicability[key]) is bool for key in APPLICABILITY_KEYS),
        "readiness-applicability-invalid",
    )
    return project["kind"]


def _validate_standards(standards: object) -> None:
    _require(
        isinstance(standards, list) and bool(standards),
        "readiness-standards-invalid",
    )
    standard_ids: set[str] = set()
    for standard in standards:
        _require(
            isinstance(standard, Mapping)
            and set(standard) == {"id", "kind", "level"},
            "readiness-standards-invalid",
        )
        identifier = standard.get("id")
        kind = standard.get("kind")
        level = standard.get("level")
        _require(
            isinstance(identifier, str)
            and re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9 .:_/-]{1,127}", identifier
            ),
            "readiness-standards-invalid",
        )
        _require(identifier not in standard_ids, "readiness-standards-invalid")
        _require(
            kind in STANDARD_KINDS
            and level in {"normative", "draft", "advisory"},
            "readiness-standards-invalid",
        )
        _require(
            kind != "rfc" or level == "normative",
            "readiness-standards-invalid",
        )
        _require(
            kind != "draft" or level != "normative",
            "readiness-standards-invalid",
        )
        standard_ids.add(identifier)


def _validate_content_signals(signals: object) -> None:
    _require(isinstance(signals, Mapping), "content-signals-policy-required")
    _require(
        not set(signals) - {"policy", "values"},
        "content-signals-policy-required",
    )
    policy = signals.get("policy")
    _require(policy in SIGNAL_POLICIES, "content-signals-policy-required")
    _require(
        policy != "unset" or "values" not in signals,
        "content-signals-values-unset",
    )
    _require(
        policy != "operator-reviewed" or isinstance(signals.get("values"), Mapping),
        "content-signals-values-required",
    )
    _scan_safe_text(signals, "content-signals")


def _validate_budgets(budgets: object) -> None:
    _require(isinstance(budgets, Mapping), "readiness-budgets-invalid")
    _require(
        not set(budgets) - {"curated_chars", "summary_chars", "full_chars"},
        "readiness-budgets-invalid",
    )
    for key, limit in (
        ("curated_chars", 32_000),
        ("summary_chars", 1_200),
        ("full_chars", 500_000),
    ):
        number = budgets.get(key, 0 if key == "full_chars" else None)
        _require(
            type(number) is int and 0 <= number <= limit,
            "readiness-budgets-invalid",
        )
        _require(
            key == "full_chars" or number >= 1,
            "readiness-budgets-invalid",
        )


def _validate_readiness_input(
    value: Mapping[str, Any], schema: Mapping[str, Any]
) -> dict[str, Any]:
    required = _validate_schema(schema)
    _require(
        set(value) == required and value.get("schema_version") == SCHEMA_VERSION,
        "readiness-schema-mismatch",
    )
    kind = _validate_project_and_applicability(value)
    _validate_standards(value.get("standards"))
    signals = value.get("content_signals")
    _validate_content_signals(signals)
    _validate_budgets(value.get("budgets"))
    capabilities = value.get("capabilities")
    _require(
        isinstance(capabilities, Mapping) and set(capabilities) == CAPABILITY_KEYS,
        "capabilities-invalid",
    )
    for name, raw in capabilities.items():
        _validate_capability_entry(name, raw, kind)
    _scan_safe_text(value, "readiness")
    return {
        "schema_version": SCHEMA_VERSION,
        "content_signals": json.loads(json.dumps(signals, sort_keys=True)),
    }


def _validate_served_capability(
    name: str, raw: Mapping[str, Any], kind: str
) -> None:
    _require(kind != "library", "library-capability-unsupported")
    _require(kind != "docs-only", "docs-only-served-capability-unsupported")
    _require(
        isinstance(raw.get("artifact"), str), "capability-authority-required"
    )
    for field, expected in OAUTH_METADATA_FIELDS.items():
        _require(
            field not in raw or raw[field] == expected,
            f"{field}-metadata-unbound",
        )
    endpoint = raw.get("endpoint")
    if endpoint is not None:
        _public_url(endpoint, f"{name}-endpoint")
    if name in SURFACE_TRANSPORTS:
        _validate_surface_reachability(name, raw)
    _scan_safe_text(raw, f"{name}-capability")


def _validate_capability_entry(name: str, raw: object, kind: str) -> None:
    """Apply the universal-skills generator's capability-entry contract."""

    _require(
        isinstance(raw, Mapping) and isinstance(raw.get("applicable"), bool),
        "capability-entry-invalid",
    )
    if name == "skills":
        allowed = {"applicable", "path"}
    elif name == "api":
        allowed = {"applicable", "artifact", "endpoint", *OAUTH_METADATA_FIELDS}
    else:
        allowed = {
            "applicable",
            "artifact",
            "endpoint",
            *OAUTH_METADATA_FIELDS,
            *TRANSPORT_KEYS,
        }
    _require(not set(raw) - allowed, "capability-entry-invalid")
    applicable = raw["applicable"]
    if not applicable:
        _require(
            set(raw) == {"applicable"}, "capability-entry-inapplicable-data"
        )
        return
    if name == "skills":
        _require(
            set(raw) == {"applicable", "path"}
            and isinstance(raw.get("path"), str),
            "skills-path-required",
        )
        return
    _validate_served_capability(name, raw, kind)


def normalized_capabilities(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    """Project declarations onto the generated manifest capability shape."""

    projected: dict[str, Any] = {}
    for name, raw in capabilities.items():
        entry: dict[str, Any] = {"applicable": raw["applicable"]}
        for field in ("artifact", "path", "transport", "reachability"):
            if isinstance(raw.get(field), str):
                entry[field] = raw[field]
        projected[name] = entry
    return projected
