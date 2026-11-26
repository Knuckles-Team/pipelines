"""Version inventory completeness and the code-enhancer consumer binding.

``project-version-sync --completeness`` discovers every project-version
location in the selected Git snapshot with the versioned static grammar of
``project_version`` and compares it with the configured selectors. A
discovered location the configuration does not map fails with its exact
location; an unsupported or dynamic construct cannot run. The evidence states
the supported grammar and the excluded categories, because a pass proves
completeness inside that grammar only.

A generic CLI pass does not prove that a consumer calls the gate. The
consumer binding names the owner repository, its revision, the real entry
point (file and function), the invocation argv and the inventory digest. It is
verified against the owner checkout: the entry must exist at that revision and
must invoke ``project-version-sync``. A missing or unverifiable binding leaves
integration unproved.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, run_git
from pipelines_hooks.release import project_version as pv

GRAMMAR = (
    "pyproject.toml project.version literal; literal module-level __version__ assignments in declared "
    "first-party roots; <!-- project-version: X --> spans in .md/.markdown/.rst; a VERSION file only when the "
    "configuration owns it with the source.VERSION selector"
)
EXCLUDED = (
    "dependency constants and VERSION files without ownership metadata",
    "historical release text",
    "computed or imported version expressions",
    "any other textual mention of a version",
)
_SUFFIXES = (".md", ".markdown", ".rst")


@dataclass(frozen=True)
class ConsumerBinding:
    """The real consumer entry that must call project-version-sync."""

    owner_repository: str
    revision: str
    entry_path: str
    entry_function: str
    invocation_argv: tuple[str, ...]
    inventory_digest: str


def load_binding(path: str) -> ConsumerBinding:
    """Parse a binding file; any missing field leaves integration unproved."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return ConsumerBinding(
            raw["owner_repository"],
            raw["revision"],
            raw["entry_path"],
            raw["entry_function"],
            tuple(raw["invocation_argv"]),
            raw["inventory_digest"],
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CannotRun(f"consumer-binding-unresolved: binding {path} is unreadable or incomplete") from exc


def verify_binding(binding: ConsumerBinding, owner_root: Path, inventory: pv.ProjectVersionInventory) -> None:
    """Refuse unless the bound entry exists at its revision and invokes project-version-sync."""
    if binding.inventory_digest != inventory.config_digest:
        raise CannotRun("consumer-binding-stale: the binding names a different inventory digest")
    if "project-version-sync" not in binding.invocation_argv:
        raise CannotRun("consumer-binding-invalid: the invocation argv does not run project-version-sync")
    head = run_git(owner_root, ("rev-parse", "HEAD"))
    if head.returncode != 0 or head.stdout.strip() != binding.revision:
        raise CannotRun("consumer-binding-stale: the owner checkout is not at the bound revision")
    entry = PurePosixPath(binding.entry_path)
    if entry.is_absolute() or ".." in entry.parts or entry.suffix != ".py":
        raise CannotRun("consumer-binding-invalid: the entry path must be a repository-relative Python file")
    try:
        source = git_text(owner_root, ("show", f"{binding.revision}:{binding.entry_path}"))
        tree = ast.parse(source)
    except (CannotRun, SyntaxError) as exc:
        raise CannotRun(
            f"consumer-binding-unresolved: entry {binding.entry_path} is not readable at the revision"
        ) from exc
    function = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == binding.entry_function
        ),
        None,
    )
    if function is None:
        raise CannotRun(f"consumer-binding-unresolved: no function {binding.entry_function} in {binding.entry_path}")
    called = any(
        isinstance(node, ast.Constant) and isinstance(node.value, str) and "project-version-sync" in node.value
        for node in ast.walk(function)
    )
    if not called:
        raise CannotRun(
            f"consumer-binding-unproved: {binding.entry_path}:{binding.entry_function} does not invoke project-version-sync"
        )


def _tracked_paths(root: Path, *, index: bool, ref: str | None) -> list[str]:
    args = ("ls-files", "-z") if index else ("ls-tree", "-r", "-z", "--name-only", ref or "HEAD")
    result = run_git(root, args, preserve_index=index)
    if result.returncode != 0:
        raise CannotRun("snapshot-unavailable: could not list the selected snapshot")
    return [path for path in result.stdout.split("\0") if path]


def snapshot_contents(
    root: Path, *, index: bool, ref: str | None, roots: tuple[str, ...], inventory: pv.ProjectVersionInventory
) -> dict[str, str]:
    """Read the snapshot blobs the discovery grammar may inspect; nothing else is read."""
    owned = {loc.path for loc in inventory.locations if pv._is_owned_version_file(loc)}  # noqa: SLF001
    tracked = _tracked_paths(root, index=index, ref=ref)
    missing = [r for r in roots if not any(p == r or p.startswith(r.rstrip("/") + "/") for p in tracked)]
    if missing:
        raise CannotRun(f"inventory-incomplete: first-party root has no tracked files ({', '.join(missing)})")
    wanted = [
        path for path in tracked if path == "pyproject.toml" or path in owned or path.endswith((".py", *_SUFFIXES))
    ]
    contents: dict[str, str] = {}
    for path in wanted:
        try:
            contents[path] = pv._selected_blob(root, path, index=index, ref=ref)[0]  # noqa: SLF001
        except CannotRun as exc:
            if "not a regular Git file" not in str(exc):
                raise
    return contents


def _located(item: Any) -> dict[str, Any]:
    return {"path": item.path, "line": getattr(item, "line", None), "role": item.role, "selector": item.selector}


def evidence_for(
    report: pv.VersionInventoryCompleteness, inventory: pv.ProjectVersionInventory, binding: str
) -> dict[str, Any]:
    """The completeness evidence: both sets, their difference and the statement of scope."""
    grammar = {"policy": report.policy_version, "supported": GRAMMAR, "excluded": list(EXCLUDED)}
    return {
        "policy_version": report.policy_version,
        "policy_digest": pv._sha256(json.dumps(grammar, sort_keys=True)),  # noqa: SLF001
        "snapshot": inventory.snapshot,
        "config_digest": inventory.config_digest,
        "discovered": [_located(item) | {"value": item.value} for item in report.discovered],
        "configured": [{"path": loc.path, "role": loc.role, "selector": loc.selector} for loc in report.configured],
        "difference": {
            "unmapped": [_located(item) for item in report.unmapped],
            "missing": [{"path": loc.path, "role": loc.role} for loc in report.missing],
            "selector_mismatch": [_located(item) for item, _ in report.selector_mismatch],
            "value_mismatch": [_located(item) for item in report.value_mismatch],
            "duplicates": [_located(item) for item in report.duplicates],
        },
        "grammar": grammar,
        "complete": report.complete,
        "scope": "completeness within the stated grammar only, not every textual version mention",
        "consumer_integration": binding,
    }


def _render_difference(report: pv.VersionInventoryCompleteness) -> list[str]:
    lines = [f"unmapped discovered location {i.path}:{i.line} ({i.role}, {i.selector})" for i in report.unmapped]
    lines += [f"configured location not discovered {loc.path} ({loc.role})" for loc in report.missing]
    lines += [f"selector mismatch {i.path}:{i.line} ({i.selector})" for i, _ in report.selector_mismatch]
    lines += [f"discovered value differs {i.path}:{i.line} = {i.value!r}" for i in report.value_mismatch]
    lines += [f"duplicate discovered location {i.path}:{i.line}" for i in report.duplicates]
    return lines


def run_completeness(args: argparse.Namespace) -> int:
    """Compare discovery with the configuration, then verify any consumer binding."""
    root, index, ref, snapshot = pv.select_snapshot(args.root, args.base_ref)
    inventory = pv.selected_inventory(root, config_path=args.config, index=index, ref=ref, snapshot=snapshot)
    roots = tuple(args.first_party_root or ("src",))
    contents = snapshot_contents(root, index=index, ref=ref, roots=roots, inventory=inventory)
    report = pv.compare_version_inventory(
        inventory, pv.discover_version_locations(contents, first_party_roots=roots, inventory=inventory)
    )
    binding = "unproved: no consumer binding supplied; a generic CLI pass does not prove consumer integration"
    if args.consumer_binding:
        if not args.owner_root:
            raise CannotRun("consumer-binding-unresolved: --owner-root names no owner checkout")
        verify_binding(load_binding(args.consumer_binding), Path(args.owner_root), inventory)
        binding = "verified: the bound entry invokes project-version-sync"
    evidence = evidence_for(report, inventory, binding)
    if args.evidence:
        Path(args.evidence).write_text(json.dumps(evidence, sort_keys=True, indent=2), encoding="utf-8")
    print("project-version-sync: evidence " + json.dumps(evidence, sort_keys=True))
    for line in _render_difference(report):
        print(f"project-version-sync: FAIL {line}")
    if report.complete:
        print(f"project-version-sync: PASS (completeness); policy={report.policy_version}; snapshot={snapshot}")
        return 0
    return 1
