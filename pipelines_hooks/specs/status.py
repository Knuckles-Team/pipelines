"""spec-status: generate and check ``specs/*/status.json`` (SPEC-STATUS-LIFECYCLE.md).

``pipelines-hook spec-status --write`` regenerates every ``specs/*/status.json``
from requirements.md, git history and test bindings. The default (check) mode
prints and fails (exit 1) on any status.json that is stale: missing,
hand-edited, or behind what the generator would produce. status.json is
machine output; a mismatch is resolved by rerunning ``--write``, never by a
textual merge. Repositories with specs require full Git history: shallow checkouts
fail with exit 2 before any writes. Fetch with ``git fetch --unshallow`` or set
``fetch-depth: 0`` in checkout before running this gate.

With 10+ parallel PR lanes, another lane's landing on ``main`` regenerates
*other* specs' status.json, so a full-repo check fails every open PR on
every unrelated landing. ``--changed-only`` (PR mode) scopes the check/write
to only the spec dirs this branch touches: a changed ``specs/<dir>/`` path,
or a commit whose ``Spec:`` trailer names an ID that dir owns, between
``--base-ref`` (default: the pushed-over ref, else ``origin/main``) and
``HEAD``. Untouched dirs are skipped. Full-repo mode (the default on
``main``/pre-push) is unchanged; PR mode also auto-enables when
``GITHUB_EVENT_NAME=pull_request`` and a base resolves, so a hosted
``pull_request`` job gets it without any extra flag.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.specs.changed_only import apply_changed_only
from pipelines_hooks.specs.generator import generate

DEFAULT_HEAD = "HEAD"


def _rendered(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _is_stale(path: Path, text: str) -> bool:
    return not path.exists() or path.read_text(encoding="utf-8") != text


def _leaf_tally(generated: dict[Path, dict]) -> dict[str, int]:
    tally: dict[str, int] = defaultdict(int)
    for document in generated.values():
        for requirement in document["requirements"]:
            if "rollup_of" not in requirement:
                tally[requirement["delivery_state"]] += 1
    return tally


def _write_or_report(generated: dict[Path, dict], *, write: bool) -> list[Path]:
    stale = []
    for path, document in generated.items():
        text = _rendered(document)
        if _is_stale(path, text):
            stale.append(path)
            if write:
                path.write_text(text, encoding="utf-8")
    return stale


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="spec-status", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--head", default=DEFAULT_HEAD)
    parser.add_argument("--write", action="store_true", help="regenerate status.json files")
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="PR mode: only check/write the spec dirs this branch touches (see --base-ref)",
    )
    parser.add_argument(
        "--base-ref",
        "--diff",
        dest="base_ref",
        default=None,
        help="base of the --changed-only diff; default: the pushed-over ref, else origin/main",
    )
    return parser.parse_args(argv)


def _report(
    root: Path, stale: list[Path], tally: dict[str, int], *, write: bool, scope_note: str = ""
) -> int:
    if write:
        print(f"{root.name}: leaf rows {tally}; {len(stale)} status.json rewritten{scope_note}")
        return 0
    if not stale:
        print(f"{root.name}: leaf rows {tally}; status.json up to date{scope_note}")
        return 0
    print(f"FAIL: status.json is stale for {len(stale)} spec(s) (run `pipelines-hook spec-status --write`):\n")
    for path in stale:
        print(f"    {path.relative_to(root)}")
    return 1


def main(argv: list[str]) -> int:
    arguments = _parse_args(argv)
    root = repo_root(arguments.root)
    generated = generate(root, arguments.head)
    generated, scope_note = apply_changed_only(root, generated, arguments)
    stale = _write_or_report(generated, write=arguments.write)
    tally = dict(sorted(_leaf_tally(generated).items()))
    return _report(root, stale, tally, write=arguments.write, scope_note=scope_note)
