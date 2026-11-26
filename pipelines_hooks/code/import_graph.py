"""Build the EAGER (load-time) internal import graph of one package.

Only imports that execute at module load are edges: an import inside a
``def``/``async def`` body or under ``if TYPE_CHECKING:`` is excluded. This
split is the entire point -- the all-imports graph of a large package is one
giant component that no small first cut can fix, while the eager graph is
enforceable at zero today. Class-body imports run at load time and count.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
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
        graph.add_edges_from(
            (module, target) for target in eager_targets(path, package_root) & set(modules) if target != module
        )
    return graph


EDGE_KINDS = ("eager-runtime", "deferred-runtime", "type-only")


@dataclass(frozen=True)
class RuntimeEdge:
    """One statically resolved import: where it sits and when it executes."""

    source: str
    target: str
    path: str
    line: int
    kind: str


@dataclass(frozen=True)
class DynamicSite:
    """A computed import whose target cannot be resolved statically."""

    source: str
    path: str
    line: int


def _is_type_checking(test: ast.expr) -> bool:
    return getattr(test, "id", None) == "TYPE_CHECKING" or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


class _KindWalker(ast.NodeVisitor):
    """Every import with its kind: function bodies are deferred, a proven TYPE_CHECKING body type-only."""

    def __init__(self) -> None:
        self.imports: list[tuple[ast.Import | ast.ImportFrom, str]] = []
        self.dynamic: list[int] = []
        self._deferred = 0
        self._typing = 0

    def _kind(self) -> str:
        if self._typing:
            return "type-only"
        return "deferred-runtime" if self._deferred else "eager-runtime"

    def _nested(self, node: ast.AST) -> None:
        self._deferred += 1
        self.generic_visit(node)
        self._deferred -= 1

    visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _nested

    def visit_If(self, node: ast.If) -> None:
        if not _is_type_checking(node.test):
            self.generic_visit(node)
            return
        self._typing += 1
        for child in node.body:
            self.visit(child)
        self._typing -= 1
        for child in node.orelse:
            self.visit(child)

    def visit_Import(self, node: ast.Import | ast.ImportFrom) -> None:
        self.imports.append((node, self._kind()))

    visit_ImportFrom = visit_Import

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in {"import_module", "__import__"} and not (
            node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
        ):
            self.dynamic.append(node.lineno)
        self.generic_visit(node)


def build_runtime_edges(
    package_roots: list[Path], *, root: Path
) -> tuple[set[str], list[RuntimeEdge], list[DynamicSite]]:
    """Static graph of every resolvable import, typed by kind, beside the eager-only graph above."""
    paths: dict[str, Path] = {}
    for package_root in package_roots:
        for p in tracked_or_walked(package_root, ("*.py",), root=root):
            if not _SKIP & set(p.parts):
                paths[module_name(p.relative_to(package_root.parent))] = p
    edges: list[RuntimeEdge] = []
    dynamic: list[DynamicSite] = []
    for module, path in sorted(paths.items()):
        walker = _KindWalker()
        walker.visit(ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path)))
        rel = path.relative_to(root).as_posix()
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        for node, kind in walker.imports:
            candidates = targets(node, package)
            submodules = [t for t in candidates[1:] if t in paths] if isinstance(node, ast.ImportFrom) else []
            for target in submodules or candidates:
                if target in paths and target != module:
                    edges.append(RuntimeEdge(module, target, rel, node.lineno, kind))
        dynamic.extend(DynamicSite(module, rel, line) for line in walker.dynamic)
    return set(paths), edges, dynamic
