"""Offline exact-ref Pages fleet parity (PIPE-PAGES-001).

The legacy filename is retained as the command entry point; the five-repository
worktree snapshot is historical. No hard-coded fleet or sibling fallback remains.

Commit a JSON declaration with schema_version=1, pipeline={repository, revision},
and consumers=[{repository, revision, content_source, shared_theme_enabled}].
Each revision is a full lowercase SHA-1 commit. Optional consumer site_url is
HTTPS. Prepare clean Git fixtures at <fixtures>/<owner>/<repo>/<revision>.

Run from the repository root::

    uv run --frozen python -m scripts.check_five_repo_parity \\
        --declaration fleet.json --fixtures /path/to/fixtures --format json

Output goes to stdout, never into consumer trees. Verification fields are stable;
generated_at is presentation metadata. --previous annotates prior JSON evidence
as historical if the input changed; it never supplies a cached verdict. Exit 0
means fixture parity, 1 means digest mismatch, and 2 means unverified/invalid.
This command proves neither public availability nor release acceptance. Production
declaration location, approval, fetching and promotion integration remain open.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Retain direct script execution as well as python -m invocation.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.pages_fleet_declaration import canonical, load
from scripts.pages_fleet_parity import reason, verify
from scripts.pages_fleet_receipt import receipt, render_receipt
from scripts.pages_fleet_trees import UNVERIFIED_ERRORS


def previous_receipt(path: Path | None) -> dict | None:
    return json.loads(path.read_text()) if path else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declaration", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args(argv)
    try:
        fleet = load(args.declaration)
        previous = previous_receipt(args.previous)
        result = receipt(verify(fleet, args.fixtures), previous=previous)
    except (*UNVERIFIED_ERRORS, KeyError, TypeError) as exc:
        print(canonical({"schema_version": 1, "status": "unverified", "reason": reason(exc)}))
        return 2
    render = {"json": canonical, "markdown": render_receipt}[args.format]
    print(render(result), end="\n")
    return {"pass": 0, "mismatch": 1, "unverified": 2}[result["verification"]["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
