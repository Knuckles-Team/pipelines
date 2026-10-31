"""Bring repositories to the spec-driven standard with one idempotent generator.

``python scripts/standardize_sdd.py --root <repo> [--root <repo> ...]`` writes the repository constitution, the
vended spec templates, the CONTRIBUTING.md pointer section and the AGENTS.md section where each is absent.
``--check`` writes nothing and exits 1 when a part is missing. Each written path is printed, one per line, so a
batch script can stage exactly those paths.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs import sdd_scaffold, templates_sync


def repository_name(root: Path) -> str:
    """The repository name from the origin URL, else the directory name."""
    url = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return Path(url.rstrip("/")).name.removesuffix(".git") if url else root.resolve().name


def _pending(root: Path, name: str, source: Path, today: date) -> list[str]:
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "repo"
        copy.mkdir()
        for rel in (".specify", "CONTRIBUTING.md", "AGENTS.md"):
            if (root / rel).is_dir():
                shutil.copytree(root / rel, copy / rel)
            elif (root / rel).is_file():
                shutil.copy2(root / rel, copy / rel)
        return sdd_scaffold.standardize(copy, name, source, today)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", required=True, help="repository root (repeatable)")
    parser.add_argument("--source-root", type=Path, default=ROOT, help="pipelines checkout")
    parser.add_argument("--name", default=None, help="repository name (default: from the origin URL)")
    parser.add_argument("--check", action="store_true", help="report missing parts and write nothing")
    args = parser.parse_args(argv)
    source = args.source_root / templates_sync.TEMPLATES
    status = 0
    try:
        for root in args.root:
            name = args.name or repository_name(root)
            if args.check:
                missing = _pending(root, name, source, date.today())
                for rel in missing:
                    print(f"{name}: missing {rel}", file=sys.stderr)
                status = max(status, 1 if missing else 0)
                continue
            for rel in sdd_scaffold.standardize(root, name, source, date.today()):
                print(rel)
    except CannotRun as exc:
        print(f"standardize-sdd: CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
