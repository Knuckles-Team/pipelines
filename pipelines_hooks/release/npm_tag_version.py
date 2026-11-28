"""npm-tag-version: refuse an npm release whose tag and registry state disagree with ``package.json``.

    pipelines-hook npm-tag-version --tag v1.2.3 [--root R] [--skip-registry]

PIPE-RELEASE-R033. Two refusals, each exit status 1 with a stable code:

- ``TAG_VERSION_MISMATCH``: the tag is not ``v`` plus the ``package.json`` version.
- ``VERSION_EXISTS``: the registry already holds that version of the package.

The check modelled on the tag check of ``python_pipeline.yml``: the tag carries the version.
It records no state; the tag and the registry hold it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

_NOT_FOUND = re.compile(r"\bE404\b|404 Not Found|is not in this registry", re.IGNORECASE)
_TIMEOUT_SECONDS = 60

#: Asks the registry whether ``name@version`` exists; tests substitute it.
RegistryLookup = Callable[[str, str], bool]


def read_package(root: Path) -> tuple[str, str]:
    """The ``name`` and ``version`` of the package at ``root``."""
    path = root / "package.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc
    name, version = (document.get(key) if isinstance(document, dict) else None for key in ("name", "version"))
    if not isinstance(name, str) or not isinstance(version, str) or not name or not version:
        raise CannotRun(f"{path} needs a string name and version")
    return name, version


def registry_has(name: str, version: str) -> bool:
    """True when the registry holds ``name@version``; an unreadable answer cannot run."""
    try:
        result = subprocess.run(
            ["npm", "view", f"{name}@{version}", "version", "--json"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"cannot ask the registry about {name}@{version}: {exc}") from exc
    if result.returncode == 0:
        return bool(result.stdout.strip())
    if _NOT_FOUND.search(result.stdout + result.stderr):
        return False
    raise CannotRun(f"the registry lookup of {name}@{version} failed: {result.stderr.strip()[:300]}")


def check(root: Path, tag: str, *, lookup: RegistryLookup | None = registry_has) -> tuple[str, str] | None:
    """None when the release may proceed, else ``(code, message)``."""
    name, version = read_package(root)
    if tag != f"v{version}":
        return "TAG_VERSION_MISMATCH", f"tag {tag!r} is not v{version} (package.json version of {name})"
    if lookup is not None and lookup(name, version):
        return "VERSION_EXISTS", f"{name}@{version} is already published; nothing changes"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="npm-tag-version", description=__doc__)
    parser.add_argument("--tag", required=True, help="the release tag, v plus the package version")
    parser.add_argument("--root", type=Path, default=Path("."), help="the package directory (default: .)")
    parser.add_argument("--skip-registry", action="store_true", help="check the tag only")
    args = parser.parse_args(list(argv) if argv is not None else None)
    refusal = check(args.root, args.tag, lookup=None if args.skip_registry else registry_has)
    if refusal is None:
        print(f"npm-tag-version: {args.tag} matches package.json and is unpublished")
        return 0
    code, message = refusal
    print(f"::error::{code}: {message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
