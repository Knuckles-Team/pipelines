"""spec-trailers: PR-only checks on ``Spec:`` commit trailers (lifecycle doc S6.3-5).

Given ``--base-ref`` (default the remote revision pre-commit is pushing over,
else ``origin/main``; see :func:`pipelines_hooks.core.baseref.upstream_base`)
and ``HEAD``, this walks the non-merge commits in ``base..HEAD`` and fails
when:

3. a commit touches a product path (anything outside ``specs/``, ``docs/``,
   ``.github/`` and ``*.md``) and no commit in the range carries a ``Spec:``
   trailer at all (``Spec: none (<reason>)`` counts as carrying one);
4. a trailer names a requirement ID that is not a table row in any
   ``specs/*/requirements.md`` (a ``PREFIX-R001..R005``-shaped token expands
   to the individual IDs in that inclusive range first);
5. a trailered, known ID has no bound test anywhere in the tree: a Python
   ``mark.spec("ID")`` call, or a ``// spec: ID`` / ``# spec: ID`` line.

One ``git log`` call (history: trailers and changed paths) and one
``git grep`` call (working tree: bound-test markers) are enough; nothing
shells out per commit.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.baseref import upstream_base
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, repo_root, run_git

#: Framing bytes for the single combined ``git log`` call: start-of-record,
#: then sha/trailer separator. Both are illegal in a sha or a trailer value.
_RECORD = "\x01"
_FIELD = "\x02"
_TRAILER_JOIN = "\x1f"
_LOG_FORMAT = f"{_RECORD}%H{_FIELD}%(trailers:key=Spec,valueonly,separator={_TRAILER_JOIN})"

_EXEMPT_PREFIXES = ("specs/", "docs/", ".github/")

_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R?\d{2,3}(?:\.\d+)*"
_ID_IN_BACKTICKS = re.compile(rf"`({_ID})`")
_ID_ANYWHERE = re.compile(_ID)
_NONE_EXEMPTION = re.compile(r"(?i)^none\b")
_RANGE = re.compile(rf"^(?P<base>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-)R(?P<start>\d{{2,3}})\.\.R?(?P<end>\d{{2,3}})$")

#: One extended-regex alternation covers every binding shape in one grep.
_BOUND_TEST_PATTERN = r"mark\.spec\(|//[[:space:]]*spec:|#[[:space:]]*spec:"


@dataclass(frozen=True)
class _Commit:
    """One non-merge commit's sha, raw ``Spec:`` trailer text, and changed paths."""

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


def _load_commits(root: Path, base: str | None) -> list[_Commit]:
    rev_range = f"{base}..HEAD" if base else "HEAD"
    raw = git_text(root, ("log", "--no-merges", f"--format={_LOG_FORMAT}", "--name-only", rev_range))
    return _parse_log(raw)


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


def _expand_token(token: str) -> list[str]:
    """A ``PREFIX-R001..R005`` range expands to its member IDs; anything else is itself."""
    match = _RANGE.match(token)
    if not match:
        return [token]
    width = len(match.group("start"))
    start, end = int(match.group("start")), int(match.group("end"))
    return [f"{match.group('base')}R{number:0{width}d}" for number in range(start, end + 1)]


def _trailer_tokens(trailer_raw: str) -> list[str]:
    tokens = (part.strip() for group in trailer_raw.split(_TRAILER_JOIN) for part in group.split(","))
    return [token for token in tokens if token]


def _named_ids(commits: list[_Commit]) -> list[str]:
    """Every requirement ID any commit's ``Spec:`` trailer names, ranges expanded."""
    ids: list[str] = []
    for commit in commits:
        for token in _trailer_tokens(commit.trailer_raw):
            if _NONE_EXEMPTION.match(token):
                continue
            ids.extend(_expand_token(token))
    return ids


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


def _bound_ids(root: Path) -> set[str]:
    """Every requirement ID found on a bound-test line, via the one allowed grep call."""
    result = run_git(root, ("grep", "-n", "-I", "-E", _BOUND_TEST_PATTERN))
    if result.returncode not in (0, 1):
        detail = (result.stderr or "").strip()[:400]
        raise CannotRun(f"git grep failed: {detail}")
    ids: set[str] = set()
    for line in (result.stdout or "").splitlines():
        ids.update(_ID_ANYWHERE.findall(line))
    return ids


def _unbound_id_failures(named: list[str], known: set[str], root: Path) -> list[str]:
    """Item 5: a trailered, known ID with no bound test anywhere in the tree."""
    known_named = sorted({identifier for identifier in named if identifier in known})
    if not known_named:
        return []
    bound = _bound_ids(root)
    unbound = [identifier for identifier in known_named if identifier not in bound]
    if not unbound:
        return []
    return [f"spec-trailers: FAIL: requirement id(s) with no bound test in the tree: {', '.join(unbound)}"]


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    root = repo_root(args.root)
    base = upstream_base(root, args.base_ref)
    commits = _load_commits(root, base)
    named = _named_ids(commits)
    known = _known_requirement_ids(root)
    failures = _missing_trailer_failures(commits)
    failures += _unknown_id_failures(named, known)
    failures += _unbound_id_failures(named, known, root)
    if failures:
        for line in failures:
            print(line)
        return 1
    print(f"spec-trailers: OK: {len(commits)} commit(s) checked")
    return 0
