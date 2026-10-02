"""Digest handoff and consumer-manifest verification (FR-4).

Produce the qualified digest mapping from a finished release run, and check
that a consumer manifest's declared workload references exactly match it.
This only reads and reports; it never edits a consumer manifest -- the
deployment owner applies reviewed, digest-pinned manifests.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .models import ReleaseRun

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def verify_consumer_manifest(run: ReleaseRun, declared: Mapping[str, str]) -> list[str]:
    """One message per workload reference that is not yet safe to mark ready."""
    mapping = run.digest_mapping()
    return [
        message
        for component_id, declared_ref in declared.items()
        if (message := _mismatch(mapping, component_id, declared_ref))
    ]


def _mismatch(mapping: Mapping[str, str], component_id: str, declared_ref: str) -> str:
    if component_id not in mapping:
        return f"{component_id}: not part of the qualified release"
    qualified_digest = mapping[component_id]
    if declared_ref == qualified_digest:
        return ""
    kind = "floating tag" if not _DIGEST_RE.match(declared_ref) else "digest mismatch"
    return f"{component_id}: {kind} ({declared_ref!r} does not match the qualified digest {qualified_digest!r})"
