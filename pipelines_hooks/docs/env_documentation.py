"""env-documentation: runtime environment reads, the example file, the README and launcher JSON agree.

Declared in ``.config/env-documentation.toml``.  Runtime reads are found with the
Python syntax tree (``os.environ[...]``, ``os.environ.get``, ``os.getenv`` and the
declared central providers); a computed name is accepted only through a declared
finite resolver bound to the source digest.  The example file documents each
variable as ``# [required|optional] purpose`` above ``NAME=default``; the README
repeats it as ``| `NAME` | `default` | required|optional | purpose |``.  Each tracked
launcher JSON binds the variables it applies to under a JSON pointer.  Everything
is read from the staged Git snapshot; no import, launcher or expansion is executed.
Secret-named variables carry no default anywhere.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import cast

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, repo_root
from pipelines_hooks.core.tracked import tracked_paths

DECLARATION = ".config/env-documentation.toml"
ADAPTERS = ("mcp-env-v1",)
SECRET_RE = re.compile(r"(?i)(token|secret|password|passwd|api_?key|credential)")
_FOREIGN = {".js", ".ts", ".go", ".rb", ".java", ".rs", ".php", ".cs"}
_SOURCED_RE = re.compile(r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^${}`]*))?\}$")
_UNSAFE_RE = re.compile(r"\$\(|`|\$\{[^}]*[^A-Za-z0-9_:\-}$][^}]*\}|\$\{[^}]*\$\{")
_ROW_RE = re.compile(
    r"^\|\s*`(?P<name>[A-Z][A-Z0-9_]*)`\s*\|\s*`?(?P<default>[^|`]*?)`?\s*\|\s*(?P<req>required|optional)\s*\|\s*(?P<purpose>[^|]+?)\s*\|\s*$"
)
_EX_RE = re.compile(r"^#\s*\[(?P<req>required|optional)\]\s*(?P<purpose>.+)$")


@dataclass(frozen=True)
class EnvUse:
    """One syntax-located runtime read."""

    name: str
    path: str
    line: int
    provider: str
    required: bool
    default: str | None


@dataclass(frozen=True)
class RuntimeEnvContract:
    """One variable: name, typed default (or none), requiredness, locations and provider provenance."""

    name: str
    default: str | None
    required: bool
    secret: bool
    uses: tuple[EnvUse, ...]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.name):
            raise CannotRun(f"env-documentation: invalid variable name {self.name!r}")
        if self.secret and self.default is not None:
            raise CannotRun(f"env-documentation: secret variable {self.name} must have no default")


@dataclass(frozen=True)
class LauncherEnvBinding:
    """One launcher JSON env table: file, identity, pointer, adapter and applicable variables."""

    path: str
    identity: str
    pointer: str
    adapter: str
    variables: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.adapter not in ADAPTERS:
            raise CannotRun(f"env-documentation: unsupported launcher dialect {self.adapter!r}")
        if not self.pointer.startswith("/") or len(set(self.variables)) != len(self.variables):
            raise CannotRun(f"env-documentation: malformed launcher binding for {self.path}")


@dataclass
class Policy:
    roots: tuple[str, ...]
    example: str
    readme: str
    providers: tuple[str, ...]
    resolvers: dict[str, tuple[str, tuple[str, ...]]]
    launchers: tuple[LauncherEnvBinding, ...]
    digest: str = ""


@dataclass
class Result:
    findings: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def _read(root: Path, path: str) -> bytes | None:
    return blob_bytes(root, f":{path}")


def _launcher_binding(entry: dict[str, object]) -> LauncherEnvBinding:
    keys = {"path", "identity", "pointer", "adapter", "variables"}
    if set(entry) - keys or {"path", "identity", "pointer", "variables"} - set(entry):
        raise CannotRun("env-documentation: launcher entries need path, identity, pointer and variables only")
    return LauncherEnvBinding(
        str(entry["path"]),
        str(entry["identity"]),
        str(entry["pointer"]),
        str(entry.get("adapter", ADAPTERS[0])),
        tuple(str(v) for v in cast("list[object]", entry["variables"])),
    )


def load_policy(root: Path) -> Policy:
    raw = _read(root, DECLARATION)
    if raw is None:
        raise CannotRun(f"env-documentation: {DECLARATION} is not in the snapshot")
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"env-documentation: {DECLARATION} is unreadable: {exc}") from exc
    known = {"schema", "source_roots", "example", "readme", "provider", "resolver", "launcher"}
    if set(data) - known or data.get("schema") != 1:
        raise CannotRun("env-documentation: unsupported schema or unknown fields")
    roots = tuple(data.get("source_roots", []))
    for item in (*roots, data.get("example", ""), data.get("readme", "")):
        pure = PurePosixPath(item)
        if not item or pure.is_absolute() or ".." in pure.parts:
            raise CannotRun(f"env-documentation: unsafe path {item!r}")
    resolvers = {
        r["path"]: (str(r["digest"]), tuple(r["values"]))
        for r in data.get("resolver", [])
        if {"path", "digest", "values"} <= set(r)
    }
    launchers = tuple(_launcher_binding(entry) for entry in data.get("launcher", []))
    return Policy(
        roots,
        data["example"],
        data["readme"],
        tuple(p["name"] for p in data.get("provider", [])),
        resolvers,
        launchers,
        _sha(raw),
    )


class _Reads(ast.NodeVisitor):
    def __init__(self, path: str, providers: tuple[str, ...]) -> None:
        self.path, self.providers = path, providers
        self.uses: list[EnvUse] = []
        self.computed: list[int] = []

    @staticmethod
    def _dotted(node: ast.AST) -> str:
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))

    def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
        if self._dotted(node.value) == "os.environ" and isinstance(node.ctx, ast.Load):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                self.uses.append(EnvUse(node.slice.value, self.path, node.lineno, "os.environ", True, None))
            else:
                self.computed.append(node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        callee = self._dotted(node.func)
        if callee in ("os.getenv", "os.environ.get") or callee.split(".")[-1] in self.providers:
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                default = (
                    node.args[1]
                    if len(node.args) > 1
                    else next((k.value for k in node.keywords if k.arg == "default"), None)
                )
                if default is None:
                    value = None
                elif isinstance(default, ast.Constant) and not isinstance(default.value, bytes):
                    value = (
                        ""
                        if default.value is None
                        else str(default.value).lower()
                        if isinstance(default.value, bool)
                        else str(default.value)
                    )
                else:
                    raise CannotRun(
                        f"env-documentation: {self.path}:{node.lineno}: non-literal default for {first.value}"
                    )
                self.uses.append(EnvUse(first.value, self.path, node.lineno, callee, False, value))
            else:
                self.computed.append(node.lineno)
        self.generic_visit(node)


def discover_reads(root: Path, policy: Policy) -> tuple[list[EnvUse], str]:
    uses: list[EnvUse] = []
    digest = hashlib.sha256()
    for path in tracked_paths(root):
        if not any(path == r or path.startswith(r.rstrip("/") + "/") for r in policy.roots):
            continue
        if PurePosixPath(path).suffix in _FOREIGN:
            raise CannotRun(f"env-documentation: {path}: unsupported source language")
        if not path.endswith(".py"):
            continue
        raw = _read(root, path) or b""
        digest.update(path.encode() + raw)
        try:
            tree = ast.parse(raw.decode("utf-8"), filename=path)
        except (SyntaxError, UnicodeError) as exc:
            raise CannotRun(f"env-documentation: {path}: cannot parse: {exc}") from exc
        visitor = _Reads(path, policy.providers)
        visitor.visit(tree)
        uses.extend(visitor.uses)
        if visitor.computed:
            resolver = policy.resolvers.get(path)
            if resolver is None or resolver[0] != _sha(raw):
                raise CannotRun(
                    f"env-documentation: {path}:{visitor.computed[0]}: computed variable name without a digest-bound resolver"
                )
            uses.extend(EnvUse(name, path, visitor.computed[0], "resolver", False, None) for name in resolver[1])
    return uses, digest.hexdigest()[:16]


def build_contracts(uses: list[EnvUse]) -> dict[str, RuntimeEnvContract]:
    contracts: dict[str, RuntimeEnvContract] = {}
    for name in sorted({u.name for u in uses}):
        group = tuple(u for u in uses if u.name == name)
        defaults = {u.default for u in group if u.default is not None}
        if len(defaults) > 1:
            where = ", ".join(f"{u.path}:{u.line}" for u in group)
            raise CannotRun(f"env-documentation: conflicting defaults for {name} at {where}")
        secret = bool(SECRET_RE.search(name))
        default = None if secret else next(iter(defaults), None)
        contracts[name] = RuntimeEnvContract(name, default, any(u.required for u in group), secret, group)
    return contracts


def _example(text: str) -> dict[str, tuple[int, str | None, str, str]]:
    found: dict[str, tuple[int, str | None, str, str]] = {}
    pending: tuple[str, str] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        header = _EX_RE.match(line)
        if header:
            pending = (header["req"], header["purpose"].strip())
        elif "=" in line and not line.startswith("#"):
            name, _, value = line.partition("=")
            found[name.strip()] = (number, value.strip() or None, *(pending or ("", "")))
            pending = None
    return found


def _readme(text: str) -> dict[str, tuple[int, str | None, str, str]]:
    rows = {}
    for number, line in enumerate(text.splitlines(), 1):
        match = _ROW_RE.match(line)
        if match:
            rows[match["name"]] = (number, match["default"].strip() or None, match["req"], match["purpose"])
    return rows


def _documentation(root: Path, policy: Policy, contracts: dict[str, RuntimeEnvContract], result: Result) -> None:
    for label, path, parse in (("example", policy.example, _example), ("readme", policy.readme, _readme)):
        raw = _read(root, path)
        if raw is None:
            result.findings.append(f"{path}: {label} file is missing")
            continue
        docs = parse(raw.decode("utf-8", errors="replace"))
        for name, contract in contracts.items():
            entry = docs.get(name)
            if entry is None:
                result.findings.append(
                    f"{path}: {name} is read at {contract.uses[0].path}:{contract.uses[0].line} but not documented"
                )
                continue
            number, default, required, purpose = entry
            result.lines.append(
                f"doc {label} name={name} line={path}:{number} default={'(secret)' if contract.secret else default} requiredness={required}"
            )
            if default != contract.default:
                result.findings.append(
                    f"{path}:{number}: {name} default {default!r} differs from code {contract.default!r}"
                )
            if required != ("required" if contract.required else "optional"):
                result.findings.append(f"{path}:{number}: {name} requiredness drifted")
            if not purpose:
                result.findings.append(f"{path}:{number}: {name} has no purpose")
        for name in sorted(set(docs) - set(contracts)):
            result.findings.append(f"{path}:{docs[name][0]}: {name} is documented but never read")
    example = _example((_read(root, policy.example) or b"").decode("utf-8", errors="replace"))
    readme = _readme((_read(root, policy.readme) or b"").decode("utf-8", errors="replace"))
    for name in contracts:
        if name in example and name in readme and example[name][3].strip() != readme[name][3].strip():
            result.findings.append(f"{policy.readme}:{readme[name][0]}: {name} purpose differs from {policy.example}")


def _json_line(text: str, key: str) -> int:
    match = re.search(rf'"{re.escape(key)}"\s*:', text)
    return text[: match.start()].count("\n") + 1 if match else 1


def _launchers(root: Path, policy: Policy, contracts: dict[str, RuntimeEnvContract], result: Result) -> None:
    declared = {b.path for b in policy.launchers}
    for path in tracked_paths(root, ("*.json",)):
        content = _read(root, path) or b""
        if path not in declared and len(content) < 1_000_000 and b'"mcpServers"' in content:
            raise CannotRun(f"env-documentation: {path}: discovered launcher is not mapped to a binding")
    for binding in policy.launchers:
        raw = _read(root, binding.path)
        if raw is None:
            result.findings.append(f"{binding.path}: declared launcher file is missing")
            continue
        text = raw.decode("utf-8", errors="replace")
        try:
            node: object = json.loads(text)
        except ValueError as exc:
            result.findings.append(f"{binding.path}: malformed JSON: {exc}")
            continue
        for part in binding.pointer.lstrip("/").split("/"):
            node = node.get(part.replace("~1", "/").replace("~0", "~")) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            result.findings.append(f"{binding.path}: JSON pointer {binding.pointer} does not resolve to an object")
            continue
        verdicts = []
        for name in binding.variables:
            contract = contracts.get(name)
            line = _json_line(text, name)
            if contract is None:
                raise CannotRun(f"env-documentation: launcher {binding.path} applies unknown variable {name}")
            if name not in node:
                result.findings.append(f"{binding.path}:{line}: {binding.pointer} lacks a binding for {name}")
                verdicts.append(f"{name}=missing")
                continue
            value = str(node[name])
            if _UNSAFE_RE.search(value):
                raise CannotRun(f"env-documentation: {binding.path}:{line}: unsupported substitution in {name}")
            sourced = _SOURCED_RE.match(value)
            if sourced and sourced["name"] != name:
                result.findings.append(f"{binding.path}:{line}: {name} is sourced from {sourced['name']}")
            effective = (
                sourced["default"] if sourced and sourced["default"] is not None else (None if sourced else value)
            )
            if contract.secret and not sourced:
                result.findings.append(f"{binding.path}:{line}: secret {name} must be sourced, not literal")
            elif not contract.secret and contract.default is not None and effective != contract.default:
                result.findings.append(
                    f"{binding.path}:{line}: {name} default {effective!r} differs from {contract.default!r}"
                )
            elif contract.required and not contract.secret and not sourced and not value:
                result.findings.append(f"{binding.path}:{line}: required {name} is bound to an empty literal")
            verdicts.append(f"{name}=bound")
        for extra in sorted(set(node) - set(binding.variables)):
            result.findings.append(f"{binding.path}:{_json_line(text, extra)}: unexpected binding {extra}")
        result.lines.append(
            f"launcher path={binding.path} identity={binding.identity} pointer={binding.pointer} adapter={binding.adapter} "
            f"applicable={list(binding.variables)} {' '.join(verdicts)}"
        )


def check(root: Path) -> Result:
    policy = load_policy(root)
    uses, source_digest = discover_reads(root, policy)
    contracts = build_contracts(uses)
    result = Result()
    for contract in contracts.values():
        use = contract.uses[0]
        for leaked in (u for u in contract.uses if contract.secret and u.default is not None):
            result.findings.append(f"{leaked.path}:{leaked.line}: secret {contract.name} must not carry a default")
        shown = "(secret)" if contract.secret else contract.default
        result.lines.append(
            f"env name={contract.name} default={shown} required={contract.required} source={use.path}:{use.line} provider={use.provider}"
        )
    _documentation(root, policy, contracts, result)
    _launchers(root, policy, contracts, result)
    consumers = _sha(b"".join((_read(root, p) or b"") for p in (policy.example, policy.readme)))
    result.lines.append(f"digests source={source_digest} consumer={consumers} policy={policy.digest} unchecked=0")
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="env-documentation", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    result = check(root)
    for line in result.lines:
        print(line)
    if not result.findings:
        print("env documentation: clean")
        return 0
    print("FAIL: environment documentation.")
    for finding in result.findings:
        print(f"  - {finding}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
