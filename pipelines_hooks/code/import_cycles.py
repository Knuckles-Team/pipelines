"""import-cycles: zero eager-import cycles in every declared package.

This gate owns kiss's ``cycle_size``, ``dependency_depth`` and
``indirect_dependencies`` on the graph that actually executes (see
:mod:`pipelines_hooks.code.import_graph`). Cycles are gated at an absolute zero;
the reach distribution is printed on every run, pass or fail. Dynamic imports
and cycles through external packages are out of scope.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import networkx as nx

from pipelines_hooks.code.import_graph import build_eager_graph
from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values) or [0]
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def report_reach(graph: nx.DiGraph) -> None:
    """Per-module transitive reach and depth on the eager graph (reported, not gated)."""
    reach = [nx.single_source_shortest_path_length(graph, node) for node in graph.nodes]
    stats = {"indirect_dependencies": [len(r) - 1 for r in reach], "dependency_depth": [max(r.values()) for r in reach]}
    for metric, values in stats.items():
        print(
            f"  {metric:24s} p50={_percentile(values, 0.5):5d} p90={_percentile(values, 0.9):5d} "
            f"p99={_percentile(values, 0.99):5d} max={max(values, default=0):5d}"
        )


def find_cycles(graph: nx.DiGraph) -> list[list[str]]:
    return sorted((sorted(c) for c in nx.strongly_connected_components(graph) if len(c) > 1), key=len, reverse=True)


def check_package(root: Path, package: str) -> int:
    package_root = root / package
    if not package_root.is_dir():
        raise CannotRun(f"package {package} not found")
    graph = build_eager_graph(package_root, root=root)
    cycles = find_cycles(graph)
    for cycle in cycles:
        print(f"  cycle ({len(cycle)} modules): {' -> '.join([*cycle, cycle[0]])}", file=sys.stderr)
    print(f"{package}: {len(cycles)} eager-import cycle(s) among {graph.number_of_nodes()} modules, {graph.number_of_edges()} eager edges")
    report_reach(graph)
    return len(cycles)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="import-cycles", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    cycles = sum(check_package(root, package) for package in load_config(root).required_packages())
    if cycles:
        print("FAIL: eager-import cycles found (function-local and TYPE_CHECKING imports excluded by design)")
        return 1
    print("import-cycles: OK: zero eager-import cycles")
    return 0
