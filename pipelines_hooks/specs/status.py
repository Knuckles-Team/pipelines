"""spec-status: compute spec delivery status at read time (SPEC-STATUS-LIFECYCLE.md).

``specs/*/status.json`` is derived data, never committed. Status is a pure
function of requirements.md, Git history (``Spec:`` trailers), test bindings
and the frozen ``.config/spec-legacy-landings.json``, so two branches touching
the same spec never conflict on it.

* default (check): compute every spec's status; fail (exit 1) if a
  ``specs/*/status.json`` is tracked by Git.
* ``--write``: also write each computed document to ``specs/<dir>/status.json``
  (gitignored) for local readers and CI page builders.
* ``--engine-endpoint`` (or ``PIPELINES_SPEC_STATUS_ENDPOINT``): after generation, read
  the engine's served state over HTTP and fail naming each row whose state differs.
* ``--freeze-legacy``: one-time cutover: record the landing SHAs a tracked
  status.json carries that trailers do not, in ``.config/spec-legacy-landings.json``.

Repositories with specs require full Git history (``fetch-depth: 0``).
"""

from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, repo_root, run_git, sanitized_env
from pipelines_hooks.core.settings import setting
from pipelines_hooks.specs.bindings import test_bindings
from pipelines_hooks.specs.engine_state import compare_engine_state
from pipelines_hooks.specs.git_log import checked_attributions
from pipelines_hooks.specs.generator import freeze_legacy, generate, render
from pipelines_hooks.states_publish import collect_states, publish_states
from pipelines_hooks.verdict_publish import target_from_environment

DEFAULT_HEAD = "HEAD"


def _leaf_tally(generated: dict[Path, dict]) -> dict[str, int]:
    tally: dict[str, int] = defaultdict(int)
    for document in generated.values():
        for requirement in document["requirements"]:
            if "rollup_of" not in requirement:
                tally[requirement["delivery_state"]] += 1
    return dict(sorted(tally.items()))


def tracked_status_files(root: Path) -> list[str]:
    """Committed ``specs/*/status.json`` paths: generated data that must not be tracked."""
    return [p for p in git_text(root, ("ls-files", "--", "specs/*/status.json")).splitlines() if p]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="spec-status", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--head", default=None)
    parser.add_argument("--write", action="store_true", help="write computed status.json files (untracked)")
    parser.add_argument("--engine-endpoint", default=None, help="served spec.status URL to compare against")
    parser.add_argument("--freeze-legacy", action="store_true", help="cutover: freeze legacy landings")
    return parser.parse_args(argv)


def _pending_merge_context(root: Path) -> str | None:
    """Return an unattached commit for the resolved pending merge candidate.

    During a merge the index is the candidate tree but HEAD names only the first
    parent; a deterministic, unreferenced commit over that index and both parents
    makes the checkout and history views agree.
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
        raise CannotRun(f"spec-status: could not create pending merge context: {(result.stderr or '').strip()[:300]}")
    return result.stdout.strip()


def _publish(root: Path, head: str, generated: dict[Path, dict]) -> None:
    """Publish the computed states to the engine (PIPE-GATES-R004.4); never changes the verdict."""
    target = target_from_environment()
    if target is None:
        publish_states([], "", "")
        return
    revision = git_text(root, ("rev-parse", "--verify", f"{head}^{{commit}}")).strip()
    records = collect_states(generated, repository=setting("GITHUB_REPOSITORY") or root.name, revision=revision)
    publish_states(records, target.endpoint, target.token)


def main(argv: list[str]) -> int:
    arguments = _parse_args(argv)
    root = repo_root(arguments.root)
    head = arguments.head or _pending_merge_context(root) or DEFAULT_HEAD
    if arguments.freeze_legacy:
        count = freeze_legacy(root, head)
        print(f"{root.name}: froze {count} legacy landing(s) into .config/spec-legacy-landings.json")
        return 0
    refused = checked_attributions(root, head, test_bindings(root))[1]
    if refused:
        print("FAIL: spec-landing-attributions refused (these rows do not count as landed):")
        for line in refused:
            print(f"    {line}")
    generated = generate(root, head)
    if arguments.write:
        for path, document in generated.items():
            path.write_text(render(document), encoding="utf-8")
    print(f"{root.name}: leaf rows {_leaf_tally(generated)}; {len(generated)} spec(s) computed")
    _publish(root, head, generated)
    tracked = tracked_status_files(root)
    if tracked:
        print("FAIL: status.json is generated, never committed; untrack it (git rm --cached) and gitignore it:")
        for tracked_path in tracked:
            print(f"    {tracked_path}")
        return 1
    endpoint = arguments.engine_endpoint or setting("PIPELINES_SPEC_STATUS_ENDPOINT")
    differing = compare_engine_state(generated, endpoint) if endpoint else []
    if differing:
        print("FAIL: generated spec status differs from the engine's served state for these rows:")
        for row_id in differing:
            print(f"    {row_id}")
    return 1 if refused or differing else 0
