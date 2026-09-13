"""Build the EAGER (load-time) internal import graph of one package.

Only imports that execute at module load are edges: an import inside a
``def``/``async def`` body or under ``if TYPE_CHECKING:`` is excluded. This
split is the entire point -- the all-imports graph of a large package is one
giant component that no small first cut can fix, while the eager graph is
enforceable at zero today. Class-body imports run at load time and count.
"""

from __future__ import annotations

import ast
from pathlib import Path

import networkx as nx

from pipelines_hooks.core.tracked import tracked_or_walked

_SKIP = frozenset({"__pycache__", ".venv", "build", "dist", "tests", "test", ".git"})


class _ImportWalker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.eager: list[ast.Import | ast.ImportFrom] = []
        self._deferred = 0

    def _nested(self, node: ast.AST) -> None:
        self._deferred += 1
        self.generic_visit(node)
        self._deferred -= 1

    visit_FunctionDef = visit_AsyncFunctionDef = _nested

    def visit_If(self, node: ast.If) -> None:
        test = node.test
        guarded = getattr(test, "id", None) == "TYPE_CHECKING" or getattr(test, "attr", None) == "TYPE_CHECKING"
        self._nested(node) if guarded else self.generic_visit(node)

    def visit_Import(self, node: ast.Import | ast.ImportFrom) -> None:
        if self._deferred == 0:
            self.eager.append(node)

    visit_ImportFrom = visit_Import


def module_name(relative: Path) -> str:
    parts = relative.with_suffix("").parts
    return ".".join(parts[:-1] if parts and parts[-1] == "__init__" else parts)


def targets(node: ast.Import | ast.ImportFrom, package: str) -> list[str]:
    """Candidate modules; ``from PKG import NAME`` also yields ``PKG.NAME`` (NAME may be a submodule)."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    parts = package.split(".") if package else []
    base_parts = parts if node.level <= 1 else parts[: max(len(parts) - (node.level - 1), 0)]
    base = node.module if node.level == 0 else ".".join(base_parts + ([node.module] if node.module else []))
    if not base:
        return []
    return [base, *(f"{base}.{alias.name}" for alias in node.names)]


def eager_targets(path: Path, package_root: Path) -> set[str]:
    """Every module one file imports at load time (unfiltered candidates)."""
    relative = path.relative_to(package_root.parent).with_suffix("")
    walker = _ImportWalker()
    walker.visit(ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path)))
    return {target for node in walker.eager for target in targets(node, ".".join(relative.parts[:-1]))}


def build_eager_graph(package_root: Path, *, root: Path) -> nx.DiGraph:
    """Directed graph of load-time internal imports under ``package_root``.

    Only real, discovered modules become edges: ``from PKG import NAME`` also
    yields ``PKG.NAME``, and filtering keeps a plain attribute import from
    inventing a phantom module (which would inflate the printed counts).
    """
    paths = [p for p in tracked_or_walked(package_root, ("*.py",), root=root) if not _SKIP & set(p.parts)]
    modules = {module_name(p.relative_to(package_root.parent)): p for p in paths}
    graph: nx.DiGraph = nx.DiGraph()
    graph.add_nodes_from(modules)
    for module, path in modules.items():
        graph.add_edges_from((module, target) for target in eager_targets(path, package_root) & set(modules) if target != module)
    return graph
