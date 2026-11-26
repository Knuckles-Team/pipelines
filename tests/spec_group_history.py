"""The ``spec`` group as the recorded consumer evidence saw it.

The immutable consumer-train fixtures record the members of the group when they were taken.
``contract-coverage`` joined the group afterwards (PIPE-GATES-R034.3), so a test that compares
recorded evidence with the group compares it with the group of that time, not the live tuple.
"""

from __future__ import annotations

from pipelines_hooks.cli import GROUPS

LATER_MEMBERS = frozenset({"contract-coverage"})
HISTORIC_SPEC_GROUP = [member for member in GROUPS["spec"] if member not in LATER_MEMBERS]
