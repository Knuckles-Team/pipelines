"""Compare generated spec status with the engine's served state (PIPE-CONNSPEC-R009).

The engine derives the same row states from its own records and serves them
through the arbora ``spec.status`` operation as ``{"rows": [{"id", "state"}]}``.
This module is the only reader of that state, over plain HTTP, and returns the
row IDs on which the two answers differ. An unconfigured endpoint means no
comparison; an unreachable or malformed endpoint is a gate that cannot run.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

MAX_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 15


def generated_states(generated: Mapping[Path, dict]) -> dict[str, str]:
    """Row ID -> delivery state over every generated status document."""
    return {
        requirement["id"]: requirement["delivery_state"].upper()
        for document in generated.values()
        for requirement in document["requirements"]
    }


def engine_states(endpoint: str) -> dict[str, str]:
    """Row ID -> state read from the served ``spec.status`` answer at ``endpoint``."""
    if urllib.parse.urlsplit(endpoint).scheme not in ("http", "https"):
        raise CannotRun(f"spec-status: engine endpoint must be an http or https URL, got {endpoint!r}")
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"}, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            body = response.read(MAX_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise CannotRun(f"spec-status: engine state unreachable: {exc}") from None
    if len(body) > MAX_BYTES:
        raise CannotRun(f"spec-status: engine state exceeds {MAX_BYTES} bytes")
    try:
        rows = json.loads(body)["rows"]
        return {row["id"]: str(row["state"]).upper() for row in rows}
    except (ValueError, KeyError, TypeError):
        raise CannotRun("spec-status: engine state is not a {'rows': [{'id', 'state'}]} document") from None


def compare_engine_state(generated: Mapping[Path, dict], endpoint: str) -> list[str]:
    """The sorted row IDs whose state differs, or that only one side holds."""
    ours = generated_states(generated)
    theirs = engine_states(endpoint)
    return sorted(rid for rid in ours.keys() | theirs.keys() if ours.get(rid) != theirs.get(rid))
