"""Rule 6 of the state-machine hooks: algebraic checks over a declared table.

A declared table is a sparse matrix: rows are states, columns are events, and a
cell holds the target state or nothing. A missing cell is a refusal. Five
checks, each linear in the size of the table, prove the matrix well formed:
reachability from ``INITIAL``, no non-terminal dead end, absorbing terminal
states, one target per cell, and a refusal test for every missing cell. A
machine declared by a function has no matrix and gets none of them.
"""

from __future__ import annotations

from collections import deque

from pipelines_hooks.code.state_machine_model import Finding, Machine

Cells = dict[tuple[str, str], set[str]]


def algebra_findings(machine: Machine) -> list[Finding]:
    """The rule 6 findings of one machine (none without a table)."""
    if machine.table is None:
        return []
    cells = _cells(machine)
    states = machine.all_states()
    found = _reachability(machine, cells, states) + _shape(machine, cells, states)
    return found + _untested_refusals(machine, cells, states)


def _finding(machine: Machine, code: str, detail: str) -> Finding:
    return Finding(machine.file, machine.line, machine.type_name, code, detail)


def _cells(machine: Machine) -> Cells:
    cells: Cells = {}
    for source, event, target in machine.edges:
        cells.setdefault((source, event), set()).add(target)
    return cells


def _reachability(machine: Machine, cells: Cells, states: list[str]) -> list[Finding]:
    """``SM-NO-INITIAL``, else ``SM-UNREACHABLE`` for each state no path from it reaches."""
    if machine.initial is None:
        return [_finding(machine, "SM-NO-INITIAL", f"table {machine.table} declares no INITIAL")]
    seen = {machine.initial}
    queue = deque([machine.initial])
    while queue:
        state = queue.popleft()
        for (source, _), targets in cells.items():
            for target in targets if source == state else ():
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
    return [_finding(machine, "SM-UNREACHABLE", f"state {s}") for s in states if s not in seen]


def _shape(machine: Machine, cells: Cells, states: list[str]) -> list[Finding]:
    """Dead ends, terminal states with an exit, and cells with two targets."""
    sources = {source for source, _ in cells}
    found = [
        _finding(machine, "SM-DEAD-END", f"state {s}")
        for s in states
        if s not in sources and s not in machine.terminals
    ]
    found += [_finding(machine, "SM-TERMINAL-NOT-ABSORBING", f"state {s}") for s in machine.terminals if s in sources]
    found += [
        _finding(machine, "SM-NONDETERMINISTIC", f"from={source} event={event} to={','.join(sorted(targets))}")
        for (source, event), targets in cells.items()
        if len(targets) > 1
    ]
    return found


def _untested_refusals(machine: Machine, cells: Cells, states: list[str]) -> list[Finding]:
    """``SM-UNTESTED-REFUSAL`` for each missing cell that no refusal test names."""
    if not machine.bound or machine.product_refusal_test:
        return []
    events = list(dict.fromkeys(event for _, event, _ in machine.edges))
    return [
        _finding(machine, "SM-UNTESTED-REFUSAL", f"from={state} event={event}")
        for state in states
        for event in events
        if (state, event) not in cells and (state, event) not in machine.refused_cells
    ]
