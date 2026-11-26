"""Per-unit build and test of a multi-unit Cargo workspace (PIPE-GATES-R064).

``rust_per_unit.py matrix`` reads ``cargo metadata`` and writes a GitHub Actions matrix with one
entry per workspace unit to ``GITHUB_OUTPUT`` (``matrix=<json>``); a workspace of one unit gets an
empty matrix. ``rust_per_unit.py run --unit NAME`` runs ``cargo build --all-features -p NAME`` and
``cargo test --all-features -p NAME``; a failing command exits 1 and prints
``PER_UNIT_FAILED: <unit>: <command>``. The unit list comes only from the workspace manifest; the
script holds no repository names. Exit 0 green, 1 a failing unit, 2 metadata that cannot be read.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


class CannotRun(RuntimeError):
    """The workspace metadata cannot be read (exit 2)."""


def units_from_metadata(metadata: dict) -> list[str]:
    """Package names of the workspace members, sorted; a single-unit workspace has no per-unit run."""
    try:
        members = set(metadata["workspace_members"])
        names = sorted(p["name"] for p in metadata["packages"] if p["id"] in members)
    except (KeyError, TypeError) as exc:
        raise CannotRun(f"cargo metadata has no workspace_members/packages: {exc!r}") from exc
    return names if len(names) > 1 else []


def matrix(units: list[str]) -> dict:
    return {"include": [{"unit": unit} for unit in units]}


def unit_commands(unit: str) -> list[list[str]]:
    return [["cargo", cmd, "--all-features", "-p", unit] for cmd in ("build", "test")]


def run_unit(unit: str, cargo: str = "cargo") -> int:
    for command in unit_commands(unit):
        command[0] = cargo
        if subprocess.run(command, check=False).returncode != 0:
            print(f"PER_UNIT_FAILED: {unit}: {' '.join(['cargo', *command[1:]])}", file=sys.stderr)
            return 1
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("matrix")
    run = sub.add_parser("run")
    run.add_argument("--unit", required=True)
    args = parser.parse_args(argv)
    if args.mode == "run":
        return run_unit(args.unit)
    done = subprocess.run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"], capture_output=True, text=True, check=False
    )
    try:
        if done.returncode != 0:
            raise CannotRun(f"cargo metadata failed: {done.stderr.strip()[-1000:]}")
        text = json.dumps(matrix(units_from_metadata(json.loads(done.stdout))), separators=(",", ":"))
    except (CannotRun, ValueError) as exc:
        print(f"CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"matrix={text}\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
