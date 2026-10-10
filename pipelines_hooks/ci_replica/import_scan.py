"""AST-level primitives for naming python modules and reading their imports.

Split out of :mod:`pipelines_hooks.ci_replica.import_graph` (which builds the
module-level graph these primitives feed) purely to keep each file's function
count under the fleet's ``functions_per_file`` cap.
"""

from __future__ import annotations

import ast
from pathlib import Path


def module_name(root: Path, file_path: Path) -> str:
    """The dotted module name ``file_path`` (relative to ``root``) defines."""
    rel = file_path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def package_name(module: str, is_package: bool) -> str:
    """The package a module's relative imports are resolved against."""
    if is_package:
        return module
    return module.rpartition(".")[0]


def resolve_relative(package: str, level: int, module: str | None) -> str | None:
    """PEP 328 relative-import resolution: ``level`` dots up from ``package``."""
    parts = package.split(".") if package else []
    climb = level - 1
    if climb > len(parts):
        return None
    base = parts[: len(parts) - climb] if climb else parts
    if module:
        base = base + module.split(".")
    return ".".join(p for p in base if p)


def _import_from_base(node: ast.ImportFrom, package: str) -> str:
    """The dotted module an ``ImportFrom`` names, resolving relative dots."""
    if not node.level:
        return node.module or ""
    return resolve_relative(package, node.level, node.module) or ""


def _import_from_targets(node: ast.ImportFrom, package: str) -> set[str]:
    """Every dotted name one ``from x import a, b`` statement could mean."""
    base = _import_from_base(node, package)
    if not base:
        return set()
    return {base, *(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")}


def imports_of(file_path: Path, package: str) -> set[str]:
    """Every dotted name ``file_path`` imports, resolved where possible.

    Never raises: a syntax error or unreadable file degrades to "no imports
    found" for that one file, rather than aborting the whole scan.
    """
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.update(_import_from_targets(node, package))
    return found


def scan_tree(root: Path, subtree: Path) -> dict[str, Path]:
    """module name -> file path for every ``.py`` file under ``subtree``."""
    if not subtree.is_dir():
        return {}
    return {module_name(root, path): path for path in subtree.rglob("*.py")}
