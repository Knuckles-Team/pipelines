"""deployment-docs: the four deployment patterns are documented, configured and launchable as exported.

Declared in ``.config/deployment-docs.json`` (the owner export ``deployment-export/1``, its
digest and the README).  The matrix has exactly four pattern ids: ``uv-stdio``,
``uv-local-http``, ``local-container-http`` and ``remote-container-url``.  A supported pattern
binds an owner capability, a tracked MCP JSON configuration (pointer), the launch or connect
argv documented in a fenced command block under its README anchor, and environment bindings.
A constrained pattern must show a reason and owner evidence and advertises no command.  A
hosted URL carries a safe example endpoint and separate owner-host instructions, never a local
spawn command.  Nothing is started and no endpoint is contacted: syntax and contract parity
only, recorded apart from any exact-version runtime receipt the owner exports.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.validation_report import redact
from pipelines_hooks.docs.gate_io import Result, fenced_blocks, finish, load_json, require, sha, strict_keys

GATE = "deployment-docs"
DECLARATION = ".config/deployment-docs.json"
FORMAT = "deployment-export/1"
PATTERNS = ("uv-stdio", "uv-local-http", "local-container-http", "remote-container-url")
TRANSPORTS = {"stdio", "http", "streamable-http"}
RUNTIMES = {"docker", "podman"}
_SHELL = re.compile(r"[|;&<>`]|\$\(")
_SOURCED = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^${}]*)?\}$")
_SAFE_HOST = re.compile(r"^https://([a-z0-9-]+\.)*(example\.(com|org|net)|[a-z0-9-]+\.example|invalid)(/|:|$)")


@dataclass(frozen=True)
class PatternRecord:
    """One pattern of the matrix: owner capability, status, configuration, argv and anchors."""

    id: str
    status: str
    capability: str | None
    transport: str | None
    config_path: str | None
    config_pointer: str | None
    argv: tuple[str, ...]
    owner_argv: tuple[str, ...]
    env: dict[str, str]
    image: str | None
    package: str | None
    reason: str | None
    owner_evidence: str | None
    prerequisites: tuple[str, ...]


@dataclass(frozen=True)
class DeploymentDocMatrix:
    """The four-pattern matrix of one owner export, bound to the export digest."""

    owner: str
    digest: str
    runtime: str
    readme: str
    require_runnable: bool
    patterns: dict[str, PatternRecord]
    receipts: dict[str, dict[str, str]]


def _record(pid: str, raw: object) -> PatternRecord:
    data = strict_keys(
        GATE,
        f"pattern {pid}",
        raw,
        {
            "status",
            "capability",
            "transport",
            "config",
            "argv",
            "owner_argv",
            "env",
            "image",
            "package",
            "reason",
            "owner_evidence",
            "prerequisites",
        },
        {"status"},
    )
    status = data["status"]
    if status not in {"supported", "constrained"}:
        raise CannotRun(f"{GATE}: pattern {pid} has unknown status {status!r}")
    transport = data.get("transport")
    if transport is not None and transport not in TRANSPORTS:
        raise CannotRun(f"{GATE}: pattern {pid} has unknown transport {transport!r}")
    if status == "supported" and not data.get("capability"):
        raise CannotRun(f"{GATE}: pattern {pid} carries no owner capability evidence")
    config = data.get("config") or {}
    argv, owner_argv = data.get("argv", []), data.get("owner_argv", [])
    for label, value in (("argv", argv), ("owner_argv", owner_argv)):
        if not isinstance(value, list) or not all(isinstance(a, str) and a and not _SHELL.search(a) for a in value):
            raise CannotRun(f"{GATE}: pattern {pid} {label} uses an unsupported command grammar")
    return PatternRecord(
        pid,
        status,
        data.get("capability"),
        transport,
        config.get("path"),
        config.get("pointer"),
        tuple(argv),
        tuple(owner_argv),
        dict(data.get("env", {})),
        data.get("image"),
        data.get("package"),
        data.get("reason"),
        data.get("owner_evidence"),
        tuple(data.get("prerequisites", [])),
    )


def load_matrix(root: Path) -> DeploymentDocMatrix:
    decl, _ = load_json(GATE, root, DECLARATION)
    decl = strict_keys(
        GATE,
        DECLARATION,
        decl,
        {"schema", "export", "export_digest", "readme"},
        {"schema", "export", "export_digest", "readme"},
    )
    if decl["schema"] != 1:
        raise CannotRun(f"{GATE}: unsupported declaration schema")
    data, raw = load_json(GATE, root, decl["export"])
    data = strict_keys(
        GATE,
        decl["export"],
        data,
        {"format", "owner", "runtime", "require_runnable", "patterns", "receipts"},
        {"format", "owner", "runtime", "patterns"},
    )
    if data["format"] != FORMAT:
        raise CannotRun(f"{GATE}: unsupported export format {data['format']!r}")
    if data["runtime"] not in RUNTIMES:
        raise CannotRun(f"{GATE}: unknown container runtime {data['runtime']!r}")
    if sha(raw) != decl["export_digest"]:
        raise CannotRun(f"{GATE}: stale owner export {decl['export']}")
    patterns = {pid: _record(pid, rec) for pid, rec in data["patterns"].items()}
    return DeploymentDocMatrix(
        data["owner"],
        sha(raw),
        data["runtime"],
        decl["readme"],
        bool(data.get("require_runnable")),
        patterns,
        dict(data.get("receipts", {})),
    )


def _section(readme: str, pid: str) -> tuple[int, str] | None:
    match = re.search(rf"^### {re.escape(pid)}\s*$", readme, re.M)
    if match is None:
        return None
    nxt = re.search(r"^#{1,3} ", readme[match.end() :], re.M)
    end = match.end() + nxt.start() if nxt else len(readme)
    return readme[: match.start()].count("\n") + 1, readme[match.end() : end]


def _pointer(node: object, pointer: str) -> object:
    for part in pointer.lstrip("/").split("/"):
        node = node.get(part.replace("~1", "/").replace("~0", "~")) if isinstance(node, dict) else None
    return node


def _command_blocks(body: str, start: int) -> dict[str, tuple[int, list[str]]]:
    """Fenced ``bash`` blocks keyed by their label (``launch``, ``connect`` or ``owner-host``)."""
    found: dict[str, tuple[int, list[str]]] = {}
    for line, info, text in fenced_blocks(body):
        parts = info.split()
        if not parts or parts[0] != "bash":
            continue
        label = parts[1] if len(parts) > 1 else "launch"
        if _SHELL.search(text):
            raise CannotRun(f"{GATE}: command block at line {start + line} uses an unsupported command grammar")
        found[label] = (start + line, shlex.split(text))
    return found


def _check_config(rec: PatternRecord, root: Path, result: Result) -> None:
    raw = require(GATE, root, rec.config_path or "") if rec.config_path else None
    if raw is None:
        result.findings.append(f"{rec.id}: supported pattern declares no MCP configuration")
        return
    try:
        server = _pointer(json.loads(raw.decode("utf-8")), rec.config_pointer or "")
    except ValueError as exc:
        result.findings.append(f"{rec.config_path}: malformed JSON: {exc}")
        return
    if not isinstance(server, dict):
        result.findings.append(f"{rec.config_path}: pointer {rec.config_pointer} does not resolve to a server object")
        return
    where = f"{rec.config_path}#{rec.config_pointer}"
    if rec.id == "uv-stdio":
        if list(rec.argv) != [server.get("command"), *server.get("args", [])]:
            result.findings.append(f"{where}: command/args differ from the launch argv {list(rec.argv)}")
        if rec.transport != "stdio" or server.get("type", "stdio") != "stdio":
            result.findings.append(f"{where}: transport must be stdio")
    elif rec.id in {"uv-local-http", "local-container-http"}:
        url = str(server.get("url", ""))
        if not re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/", url) or rec.transport not in {
            "http",
            "streamable-http",
        }:
            result.findings.append(f"{where}: a local http pattern needs a loopback http url, found {url!r}")
        if "command" in server:
            result.findings.append(f"{where}: an http configuration must not spawn a command")
    else:
        url = str(server.get("url", ""))
        if not _SAFE_HOST.match(url):
            result.findings.append(f"{where}: remote url {url!r} is not a safe example endpoint")
        if "command" in server or "args" in server:
            result.findings.append(f"{where}: a hosted url has no local spawn command")
    env = server.get("env", {})
    for name in sorted(set(rec.env) ^ set(env)):
        result.findings.append(f"{where}: environment binding {name} differs between export and configuration")
    for name, value in env.items():
        if name in rec.env and str(value) != rec.env[name]:
            result.findings.append(f"{where}: environment binding {name} differs from the export")
        if not _SOURCED.match(str(value)):
            result.findings.append(f"{where}: environment binding {name} must be sourced, not a literal")


def check(root: Path) -> Result:
    matrix = load_matrix(root)
    result = Result()
    if tuple(sorted(matrix.patterns)) != tuple(sorted(PATTERNS)):
        missing = sorted(set(PATTERNS) - set(matrix.patterns))
        extra = sorted(set(matrix.patterns) - set(PATTERNS))
        result.findings.append(
            f"export: pattern ids must be exactly {list(PATTERNS)} (missing {missing}, extra {extra})"
        )
    readme = require(GATE, root, matrix.readme).decode("utf-8", errors="replace")
    result.lines.append(f"matrix owner={matrix.owner} digest={matrix.digest} runtime={matrix.runtime}")
    for pid in PATTERNS:
        rec = matrix.patterns.get(pid)
        if rec is None:
            continue
        section = _section(readme, pid)
        if section is None:
            result.findings.append(f"{matrix.readme}: no documentation anchor ### {pid}")
            continue
        start, body = section
        blocks = _command_blocks(body, start)
        if rec.status == "constrained":
            if not rec.reason or not rec.owner_evidence:
                result.findings.append(f"{pid}: a constrained pattern needs a reason and owner evidence")
            if blocks:
                result.findings.append(
                    f"{matrix.readme}:{start}: constrained pattern {pid} advertises a runnable command"
                )
            result.lines.append(
                f"pattern id={pid} state=unsupported reason={redact(rec.reason or '')} owner-evidence={rec.owner_evidence}"
            )
            continue
        _check_config(rec, root, result)
        label = "connect" if pid == "remote-container-url" else "launch"
        documented = blocks.get(label)
        if pid == "remote-container-url":
            if documented is not None and documented[1]:
                result.findings.append(
                    f"{matrix.readme}:{documented[0]}: a hosted url has nothing to launch locally; connect instructions carry no argv"
                )
            owner = blocks.get("owner-host")
            if owner is None or list(rec.owner_argv) != owner[1]:
                result.findings.append(
                    f"{matrix.readme}:{start}: separate owner-host launch instructions are missing or differ from the export"
                )
        elif documented is None:
            result.findings.append(f"{matrix.readme}:{start}: pattern {pid} documents no {label} command")
        elif list(rec.argv) != documented[1]:
            result.findings.append(
                f"{matrix.readme}:{documented[0]}: {pid} command {documented[1]} differs from the export {list(rec.argv)}"
            )
        if pid == "local-container-http":
            if not rec.argv or rec.argv[0] != matrix.runtime:
                result.findings.append(f"{pid}: argv must launch the declared {matrix.runtime} runtime")
            if not rec.image or rec.image not in rec.argv:
                result.findings.append(f"{pid}: image reference {rec.image!r} is not in the launch argv")
        if pid.startswith("uv-") and (not rec.package or rec.package not in rec.argv):
            result.findings.append(f"{pid}: package {rec.package!r} is not in the launch argv")
        loc = documented[0] if documented else start
        result.lines.append(
            f"pattern id={pid} state=supported capability={rec.capability} config={rec.config_path}#{rec.config_pointer} "
            f"command={matrix.readme}:{loc} argv={list(documented[1]) if documented else []} prerequisites={list(rec.prerequisites)} "
            "validation=syntax-and-contract"
        )
    for pid, receipt in sorted(matrix.receipts.items()):
        result.lines.append(
            f"runtime-receipt id={pid} version={receipt.get('version')} digest={receipt.get('digest')} source=owner"
        )
    if not matrix.receipts:
        result.lines.append("runtime-receipt none: documentation parity does not certify a deployment")
    unsupported = [p for p, r in matrix.patterns.items() if r.status != "supported"]
    result.lines.append(f"coverage {'incomplete' if unsupported else 'complete'} unsupported={sorted(unsupported)}")
    if unsupported and matrix.require_runnable:
        result.findings.append(
            f"export: the contract requires four runnable patterns but {sorted(unsupported)} are constrained"
        )
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=GATE, description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return finish(GATE, "deployment documentation", check(repo_root(parser.parse_args(argv).root)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
