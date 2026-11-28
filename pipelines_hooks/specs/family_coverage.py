"""spec-family-coverage: every spec directory of this repository has a node in the architecture model.

The architecture explorer (Canopy) refuses a spec family that no node of the owning repository lists in
``fam``, and the refusal used to appear only when Canopy published. This gate runs the same test in the
repository that adds the spec directory. It reads the architecture model and the repository registry
from the pipelines ``main`` branch (public, unauthenticated), resolves this repository's name the way the
explorer keys it, and asks :mod:`pipelines_hooks.specs.family_scope` (the matcher the explorer build uses)
whether a node of that repository owns each ``specs/<dir>/`` that holds requirement rows.

An unmapped directory prints ``SPEC_FAMILY_UNMAPPED <repo>:<dir> — add fam to a node in pipelines
scripts/architecture_explorer/model.json`` and exits 1. When the model cannot be fetched the gate fails
closed under GitHub Actions and prints one warning and passes anywhere else, so an offline commit works.
In the pipelines repository itself the working-tree model is used and nothing is fetched.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.settings import setting
from pipelines_hooks.specs.aliases import load_aliases
from pipelines_hooks.specs.family_scope import canonical_family, family_dirs, is_owned, owned_families
from pipelines_hooks.specs.repository_identity import repository_owner

OWNER = "Knuckles-Team"
EXPLORER = "scripts/architecture_explorer"
RAW = f"https://raw.githubusercontent.com/{OWNER}/pipelines/main/{EXPLORER}"
MODEL_URL = f"{RAW}/model.json"
REGISTRY_URL = f"{RAW}/registry.json"
PIPELINES = "pipelines"
TIMEOUT_SECONDS = 15


class ModelUnavailable(Exception):
    """The architecture model or registry could not be read."""


def fetch_json(url: str) -> dict:
    """One public JSON document from the pipelines ``main`` branch."""
    request = urllib.request.Request(url, headers={"User-Agent": "spec-family-coverage"})  # noqa: S310 - fixed https host
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            document = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise ModelUnavailable(f"{url}: {exc}") from exc
    if not isinstance(document, dict):
        raise ModelUnavailable(f"{url}: not a JSON object")
    return document


def explorer_name(slug: str, registry: dict) -> str:
    """The name the explorer keys this repository's rows by: its registry ``name``, else the slug itself.

    A repository outside the registry joins the scan under its slug (``sources.reconcile``).
    """
    for entry in registry.get("repositories", []):
        if slug in (entry.get("slug"), entry.get("name")):
            return str(entry["name"])
    return slug


def unmapped_findings(root: Path, repository: str, model: dict) -> list[str]:
    """One ``SPEC_FAMILY_UNMAPPED`` line per spec directory with rows that no node of ``repository`` owns."""
    aliases = load_aliases(root)
    owned = owned_families(model, repository, aliases)
    return [
        f"SPEC_FAMILY_UNMAPPED {repository}:{name} — add fam to a node in pipelines {EXPLORER}/model.json"
        for name in family_dirs(root / "specs", require_rows=True)
        if not is_owned(owned, canonical_family(name, aliases))
    ]


def _local_documents(root: Path) -> tuple[dict, dict] | None:
    """The working-tree model and registry, when ``root`` is the pipelines repository itself."""
    model, registry = root / EXPLORER / "model.json", root / EXPLORER / "registry.json"
    if not (model.is_file() and registry.is_file()):
        return None
    return json.loads(model.read_text(encoding="utf-8")), json.loads(registry.read_text(encoding="utf-8"))


def main(argv: list[str], fetch=fetch_json) -> int:
    parser = argparse.ArgumentParser(prog="spec-family-coverage", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    if not family_dirs(root / "specs", require_rows=True):
        print("spec-family-coverage: OK (no spec directory with requirement rows)")
        return 0
    documents = _local_documents(root)
    try:
        model, registry = documents or (fetch(MODEL_URL), fetch(REGISTRY_URL))
    except ModelUnavailable as exc:
        if setting("GITHUB_ACTIONS"):
            print(f"spec-family-coverage: FAILED: the architecture model cannot be read ({exc}); failing closed in CI.")
            return 1
        print(f"spec-family-coverage: WARNING: the architecture model cannot be read ({exc}); skipped offline.")
        return 0
    slug = repository_owner(root)
    if not slug:
        print("spec-family-coverage: FAILED: this repository's name cannot be resolved (no git remote or declaration).")
        return 1
    findings = unmapped_findings(root, explorer_name(slug, registry), model)
    for finding in findings:
        print(finding)
    if not findings:
        print("spec-family-coverage: OK")
    return 1 if findings else 0
