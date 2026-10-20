"""The gate set partition declared in the shipped ``gate_sets.toml``.

The eight blocking gates of the gate standard (reference/gate-standard.md)
split into the pre-land fast set and the post-land full set. The split is
declared once, in the shipped declaration, and every reader -- the
partition test, the gate-set runner and the landing policy -- loads it
through this module. A gate moves between sets only by changing the
declaration under review.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

#: The gate standard's eight blocking checks, by name.
BLOCKING_GATES = (
    "format",
    "hygiene",
    "secrets",
    "types",
    "tests-fast",
    "spec",
    "tests",
    "supply-chain",
)

VERSION = 1


@dataclass(frozen=True)
class GateSets:
    """One validated partition of the blocking gates."""

    blocking: tuple[str, ...]
    fast: tuple[str, ...]
    full: tuple[str, ...]


def declaration_path() -> Path:
    """The shipped declaration, beside the gate modules."""
    return Path(__file__).with_name("gate_sets.toml")


def _string_list(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise CannotRun(f"gate-sets: {key} must be a list of gate names")
    if len(set(value)) != len(value):
        raise CannotRun(f"gate-sets: {key} declares a gate twice")
    return tuple(value)


def load_gate_sets(path: Path) -> GateSets:
    """One validated partition; any deviation from the standard is a configuration error.

    The blocking set must be exactly the eight standard gates: a missing
    gate or a ninth gate fails the load. The sides must partition it:
    disjoint, and their union the whole blocking set, so the full set is
    the fast set's complement.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"gate-sets: cannot read {path}: {exc}") from exc
    if set(raw) != {"version", "blocking", "fast", "full"}:
        raise CannotRun(f"gate-sets: expected exactly version, blocking, fast, full; found {sorted(raw)}")
    if raw["version"] != VERSION:
        raise CannotRun(f"gate-sets: unsupported version {raw['version']!r}")
    blocking = _string_list(raw["blocking"], "blocking")
    fast = _string_list(raw["fast"], "fast")
    full = _string_list(raw["full"], "full")
    missing = sorted(set(BLOCKING_GATES) - set(blocking))
    if missing:
        raise CannotRun(f"gate-sets: the blocking set is missing {', '.join(missing)}")
    extra = sorted(set(blocking) - set(BLOCKING_GATES))
    if extra:
        raise CannotRun(f"gate-sets: the blocking set declares the undeclared gate(s) {', '.join(extra)}")
    outside = sorted((set(fast) | set(full)) - set(blocking))
    if outside:
        raise CannotRun(f"gate-sets: {', '.join(outside)} is not a blocking gate")
    overlap = sorted(set(fast) & set(full))
    if overlap:
        raise CannotRun(f"gate-sets: {', '.join(overlap)} sits in both the fast and the full set")
    uncovered = sorted(set(blocking) - set(fast) - set(full))
    if uncovered:
        raise CannotRun(f"gate-sets: fast plus full leaves {', '.join(uncovered)} in no set")
    return GateSets(blocking=blocking, fast=fast, full=full)


def published_sets() -> GateSets:
    """The shipped partition, loaded through the one loader."""
    return load_gate_sets(declaration_path())
