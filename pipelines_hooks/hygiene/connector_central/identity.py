"""Connector identity rules (PIPE-GATES-R016.100): one name, the SDK identity, everywhere.

* ``id.name``: a hard-coded ``_SOURCE = "<name>"`` in ``<pkg>/kg_*.py`` whose value is not the entry-point name becomes
  ``_SOURCE = connector_name("<pkg>")``; ``connector:`` in ``<pkg>/ontology/mappings/*.yaml`` is set to the entry-point name.
  A value already equal to the identity (or an ingest rule that removed the constant) is left alone.
* ``pl.w`` (workflow refs) lives in this module with the other repo-wide text rules: ``uses: Knuckles-Team/pipelines/...@<ref>``
  with any ref but ``main`` becomes ``@main`` (pipelines is always referenced at main).
"""

from __future__ import annotations

import ast
import re

from pipelines_hooks.hygiene.connector_central.base import Ctx, rule
from pipelines_hooks.hygiene.connector_central.pipelines import pipelines_root

ORDER = ("id.name", "pl.w", "pl.y")
_IMPORT = "from agent_connector_sdk.connector_identity import connector_name"
_YAML_CONNECTOR = re.compile(r"(?m)^(connector:[ \t]*)([\"']?)([^\s\"'#]+)\2([ \t]*(?:#.*)?)$")
_USES = re.compile(
    r"(?m)^(\s*(?:-\s*)?uses:\s*Knuckles-Team/pipelines/\.github/workflows/[\w.-]+\.ya?ml@)(?!main\b)([^\s#]+)"
)


def _source_literals(text: str) -> list[ast.Assign]:
    tree = ast.parse(text)
    return [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "_SOURCE"
        and isinstance(n.value, ast.Constant)
        and isinstance(n.value.value, str)
    ]


def _add_import(text: str) -> str:
    if _IMPORT in text:
        return text
    tree = ast.parse(text)
    imports = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
    if not imports:
        return _IMPORT + "\n" + text
    last = imports[-1].end_lineno or imports[-1].lineno
    lines = text.splitlines(keepends=True)
    lines.insert(last, _IMPORT + "\n")
    return "".join(lines)


@rule("id.name")
def connector_names(ctx: Ctx) -> None:
    for path in sorted(ctx.pkg.glob("kg_*.py")):
        rel = ctx.rel(path)
        text = path.read_text(encoding="utf-8")
        try:
            hits = [n for n in _source_literals(text) if n.value.value != ctx.fleet]  # type: ignore[attr-defined]
        except SyntaxError:
            ctx.note("id.name", "file does not parse", rel, blocking=True)
            continue
        if not hits:
            continue
        if len(hits) != 1:
            ctx.note("id.name", "more than one hard-coded _SOURCE", rel, blocking=True)
            continue
        node = hits[0]
        lines = text.splitlines(keepends=True)
        lines[node.lineno - 1 : node.end_lineno] = [f'_SOURCE = connector_name("{ctx.pkg_name}")\n']
        ctx.write(rel, _add_import("".join(lines)), "id.name")
    for path in sorted((ctx.pkg / "ontology" / "mappings").glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        m = _YAML_CONNECTOR.search(text)
        if m and m.group(3) != ctx.fleet:
            ctx.write(ctx.rel(path), text[: m.start(3)] + ctx.fleet + text[m.end(3) :], "id.name")


@rule("pl.w")
def workflow_refs(ctx: Ctx) -> None:
    for path in sorted((ctx.root / ".github" / "workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        new = _USES.sub(lambda m: m.group(1) + "main", text)
        if new != text:
            ctx.write(ctx.rel(path), new, "pl.w")


ORG_SITE = """name: Notify org site

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  notify:
    uses: Knuckles-Team/pipelines/.github/workflows/notify_org_site.yml@main
    secrets: inherit
"""


@rule("pl.y")
def org_site(ctx: Ctx) -> None:
    """``org-site.yml`` has exactly this content; skipped (silently) while pipelines main has no ``notify_org_site.yml``."""
    if not (pipelines_root(ctx) / ".github" / "workflows" / "notify_org_site.yml").is_file():
        return
    ctx.write(".github/workflows/org-site.yml", ORG_SITE, "pl.y")
