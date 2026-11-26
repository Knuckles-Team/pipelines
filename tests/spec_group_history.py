"""The members of the ``spec`` grouped check that the frozen consumer evidence recorded.

The consumer-train evidence files are historical measurements. They recorded the group before
``ingest-worker-policy`` joined it (PIPE-GATES-R018), so they compare against this constant, not
against the live group.
"""

from __future__ import annotations

HISTORICAL_SPEC_GROUP = ("spec-standard", "plan-conformance", "spec-decomposition", "spec-status", "spec-trailers")
