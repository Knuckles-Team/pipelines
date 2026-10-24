"""Connector identity rules (PIPE-GATES-R016.100): one name, the SDK identity, everywhere.

* ``id.name``: a hard-coded ``_SOURCE = "<name>"`` (or the constant an ``IngestBinding``/``SourceStream`` takes as
  ``connector=``, e.g. ``_CONNECTOR``) in ``<pkg>/kg_*.py`` whose value is not the entry-point name becomes
  ``<constant> = connector_name("<pkg>")``; ``connector:`` in ``<pkg>/ontology/mappings/*.yaml`` is set to the entry-point name.
  A value already equal to the identity (or an ingest rule that removed the constant) is left alone.
* ``pl.w`` (workflow refs) lives in this module with the other repo-wide text rules: ``uses: Knuckles-Team/pipelines/...@<ref>``
  with any ref but ``main`` becomes ``@main`` (pipelines is always referenced at main).
"""

from __future__ import annotations

import ast
import re
import sys

from pipelines_hooks.hygiene.connector_central.base import Ctx, rule
from pipelines_hooks.hygiene.connector_central.pipelines import pipelines_root

ORDER = ("id.name", "pl.w", "pl.y", "pl.z", "pl.aa", "pl.ab", "pl.ac", "pl.ad", "pl.ae")
_IMPORT = "from agent_connector_sdk.connector_identity import connector_name"
_YAML_CONNECTOR = re.compile(r"(?m)^(connector:[ \t]*)([\"']?)([^\s\"'#]+)\2([ \t]*(?:#.*)?)$")
_USES = re.compile(
    r"(?m)^(\s*(?:-\s*)?uses:\s*Knuckles-Team/pipelines/\.github/workflows/[\w.-]+\.ya?ml@)(?!main\b)([^\s#]+)"
)


def _binding_names(tree: ast.Module) -> set[str]:
    """Names passed as ``connector=<Name>`` to an ``IngestBinding`` or ``SourceStream`` call (``_CONNECTOR``, ``NAME``, ...)."""
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and ast.unparse(n.func).rsplit(".", 1)[-1] in ("IngestBinding", "SourceStream"):
            out |= {k.value.id for k in n.keywords if k.arg == "connector" and isinstance(k.value, ast.Name)}
    return out


def _source_literals(text: str) -> list[ast.Assign]:
    """Module-level ``<name> = "<literal>"`` where ``<name>`` is ``_SOURCE`` or the name a binding takes as ``connector=``."""
    tree = ast.parse(text)
    names = {"_SOURCE"} | _binding_names(tree)
    return [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id in names
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


def _retarget_tests(ctx: Ctx, old_names: set[str]) -> None:
    """``<x>.connector == "<old name>"`` in a test now compares with the fleet name the ingest module derives."""
    for path in sorted((ctx.root / "tests").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if not any(old in text for old in old_names):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        spans: list[tuple[int, int, int]] = []
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.Eq | ast.NotEq)):
                continue
            pair = (n.left, n.comparators[0])
            for attr, const in (pair, pair[::-1]):
                if (
                    isinstance(attr, ast.Attribute)
                    and attr.attr == "connector"
                    and isinstance(const, ast.Constant)
                    and const.value in old_names
                    and const.lineno == const.end_lineno
                ):
                    spans.append((const.lineno, const.col_offset, const.end_col_offset or 0))
        if not spans:
            continue
        rows = text.split("\n")
        for ln, col, end in sorted(spans, reverse=True):
            raw = rows[ln - 1].encode("utf-8")
            rows[ln - 1] = (raw[:col] + f'"{ctx.fleet}"'.encode() + raw[end:]).decode("utf-8")
        ctx.write(ctx.rel(path), "\n".join(rows), "id.name")


@rule("id.name")
def connector_names(ctx: Ctx) -> None:
    renamed: set[str] = set()
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
        targets = [n.targets[0].id for n in hits if isinstance(n.targets[0], ast.Name)]
        if len(set(targets)) != len(targets):
            ctx.note("id.name", "more than one hard-coded connector name constant of the same name", rel, blocking=True)
            continue
        renamed.update(str(n.value.value) for n in hits)  # type: ignore[attr-defined]
        lines = text.splitlines(keepends=True)
        for node, name in sorted(zip(hits, targets, strict=True), key=lambda x: x[0].lineno, reverse=True):
            lines[node.lineno - 1 : node.end_lineno] = [f'{name} = connector_name("{ctx.pkg_name}")\n']
        ctx.write(rel, _add_import("".join(lines)), "id.name")
    if renamed:
        _retarget_tests(ctx, renamed)
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


_SPEC_TITLE = re.compile(r"(?m)^#\s+(\S+)\s+[\u2014-]+\s+(.+?)\s*$")
_NO_SPECS = "This repository has no local spec yet."


@rule("pl.z")
def spec_index(ctx: Ctx) -> None:
    """Every ``specs/<area>/spec.md`` is indexed in ``specs/README.md`` (the ``spec-standard`` gate fails otherwise)."""
    readme = ctx.root / "specs" / "README.md"
    if not readme.is_file():
        return
    text = readme.read_text(encoding="utf-8")
    lines: list[str] = []
    for spec in sorted((ctx.root / "specs").glob("*/spec.md")):
        area = spec.parent.name
        if area.startswith("_") or f"({area}/spec.md)" in text:
            continue
        m = _SPEC_TITLE.search(spec.read_text(encoding="utf-8"))
        if m is None:
            ctx.note(
                "pl.z", f"specs/{area}/spec.md has no `# <ID> \u2014 <title>` heading to index", f"specs/{area}/spec.md"
            )
            continue
        lines.append(f"- [`{m.group(1)}`]({area}/spec.md) \u2014 {m.group(2).rstrip('.')}.")
    if not lines:
        return
    block = "\n".join(lines)
    new = text.replace(_NO_SPECS, block, 1) if _NO_SPECS in text else text.rstrip("\n") + "\n" + block + "\n"
    ctx.write("specs/README.md", new, "pl.z")


def _docs_dir(ctx: Ctx) -> str | None:
    """The MkDocs content directory: ``docs_dir`` of ``mkdocs.yml`` or ``docs``; None without a MkDocs site."""
    if not ctx.exists("mkdocs.yml"):
        return None
    m = re.search(r"(?m)^docs_dir:\s*[\"']?([\w./-]+)[\"']?\s*$", ctx.read("mkdocs.yml"))
    return m.group(1) if m else "docs"


@rule("pl.aa")
def theme_files(ctx: Ctx) -> None:
    """Missing or stale generated theme files are synced from the canonical copy (``scripts/sync_mkdocs_theme.py``).

    Only the generated-file mismatches are acted on; a runtime-diagram reference in a page is reported, not edited.
    """
    import importlib.util

    docs = _docs_dir(ctx)
    root = pipelines_root(ctx)
    script = root / "scripts" / "sync_mkdocs_theme.py"
    if docs is None or not script.is_file() or not (ctx.root / docs).is_dir():
        return
    spec = importlib.util.spec_from_file_location("sync_mkdocs_theme", script)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_mkdocs_theme"] = mod  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(mod)
    try:
        mismatches = mod.sync_theme(source_root=root, repository_root=ctx.root, content_source=docs, mode="check")
    except (OSError, mod.ThemeSyncError) as exc:
        ctx.note("pl.aa", f"theme check cannot run: {exc}", docs, blocking=True)
        return
    stale = [m for m in mismatches if m.startswith(("missing generated file", "generated file differs"))]
    for other in mismatches:
        if other not in stale:
            ctx.note("pl.aa", other, docs, blocking=False)
    if not stale:
        return
    mod.sync_theme(source_root=root, repository_root=ctx.root, content_source=docs, mode="sync")
    for m in stale:
        rel = m.split(": ", 1)[1]
        ctx.changed.add(rel)
        if "pl.aa" not in ctx.applied:
            ctx.applied.append("pl.aa")


NEUTRAL_AUTHOR_NAME = "Repository Maintainers"
NEUTRAL_AUTHOR_EMAIL = "maintainers@knuckles.team"
_AUTHORS = re.compile(r"(?m)^\[\[project\.authors\]\]\n((?:(?!\[)[^\n]*\n?)*)")
_AUTHOR_FIELD = re.compile(r'(?m)^(name|email)\s*=\s*"[^"\n]*"[ \t]*$')


@rule("pl.ab")
def neutral_author(ctx: Ctx) -> None:
    """Every ``[[project.authors]]`` block carries the neutral organisation name and role address (tracked-privacy).

    A block whose fields are not plain ``name``/``email`` strings is left alone and reviewed.
    """
    text = ctx.read("pyproject.toml")

    def fix(m: re.Match[str]) -> str:
        body = m.group(1)
        fields = {f.group(1) for f in _AUTHOR_FIELD.finditer(body)}
        if not fields <= {"name", "email"} or {x for x in re.findall(r"(?m)^(\w+)\s*=", body)} - {"name", "email"}:
            ctx.note("pl.ab", "authors block has fields other than plain name/email strings", "pyproject.toml")
            return m.group(0)
        new = _AUTHOR_FIELD.sub(
            lambda f: (
                f'name = "{NEUTRAL_AUTHOR_NAME}"' if f.group(1) == "name" else f'email = "{NEUTRAL_AUTHOR_EMAIL}"'
            ),
            body,
        )
        return "[[project.authors]]\n" + new

    new_text = _AUTHORS.sub(fix, text)
    if new_text != text:
        ctx.write("pyproject.toml", new_text, "pl.ab")


_CRED_URI = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)([^\s/@:`'\"]+):([^\s/@`'\"]+)(@)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE = re.compile(r"`[^`\n]+`")
PLACEHOLDER_USER = "USER"
PLACEHOLDER_SECRET = "PASSWORD"


def _mask_uris(text: str) -> str:
    from pipelines_hooks.security.placeholders import is_placeholder_secret

    def sub(m: re.Match[str]) -> str:
        if is_placeholder_secret(m.group(3)):
            return m.group(0)
        return f"{m.group(1)}{PLACEHOLDER_USER}:{PLACEHOLDER_SECRET}{m.group(4)}"

    return _CRED_URI.sub(sub, text)


def mask_markdown(text: str) -> str:
    """Example credential URIs inside fenced code blocks and inline code become ``scheme://USER:PASSWORD@host``."""
    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        m = _FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            out.append(line)
        elif fence:
            out.append(_mask_uris(line))
        else:
            out.append(_INLINE.sub(lambda c: _mask_uris(c.group(0)), line))
    return "\n".join(out)


@rule("pl.ac")
def docs_credential_examples(ctx: Ctx) -> None:
    """Only ``README.md`` and ``docs/**/*.md``, only code (fences and inline code), only a secret the gate would flag."""
    files = [ctx.root / "README.md", *sorted((ctx.root / "docs").glob("**/*.md"))]
    for path in files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        new = mask_markdown(text)
        if new != text:
            ctx.write(ctx.rel(path), new, "pl.ac")


#: The fleet's reviewed pins (the same lines `archimate-mcp`, `arr-mcp` and `gitlab-api` already commit).
PINNED_ACTIONS = {
    "actions/checkout": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
    "actions/setup-python": "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
}
_MUTABLE_ACTION = re.compile(
    r"(?m)^(\s*(?:-\s*)?uses:\s*)(actions/(?:checkout|setup-python))@v\d+(?:\.\d+){0,2}[ \t]*$"
)


@rule("pl.ad")
def pin_actions(ctx: Ctx) -> None:
    """A mutable ``@vN`` tag of ``actions/checkout`` or ``actions/setup-python`` becomes the fleet's reviewed SHA pin.

    Other mutable actions are left alone; the connector-security check reports them.
    """
    for path in sorted((ctx.root / ".github" / "workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        new = _MUTABLE_ACTION.sub(lambda m: m.group(1) + PINNED_ACTIONS[m.group(2)], text)
        if new != text:
            ctx.write(ctx.rel(path), new, "pl.ad")


_REV_ASSERT = re.compile(r'(?m)^(\s*assert repo\["rev"\] == )CONTRACT(\s*)$')


@rule("pl.ae")
def publication_test_rev(ctx: Ctx) -> None:
    """``tests/test_publication_workflow.py`` asserts the shared hook repo is pinned to a contract SHA.

    The central pre-commit config references pipelines at ``main`` (policy), so that one assertion expects ``main``;
    the dependency-readiness presence and bare-hook assertions stay as they are.
    """
    rel = "tests/test_publication_workflow.py"
    if not ctx.exists(rel):
        return
    text = ctx.read(rel)
    new = _REV_ASSERT.sub(lambda m: f'{m.group(1)}"main"{m.group(2)}', text)
    if new != text:
        ctx.write(rel, new, "pl.ae")
