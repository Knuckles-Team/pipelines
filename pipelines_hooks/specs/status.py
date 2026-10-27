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
import subprocess
from collections import defaultdict
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, repo_root, run_git, sanitized_env
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
    parser.add_argument("--head", default=None)
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


def _pending_merge_context(root: Path) -> str | None:
    """Return an unattached commit for the resolved pending merge candidate.

    Status generation reads requirement/test files from the checkout and
    evidence from Git history. During a merge, the index is the candidate tree
    but HEAD still names only the first parent. A deterministic, unreferenced
    commit over that index and both actual parents makes those views agree. The
    temporary commit has no Spec trailer and the landing scan excludes merges.
    """
    merge_path = Path(git_text(root, ("rev-parse", "--git-path", "MERGE_HEAD")).strip())
    if not merge_path.is_absolute():
        merge_path = root / merge_path
    if not merge_path.exists():
        return None

    merge_heads = merge_path.read_text(encoding="ascii").split()
    if not merge_heads:
        raise CannotRun("spec-status: pending merge has an empty MERGE_HEAD")
    if run_git(root, ("ls-files", "--unmerged")).stdout.strip():
        raise CannotRun("spec-status: pending merge has unresolved index entries")
    if run_git(root, ("diff", "--quiet")).returncode != 0:
        raise CannotRun("spec-status: pending merge worktree differs from its index")
    untracked_specs = run_git(root, ("ls-files", "--others", "--exclude-standard", "--", "specs"))
    ignored_specs = run_git(
        root,
        ("ls-files", "--others", "--ignored", "--exclude-standard", "--", "specs"),
    )
    if untracked_specs.returncode != 0 or ignored_specs.returncode != 0:
        raise CannotRun("spec-status: could not inspect spec files during pending merge")
    if untracked_specs.stdout.strip() or ignored_specs.stdout.strip():
        raise CannotRun("spec-status: untracked or ignored spec files make the pending merge ambiguous")

    parents = [git_text(root, ("rev-parse", "--verify", "HEAD^{commit}")).strip()]
    for merge_head in merge_heads:
        parents.append(git_text(root, ("rev-parse", "--verify", f"{merge_head}^{{commit}}")).strip())
    tree = git_text(root, ("write-tree",)).strip()
    command = ["git", "commit-tree", tree]
    for parent in parents:
        command.extend(("-p", parent))
    environment = sanitized_env()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "pipelines spec-status",
            "GIT_AUTHOR_EMAIL": "pipelines-spec-status@invalid",
            "GIT_COMMITTER_NAME": "pipelines spec-status",
            "GIT_COMMITTER_EMAIL": "pipelines-spec-status@invalid",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
        }
    )
    try:
        result = subprocess.run(
            command,
            cwd=str(root),
            env=environment,
            input="pipelines spec-status pending merge context\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise CannotRun(f"spec-status: could not create pending merge context: {exc}") from None
    if result.returncode != 0 or not result.stdout.strip():
        detail = (result.stderr or "").strip()[:300]
        raise CannotRun(f"spec-status: could not create pending merge context: {detail}")
    return result.stdout.strip()


def _report(root: Path, stale: list[Path], tally: dict[str, int], *, write: bool, scope_note: str = "") -> int:
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
    head = arguments.head if arguments.head is not None else DEFAULT_HEAD
    if arguments.head is None:
        head = _pending_merge_context(root) or head
    generated = generate(root, head)
    generated, scope_note = apply_changed_only(root, generated, arguments)
    stale = _write_or_report(generated, write=arguments.write)
    tally = dict(sorted(_leaf_tally(generated).items()))
    return _report(root, stale, tally, write=arguments.write, scope_note=scope_note)
