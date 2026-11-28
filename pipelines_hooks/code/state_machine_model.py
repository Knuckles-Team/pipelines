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
#: Functions that build an instance; a status set in one is set at construction.
CONSTRUCTORS = frozenset({"__init__", "__post_init__", "__new__", "model_post_init"})
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
    UNRESOLVED = 7


#: Finding code -> rule.
CODES: dict[str, Rule] = {
    "SM-MULTI-ASSIGN": Rule.MULTI_ASSIGN,
    "SM-STRING-STATUS": Rule.STRING_STATUS,
    "SM-STRING-VALUE": Rule.STRING_STATUS,
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
    "SM-UNRESOLVED-RECEIVER": Rule.UNRESOLVED,
}


@dataclass(frozen=True)
class Site:
    """One place in source: an assignment of the status field or a string compare."""

    file: str
    line: int
    function: str
    #: The function whose result an assignment stores (``x.status = transition(..)``), if any.
    through: str = ""
    #: ``recompute`` when the write replaces the status (``model_copy``, ``replace``) with a
    #: value computed in the same function and the function never compares that type's status.
    how: str = ""


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
    #: The machine-definition type (a static of it is the table) of a declaration.
    def_type: str | None = None
    #: True when the type is immutable by declaration (a frozen dataclass or model).
    frozen: bool = False
    #: True when the status type is called an enum only by its name suffix; the
    #: hook settles it against the enums and literal unions that exist.
    guessed_enum: bool = False
    #: Set by ``settle_immutable`` once the hook has attached every use: the
    #: status is never assigned outside construction. Hand-built records stay False.
    immutable: bool = False
    assigners: list[Site] = field(default_factory=list)
    string_compares: list[Site] = field(default_factory=list)
    #: Lifecycle booleans and nullable lifecycle timestamps on the type.
    flags: tuple[str, ...] = ()
    #: The flags some function other than a constructor assigns (PIPE-GATES-R086.27).
    assigned_flags: set[str] = field(default_factory=set)
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
    def is_value(self) -> bool:
        """An undeclared type whose status is set only at construction is a value, not a lifecycle."""
        return self.status_field is not None and not self.declared and (self.immutable or self.derived)

    @property
    def derived(self) -> bool:
        """A derived rollup (PIPE-GATES-R086.28): every write of the status replaces it with a recomputed value."""
        return (
            self.status_field is not None
            and not self.declared
            and bool(self.assigners)
            and all(site.how == "recompute" for site in self.assigners)
        )

    def settle_flags(self) -> None:
        """Called once every use is attached: a Python flag no function assigns after construction is a kind, not a lifecycle."""
        if self.language == "python":
            self.flags = tuple(flag for flag in self.flags if flag in self.assigned_flags)

    def settle_immutable(self) -> None:
        """Called once every use is attached: set ``immutable`` when no function but a constructor assigns."""
        self.immutable = all(site.function.rsplit(".", 1)[-1] in CONSTRUCTORS for site in self.assigners)

    @property
    def declared(self) -> bool:
        """A declared machine has a transition table or a transition function."""
        return self.table is not None or self.function is not None


@dataclass(frozen=True)
class Use:
    """An assignment or string compare of a status field through a receiver.

    ``receiver`` is the type the receiver resolves to (``None`` when it does
    not resolve); ``local`` is true when the receiver is ``self`` or a type
    path, which the reader attaches itself.
    """

    field: str
    kind: str
    site: Site
    receiver: str | None
    module_names: frozenset[str]
    local: bool = False


#: The type name a finding carries when the receiver of a use does not resolve.
UNRESOLVED_TYPE = "<unresolved>"


def attach(machine: Machine, use: Use) -> None:
    """Record one use on a machine; a compare in a module naming the enum is fine."""
    if use.kind == "flag":
        if use.site.function.rsplit(".", 1)[-1] not in CONSTRUCTORS:
            machine.assigned_flags.add(use.field)
    elif use.kind == "assign":
        machine.assigners.append(use.site)
    elif machine.status_kind != "enum" or machine.status_type not in use.module_names:
        machine.string_compares.append(use.site)
