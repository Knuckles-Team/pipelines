"""tool-mapping: the published tool/method inventory equals the documentation rows.

Declared in ``.config/tool-mapping.json``: the owner-exported registry (``tool-registry/1``,
the only tool authority; pipelines keeps no second one), the registry digest the export
was made at, and the reference page.  The page is rendered from the registry (``--render
DEST``) and checked against it: exact set equality of tools and nested methods, every
parameter (type, requiredness, default), the result (or an explicit ``void``), and at
least one schema-valid request/result example.  A schema-valid example is documentation
parity, never evidence that a deployed method succeeds.  No repository module is imported.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.docs.gate_io import (
    Result,
    finish,
    load_json,
    require,
    sha,
    strict_keys,
    type_ok,
)

GATE = "tool-mapping"
DECLARATION = ".config/tool-mapping.json"
REGISTRY_FORMAT = "tool-registry/1"
_MARK = re.compile(r"<!-- tool-mapping registry=(?P<digest>\w+) -->")
_HEADING = re.compile(r"^(?P<hashes>#{3,6}) (?P<id>\S+)\s*$", re.M)


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    required: bool
    default: Any


@dataclass(frozen=True)
class Method:
    """One method: identity, registry pointer, parameters, result schema and examples."""

    id: str
    pointer: str
    parameters: tuple[Parameter, ...]
    result: tuple[tuple[str, str], ...] | None  # None is void
    examples: tuple[dict[str, Any], ...]
    children: tuple[Method, ...] = ()

    def walk(self) -> list[Method]:
        return [self, *(m for child in self.children for m in child.walk())]


@dataclass(frozen=True)
class ToolDocMapping:
    """The checked registry: producer identity, digest and every tool/method (nested included)."""

    producer: str
    version: str
    digest: str
    methods: tuple[Method, ...]
    tools: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        ids = [m.id for top in self.methods for m in top.walk()]
        if len(ids) != len(set(ids)):
            raise CannotRun(f"{GATE}: duplicate method identity in the registry")

    def inventory(self) -> list[Method]:
        return [m for top in self.methods for m in top.walk()]


def _method(raw: object, pointer: str) -> Method:
    data = strict_keys(
        GATE,
        pointer,
        raw,
        {"id", "parameters", "result", "examples", "methods"},
        {"id", "parameters", "result", "examples"},
    )
    params = []
    for i, item in enumerate(data["parameters"]):
        p = strict_keys(
            GATE,
            f"{pointer}/parameters/{i}",
            item,
            {"name", "type", "required", "default"},
            {"name", "type", "required"},
        )
        type_ok(None, p["type"])
        params.append(Parameter(p["name"], p["type"], bool(p["required"]), p.get("default")))
    result = data["result"]
    if result == {"type": "void"}:
        fields = None
    else:
        r = strict_keys(GATE, f"{pointer}/result", result, {"type", "fields"}, {"type", "fields"})
        if r["type"] != "object":
            raise CannotRun(f"{GATE}: {pointer}/result has an ambiguous schema")
        fields = tuple((f["name"], f["type"]) for f in r["fields"])
        for _n, t in fields:
            type_ok(None, t)
    children = tuple(_method(c, f"{pointer}/methods/{i}") for i, c in enumerate(data.get("methods", [])))
    return Method(data["id"], pointer, tuple(params), fields, tuple(data["examples"]), children)


def load_registry(root: Path) -> tuple[ToolDocMapping, str, str]:
    """The declaration's registry, refused as stale when its digest differs from the declared one."""
    decl, _ = load_json(GATE, root, DECLARATION)
    decl = strict_keys(
        GATE,
        DECLARATION,
        decl,
        {"schema", "registry", "registry_digest", "table"},
        {"schema", "registry", "registry_digest", "table"},
    )
    if decl["schema"] != 1:
        raise CannotRun(f"{GATE}: unsupported declaration schema {decl['schema']!r}")
    data, raw = load_json(GATE, root, decl["registry"])
    if not isinstance(data, dict) or data.get("format") != REGISTRY_FORMAT:
        raise CannotRun(f"{GATE}: unsupported registry format in {decl['registry']}")
    if not data.get("producer") or not data.get("version"):
        raise CannotRun(f"{GATE}: {decl['registry']} carries no producer evidence")
    digest = sha(raw)
    if digest != decl["registry_digest"]:
        raise CannotRun(
            f"{GATE}: stale registry export {decl['registry']}: digest {digest} != declared {decl['registry_digest']}"
        )
    methods: list[Method] = []
    tools: list[str] = []
    for i, tool in enumerate(data.get("tools", [])):
        t = strict_keys(GATE, f"/tools/{i}", tool, {"id", "methods"}, {"id", "methods"})
        tools.append(t["id"])
        methods.extend(_method(m, f"/tools/{i}/methods/{j}") for j, m in enumerate(t["methods"]))
    mapping = ToolDocMapping(data["producer"], str(data["version"]), digest, tuple(methods), tuple(tools))
    return mapping, decl["registry"], decl["table"]


def _fmt_default(value: object) -> str:
    return "none" if value is None else json.dumps(value)


def render(mapping: ToolDocMapping) -> str:
    """The reference page for the registry: one section per method, nested methods one level deeper."""
    out = [f"<!-- tool-mapping registry={mapping.digest} -->", "# Tool reference", ""]

    def emit(method: Method, depth: int) -> None:
        out.append(f"{'#' * min(3 + depth, 6)} {method.id}")
        out.append("")
        if method.parameters:
            for p in method.parameters:
                out.append(
                    f"- parameter `{p.name}` type={p.type} required={str(p.required).lower()} default={_fmt_default(p.default)}"
                )
        else:
            out.append("- parameters: none")
        if method.result is None:
            out.append("- result: void")
        else:
            out.extend(f"- result field `{n}` type={t}" for n, t in method.result)
            if not method.result:
                out.append("- result: empty object")
        for ex in method.examples:
            out.extend(["", "Request example:", "```json", json.dumps(ex["request"], sort_keys=True), "```"])
            out.extend(["", "Result example:", "```json", json.dumps(ex["result"], sort_keys=True), "```"])
        out.append("")
        for child in method.children:
            emit(child, depth + 1)

    for top in mapping.methods:
        emit(top, 0)
    return "\n".join(out)


def _example_findings(method: Method, where: str, example: object) -> list[str]:
    found: list[str] = []
    if not isinstance(example, dict) or set(example) != {"request", "result"}:
        return [f"{where}: example of {method.id} must carry exactly request and result"]
    request, result = example["request"], example["result"]
    names = {p.name: p for p in method.parameters}
    if not isinstance(request, dict):
        return [f"{where}: request example of {method.id} is not an object"]
    for p in method.parameters:
        if p.required and p.name not in request:
            found.append(f"{where}: request example of {method.id} omits required parameter {p.name}")
    for key, value in request.items():
        if key not in names:
            found.append(f"{where}: request example of {method.id} carries undeclared parameter {key}")
        elif not type_ok(value, names[key].type):
            found.append(f"{where}: request example of {method.id} parameter {key} is not {names[key].type}")
    if method.result is None:
        if result is not None:
            found.append(f"{where}: void method {method.id} has a non-null result example")
    elif not isinstance(result, dict):
        found.append(f"{where}: result example of {method.id} is not an object")
    else:
        declared = dict(method.result)
        for key, value in result.items():
            if key not in declared:
                found.append(f"{where}: result example of {method.id} carries undeclared field {key}")
            elif not type_ok(value, declared[key]):
                found.append(f"{where}: result example of {method.id} field {key} is not {declared[key]}")
        for key in declared:
            if key not in result:
                found.append(f"{where}: result example of {method.id} omits field {key}")
    return found


def _sections(text: str) -> dict[str, tuple[int, str]]:
    heads = list(_HEADING.finditer(text))
    out: dict[str, tuple[int, str]] = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out[h["id"]] = (text[: h.start()].count("\n") + 1, text[h.end() : end])
    return out


def _section_findings(method: Method, table: str, line: int, body: str, found: list[str]) -> tuple[int, int, int]:
    where = f"{table}:{line}"
    seen = {
        m["name"]: m
        for m in re.finditer(
            r"^- parameter `(?P<name>[^`]+)` type=(?P<type>\S+) required=(?P<req>\w+) default=(?P<default>.*)$",
            body,
            re.M,
        )
    }
    if method.parameters:
        for p in method.parameters:
            row = seen.pop(p.name, None)
            if row is None:
                found.append(
                    f"{where}: {method.id} documents no parameter {p.name} (registry {method.pointer}/parameters)"
                )
            elif (row["type"], row["req"], row["default"]) != (
                p.type,
                str(p.required).lower(),
                _fmt_default(p.default),
            ):
                found.append(
                    f"{where}: {method.id} parameter {p.name} is documented as {row['type']} required={row['req']} default={row['default']}, registry has {p.type} required={str(p.required).lower()} default={_fmt_default(p.default)}"
                )
    elif "- parameters: none" not in body:
        found.append(f"{where}: {method.id} does not describe its empty parameter set")
    found.extend(f"{where}: {method.id} documents extra parameter {name}" for name in seen)
    fields = {
        m["name"]: m["type"] for m in re.finditer(r"^- result field `(?P<name>[^`]+)` type=(?P<type>\S+)$", body, re.M)
    }
    if method.result is None:
        if "- result: void" not in body:
            found.append(f"{where}: {method.id} does not describe its void result")
        if fields:
            found.append(f"{where}: {method.id} documents result fields for a void method")
    else:
        for name, typ in method.result:
            if name not in fields:
                found.append(
                    f"{where}: {method.id} documents no result field {name} (registry {method.pointer}/result)"
                )
            elif fields[name] != typ:
                found.append(
                    f"{where}: {method.id} result field {name} is documented as {fields[name]}, registry has {typ}"
                )
        found.extend(
            f"{where}: {method.id} documents extra result field {n}"
            for n in set(fields) - {n for n, _ in method.result}
        )
    requests = [
        b
        for b in re.finditer(
            r"Request example:\n```json\n(?P<j>.*?)\n```\n\nResult example:\n```json\n(?P<r>.*?)\n```", body, re.S
        )
    ]
    if not requests:
        found.append(f"{where}: {method.id} has no request/result example (registry {method.pointer}/examples)")
    for m in requests:
        try:
            pair = {"request": json.loads(m["j"]), "result": json.loads(m["r"])}
        except ValueError:
            found.append(f"{where}: {method.id} example is not valid JSON")
            continue
        found.extend(_example_findings(method, where, pair))
    return len(method.parameters), 0 if method.result is None else len(method.result), len(requests)


def check(root: Path) -> Result:
    mapping, registry, table = load_registry(root)
    page = require(GATE, root, table).decode("utf-8", errors="replace")
    result = Result()
    mark = _MARK.search(page)
    if mark is None or mark["digest"] != mapping.digest:
        raise CannotRun(
            f"{GATE}: {table} was generated from registry {mark['digest'] if mark else 'unknown'}, not {mapping.digest}"
        )
    result.lines.append(
        f"registry path={registry} producer={mapping.producer} version={mapping.version} digest={mapping.digest}"
    )
    inventory = mapping.inventory()
    for method in inventory:
        for i, ex in enumerate(method.examples):
            result.findings.extend(_example_findings(method, f"{registry}{method.pointer}/examples/{i}", ex))
        if not method.examples:
            result.findings.append(f"{registry}{method.pointer}: {method.id} declares no example")
    sections = _sections(page)
    params = results = examples = 0
    for method in inventory:
        found = sections.get(method.id)
        if found is None:
            result.findings.append(
                f"{registry}{method.pointer}: {method.id} has no row in {table} (expected section ### {method.id})"
            )
            result.lines.append(f"comparison id={method.id} row=absent")
            continue
        line, body = found
        p, r, e = _section_findings(method, table, line, body, result.findings)
        params, results, examples = params + p, results + r, examples + e
        result.lines.append(
            f"comparison id={method.id} row={table}:{line} anchor=#{method.id} registry={method.pointer}"
        )
    for extra in sorted(set(sections) - {m.id for m in inventory}):
        result.findings.append(f"{table}:{sections[extra][0]}: row {extra} is not in the registry")
    result.lines.append(f"inventory tools={list(mapping.tools)} methods={[m.id for m in inventory]}")
    result.lines.append(
        f"counts methods={len(inventory)} parameters={params} result-fields={results} examples={examples}"
    )
    result.lines.append(
        "evidence=schema-parity runtime=none: schema-valid examples do not prove a deployed method succeeds"
    )
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=GATE, description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--render", type=Path, metavar="DEST", help="write the reference page to a new file")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    if args.render is not None:
        if args.render.exists():
            raise CannotRun(f"{GATE}: refusing to overwrite {args.render}")
        mapping, _registry, _table = load_registry(root)
        args.render.parent.mkdir(parents=True, exist_ok=True)
        args.render.write_text(render(mapping), encoding="utf-8")
        print(f"rendered {args.render}")
        return 0
    return finish(GATE, "tool mapping", check(root))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
