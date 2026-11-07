"""The shared rule set of the state-machine hooks: ``findings(machine)``.

Pure functions over ``Machine``; no file reads. Rules 1 to 5 are in plan.md
("Explicit state machines"); rule 6, the algebraic checks, is
``state_machine_algebra.algebra_findings``.
"""

from __future__ import annotations

from pipelines_hooks.code.state_machine_algebra import algebra_findings
from pipelines_hooks.code.state_machine_model import Finding, Machine, Site


def findings(machine: Machine) -> list[Finding]:
    """Every finding of rules 1 to 6 for one machine."""
    return [
        *_multi_assign(machine),
        *_string_status(machine),
        *_lifecycle_flags(machine),
        *_untested(machine),
        *_no_declaration(machine),
        *algebra_findings(machine),
    ]


def _finding(
    machine: Machine, code: str, line: int | None = None, detail: str = "", file: str | None = None
) -> Finding:
    return Finding(file or machine.file, machine.line if line is None else line, machine.type_name, code, detail)


def _first_sites(sites: list[Site]) -> dict[tuple[str, str], Site]:
    """The first site of each assigning function, keyed by file and function."""
    first: dict[tuple[str, str], Site] = {}
    for site in sorted(sites, key=lambda s: (s.file, s.line)):
        first.setdefault((site.file, site.function), site)
    return first


def _multi_assign(machine: Machine) -> list[Finding]:
    """Rule 1: the status is assigned outside the one transition function."""
    first = _first_sites(machine.assigners)
    if machine.function is not None:
        stray = [site for (_, function), site in first.items() if function != machine.function]
    else:
        stray = list(first.values()) if len(first) >= 2 else []
    return [
        _finding(machine, "SM-MULTI-ASSIGN", site.line, f"assigned in {site.function}", site.file) for site in stray
    ]


def _string_status(machine: Machine) -> list[Finding]:
    """Rule 2: a string-typed status field, or a string-literal compare of it."""
    found = [_finding(machine, "SM-STRING-STATUS", detail=f"{machine.status_field}: {machine.status_type}")]
    found = found if machine.status_kind == "string" else []
    found += [
        _finding(machine, "SM-STRING-STATUS", site.line, f"string compare in {site.function}", site.file)
        for site in machine.string_compares
    ]
    return found


def _lifecycle_flags(machine: Machine) -> list[Finding]:
    """Rule 3: two or more lifecycle flags or timestamps on one type."""
    if len(machine.flags) < 2:
        return []
    return [_finding(machine, "SM-LIFECYCLE-FLAGS", detail=", ".join(machine.flags))]


def _untested(machine: Machine) -> list[Finding]:
    """Rule 4: a declared machine without a test per edge and a refusal test."""
    if not (machine.declared and machine.bound):
        return []
    found = [
        _finding(machine, "SM-UNTESTED-EDGE", detail=f"from={source} event={event}")
        for source, event in machine.untested_edges
    ]
    if not machine.refusal_tested:
        found.append(_finding(machine, "SM-NO-REFUSAL-TEST", detail=f"refusal {machine.refusal or '?'}"))
    return found


def _no_declaration(machine: Machine) -> list[Finding]:
    """Rule 5: an enum-typed status field with no table and no function."""
    if machine.status_kind != "enum" or machine.declared:
        return []
    return [_finding(machine, "SM-NO-DECLARATION", detail=f"{machine.status_field}: {machine.status_type}")]
