"""Declared component boundaries, runtime reachability and handoff proof for ``test-quality``.

A versioned declaration (TOML) names the package roots, the components with their module
prefixes, the permitted edges between components, the entry modules and the risky
handoffs.  The static graph comes from ``import_graph.build_runtime_edges``: imports in
``def``/``async def`` bodies are ``deferred-runtime``, a proven ``TYPE_CHECKING`` body is
``type-only`` (checked against its own permissions, excluded from reachability).  A
computed import is located uncertainty: unless its module is a declared dynamic entry
the verdict is ``CannotRun``.  Handoff proof is a receipt file bound to the scanned
commit that holds a passing property test and a passing real-component integration test.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pipelines_hooks.code.import_graph import EDGE_KINDS, RuntimeEdge, build_runtime_edges
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text

SCHEMA = 1
RUNTIME = ("eager-runtime", "deferred-runtime")


@dataclass(frozen=True)
class Handoff:
    id: str
    components: tuple[str, str]
    property_test: str
    integration_test: str


@dataclass(frozen=True)
class Declaration:
    roots: tuple[str, ...]
    components: dict[str, tuple[str, ...]]
    allowed: frozenset[tuple[str, str, str]]
    entries: tuple[str, ...]
    dynamic_entries: tuple[str, ...]
    handoffs: tuple[Handoff, ...]
    receipts: str
    digest: str


@dataclass(frozen=True)
class Located:
    path: str
    line: int
    rule: str
    detail: str = ""


@dataclass
class BoundaryResult:
    findings: list[Located] = field(default_factory=list)
    evidence: dict[str, object] = field(default_factory=dict)


def load_declaration(path: Path) -> Declaration:
    """Parse and validate a declaration; anything malformed is CannotRun, never a pass."""
    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"{path.name}: component declaration is unreadable: {exc}") from exc
    if data.get("version") != SCHEMA:
        raise CannotRun(f"{path.name}: component declaration needs version = {SCHEMA}")
    try:
        components = {c["name"]: tuple(c["modules"]) for c in data["components"]}
        allowed = frozenset(
            (e["from"], e["to"], k) for e in data.get("edges", []) for k in e.get("kinds", list(RUNTIME))
        )
        bad = sorted({k for _, _, k in allowed} - set(EDGE_KINDS))
        if bad:
            raise ValueError(f"unknown edge kinds {bad}")
        unknown = sorted({n for a, b, _ in allowed for n in (a, b)} - set(components))
        if unknown:
            raise ValueError(f"edges name undeclared components {unknown}")
        handoffs = tuple(
            Handoff(h["id"], (h["components"][0], h["components"][1]), h["property_test"], h["integration_test"])
            for h in data.get("handoffs", [])
        )
        declaration = Declaration(
            roots=tuple(data["roots"]),
            components=components,
            allowed=allowed,
            entries=tuple(data["entry_modules"]),
            dynamic_entries=tuple(data.get("dynamic_entry_modules", [])),
            handoffs=handoffs,
            receipts=data.get("receipts", "handoff-receipts.json"),
            digest=hashlib.sha256(raw).hexdigest(),
        )
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise CannotRun(f"{path.name}: malformed component declaration: {exc!r}") from exc
    if not declaration.roots or not declaration.entries:
        raise CannotRun(f"{path.name}: roots and entry_modules must be non-empty")
    return declaration


def _component(declaration: Declaration, module: str) -> str | None:
    best: tuple[int, str] | None = None
    for name, prefixes in declaration.components.items():
        for prefix in prefixes:
            if (module == prefix or module.startswith(prefix + ".")) and (best is None or len(prefix) > best[0]):
                best = (len(prefix), name)
    return best[1] if best else None


def _reachable(modules: set[str], edges: list[RuntimeEdge], starts: list[str]) -> set[str]:
    out: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.kind in RUNTIME:
            out[edge.source].add(edge.target)
    seen: set[str] = set()
    todo = [m for m in starts if m in modules]
    while todo:
        module = todo.pop()
        if module in seen:
            continue
        seen.add(module)
        todo.extend(out[module])
        parts = module.split(".")  # importing a.b.c also executes a and a.b
        todo.extend(".".join(parts[:i]) for i in range(1, len(parts)) if ".".join(parts[:i]) in modules)
    return seen


def check_receipts(root: Path, declaration: Declaration) -> tuple[list[Located], list[dict[str, object]]]:
    """Each risky handoff needs a passing property and a passing integration receipt at HEAD."""
    findings: list[Located] = []
    if not declaration.handoffs:
        return findings, []
    path = root / declaration.receipts
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        receipts = {r["test_id"]: r for r in document["receipts"]}
        commit = document["commit"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CannotRun(f"{declaration.receipts}: handoff receipts are missing or malformed: {exc!r}") from exc
    head = git_text(root, ["rev-parse", "HEAD"]).strip()
    if commit != head:
        raise CannotRun(f"{declaration.receipts}: stale receipts for {commit[:12]}, scanned commit is {head[:12]}")
    used: list[dict[str, object]] = []
    for handoff in declaration.handoffs:
        for kind, test_id, rule in (
            ("property", handoff.property_test, "missing-property-proof"),
            ("integration", handoff.integration_test, "missing-integration-proof"),
        ):
            receipt = receipts.get(test_id)
            if receipt is not None and receipt.get("outcome") == "skipped":
                raise CannotRun(f"{declaration.receipts}: {test_id} was skipped; a skipped test proves nothing")
            ok = receipt is not None and receipt.get("outcome") == "passed" and receipt.get("kind") == kind
            if ok and kind == "integration":
                ok = sorted(receipt.get("components", [])) == sorted(handoff.components)
            if ok and kind == "property":
                ok = isinstance(receipt.get("seed"), int)
            if not ok:
                findings.append(Located(declaration.receipts, 1, rule, f"{handoff.id}: {test_id}"))
            elif receipt is not None:
                used.append({"handoff": handoff.id, **receipt})
    return findings, used


def check(root: Path, declaration_path: Path) -> BoundaryResult:
    declaration = load_declaration(declaration_path)
    roots = [root / r for r in declaration.roots]
    missing = [r for r in declaration.roots if not (root / r).is_dir()]
    if missing:
        raise CannotRun(f"{declaration_path.name}: declared roots not found: {missing}")
    modules, edges, dynamic = build_runtime_edges(roots, root=root)
    result = BoundaryResult()
    declared_dynamic = set(declaration.dynamic_entries)
    undeclared = [d for d in dynamic if d.source not in declared_dynamic]
    if undeclared:
        where = ", ".join(f"{d.path}:{d.line}" for d in undeclared)
        raise CannotRun(f"computed import cannot be resolved ({where}); declare the module in dynamic_entry_modules")
    unknown_entries = [e for e in (*declaration.entries, *declaration.dynamic_entries) if e not in modules]
    if unknown_entries:
        raise CannotRun(f"{declaration_path.name}: entry modules not found: {unknown_entries}")
    for edge in edges:
        a, b = _component(declaration, edge.source), _component(declaration, edge.target)
        if a is None or b is None or a == b:
            continue
        if (a, b, edge.kind) not in declaration.allowed:
            result.findings.append(
                Located(edge.path, edge.line, "interface-violation", f"{edge.source} -> {edge.target} ({edge.kind})")
            )
    reach = _reachable(modules, edges, [*declaration.entries, *declaration.dynamic_entries])
    paths = {e.source: e.path for e in edges}
    for module in sorted(modules - reach):
        result.findings.append(Located(paths.get(module, module.replace(".", "/") + ".py"), 1, "orphan-module", module))
    handoff_findings, receipts = check_receipts(root, declaration)
    result.findings.extend(handoff_findings)
    result.evidence = {
        "declaration_digest": declaration.digest,
        "edges": [[e.source, e.target, f"{e.path}:{e.line}", e.kind] for e in edges],
        "type_only_excluded": sorted({e.target for e in edges if e.kind == "type-only"} - reach),
        "reachable": sorted(reach),
        "dynamic_uncertainty": [f"{d.path}:{d.line}" for d in dynamic],
        "receipts": receipts,
        "source_digest": hashlib.sha256(
            b"".join((root / p).read_bytes() for p in sorted(set(paths.values())))
        ).hexdigest(),
    }
    return result
