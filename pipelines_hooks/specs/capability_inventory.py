"""capability-coverage: every first-party function, test and MCP tool names the capability it serves.

The gate scans the declared project roots (Git index bytes) with static adapters for Python (AST) and Rust
(syntax), reads the owner-exported capability registry and the owner-exported MCP tool inventory, and
checks that each item carries a ``capability: <id>`` binding that resolves in the registry. A binding
comment sits directly above the item (``# capability: a.b`` or ``// capability: a.b``). A capability ID
is lowercase and dotted, so it can never be mistaken for a specification requirement ID.

Findings (exit 1) name the item's location. Anything that could make the scan non-exhaustive (a source
language without an adapter, a missing registry export, an incomplete tool inventory) is exit 2. The
gate never mints an ID and never infers one from shared code.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, git_text, nul_split, repo_root

ADAPTER_VERSIONS = {"inventory": "1", "python": "1", "rust": "1"}
CONFIG = ".config/capability-coverage.json"
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
BINDING = re.compile(r"^\s*(?:#|//)\s*capability:\s*(\S.*?)\s*$")
UNSUPPORTED = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt", ".c", ".cc", ".cpp", ".h", ".rb", ".cs", ".swift", ".php"}
)
TEST_FILE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|tests?/[^/]*\.rs)$")
RUST_FN = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:default\s+|const\s+|async\s+|unsafe\s+|extern\s+\"[^\"]*\"\s+)*fn\s+(\w+)"
)
RUST_BLOCK = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:unsafe\s+)?(impl|mod|trait)\b\s*(?:<[^>]*>\s*)?(?:[\w:<>, &']+?\s+for\s+)?(\w+)"
)


@dataclass(frozen=True)
class Item:
    """One discovered function, test or tool and its binding."""

    kind: str
    path: str
    line: int
    symbol: str
    sha256: str
    capabilities: tuple[str, ...]

    @property
    def identity(self) -> str:
        return self.symbol if self.kind == "tool" else f"{self.path}::{self.symbol}"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bindings(lines: list[str], line: int) -> tuple[str, ...]:
    """Capability IDs of the ``capability:`` comment lines directly above the 1-based ``line`` (decorators included)."""
    found: list[str] = []
    index = line - 2
    while index >= 0 and (BINDING.match(lines[index]) or lines[index].lstrip().startswith(("@", "#["))):
        match = BINDING.match(lines[index])
        if match:
            found += [part.strip() for part in match.group(1).split(",") if part.strip()]
        index -= 1
    return tuple(reversed(found))


def python_items(path: str, text: str, is_test_file: bool) -> list[Item]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise CannotRun(f"{path}:{exc.lineno}: not parseable Python: {exc.msg}") from exc
    lines, items = text.splitlines(), []

    def walk(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = ".".join((*scope, child.name))
                first = min([child.lineno, *(d.lineno for d in child.decorator_list)])
                kind = "test" if is_test_file and child.name.startswith("test_") else "function"
                source = "\n".join(lines[first - 1 : child.end_lineno])
                items.append(Item(kind, path, child.lineno, symbol, _sha(source), _bindings(lines, first)))
                walk(child, (*scope, child.name))
            elif isinstance(child, ast.ClassDef):
                walk(child, (*scope, child.name))
            else:
                walk(child, scope)

    walk(tree, ())
    return items


def _strip_rust(line: str) -> str:
    """The line without string literals and trailing ``//`` comments, so braces count only as syntax."""
    line = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    return line.split("//", 1)[0]


def rust_items(path: str, text: str, is_test_file: bool) -> list[Item]:
    lines, items = text.splitlines(), []
    stack: list[tuple[str, int]] = []  # (qualifier, brace depth that closes it)
    depth, pending, in_block = 0, None, False
    for number, raw in enumerate(lines, 1):
        code = _strip_rust(raw)
        if in_block:
            in_block = "*/" not in raw
            continue
        if raw.lstrip().startswith("/*") and "*/" not in raw:
            in_block = True
            continue
        fn, block = RUST_FN.match(code), RUST_BLOCK.match(code)
        if fn:
            attributes = " ".join(lines[max(0, number - 4) : number - 1])
            is_test = "#[test]" in attributes or "::test]" in attributes or "::test(" in attributes
            symbol = ".".join([q for q, _ in stack] + [fn.group(1)])
            end = _rust_end(lines, number - 1)
            first = number
            while first > 1 and lines[first - 2].lstrip().startswith(("#[", "// capability:")):
                first -= 1
            kind = "test" if is_test else "function"
            items.append(
                Item(kind, path, number, symbol, _sha("\n".join(lines[first - 1 : end])), _bindings(lines, number))
            )
            pending = (fn.group(1), depth + 1) if "{" in code else pending
        elif block:
            pending = (block.group(2), depth + 1) if "{" in code else pending
        depth += code.count("{") - code.count("}")
        if pending and "{" in code:
            stack.append(pending)
            pending = None
        while stack and depth < stack[-1][1]:
            stack.pop()
    return items


def _rust_end(lines: list[str], start: int) -> int:
    """The 1-based last line of the item that opens on ``lines[start]`` (a bodiless signature ends at its ``;``)."""
    depth, opened = 0, False
    for index in range(start, len(lines)):
        code = _strip_rust(lines[index])
        depth += code.count("{") - code.count("}")
        opened = opened or "{" in code
        if (opened and depth <= 0) or (not opened and code.rstrip().endswith(";")):
            return index + 1
    return len(lines)


def _load_json(path: Path, what: str) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun(f"{what} {path} is unavailable: {exc}") from exc
    if not isinstance(document, dict):
        raise CannotRun(f"{what} {path} is not a JSON object")
    return document


def load_config(root: Path, explicit: Path | None) -> dict:
    config = _load_json(explicit or root / CONFIG, "capability-coverage config")
    for key in ("repository", "registry", "roots", "tools"):
        if key not in config:
            raise CannotRun(f"capability-coverage config lacks {key!r}")
    if not isinstance(config["roots"], list) or not config["roots"]:
        raise CannotRun("capability-coverage config declares no project roots")
    return config


def scan(root: Path, roots: list[str]) -> list[Item]:
    items: list[Item] = []
    for path in sorted(nul_split(git_text(root, ("ls-files", "-z", "--", *roots)))):
        suffix = PurePosixPath(path).suffix
        if suffix in UNSUPPORTED:
            raise CannotRun(
                f"{path}: no capability-coverage adapter for {suffix} sources; coverage would not be exhaustive"
            )
        if suffix not in {".py", ".rs"}:
            continue
        text = (blob_bytes(root, f":{path}") or b"").decode("utf-8")
        adapter = python_items if suffix == ".py" else rust_items
        items += adapter(path, text, bool(TEST_FILE.search(path)))
    return items


def tool_items(root: Path, tools: dict, items: list[Item]) -> tuple[list[Item], list[str]]:
    """MCP tools from the owner inventory, each tied to the function that implements it."""
    if tools.get("scope") == "none":
        return [], []
    path = tools.get("inventory")
    if tools.get("scope") != "inventory" or not path:
        raise CannotRun("capability-coverage config: tools.scope must be 'none' or 'inventory' with an inventory path")
    document = _load_json(root / path, "MCP tool inventory")
    if document.get("complete") is not True or not isinstance(document.get("tools"), list):
        raise CannotRun(f"MCP tool inventory {path} is incomplete: it must declare complete=true and a tools list")
    by_identity = {i.identity: i for i in items if i.kind != "tool"}
    found, findings = [], []
    for tool in document["tools"]:
        name, source, symbol = tool.get("name"), tool.get("path"), tool.get("symbol")
        bound = (tool.get("capability"),) if tool.get("capability") else ()
        implementation = by_identity.get(f"{source}::{symbol}")
        where = f"{path}: tool {name!r}"
        if implementation is None:
            findings.append(f"{where}: implementation {source}::{symbol} not found in the scanned roots")
        elif tool.get("sha256") not in (None, implementation.sha256):
            findings.append(f"{where}: source digest does not match {source}::{symbol}")
        elif bound and implementation.capabilities and bound != implementation.capabilities[:1]:
            findings.append(
                f"{where}: capability {bound[0]} differs from the implementation's {implementation.capabilities[0]}"
            )
        found.append(
            Item(
                "tool",
                str(source),
                implementation.line if implementation else 0,
                str(name),
                implementation.sha256 if implementation else "",
                bound,
            )
        )
    return found, findings


def check_items(items: list[Item], registry: set[str]) -> list[str]:
    findings = []
    for item in items:
        where = f"{item.path}:{item.line}: {item.kind} {item.symbol}"
        if not item.capabilities:
            findings.append(f"{where}: no capability binding")
        for capability in item.capabilities:
            if not CAPABILITY_ID.match(capability):
                findings.append(f"{where}: {capability!r} is not a capability ID")
            elif capability not in registry:
                findings.append(f"{where}: capability {capability} is not in the registry export")
    return findings


def evidence(root: Path, config: dict, registry: dict, items: list[Item], tools: list[Item]) -> dict:
    every = [*items, *tools]
    coverage = {c: {"function": 0, "test": 0, "tool": 0} for c in sorted(registry["capabilities"])}
    for item in every:
        for capability in item.capabilities:
            if capability in coverage:
                coverage[capability][item.kind] += 1
    return {
        "gate": "capability-coverage",
        "adapters": ADAPTER_VERSIONS,
        "registry_revision": registry.get("revision"),
        "repository": config["repository"],
        "source_snapshot": _sha("\n".join(f"{i.path}:{i.sha256}" for i in items)),
        "scope": {"roots": config["roots"], "tools": config["tools"].get("scope")},
        "counts": {kind: sum(1 for i in every if i.kind == kind) for kind in ("function", "test", "tool")},
        "identities": {
            kind: sorted(i.identity for i in every if i.kind == kind) for kind in ("function", "test", "tool")
        },
        "unmatched": sorted(i.identity for i in every if not i.capabilities),
        "capabilities": coverage,
        "uncovered": {
            c: [k for k, n in counts.items() if not n] for c, counts in coverage.items() if not all(counts.values())
        },
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="capability-coverage", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, help=f"default {CONFIG}")
    arguments = parser.parse_args(argv)
    root = repo_root(arguments.root)
    config = load_config(root, arguments.config)
    registry = _load_json(root / config["registry"], "capability registry export")
    if not isinstance(registry.get("capabilities"), list) or not registry.get("revision"):
        raise CannotRun("capability registry export needs a revision and a capabilities list")
    items = scan(root, list(config["roots"]))
    tools, findings = tool_items(root, config["tools"], items)
    findings += check_items([*items, *tools], set(registry["capabilities"]))
    print(json.dumps(evidence(root, config, registry, items, tools), sort_keys=True))
    for line in findings:
        print(f"capability-coverage: {line}")
    return 1 if findings else 0
