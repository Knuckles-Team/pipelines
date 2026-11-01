"""connector-ontology-map migrate --central: the one central connector migration (PIPE-GATES-R016.50 to R016.100).

Applies four rule sets in a fixed order, deterministic and idempotent, per connector repo:

1. wave 1 (SDK 0.5): ``Connector``/``run()``, version from metadata, ``load_declaration``, one entry point;
2. auth: ``client_factory`` declarations (exact shapes only; otherwise a review item carrying the proposed declaration);
3. ingest (SDK 0.5.2): ``kg_ingest`` plumbing becomes ``SourceStream`` and mappers;
4. wave 1 tests (scaffold tests by fingerprint), then the pipelines-owned rules (version, rendered containers,
   generated ontology artifacts, shared pre-commit config, security scaffold, bootstrap, API parity), and last the
   spelling rule (safe typo fixes, identifier words to ``ignore_words``) before the final codespell scan.

A rule rewrites exactly or records a review item and leaves the files alone. The patch version is bumped once, only when
some rule changed something, so a second run changes nothing.
"""

from __future__ import annotations

import ast
import datetime
import importlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pipelines_hooks.hygiene.connector_central.base import (
    RULE_ROWS,
    RULE_TABLE,
    RULES,
    SDK_FLOOR,
    Ctx,
    make_ctx,
)

MODULES = ("wave1", "auth", "ingest", "identity", "pipelines", "scaffold", "spelling")
FINAL_STEP = "central"


def load_rules() -> dict[str, Any]:
    """Import every rule module (registering its rules) and return ``{module: module object}``."""
    return {name: importlib.import_module(f"pipelines_hooks.hygiene.connector_central.{name}") for name in MODULES}


def rule_order() -> list[str]:
    """The fixed rule order: wave 1, auth, ingest, wave 1 tests, pipelines, scaffold."""
    mods = load_rules()
    order = [
        *mods["wave1"].ORDER,
        *mods["auth"].ORDER,
        *mods["ingest"].ORDER,
        *mods["identity"].ORDER,
        *mods["wave1"].ORDER_LAST,
    ]
    order += mods["pipelines"].ORDER
    order += mods["scaffold"].ORDER
    order += mods["spelling"].ORDER
    missing = sorted(set(RULE_ROWS) - set(order))
    if missing:
        raise RuntimeError(f"rules registered but not ordered: {missing}")
    return order


_VERSION = re.compile(r'(?m)^(version\s*=\s*")(\d+)\.(\d+)\.(\d+)(")')


def bump_patch(ctx: Ctx) -> str | None:
    """Bump the static ``[project] version`` patch once; returns the new version."""
    text = ctx.read("pyproject.toml")
    m = _VERSION.search(text)
    if m is None:
        ctx.note(FINAL_STEP, "no static [project] version to bump", "pyproject.toml")
        return None
    new = f"{m.group(2)}.{m.group(3)}.{int(m.group(4)) + 1}"
    ctx.write("pyproject.toml", text[: m.start()] + f"{m.group(1)}{new}{m.group(5)}" + text[m.end() :])
    return new


def add_changelog(ctx: Ctx, version: str, today: str | None = None) -> None:
    """One fixed Keep-a-Changelog entry for the bumped version (release tests pin it)."""
    if not ctx.exists("CHANGELOG.md"):
        return
    text = ctx.read("CHANGELOG.md")
    first = re.search(r"(?m)^## \[", text)
    if first is None or re.search(rf"(?m)^## \[{re.escape(version)}\]", text):
        return
    day = today or datetime.date.today().isoformat()
    entry = (
        f"## [{version}] - {day}\n\n### Changed\n"
        f"- Central connector migration: requires `{ctx.sdk_distribution}>={SDK_FLOOR}`; server bootstrap, version, "
        "containers, ontology artifacts, security scaffold and pre-commit config are provided centrally.\n\n"
    )
    ctx.write("CHANGELOG.md", text[: first.start()] + entry + text[first.start() :])


def _hook_ruff(ctx: Ctx) -> str | None:
    """``uvx ruff@<version>`` for the version the shared pre-commit template pins: the commit hook then finds nothing more.

    A different ruff has different default rules (0.16 enables import sorting by default), so a fixer older or newer than
    the hook leaves findings the hook reports at commit time.
    """
    from pipelines_hooks.hygiene.connector_central.pipelines import pipelines_root

    uvx = shutil.which("uvx")
    template = pipelines_root(ctx) / "templates" / "connector" / "pre-commit-config.yaml"
    if uvx is None or not template.is_file():
        return None
    m = re.search(r"ruff-pre-commit\s+rev:\s*\S+\s*#\s*v(\d+\.\d+\.\d+)", template.read_text(encoding="utf-8"))
    return f"{uvx} ruff@{m.group(1)}" if m else None


def tidy(ctx: Ctx) -> None:
    """Fix and format the files the rules rewrote with the repo's own ruff table, so the commit hooks find nothing.

    Every selected rule runs with its safe fixes (``extend-exclude`` is honoured). A finding ruff cannot fix is a
    blocking review item with its rule ids; nothing is ignored on the way.
    """
    files = [f for f in sorted(ctx.changed) if f.endswith(".py") and (ctx.root / f).is_file()]
    if not files:
        return
    ruff = _hook_ruff(ctx) or shutil.which("ruff") or (f"{shutil.which('uvx')} ruff" if shutil.which("uvx") else None)
    if ruff is None:
        ctx.note("tidy", "ruff is not installed; imports and formatting left to the commit hooks", "", blocking=True)
        return
    base = [*ruff.split(), "--config", str(ctx.root / "pyproject.toml")]
    subprocess.run([*base, "check", "--fix", "--force-exclude", "--quiet", *files], cwd=ctx.root, capture_output=True)
    subprocess.run([*base, "format", "--force-exclude", "--quiet", *files], cwd=ctx.root, capture_output=True)
    left = subprocess.run(
        [*base, "check", "--force-exclude", "--output-format", "json", "--no-cache", *files],
        cwd=ctx.root,
        capture_output=True,
        text=True,
    )
    try:
        found = json.loads(left.stdout or "[]")
    except ValueError:
        ctx.note("tidy", f"ruff check output cannot be read: {(left.stderr or left.stdout)[-300:]}", "", blocking=True)
        return
    by_file: dict[str, list[str]] = {}
    for item in found:
        name = Path(item["filename"])
        try:
            rel = name.resolve().relative_to(ctx.root.resolve()).as_posix()
        except ValueError:
            rel = str(name)
        by_file.setdefault(rel, []).append(f"{item.get('code')} line {item['location']['row']}")
    for rel, hits in sorted(by_file.items()):
        ctx.note("tidy", f"ruff still reports after the fix pass: {', '.join(hits)}", rel, blocking=True)


def spell_check(ctx: Ctx) -> None:
    """Run the central codespell check on the migrated tree; a finding is a blocking review item, never ignored."""
    if not ctx.applied:
        return
    from pipelines_hooks.connector import codespell

    try:
        lines = codespell.findings(ctx.root, extra=sorted(ctx.changed - ctx.deleted))
    except Exception as exc:  # noqa: BLE001 - an unavailable codespell is reported, the migration continues
        ctx.note("codespell", f"codespell could not run: {exc}", "", blocking=False)
        return
    reasons = ctx.options.get("spelling_reasons", {})
    for line in lines:
        rel, _, rest = line.partition(":")
        num, _, finding = rest.strip().partition(": ")
        why = reasons.get(f"{rel}:{num}:{finding.partition(' ==> ')[0]}")
        note = f" [{why}: review by hand]" if why else ""
        ctx.note("codespell", f"central codespell would fail: {rest.strip()}{note}", rel, blocking=True)


def refresh_lock(ctx: Ctx) -> None:
    """``uv lock`` against PyPI; with ``sdk_path`` (dry run, 0.5.2 unpublished) the lock cannot resolve and is skipped."""
    if ctx.options.get("no_lock") or ctx.options.get("sdk_path"):
        return
    r = subprocess.run(
        ["uv", "lock", "--upgrade-package", ctx.sdk_distribution], cwd=ctx.root, capture_output=True, text=True
    )
    if r.returncode:
        ctx.note("lock", "uv lock failed: " + (r.stderr or r.stdout)[-400:], "uv.lock", blocking=True)
    else:
        ctx.changed.add("uv.lock")


def migrate_central(root: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run every central rule on one connector checkout; returns ``{changed, deleted, review, applied, rules}``."""
    root = Path(root)
    ctx = make_ctx(root, options)
    if ctx is None:
        from pipelines_hooks.hygiene.connector_central.base import Review

        r = Review()
        r.add("discover", "exactly one scion_sdk.connector entry point resolving to a package is required")
        return {"changed": [], "deleted": [], "review": r.items, "applied": [], "rules": 0}
    order = rule_order()
    for rid in order:
        before = len(ctx.review.items)
        try:
            RULES[rid](ctx)
        except Exception as exc:  # noqa: BLE001 - a crashing rule is a blocking review item, never a skipped rule
            ctx.review.add(rid, f"rule crashed: {type(exc).__name__}: {exc}", "", True)
        for item in ctx.review.items[before:]:
            item.setdefault("rule", rid)
    tidy(ctx)
    spell_check(ctx)
    for rel in sorted(ctx.changed):
        if rel.endswith(".py"):
            try:
                ast.parse(ctx.read(rel))
            except SyntaxError as exc:
                ctx.review.add(FINAL_STEP, f"a rule left {rel} unparseable: {exc.msg} (line {exc.lineno})", rel, True)
    if ctx.applied:
        version = bump_patch(ctx)
        if version:
            add_changelog(ctx, version)
        refresh_lock(ctx)
    return {
        "changed": sorted(ctx.changed - ctx.deleted),
        "deleted": sorted(ctx.deleted),
        "review": ctx.review.items,
        "applied": ctx.applied,
        "rules": len(order),
    }


def rule_counts() -> dict[str, int]:
    """Rule count by source document."""
    out: dict[str, int] = {}
    for _rid, source, _text in RULE_TABLE:
        out[source] = out.get(source, 0) + 1
    return out
