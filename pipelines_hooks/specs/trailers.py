"""spec-trailers: PR-only checks on ``Spec:`` commit trailers (lifecycle doc S6.3-5).

Given ``--base-ref`` (default the remote revision pre-commit is pushing over,
else ``origin/main``; see :func:`pipelines_hooks.core.baseref.upstream_base`)
and ``HEAD``, this walks the commits in ``base..HEAD`` and fails
when:

3. a commit touches a product path (anything outside ``specs/``, ``docs/``,
   ``.github/`` and ``*.md``) and no commit in the range carries a ``Spec:``
   trailer at all (``Spec: none (<reason>)`` counts as carrying one);
4. a trailer names a requirement ID that is not a table row in any
   ``specs/*/requirements.md`` (a ``PREFIX-R001..R005``-shaped token expands
   to the individual IDs in that inclusive range first);
5. a trailered, known ID has no bound test anywhere in the tree: a Python
   ``mark.spec("ID")`` call, or a ``// spec: ID`` / ``# spec: ID`` line.

Commits already reachable from the current ``origin/main`` are excluded even
when the pushed-over base is older; new branch commits are still checked
against the current requirement and test-binding tree.

A repository's ``.config/spec-aliases.toml`` (see :mod:`pipelines_hooks.specs.aliases`)
maps retired ID prefixes to canonical ones: a trailer or binding with a retired
prefix counts for the canonical ID, and a trailer in the range that still uses a
retired prefix only prints a WARN line.

Explicit evidence withdrawals additionally validate the complete PR diff against
its merge base. See ``reference/spec-standard.md`` for the restricted contract.

History and bindings are scanned without a subprocess per commit.
Withdrawals additionally inspect the affected source blobs.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.baseref import commit, upstream_base
from pipelines_hooks.core.bounded_json import read_bounded_json
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, repo_root, run_git
from pipelines_hooks.core.settings import setting
from pipelines_hooks.specs.aliases import (
    Aliases,
    canonical_id,
    canonical_ids,
    load_aliases,
    canonical_trailer_ids,
)
from pipelines_hooks.specs.git_log import reverted_shas
from pipelines_hooks.specs.trailer_ids import TRAILER_JOIN
from pipelines_hooks.specs.withdrawal import withdrawals

#: Framing bytes for the single combined ``git log`` call: start-of-record,
#: then sha/trailer separator. Both are illegal in a sha or a trailer value.
_RECORD = "\x01"
_FIELD = "\x02"
_LOG_FORMAT = f"{_RECORD}%H{_FIELD}%(trailers:key=Spec,valueonly,separator={TRAILER_JOIN})"

_EXEMPT_PREFIXES = ("specs/", "docs/", ".github/")
_PULL_MERGE_REF = re.compile(r"^refs/pull/(?P<number>[1-9][0-9]*)/merge$")
MAX_EVENT_BYTES = 2 * 1024 * 1024

_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R?\d{2,3}(?:\.\d+)*"
_ID_IN_BACKTICKS = re.compile(rf"`({_ID})`")
_ID_ANYWHERE = re.compile(_ID)

#: One extended-regex alternation covers every binding shape in one grep.
_BOUND_TEST_PATTERN = r"mark\.spec\(|//[[:space:]]*spec:|#[[:space:]]*spec:"


@dataclass(frozen=True)
class _Commit:
    """One commit's sha, raw ``Spec:`` trailer text, and changed paths."""

    sha: str
    trailer_raw: str
    paths: tuple[str, ...]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="spec-trailers", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", default=None, help="default: see module docstring")
    return parser.parse_args(argv)


def _parse_log(raw: str) -> list[_Commit]:
    commits = []
    for chunk in raw.split(_RECORD):
        if not chunk:
            continue
        header, _, remainder = chunk.partition("\n")
        sha, _, trailer_raw = header.partition(_FIELD)
        paths = tuple(line for line in remainder.splitlines() if line)
        commits.append(_Commit(sha=sha, trailer_raw=trailer_raw, paths=paths))
    return commits


def _github_synthetic_merge(root: Path, base: str | None) -> str | None:
    """Return a verified GitHub PR merge ref SHA, never an arbitrary merge SHA.

    GitHub checks out ``refs/pull/<number>/merge`` for pull-request workflows.
    That generated commit has no author-supplied trailer, so it is excluded only
    when the event payload and its two Git parents identify the same base/head
    pair. Missing or malformed metadata leaves the merge in the range.
    """
    if setting("GITHUB_EVENT_NAME") != "pull_request" or base is None:
        return None
    ref_match = _PULL_MERGE_REF.fullmatch(setting("GITHUB_REF"))
    event_path = setting("GITHUB_EVENT_PATH")
    if ref_match is None or not event_path:
        return None
    try:
        payload = read_bounded_json(Path(event_path), MAX_EVENT_BYTES, what="GitHub event payload", error=ValueError)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    number = payload.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or str(number) != ref_match.group("number"):
        return None

    def event_sha(container: object, key: str) -> str | None:
        if not isinstance(container, dict):
            return None
        value = container.get(key)
        if not isinstance(value, str):
            return None
        return commit(root, value)

    event_base = event_sha(pull_request.get("base"), "sha")
    event_head = event_sha(pull_request.get("head"), "sha")
    event_merge = event_sha(pull_request, "merge_commit_sha")
    if event_base is None or event_head is None or event_merge is None or event_base != base:
        return None
    head = git_text(root, ("rev-parse", "HEAD")).strip()
    if head != event_merge:
        return None
    parents = git_text(root, ("rev-list", "--parents", "-n", "1", "HEAD")).split()
    if len(parents) != 3 or set(parents[1:]) != {event_base, event_head}:
        return None
    return head


def _load_commits(root: Path, base: str | None) -> list[_Commit]:
    rev_range = f"{base}..HEAD" if base else "HEAD"
    arguments = ["log", "--diff-merges=first-parent", f"--format={_LOG_FORMAT}", "--name-only", rev_range]
    # PRE_COMMIT_FROM_REF can be older than a freshly advanced origin/main. A
    # topic branch may merge that current main and inherit commits with Spec
    # trailers that are no longer part of the branch's unpublished changes.
    # Exclude the current main reachability independently of the pushed-over
    # base, while retaining every commit unique to the branch.
    current_main = commit(root, "origin/main")
    if current_main is not None:
        arguments.extend(("--not", current_main))
    raw = git_text(root, tuple(arguments))
    commits = _parse_log(raw)
    synthetic_merge = _github_synthetic_merge(root, base)
    if synthetic_merge is not None:
        commits = [commit for commit in commits if commit.sha != synthetic_merge]
    return commits


def _is_product_path(path: str) -> bool:
    """True when ``path`` is not exempt (not specs/docs/.github and not *.md)."""
    if path.endswith(".md"):
        return False
    return not path.startswith(_EXEMPT_PREFIXES)


def _missing_trailer_failures(commits: list[_Commit]) -> list[str]:
    """Item 3: a product-path commit exists, but no commit carries ``Spec:`` at all."""
    touches_product = any(any(_is_product_path(path) for path in commit.paths) for commit in commits)
    has_trailer = any(commit.trailer_raw.strip() for commit in commits)
    if touches_product and not has_trailer:
        return [
            "spec-trailers: FAIL: a commit touches a product path but no commit in the "
            "range carries a Spec: trailer (use 'Spec: none (<reason>)' when none applies)"
        ]
    return []


def _known_requirement_ids(root: Path) -> set[str]:
    """Every backtick-quoted ID in a ``specs/*/requirements.md`` table row."""
    ids: set[str] = set()
    for path in sorted(root.glob("specs/*/requirements.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CannotRun(f"could not read {path}: {exc}") from exc
        ids.update(_ID_IN_BACKTICKS.findall(text))
    return ids


def _unknown_id_failures(named: list[str], known: set[str]) -> list[str]:
    """Item 4: a trailer names an ID with no requirements.md row."""
    unknown = sorted({identifier for identifier in named if identifier not in known})
    if not unknown:
        return []
    return [f"spec-trailers: FAIL: unknown requirement id(s), no requirements.md row: {', '.join(unknown)}"]


def _bound_ids(root: Path, aliases: Aliases | None = None) -> set[str]:
    """Every requirement ID found on a bound-test line, via the one allowed grep call."""
    result = run_git(root, ("grep", "-n", "-I", "-E", _BOUND_TEST_PATTERN))
    if result.returncode not in (0, 1):
        detail = (result.stderr or "").strip()[:400]
        raise CannotRun(f"git grep failed: {detail}")
    ids: set[str] = set()
    for line in (result.stdout or "").splitlines():
        ids.update(canonical_id(rid, aliases or {}) for rid in _ID_ANYWHERE.findall(line))
    return ids


def _unbound_id_failures(named: list[str], known: set[str], root: Path, *, aliases: Aliases | None = None) -> list[str]:
    """Item 5: a trailered, known ID with no bound test anywhere in the tree."""
    known_named = sorted({identifier for identifier in named if identifier in known})
    if not known_named:
        return []
    bound = _bound_ids(root, aliases)
    unbound = [identifier for identifier in known_named if identifier not in bound]
    if not unbound:
        return []
    return [f"spec-trailers: FAIL: requirement id(s) with no bound test in the tree: {', '.join(unbound)}"]


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    root = repo_root(args.root)
    base = upstream_base(root, args.base_ref)
    commits = _load_commits(root, base)
    # A delivery that was reverted in the same range delivers nothing: its
    # ``Spec:`` trailer must not demand a bound test for work that is gone.
    reverted = reverted_shas(root, "HEAD")
    aliases = load_aliases(root)
    named = canonical_trailer_ids([commit.trailer_raw for commit in commits if commit.sha not in reverted], aliases)
    known = set(canonical_ids(_known_requirement_ids(root), aliases))
    failures = _missing_trailer_failures(commits)
    failures += _unknown_id_failures(named, known)
    withdrawn, withdrawal_errors = withdrawals(
        root, base, named=set(named), known=known, bound=_bound_ids(root, aliases)
    )
    failures += withdrawal_errors
    failures += _unbound_id_failures([rid for rid in named if rid not in withdrawn], known, root, aliases=aliases)
    if failures:
        for line in failures:
            print(line)
        return 1
    print(f"spec-trailers: OK: {len(commits)} commit(s) checked")
    return 0
