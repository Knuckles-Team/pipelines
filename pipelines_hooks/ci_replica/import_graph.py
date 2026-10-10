"""Static import-graph fallback for ``pr-test-scope`` (python only).

When a changed module under ``--src-root`` has no mirrored ``test_<name>.py``,
the scope gate used to force the full suite -- correct, but needlessly broad
for a fleet-wide package whose test tree does not literally mirror its source
layout file-for-file (``agent_utilities``). This module builds a module-level
import graph from :mod:`pipelines_hooks.ci_replica.import_scan`'s AST scan of
``--src-root`` and ``--tests-root``, and answers: which test files import the
changed module directly? (Transitive reach is left to the full suite on main.)
"""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.ci_replica.import_scan import imports_of, module_name, package_name, scan_tree

#: Direct importers only. Transitive reach through package re-exports selects most of a
#: large suite (AU: 997 files for one module), which defeats a fast PR subset; main CI
#: runs the full suite and catches transitive breakage (fix forward).
MAX_DEPTH = 1


def _known_prefixes(dotted: str, known: set[str]) -> set[str]:
    """Which dotted prefixes of ``dotted`` (longest first) are known modules.

    A dotted import may name a package *or* an attribute inside one
    (``from a.b import c`` is ambiguous without resolving ``a.b``); keep
    every prefix that matches a module this scan itself discovered.
    """
    pieces = dotted.split(".")
    prefixes = (".".join(pieces[:end]) for end in range(len(pieces), 0, -1))
    return {candidate for candidate in prefixes if candidate in known}


def _edges_for(name: str, path: Path, known: set[str]) -> set[str]:
    """What module ``name`` (at ``path``) imports, limited to ``known`` modules."""
    package = package_name(name, path.name == "__init__.py")
    resolved: set[str] = set()
    for dotted in imports_of(path, package):
        resolved |= _known_prefixes(dotted, known)
    return resolved


def build_import_graph(root: Path, src_prefix: str, tests_prefix: str) -> tuple[dict[str, set[str]], dict[str, Path]]:
    """``(edges, modules)``: ``edges[m]`` is what module ``m`` imports, limited
    to modules this scan itself discovered (external/stdlib imports dropped).
    """
    modules = scan_tree(root, root / src_prefix.rstrip("/"))
    modules.update(scan_tree(root, root / tests_prefix.rstrip("/")))
    known = set(modules)
    edges = {name: _edges_for(name, path, known) for name, path in modules.items()}
    return edges, modules


def importers_within_depth(edges: dict[str, set[str]], target: str, max_depth: int = MAX_DEPTH) -> set[str]:
    """Modules that import ``target``, directly or via a chain of imports.

    ``max_depth`` bounds the number of import hops walked backward from
    ``target``; the default (1) selects only tests that import it directly.
    """
    reverse: dict[str, set[str]] = {}
    for src, dests in edges.items():
        for dest in dests:
            reverse.setdefault(dest, set()).add(src)
    seen = {target}
    frontier = {target}
    for _ in range(max_depth):
        importers = {m for node in frontier for m in reverse.get(node, ())} - seen
        if not importers:
            break
        seen |= importers
        frontier = importers
    seen.discard(target)
    return seen


def test_files_importing(root: Path, src_prefix: str, *, tests_prefix: str, changed_module: str) -> list[str]:
    """Repo-relative test paths that reach ``changed_module`` via imports."""
    edges, modules = build_import_graph(root, src_prefix, tests_prefix)
    if changed_module not in modules:
        return []
    reached = importers_within_depth(edges, changed_module)
    tests_root = tests_prefix.rstrip("/") + "/"
    selected = [
        modules[name].relative_to(root).as_posix()
        for name in reached
        if name in modules and modules[name].relative_to(root).as_posix().startswith(tests_root)
    ]
    return sorted(selected)


def module_for_path(root: Path, src_prefix: str, rel_path: str) -> str:
    """The dotted module name for ``<src_prefix><rel_path>`` (rel to src root)."""
    return module_name(root, root / src_prefix.rstrip("/") / rel_path)
