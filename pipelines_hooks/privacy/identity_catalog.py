"""Load the operator-owned prohibited-identity catalog (bounded, versioned JSON).

The catalog lives outside every repository (it names what must not appear in
one). Its format is ``{"version": "...", "identities": ["name", ...]}`` with
ASCII-letter identities of 2..64 characters.
"""

from __future__ import annotations

import json
from pathlib import Path

MAX_CATALOG_BYTES = 64 * 1024


class IdentityPolicyError(ValueError):
    """The external policy or scanned input violates a bounded contract."""


def _validated_identity(identity: object) -> bytes:
    if not isinstance(identity, str) or not identity.isascii() or not identity.isalpha():
        raise IdentityPolicyError("identity catalog entries must be ASCII letters")
    encoded = identity.casefold().encode("ascii")
    if not 2 <= len(encoded) <= 64:
        raise IdentityPolicyError("identity catalog entry length is outside 2..64")
    return encoded


def validated_terms(raw: object) -> tuple[bytes, ...]:
    if not isinstance(raw, dict) or set(raw) != {"version", "identities"}:
        raise IdentityPolicyError("identity catalog must contain version and identities")
    if not isinstance(raw["version"], str) or not raw["version"].strip():
        raise IdentityPolicyError("identity catalog version must be non-empty")
    identities = raw["identities"]
    if not isinstance(identities, list) or not identities:
        raise IdentityPolicyError("identity catalog identities must be a non-empty list")
    return tuple(sorted({_validated_identity(identity) for identity in identities}))


def load_identity_catalog(path: Path) -> tuple[bytes, ...]:
    """The catalog's identities; oversized or malformed input raises."""
    with path.open("rb") as stream:
        payload = stream.read(MAX_CATALOG_BYTES + 1)
    if len(payload) > MAX_CATALOG_BYTES:
        raise IdentityPolicyError("identity catalog exceeds the size limit")
    try:
        return validated_terms(json.loads(payload))
    except json.JSONDecodeError as exc:
        raise IdentityPolicyError("identity catalog is not valid JSON") from exc
