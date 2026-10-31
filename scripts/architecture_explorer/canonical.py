"""One canonicalization step: retired spec prefixes become their canonical form before placement.

A repository that renames its spec prefix lists the retired prefix in ``.config/spec-aliases.toml``
(reference/spec-standard.md). Rows and ``model.json`` keys both go through ``canonical_id`` here, so a
rename never unmaps rows and the model may use either the retired or the current key.
"""

from __future__ import annotations

import re
from collections import Counter

from pipelines_hooks.specs.aliases import canonical_id


def tag_family_keys(snaps) -> None:
    """Give each row ``family_key``: its spec directory name with the repository's retired prefix replaced."""
    for snap in snaps:
        for row in snap.rows:
            row["family_key"] = canonical_id(row["family"], prefix_aliases(snap.aliases))


def prefix_aliases(aliases: dict[str, str]) -> dict[str, str]:
    """Only the prefix entries; an exact row-ID alias must never rename a spec directory."""
    return {k: v for k, v in aliases.items() if k.endswith("-")}


def merged_aliases(snaps) -> dict[str, str]:
    """Every scanned repository's retired prefix -> canonical prefix."""
    return {k: v for snap in snaps for k, v in prefix_aliases(snap.aliases).items()}


def canonical_model(node: dict, aliases: dict[str, str]) -> None:
    """Rewrite ``fam`` and ``ids`` keys of the model tree (in place) to canonical prefixes."""
    for key in ("fam", "ids"):
        if key in node:
            node[key] = [canonical_id(v, aliases) for v in node[key]]
    for child in node.get("children", []):
        canonical_model(child, aliases)


def failure_message(errors: dict[str, str], violations: list[str], limit: int = 20) -> str:
    """The cause of a refused build: snapshot errors per repository, unmapped rows grouped by ``repo:FAMILY``."""
    lines = ["source-chart build refused."]
    if errors:
        lines.append(f"snapshot errors ({len(errors)} repositories):")
        lines += [f"  {repo}: {err}" for repo, err in sorted(errors.items())[:limit]]
    if violations:
        family = lambda v: re.sub(r"-R?[0-9][0-9.]*$", "", v)  # noqa: E731
        groups = Counter(family(v) for v in violations)
        first = {}
        for v in sorted(violations):
            first.setdefault(family(v), v)
        rows = sorted(((f"{k} (e.g. {first[k]})", n) for k, n in groups.items()), key=lambda kv: (-kv[1], kv[0]))
        lines.append(f"rows of families with no node: {len(violations)} in {len(rows)} repo:FAMILY groups:")
        lines += [f"  {k}: {n}" for k, n in rows[:limit]]
        if len(rows) > limit:
            lines.append(f"  ... and {len(rows) - limit} more")
        lines.append("fix: add a node that owns the family (fam) in scripts/architecture_explorer/model.json")
    return "\n".join(lines)
