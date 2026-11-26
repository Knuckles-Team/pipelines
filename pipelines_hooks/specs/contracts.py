"""contract-coverage: a row that cites another repository's row is covered by a contract (PIPE-GATES-R034).

A contract is the hand-written file ``specs/<family>/contracts/<seam>.md``. It holds the lines
``Provider: <repository> <ROW-ID>`` and ``Consumer: <repository> <ROW-ID>`` and the sections
Wire shape, Refusal codes, Authoritative types and Test vectors. A row that names a row ID whose
prefix no row of this repository uses is covered when a contract names both the citing row and
the cited row. A citation the change adds fails; an older citation is advisory. A contract that
names a row its owner does not define, or the same pair as another contract, fails. A contract file
the change does not touch is advisory, so a repository with older contracts is not blocked by them.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.baseref import upstream_base
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, repo_root
from pipelines_hooks.core.settings import setting
from pipelines_hooks.specs import narrative
from pipelines_hooks.specs.narrative import ROW_TOKEN_RE
from pipelines_hooks.specs.artifacts import section
from pipelines_hooks.specs.ids import ROW_RE
from pipelines_hooks.specs.requirements_doc import parse_rows

SECTIONS = ("Wire shape", "Refusal codes", "Authoritative types", "Test vectors")
ADVISORY = " [advisory]"
_LINE = r"^{}: (\S+) ({})\s*$"
_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R\d{3}(?:\.\d+)*"
PROVIDER_RE = re.compile(_LINE.format("Provider", _ID), re.M)
CONSUMER_RE = re.compile(_LINE.format("Consumer", _ID), re.M)
SUFFIX_RE = re.compile(r"-R\d+(?:\.\d+)*$")


@dataclass(frozen=True)
class Contract:
    """One parsed seam contract; ``provider`` and ``consumer`` are ``(repository, row ID)`` or ``None``."""

    path: str
    provider: tuple[tuple[str, str], ...]
    consumer: tuple[tuple[str, str], ...]
    sections: tuple[str, ...]

    @property
    def pairs(self) -> tuple[tuple[str, str], ...]:
        """Every ``(provider row, consumer row)`` the contract names."""
        return tuple((p[1], c[1]) for p in self.provider for c in self.consumer)


def parse_contract(text: str, path: str = "") -> Contract:
    """Read the ``Provider:`` and ``Consumer:`` lines and the sections that hold content."""
    present = tuple(name for name in SECTIONS if section(text, name))
    return Contract(
        path,
        tuple(PROVIDER_RE.findall(text)),
        tuple(CONSUMER_RE.findall(text)),
        present,
    )


def load_contracts(root: Path) -> list[Contract]:
    return [
        parse_contract(p.read_text(encoding="utf-8", errors="replace"), p.relative_to(root).as_posix())
        for p in sorted((root / "specs").glob("*/contracts/*.md"))
    ]


def check_shape(contracts: list[Contract]) -> list[str]:
    out = []
    for c in contracts:
        for side, value in (("Provider", c.provider), ("Consumer", c.consumer)):
            if not value:
                out.append(f"{c.path}: lacks a '{side}: <repository> <ROW-ID>' line")
        out += [f"{c.path}: lacks the '{name}' section" for name in SECTIONS if name not in c.sections]
    return out


def _prefix(row_id: str) -> str:
    return SUFFIX_RE.sub("", row_id)


def row_citations(text: str, local: set[str]) -> dict[str, set[str]]:
    """Row ID -> the row IDs of other repositories that its line names."""
    found: dict[str, set[str]] = {}
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match:
            continue
        cited = {i for i in ROW_TOKEN_RE.findall(match.group(2)) if _prefix(i) not in local}
        if cited:
            found.setdefault(match.group(1), set()).update(cited)
    return found


def _base_text(root: Path, spec_dir: Path, base: str | None) -> str:
    try:
        return git_text(root, ("show", f"{upstream_base(root, base)}:specs/{spec_dir.name}/requirements.md"))
    except CannotRun:
        return ""


def check_citations(
    spec_dir: Path, contracts: list[Contract], local: set[str], *, root: Path | None = None, base: str | None = None
) -> list[str]:
    """``<ROW> cites <OTHER> without a contract``; a citation the change did not add is advisory."""
    text = (spec_dir / "requirements.md").read_text(encoding="utf-8", errors="replace")
    pairs = {pair for c in contracts for pair in c.pairs}
    covered = pairs | {(b, a) for a, b in pairs}
    before = row_citations(_base_text(root, spec_dir, base), local) if root else {}
    out = []
    for row, cited in sorted(row_citations(text, local).items()):
        for other in sorted(cited):
            if (row, other) in covered:
                continue
            tag = "" if other not in before.get(row, set()) else ADVISORY
            out.append(f"specs/{spec_dir.name}: {row} cites {other} without a contract{tag}")
    return out


def check_dangling_and_duplicates(contracts: list[Contract], owner_rows: dict[str, set[str]]) -> list[str]:
    """A contract naming an absent row, or the pair of another contract, is a finding.

    ``owner_rows`` maps a row-ID prefix to the IDs its owner defines; a prefix with no entry is an
    unreachable owner and yields an advisory finding.
    """
    out, seen = [], {}
    for c in contracts:
        for repo, row in (*c.provider, *c.consumer):
            rows = owner_rows.get(_prefix(row))
            if rows is None:
                out.append(f"{c.path}: owner of {row} ({repo}) is unreachable; the row was not checked{ADVISORY}")
            elif row not in rows:
                out.append(f"{c.path}: names {row}, which {repo} does not define")
        for pair in c.pairs:
            if pair in seen and seen[pair] != c.path:
                out.append(f"{c.path}: duplicates {seen[pair]} for {pair[0]} and {pair[1]}")
            seen.setdefault(pair, c.path)
    return out


def _rows_of(directory: Path) -> set[str]:
    return {r.id for f in sorted(directory.glob("specs/*/requirements.md")) for r in parse_rows(f.read_text("utf-8"))}


def owner_rows(root: Path, siblings: Path | None, index: Path | None) -> dict[str, set[str]]:
    """Prefix -> row IDs from this checkout, sibling checkouts, then the cross-repo ID index."""
    found: dict[str, set[str]] = {}

    def add(ids: set[str]) -> None:
        for i in ids:
            found.setdefault(_prefix(i), set()).add(i)

    add(_rows_of(root))
    if siblings and siblings.is_dir():
        for directory in sorted(p for p in siblings.iterdir() if (p / "specs").is_dir() and p.resolve() != root):
            add(_rows_of(directory))
    if index:
        try:
            doc = json.loads(index.read_text(encoding="utf-8"))
            for ids in doc["repos"].values():
                add(set(ids))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise CannotRun(f"cannot read the cross-repo ID index {index}: {exc}") from exc
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="contract-coverage", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default=None, help="revision the change is measured against")
    parser.add_argument("--siblings", type=Path, default=None, help="directory of sibling checkouts")
    parser.add_argument("--id-index", type=Path, default=None, help="cross-repo ID index (PIPELINES_SPEC_ID_INDEX)")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    sibs, idx = args.siblings, args.id_index or setting("PIPELINES_SPEC_ID_INDEX")
    contracts = load_contracts(root)
    rows = owner_rows(root, sibs, Path(idx) if idx else None)
    local = {_prefix(i) for i in _rows_of(root)}
    found = check_shape(contracts) + check_dangling_and_duplicates(contracts, rows)
    for spec_dir in sorted(d for d in (root / "specs").glob("*/") if (d / "requirements.md").is_file()):
        found += check_citations(spec_dir, contracts, local, root=root, base=args.base)
    touched = narrative.touched_paths(root, args.base)
    found = [f if f.split(":")[0] in touched or "/contracts/" not in f.split(":")[0] else f + ADVISORY for f in found]
    failing = [f for f in found if not f.endswith(ADVISORY)]
    for finding in found:
        print(f"contract-coverage: {finding}" if finding in failing else f"ADV contract-coverage: {finding}")
    if failing:
        print(f"contract-coverage: FAIL: {len(failing)} finding(s)")
        return 1
    print(f"contract-coverage: clean ({len(contracts)} contract(s) checked)")
    return 0
