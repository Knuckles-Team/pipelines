"""Vend the spec templates of this pipelines checkout into a consumer repository.

``python scripts/sync_spec_templates.py --root <repo>`` copies ``.specify/templates/`` into the
consumer. ``--check`` writes nothing and exits 1 when the consumer's copy differs, like
``scripts/sync_mkdocs_theme.py check``. The consumer's ``spec`` hook runs the same check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs import templates_sync


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="consumer repository root")
    parser.add_argument("--source-root", type=Path, default=ROOT, help="pipelines checkout holding .specify/templates")
    parser.add_argument("--check", action="store_true", help="report drift and write nothing")
    args = parser.parse_args(argv)
    forwarded = ["--root", str(args.root), "--source", str(args.source_root / templates_sync.TEMPLATES)]
    try:
        return templates_sync.main(forwarded if args.check else [*forwarded, "--write"])
    except CannotRun as exc:
        print(f"spec templates: CANNOT RUN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
