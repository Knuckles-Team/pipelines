"""Check configured static import boundaries in tracked consumer packages.

Two policies share one scan: ``forbidden``/``allowed`` module prefixes
(PIPE-GATES-R009) and an ordered ``layers`` list, most stable first
(PIPE-GATES-R088). This AST check does not resolve dynamic imports or prove runtime isolation.
"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.paths import relative_to_root, under_any
from pipelines_hooks.core.tracked import tracked_paths


def _prefixes(value: object, label: str) -> tuple[str, ...]:
    prefixes = string_tuple(value, label)
    if any(not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", item) for item in prefixes):
        raise CannotRun(f"{label} must contain dotted Python module names")
    return prefixes


def _matches(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            # Include the imported member: `from arbora import client` is legal,
            # but `from arbora import runtime` must not bypass a denied parent.
            for alias in node.names:
                yield node.lineno, node.module + "." + alias.name


def _layers(value: object) -> list[tuple[str, ...]]:
    """The layer order: each entry one unit, or a list of peer units."""
    if not isinstance(value, list):
        raise CannotRun("coupling.layers must be a list of unit names or lists of peer unit names")
    layers = [_prefixes(item if isinstance(item, list) else [item], "coupling.layers") for item in value]
    flat = [unit for layer in layers for unit in layer]
    if len(set(flat)) != len(flat):
        raise CannotRun("coupling.layers names a unit twice")
    return layers


def _unit_name(module: str, depth: int) -> str:
    return ".".join(module.split(".")[: depth + 1])


def _module_name(relative: str, package: str) -> str:
    """Dotted module of a tracked file; the package's last segment is its import name."""
    parts = Path(relative).with_suffix("").parts
    base = len(Path(package).parts) - 1
    parts = parts[base:]
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _layer_imports(tree: ast.AST, module: str, is_package: bool):
    """Every static import with relative forms resolved against ``module``."""
    anchor = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, ()
        elif isinstance(node, ast.ImportFrom):
            base = anchor[: len(anchor) - (node.level - 1)] if node.level else []
            if node.level and len(anchor) < node.level:
                continue
            name = ".".join([*base, *([node.module] if node.module else [])])
            if name:
                yield node.lineno, name, tuple(alias.name for alias in node.names)


def _private_segment(module: str) -> bool:
    return any(part.startswith("_") and not part.startswith("__") for part in module.split(".")[1:])


def _cycle_groups(edges: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected unit groups of more than one unit (iterative Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[list[str]] = []
    counter = 0
    for start in sorted(edges):
        if start in index:
            continue
        work = [(start, iter(sorted(edges[start])))]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, children = work[-1]
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(edges.get(child, ())))))
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    group = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        group.append(member)
                        if member == node:
                            break
                    if len(group) > 1:
                        groups.append(sorted(group))
    return groups


def _layer_findings(parsed: list[tuple[str, str, ast.AST]], layers: list[tuple[str, ...]], depth: int) -> list[str]:
    """Upward imports, private reaches, unlayered units and unit cycles (PIPE-GATES-R088).

    ``parsed`` holds (relative path, dotted module, tree) for each tracked file;
    ``depth`` is the number of segments below the package that name a unit (one).
    """
    rank = {unit: number for number, layer in enumerate(layers) for unit in layer}
    modules = {module for _, module, _ in parsed}
    units = {_unit_name(module, depth) for module in modules}
    findings: list[str] = []
    edges: dict[str, set[str]] = {unit: set() for unit in units}
    edge_site: dict[tuple[str, str], str] = {}
    unlayered: set[str] = set()
    for relative, module, tree in parsed:
        source = _unit_name(module, depth)
        if source not in rank and source not in unlayered:
            unlayered.add(source)
            findings.append(f"{relative}:1: unit {source} is named in no layer")
        is_package = relative.endswith("__init__.py")
        for line, name, members in _layer_imports(tree, module, is_package):
            joined = [f"{name}.{member}" for member in members]
            resolved = [t for t in joined if t in modules or _unit_name(t, depth) in units]
            # A member that names a module or unit is the dependency; otherwise the parent is.
            for target in dict.fromkeys(resolved or [name]):
                destination = _unit_name(target, depth)
                if destination not in units or destination == source:
                    continue
                edges[source].add(destination)
                edge_site.setdefault((source, destination), f"{relative}:{line}")
                if _private_segment(target):
                    findings.append(f"{relative}:{line}: import of private module {target} of unit {destination}")
                if source in rank and destination in rank and rank[destination] > rank[source]:
                    findings.append(
                        f"{relative}:{line}: {source} (layer {rank[source] + 1}) imports {target} "
                        f"of {destination} (layer {rank[destination] + 1}), a less stable layer"
                    )
    for group in _cycle_groups(edges):
        inside = sorted(site for (a, b), site in edge_site.items() if a in group and b in group)
        findings.append(f"{inside[0]}: import cycle among units {', '.join(group)}")
    return findings


def scan(root: Path) -> list[str]:
    root = root.resolve()
    if repo_root(root).resolve() != root:
        raise CannotRun("--root must identify the consumer repository root")
    config = load_config(root)
    section = config.section("coupling")
    denied = _prefixes(section.get("forbidden", []), "coupling.forbidden")
    allowed = _prefixes(section.get("allowed", []), "coupling.allowed")
    layers = _layers(section["layers"]) if "layers" in section else []
    if not denied and not layers:
        raise CannotRun("coupling.forbidden must declare the consumer boundary")
    if any(not _matches(prefix, denied) or prefix in denied for prefix in allowed):
        raise CannotRun("coupling.allowed must name strict submodules of forbidden prefixes")
    packages = []
    for package in config.required_packages():
        try:
            relative = relative_to_root(package, root)
        except ValueError as exc:
            raise CannotRun(str(exc)) from exc
        if not relative or not (root / relative).is_dir():
            raise CannotRun(f"package directory is missing or invalid: {package}")
        packages.append(relative)
    files = [
        p for p in tracked_paths(root, preserve_index=False) if p.endswith(".py") and under_any(p, tuple(packages))
    ]
    if any(not any(under_any(p, (package,)) for p in files) for package in packages):
        raise CannotRun("every configured package must contain tracked Python source")
    findings = []
    parsed: list[tuple[str, str, ast.AST]] = []
    for relative in files:
        path = root / relative
        if not path.exists() and not path.is_symlink():
            continue  # tracked deletion is not surviving source
        if not path.resolve().is_relative_to(root):
            raise CannotRun(f"source escapes the consumer repository: {relative}")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise CannotRun(f"cannot parse {relative}: {exc}") from exc
        for line, module in _imports(tree):
            if _matches(module, denied) and not _matches(module, allowed):
                findings.append(f"{relative}:{line}: prohibited import {module}")
        owner = next(package for package in packages if under_any(relative, (package,)))
        parsed.append((relative, _module_name(relative, owner), tree))
    if layers:
        for package in packages:
            members = [item for item in parsed if under_any(item[0], (package,))]
            findings.extend(_layer_findings(members, layers, 1))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    findings = scan(args.root)
    for finding in findings:
        print(finding)
    return 1 if findings else 0
