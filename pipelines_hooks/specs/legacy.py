"""Legacy ``merged_head`` evidence already recorded in a committed status.json.

New landings use commit trailers only (git_log.landing_commits); this is a
frozen list for status.json files written before the trailer convention.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_PREFIX_RE = re.compile(r"[0-9a-f]{7,40}")


def _requirement_dicts(status: dict) -> list[dict]:
    requirements = status.get("requirements") or []
    if isinstance(requirements, dict):
        requirements = list(requirements.values())
    return [r for r in requirements if isinstance(r, dict)]


def _merged_head_shas(requirement: dict) -> list[str]:
    return [
        str(evidence["commit"])
        for evidence in requirement.get("evidence") or []
        if isinstance(evidence, dict)
        and evidence.get("kind") == "merged_head"
        and _SHA_RE.fullmatch(str(evidence.get("commit", "")))
    ]


def _landed_in_prefixes(requirement: dict) -> list[str]:
    """Schema v2 carries prior landings forward as ``landed_in`` SHA prefixes."""
    return [
        str(s)
        for s in requirement.get("landed_in") or []
        if _PREFIX_RE.fullmatch(str(s))
    ]


def legacy_landings(
    status: dict, resolve: Callable[[str], str | None]
) -> dict[str, list[str]]:
    """requirement ID -> recorded landing SHAs (v1 ``merged_head`` evidence or v2 ``landed_in``)
    that ``resolve`` maps to a live (reachable, not reverted) full SHA. Carrying v2 landings
    forward keeps regeneration idempotent."""
    out: dict[str, list[str]] = defaultdict(list)
    for requirement in _requirement_dicts(status):
        recorded = _merged_head_shas(requirement) + _landed_in_prefixes(requirement)
        live = (resolve(sha) for sha in recorded)
        out[requirement.get("id", "")].extend(sorted({sha for sha in live if sha}))
    return out
