"""The records the state-machine hooks share: ``Machine``, ``Finding`` and ``Rule``.

A reader (Python or Rust) builds one ``Machine`` per type; ``bind_tests`` fills
the test bindings; ``findings`` turns the record into typed findings. The two
languages fill the same fields, so one rule set serves both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

#: Field names that hold a lifecycle.
STATUS_FIELDS = ("status", "state", "phase", "stage", "lifecycle")
#: Nullable timestamps that encode a lifecycle step.
LIFECYCLE_TIMESTAMPS = frozenset(
    {
        "started_at",
        "finished_at",
        "completed_at",
        "cancelled_at",
        "failed_at",
        "closed_at",
        "ended_at",
        "stopped_at",
        "expired_at",
        "archived_at",
        "resolved_at",
        "claimed_at",
    }
)


class Rule(IntEnum):
    """The rule each finding code belongs to (plan.md, "Finding codes")."""

    MULTI_ASSIGN = 1
    STRING_STATUS = 2
    LIFECYCLE_FLAGS = 3
    TESTS = 4
    NO_DECLARATION = 5
    ALGEBRA = 6


#: Finding code -> rule.
CODES: dict[str, Rule] = {
    "SM-MULTI-ASSIGN": Rule.MULTI_ASSIGN,
    "SM-STRING-STATUS": Rule.STRING_STATUS,
    "SM-LIFECYCLE-FLAGS": Rule.LIFECYCLE_FLAGS,
    "SM-UNTESTED-EDGE": Rule.TESTS,
    "SM-NO-REFUSAL-TEST": Rule.TESTS,
    "SM-NO-DECLARATION": Rule.NO_DECLARATION,
    "SM-UNREACHABLE": Rule.ALGEBRA,
    "SM-DEAD-END": Rule.ALGEBRA,
    "SM-TERMINAL-NOT-ABSORBING": Rule.ALGEBRA,
    "SM-NONDETERMINISTIC": Rule.ALGEBRA,
    "SM-UNTESTED-REFUSAL": Rule.ALGEBRA,
    "SM-NO-INITIAL": Rule.ALGEBRA,
}


@dataclass(frozen=True)
class Site:
    """One place in source: an assignment of the status field or a string compare."""

    file: str
    line: int
    function: str


@dataclass(frozen=True)
class Finding:
    """One violation, printed as ``<file>:<line> <type> <code> rule <n>``."""

    file: str
    line: int
    type_name: str
    code: str
    detail: str = ""

    @property
    def rule(self) -> int:
        return int(CODES[self.code])

    def render(self) -> str:
        text = f"{self.file}:{self.line} {self.type_name} {self.code} rule {self.rule}"
        return f"{text}: {self.detail}" if self.detail else text


Edge = tuple[str, str, str]


@dataclass
class Machine:
    """One type whose lifecycle a status field, flags or timestamps carry."""

    language: str
    file: str
    line: int
    type_name: str
    #: The status field, its declared type text, and whether that type is an
    #: ``enum`` or a ``string`` (``str``, ``String``, an integer or ``Literal``).
    status_field: str | None = None
    status_type: str | None = None
    status_kind: str = ""
    #: Declared states (the enum members) and the declared table.
    states: tuple[str, ...] = ()
    table: str | None = None
    edges: tuple[Edge, ...] = ()
    #: The ``INITIAL`` and ``TERMINAL``/``TERMINALS`` constants beside the table.
    initial: str | None = None
    terminals: tuple[str, ...] = ()
    #: The one transition function and the refusal type it raises or returns.
    function: str | None = None
    refusal: str | None = None
    #: True when the declaration was resolved from the status enum, which lives
    #: in another file: the holder type then has one commit function of its own.
    via_enum: bool = False
    assigners: list[Site] = field(default_factory=list)
    string_compares: list[Site] = field(default_factory=list)
    #: Lifecycle booleans and nullable lifecycle timestamps on the type.
    flags: tuple[str, ...] = ()
    #: Filled by ``bind_tests``: whether binding ran, the edges without a test
    #: as ``(from, event)``, and whether a refusal test names ``refusal``.
    bound: bool = False
    untested_edges: list[tuple[str, str]] = field(default_factory=list)
    refusal_tested: bool = False
    #: Missing cells ``(state, event)`` a refusal test names, and whether one
    #: refusal test iterates the whole state-by-event product of the table.
    refused_cells: set[tuple[str, str]] = field(default_factory=set)
    product_refusal_test: bool = False

    def all_states(self) -> list[str]:
        """Declared states, then table states, then terminal states, without repeats."""
        edge_states = (state for source, _, target in self.edges for state in (source, target))
        return list(dict.fromkeys([*self.states, *edge_states, *self.terminals]))

    @property
    def declared(self) -> bool:
        """A declared machine has a transition table or a transition function."""
        return self.table is not None or self.function is not None


@dataclass(frozen=True)
class Use:
    """An assignment or string compare of a status field through a receiver."""

    field: str
    kind: str
    site: Site
    receiver: str | None
    module_names: frozenset[str]


def attach(machine: Machine, use: Use) -> None:
    """Record one use on a machine; a compare in a module naming the enum is fine."""
    if use.kind == "assign":
        machine.assigners.append(use.site)
    elif machine.status_kind != "enum" or machine.status_type not in use.module_names:
        machine.string_compares.append(use.site)
