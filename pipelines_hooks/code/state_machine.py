"""state-machine-shape / state-machine-census: report implicit state machines.

``state-machine-shape`` (pre-commit and pre-push) reads every source and test
file of the declared paths so it resolves types, assigners and tests, and
reports a finding only for a type declared in, or assigned from, a changed
file. A use is counted against the type its receiver resolves to; one that
does not resolve is a single ``<unresolved>`` finding (``SM-UNRESOLVED-RECEIVER``),
never one per type sharing the field name. ``state-machine-census`` (manual)
reports the whole tree, with no baseline and no allowance. Each finding line is
``<file>:<line> <type> <code> rule <n>``. Policy:
``[tool.pipelines_hooks.state_machine]`` with ``paths``, ``exclude``,
``languages`` and ``mode`` (``staged`` prints findings and exits 0,
``blocking`` exits 1 on any finding). Exit 2: the gate could not run.
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Callable
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from pipelines_hooks.code import state_machine_py, state_machine_rs
from pipelines_hooks.code.state_machine_model import UNRESOLVED_TYPE, Finding, Machine, Use, attach
from pipelines_hooks.code.state_machine_rules import findings
from pipelines_hooks.code.state_machine_tests import bind_tests
from pipelines_hooks.core.baseref import upstream_base
from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, nul_split, repo_root, staged_paths
from pipelines_hooks.core.tracked import tracked_paths

SUFFIXES = {"python": ".py", "rust": ".rs"}


@dataclass(frozen=True)
class Policy:
    paths: tuple[str, ...]
    exclude: tuple[str, ...]
    languages: tuple[str, ...]
    mode: str


def _load_policy(root: Path) -> Policy:
    """``[tool.pipelines_hooks.state_machine]``; a missing table cannot run."""
    section = load_config(root).section("state_machine")
    if not section.get("paths"):
        raise CannotRun("[tool.pipelines_hooks.state_machine] declares no paths")
    languages = string_tuple(section.get("languages", ["python", "rust"]), "state_machine.languages")
    mode = section.get("mode", "blocking")
    if set(languages) - set(SUFFIXES) or mode not in {"staged", "blocking"}:
        raise CannotRun("[tool.pipelines_hooks.state_machine] languages must be python/rust and mode staged/blocking")
    exclude = string_tuple(section.get("exclude", []), "state_machine.exclude") if section.get("exclude") else ()
    return Policy(string_tuple(section["paths"], "state_machine.paths"), exclude, languages, mode)


def _is_test(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return "tests" in parts[:-1] or parts[-1].startswith("test_") or parts[-1] == "conftest.py"


def _files(root: Path, policy: Policy) -> tuple[list[str], list[str]]:
    """``(sources, tests)``: tracked files of the policy languages outside ``exclude``."""
    suffixes = tuple(SUFFIXES[language] for language in policy.languages)
    kept = [
        path
        for path in tracked_paths(root)
        if path.endswith(suffixes) and not any(fnmatch(path, pattern) for pattern in policy.exclude)
    ]
    under = [path for path in kept if any(path == p or path.startswith(p.rstrip("/") + "/") for p in policy.paths)]
    tests = [path for path in kept if _is_test(path) or (path.endswith(".rs") and "#[cfg(test)]" in _read(root, path))]
    return [path for path in under if not _is_test(path)], tests


def _read(root: Path, path: str) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc


def _unit(root: Path, path: str) -> str:
    """The crate (nearest ``Cargo.toml``) or top-level package (``__init__.py`` chain) of a file."""
    parent = PurePosixPath(path).parent
    marker = "Cargo.toml" if path.endswith(".rs") else "__init__.py"
    found = str(parent)
    for directory in (parent, *parent.parents):
        if (root / directory / marker).is_file():
            found = str(directory)
            if marker == "Cargo.toml":
                break
    return found


def _parse(path: str, source: str, *, strict: bool = True) -> tuple[list[Machine], list[Use]]:
    if path.endswith(".rs"):
        machines = state_machine_rs.read_rust(path, source, strict=strict)
        return machines, state_machine_rs.loose_sites(path, source, strict=strict)
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise CannotRun(f"{path}: Python source does not parse: {exc.msg}") from exc
    return state_machine_py.read_python(path, tree), state_machine_py.loose_sites(path, tree)


@dataclass(frozen=True)
class Report:
    """The findings of one run, and the Rust files read from an error-recovered tree."""

    findings: list[Finding]
    partial: list[str]


def _resolve_enum_machines(machines: list[Machine], declared: dict[str, Machine]) -> None:
    """Give a type whose status enum owns the machine elsewhere that declaration.

    The enum is matched by name across every scanned source (the holder and the
    machine often sit in different modules or crates). A type that declares a
    machine itself, or whose enum has none anywhere, is left as it is.
    """
    for machine in machines:
        owner = declared.get(machine.status_type or "") if machine.status_kind == "enum" else None
        if owner is None or machine.declared or machine.language != owner.language:
            continue
        machine.table, machine.edges, machine.function, machine.refusal = (
            owner.table,
            owner.edges,
            owner.function,
            owner.refusal,
        )
        machine.initial, machine.terminals, machine.states = owner.initial, owner.terminals, owner.states
        machine.via_enum = True


def _machines(
    root: Path, sources: list[str], must_parse: Callable[[str], bool]
) -> tuple[list[Machine], list[str], list[Finding]]:
    """Read every source; attach each use to the one type its receiver resolves to.

    A file ``must_parse`` names cannot run on a parse error. Any other Rust file
    is read from its error-recovered tree and listed as partial; any other
    Python file with a syntax error is skipped. A use whose receiver does not
    resolve, or names a type declared twice in its unit, becomes one
    ``<unresolved>`` finding; it is never attached to every type sharing the field.
    """
    machines: list[Machine] = []
    loose: list[Use] = []
    partial: list[str] = []
    declared: dict[str, Machine] = {}
    for path in sources:
        source = _read(root, path)
        try:
            found, uses = _parse(path, source)
        except CannotRun:
            if must_parse(path):
                raise
            if not path.endswith(".rs"):
                continue
            found, uses = _parse(path, source, strict=False)
            partial.append(path)
        machines += found
        loose += uses
        if path.endswith(".rs"):
            declared |= _enum_declarations(path, source)
    _resolve_enum_machines(machines, declared)
    return machines, partial, _attach_uses(root, machines, loose)


def _attach_uses(root: Path, machines: list[Machine], loose: list[Use]) -> list[Finding]:
    """Attach each non-``self`` use to its resolved type; return the unresolved ones as findings."""
    by_name: dict[str, list[Machine]] = {}
    by_field: dict[tuple[str, str | None], list[Machine]] = {}
    for machine in machines:
        by_name.setdefault(machine.type_name, []).append(machine)
        by_field.setdefault((_unit(root, machine.file), machine.status_field), []).append(machine)
    unresolved: dict[tuple[str, int, str, str], Finding] = {}
    for use in loose:
        unit = _unit(root, use.site.file)
        peers = [m for m in by_field.get((unit, use.field), []) if m.status_field == use.field]
        if not peers:
            continue
        reason = "receiver type unknown"
        if use.receiver is not None:
            named = [m for m in by_name.get(use.receiver, []) if m in peers]
            if not named or any(m.file == use.site.file for m in named):
                continue  # not a type with this field, or the reader already attached it
            if len(named) == 1:
                attach(named[0], use)
                continue
            reason = f"type {use.receiver} is declared {len(named)} times in the unit"
        elif use.kind == "compare" and all(_enum_compare_ok(m, use) for m in peers):
            continue
        key = (use.site.file, use.site.line, use.field, use.kind)
        detail = f"{use.kind} of .{use.field} in {use.site.function}: {reason}"
        unresolved.setdefault(
            key, Finding(use.site.file, use.site.line, UNRESOLVED_TYPE, "SM-UNRESOLVED-RECEIVER", detail)
        )
    return list(unresolved.values())


def _enum_compare_ok(machine: Machine, use: Use) -> bool:
    """A compare in a module that names the machine's status enum is not a string compare."""
    return machine.status_kind == "enum" and machine.status_type in use.module_names


def _enum_declarations(path: str, source: str) -> dict[str, Machine]:
    try:
        return state_machine_rs.enum_declarations(path, source)
    except CannotRun:
        return state_machine_rs.enum_declarations(path, source, strict=False)


def _changed(root: Path) -> set[str]:
    """Staged paths, plus the diff against the upstream base at push time."""
    changed = set(staged_paths(root))
    base = upstream_base(root, None)
    if base:
        changed |= set(nul_split(git_text(root, ("diff", "--name-only", "-z", "--diff-filter=ACMR", base))))
    return changed


def _touches(machine: Machine, changed: set[str]) -> bool:
    return machine.file in changed or any(site.file in changed for site in machine.assigners)


def _must_parse_in_census(path: str) -> bool:
    """The census reads every file: Python must parse, Rust may be partial."""
    return not path.endswith(".rs")


def run(root: Path, *, census: bool) -> Report:
    """Every finding of the census, or the findings of the types the change touches."""
    policy = _load_policy(root)
    sources, tests = _files(root, policy)
    changed = set() if census else _changed(root)
    machines, partial, unresolved = _machines(root, sources, _must_parse_in_census if census else changed.__contains__)
    test_files = [(path, _read(root, path)) for path in tests]
    for machine in machines:
        bind_tests(machine, test_files)
    kept = machines if census else [machine for machine in machines if _touches(machine, changed)]
    stray = [finding for finding in unresolved if census or finding.file in changed]
    return Report([*(finding for machine in kept for finding in findings(machine)), *stray], partial)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="state-machine-shape", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--census", action="store_true", help="report the whole tree (state-machine-census)")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    report = run(root, census=args.census)
    for finding in report.findings:
        print(finding.render())
    name = "state-machine-census" if args.census else "state-machine-shape"
    for path in report.partial:
        print(f"{name}: {path}: partial parse (the Rust grammar could not parse part of this file)")
    print(f"{name}: {len(report.findings)} finding(s), {len(report.partial)} partially parsed file(s)")
    return 1 if report.findings and _load_policy(root).mode == "blocking" else 0
