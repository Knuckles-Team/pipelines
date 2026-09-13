"""tracked-privacy gate: public text artifacts, runtime source, and the identity catalog.

The catalog is REQUIRED (``--identity-catalog``, default the operator's
``agent-utilities/governance/prohibited-identities.json`` user config file); a
missing or malformed catalog is exit 2, never a silently narrower scan. The
absolute maximum is zero findings: there is no count-based allowance.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.privacy import classify, inventory
from pipelines_hooks.privacy.identities import derive_local_identifiers
from pipelines_hooks.privacy.identity_catalog import IdentityPolicyError, load_identity_catalog
from pipelines_hooks.privacy.identity_scan import scan_prohibited_identities


@dataclass
class Findings:
    """Accumulated violations; each is ``(path, line, category)``."""

    identifiers: frozenset[str]
    rows: set[tuple[str, int, str, str]] = field(default_factory=set)

    def add(self, path: str, line: int, *, category: str, text: str) -> None:
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
        self.rows.add((path, line, category, digest))


def _scan_public(path: Path, root: Path, findings: Findings) -> None:
    relative = path.relative_to(root)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for number in classify.author_metadata_lines(path, lines):
        findings.add(relative.as_posix(), number, category="non-neutral package author identity", text=lines[number - 1])
    deployment_doc = classify.is_deployment_doc(relative)
    for number, line in enumerate(lines, 1):
        for category in classify.classify_line(line, identifiers=findings.identifiers, deployment_doc=deployment_doc):
            findings.add(relative.as_posix(), number, category=category, text=line)


def _scan_runtime(path: Path, root: Path, findings: Findings) -> None:
    relative = path.relative_to(root)
    if inventory.is_bundled_connector_profile(relative):
        findings.add(relative.as_posix(), 1, category="bundled environment-specific connector profile", text=relative.as_posix())
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for category in classify.classify_runtime_source_line(line, identifiers=findings.identifiers):
            findings.add(relative.as_posix(), number, category=category, text=line)


def scan(root: Path, identities: tuple[bytes, ...]) -> list[tuple[str, int, str, str]]:
    findings = Findings(identifiers=derive_local_identifiers(root))
    files = sorted(path for path in inventory.candidates(root) if path.is_file() and not path.is_symlink())
    for path in files:
        relative = path.relative_to(root)
        if inventory.is_public_artifact(relative):
            _scan_public(path, root, findings)
        if path.suffix.casefold() in inventory.SOURCE_SUFFIXES:
            _scan_runtime(path, root, findings)
    for hit in scan_prohibited_identities(root, files, identities):
        findings.add(hit.path, hit.line, category="model-specific identity in tracked artifact", text=hit.evidence)
    return sorted(findings.rows)


def _catalog(path: Path) -> tuple[bytes, ...]:
    try:
        return load_identity_catalog(path)
    except (OSError, IdentityPolicyError) as exc:
        raise CannotRun(f"cannot load the external identity policy ({type(exc).__name__}: {exc})") from exc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="tracked-privacy", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    default = platformdirs.user_config_path("agent-utilities", appauthor=False) / "governance" / "prohibited-identities.json"
    parser.add_argument("--identity-catalog", type=Path, default=default)
    args = parser.parse_args(argv)
    rows = scan(args.root.resolve(), _catalog(args.identity_catalog))
    print(f"Tracked artifact privacy gate: {len(rows)} finding(s) (MAX=0).")
    if not rows:
        print("Tracked artifact privacy gate PASSED.")
        return 0
    for path, line, category, _digest in rows:
        print(f"  - {path}:{line}: {category}")
    print("Matched values are intentionally suppressed.", file=sys.stderr)
    return 1
