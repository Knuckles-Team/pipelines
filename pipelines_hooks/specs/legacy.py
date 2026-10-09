"""Legacy ``merged_head`` evidence already recorded in a committed status.json.

New landings use commit trailers only (git_log.landing_commits); this is a
frozen list for status.json files written before the trailer convention.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable

_SHA_RE = re.compile(r"[0-9a-f]{40}")


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


def legacy_landings(status: dict, reachable: Callable[[str], bool]) -> dict[str, list[str]]:
    """requirement ID -> frozen pre-trailer commit SHAs still reachable from head."""
    out: dict[str, list[str]] = defaultdict(list)
    for requirement in _requirement_dicts(status):
        out[requirement.get("id", "")].extend(sha for sha in _merged_head_shas(requirement) if reachable(sha))
    return out
