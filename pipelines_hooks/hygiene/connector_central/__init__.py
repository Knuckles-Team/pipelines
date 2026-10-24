"""connector-ontology-map migrate --central: the one central connector migration (PIPE-GATES-R016.50 to R016.100).

Applies four rule sets in a fixed order, deterministic and idempotent, per connector repo:

1. wave 1 (SDK 0.5): ``Connector``/``run()``, version from metadata, ``load_declaration``, one entry point;
2. auth: ``client_factory`` declarations (exact shapes only; otherwise a review item carrying the proposed declaration);
3. ingest (SDK 0.5.2): ``kg_ingest`` plumbing becomes ``SourceStream`` and mappers;
4. wave 1 tests (scaffold tests by fingerprint), then the pipelines-owned rules (version, rendered containers,
   generated ontology artifacts, shared pre-commit config, security scaffold, bootstrap, API parity).

A rule rewrites exactly or records a review item and leaves the files alone. The patch version is bumped once, only when
some rule changed something, so a second run changes nothing.
"""

from __future__ import annotations

import datetime
import importlib
import re
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

MODULES = ("wave1", "auth", "ingest", "pipelines")
FINAL_STEP = "central"


def load_rules() -> dict[str, Any]:
    """Import every rule module (registering its rules) and return ``{module: module object}``."""
    return {name: importlib.import_module(f"pipelines_hooks.hygiene.connector_central.{name}") for name in MODULES}


def rule_order() -> list[str]:
    """The fixed rule order: wave 1, auth, ingest, wave 1 tests, pipelines."""
    mods = load_rules()
    order = [*mods["wave1"].ORDER, *mods["auth"].ORDER, *mods["ingest"].ORDER, *mods["wave1"].ORDER_LAST]
    order += mods["pipelines"].ORDER
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
        f"- Central connector migration: requires `agent-connector-sdk>={SDK_FLOOR}`; server bootstrap, version, "
        "containers, ontology artifacts, security scaffold and pre-commit config are provided centrally.\n\n"
    )
    ctx.write("CHANGELOG.md", text[: first.start()] + entry + text[first.start() :])


def refresh_lock(ctx: Ctx) -> None:
    """``uv lock`` against PyPI; with ``sdk_path`` (dry run, 0.5.2 unpublished) the lock cannot resolve and is skipped."""
    if ctx.options.get("no_lock") or ctx.options.get("sdk_path"):
        return
    r = subprocess.run(
        ["uv", "lock", "--upgrade-package", "agent-connector-sdk"], cwd=ctx.root, capture_output=True, text=True
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
        r.add("discover", "exactly one agent_connector_sdk.connector entry point resolving to a package is required")
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
    scaffold_delta(ctx)
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


#: Top-level entries the canonical scaffold (universal-skills ``scaffold_connector.py``) does not have and that no rule owns.
SCAFFOLD_DELTA = (
    "MANIFEST.in",
    "requirements.txt",
    ".dockerignore",
    ".env.example",
    "mcp_config.json",
    "opencode.json",
)


def scaffold_delta(ctx: Ctx) -> None:
    """Informational: files still present that the canonical scaffold tree does not contain (no rule deletes them)."""
    left = [n for n in SCAFFOLD_DELTA if ctx.exists(n)]
    if left:
        ctx.note("scaffold-delta", "present but not in the canonical scaffold tree: " + ", ".join(left))


def rule_counts() -> dict[str, int]:
    """Rule count by source document."""
    out: dict[str, int] = {}
    for _rid, source, _text in RULE_TABLE:
        out[source] = out.get(source, 0) + 1
    return out
