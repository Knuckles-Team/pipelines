"""Which architecture-model node owns a spec family, within one repository's scope.

The architecture explorer (``scripts/architecture_explorer/place.py``) places a spec row on the node
that lists the row's family in ``fam`` **and** belongs to the row's repository: a node's repository
is its own ``repo`` or the nearest ancestor's, and ``"*"`` in ``fam`` owns every family of that
repository. A family name is the lowercase spec directory name with the repository's retired prefix
replaced (``.config/spec-aliases.toml``). The explorer build and the ``spec-family-coverage`` gate
both ask this module, so they cannot disagree about who owns a family (PIPE-GATES-R061.1).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

from pipelines_hooks.specs.aliases import canonical_id
from pipelines_hooks.specs.requirements_doc import parse_rows

WILDCARD = "*"


def prefix_aliases(aliases: Mapping[str, str]) -> dict[str, str]:
    """Only the prefix entries; an exact row-ID alias must never rename a spec directory."""
    return {k: v for k, v in aliases.items() if k.endswith("-")}


def canonical_family(name: str, aliases: Mapping[str, str]) -> str:
    """A spec directory name with the repository's retired prefix replaced by the canonical one."""
    return canonical_id(name, prefix_aliases(aliases))


def family_claims(model: dict, repo: str | None = None) -> Iterator[tuple[str, str, str]]:
    """``(repository, family, node id)`` for every ``fam`` entry of a non-external node, in model order."""
    repo = model.get("repo") or repo
    if repo and not model.get("external"):
        for fam in model.get("fam", []):
            yield repo, fam, model["id"]
    for child in model.get("children", []):
        yield from family_claims(child, repo)


def owned_families(model: dict, repository: str, aliases: Mapping[str, str] | None = None) -> set[str]:
    """Every family a node of ``repository`` lists (canonicalized by its prefix aliases), ``"*"`` included."""
    aliases = aliases or {}
    return {canonical_family(fam, aliases) for repo, fam, _ in family_claims(model) if repo == repository}


def is_owned(owned: set[str], family: str) -> bool:
    """True when one node of the repository lists ``family`` or owns the whole repository with ``"*"``."""
    return family in owned or WILDCARD in owned


def family_dirs(specs_dir: Path, *, require_rows: bool = False) -> list[str]:
    """Spec directory names; with ``require_rows`` only those whose ``requirements.md`` holds a row."""
    if not specs_dir.is_dir():
        return []
    names = sorted(p.name for p in specs_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
    if not require_rows:
        return names
    return [n for n in names if _has_rows(specs_dir / n / "requirements.md")]


def _has_rows(requirements: Path) -> bool:
    try:
        return bool(parse_rows(requirements.read_text(encoding="utf-8")))
    except (OSError, UnicodeError):
        return False
