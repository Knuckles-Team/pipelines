"""Validation for declared MCP and A2A surface reachability."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .constants import (
    REACHABILITY_VALUES,
    SERVICE_IDENTITY_PATTERN,
    SURFACE_TRANSPORTS,
    TRANSPORT_KEYS,
)
from .errors import _fail


def _validate_transport_declaration(
    name: str, raw: Mapping[str, Any]
) -> tuple[Any, Any] | None:
    if not TRANSPORT_KEYS & set(raw):
        return None
    transport = raw.get("transport")
    reachability = raw.get("reachability")
    if transport is None or reachability is None:
        _fail("capability-transport-incomplete")
    if transport not in SURFACE_TRANSPORTS[name]:
        _fail("capability-transport-unsupported")
    if reachability not in REACHABILITY_VALUES:
        _fail("capability-reachability-invalid")
    return transport, reachability


def _validate_transport_reachability(transport: Any, reachability: Any) -> None:
    if (transport == "stdio") != (reachability == "local"):
        _fail("capability-reachability-inconsistent")


def _validate_public_reachability(endpoint: Any, identity: Any) -> None:
    if identity is not None:
        _fail("capability-reachability-inconsistent")
    if not isinstance(endpoint, str):
        _fail("capability-endpoint-required")


def _validate_non_public_reachability(
    reachability: Any, endpoint: Any, identity: Any
) -> None:
    if endpoint is not None:
        _fail("capability-reachability-inconsistent")
    if reachability == "local":
        if identity is not None:
            _fail("capability-reachability-inconsistent")
        return
    if identity is None:
        _fail("capability-service-identity-required")
    if (
        not isinstance(identity, str)
        or len(identity) > 253
        or not SERVICE_IDENTITY_PATTERN.fullmatch(identity)
    ):
        _fail("capability-service-identity-invalid")


def _validate_surface_reachability(name: str, raw: Mapping[str, Any]) -> None:
    """Validate how a served MCP/A2A surface is actually reached.

    A declaration without ``transport``/``reachability`` keeps the original
    v1 meaning (an optional ``endpoint``, validated as public HTTPS when
    present). Once either is declared, both are required and must agree:
    ``local`` is MCP ``stdio`` with no endpoint or service identity;
    ``in-cluster`` is a network transport with a ``service_identity`` and no
    public endpoint; ``public`` is a network transport with a verifiable
    public HTTPS ``endpoint``.
    """

    declaration = _validate_transport_declaration(name, raw)
    if declaration is None:
        return
    transport, reachability = declaration
    _validate_transport_reachability(transport, reachability)
    endpoint = raw.get("endpoint")
    identity = raw.get("service_identity")
    if reachability == "public":
        _validate_public_reachability(endpoint, identity)
        return
    _validate_non_public_reachability(reachability, endpoint, identity)
