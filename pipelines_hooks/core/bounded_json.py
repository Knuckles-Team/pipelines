"""Read a small, size-bounded JSON policy file without trusting its length."""

from __future__ import annotations

import json
from pathlib import Path


def read_bounded_json(path: Path, limit: int, what: str, error: type[Exception]) -> object:
    """The decoded payload; an oversized or undecodable file raises ``error``."""
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise error(f"{what} exceeds the size limit")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise error(f"{what} is not valid JSON") from exc
