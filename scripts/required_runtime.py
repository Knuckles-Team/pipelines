"""Required runtime manifest gate (PIPE-GATES-R017).

``python scripts/required_runtime.py --manifest required-runtime.toml`` reads the
consumer's manifest of ``[[entry]]`` tables ``{crate, filter, features}``. For
each entry it lists the selected tests with ``cargo test -- --list``; an entry
that selects none fails with ``ZERO_SELECTED_TESTS``. It then runs the selected
tests; a failing test fails the gate. Every selected test name goes to the job
summary (``GITHUB_STEP_SUMMARY``). The consumer owns the manifest; this script
holds no repository names. Exit 0 green, 1 a blocked entry, 2 a manifest that
cannot be read.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path


class CannotRun(RuntimeError):
    """The manifest or the toolchain cannot give a trustworthy verdict (exit 2)."""


def read_entries(path: Path, table: str, fields: dict[str, type]) -> list[dict]:
    """The ``[[table]]`` entries of a TOML manifest, each holding exactly ``fields``."""
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc
    entries = document.get(table, [])
    if not isinstance(entries, list):
        raise CannotRun(f"{path}: [[{table}]] must be an array of tables")
    for number, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != set(fields):
            raise CannotRun(f"{path}: {table}[{number}] must hold exactly {', '.join(sorted(fields))}")
        for key, kind in fields.items():
            if not isinstance(entry[key], kind):
                raise CannotRun(f"{path}: {table}[{number}].{key} must be a {kind.__name__}")
    return entries


def _command(cargo: str, entry: dict, *tail: str) -> list[str]:
    features = ["--features", ",".join(entry["features"])] if entry["features"] else []
    filters = [entry["filter"]] if entry["filter"] else []
    return [cargo, "test", "-p", entry["crate"], *features, "--", *filters, *tail]


def selected_tests(cargo: str, entry: dict) -> list[str]:
    listed = subprocess.run(_command(cargo, entry, "--list"), capture_output=True, text=True, check=False)
    if listed.returncode != 0:
        raise CannotRun(f"cargo test --list failed for {entry['crate']}: {listed.stderr.strip()[-2000:]}")
    return [line[: -len(": test")] for line in listed.stdout.splitlines() if line.endswith(": test")]


def gate_entry(cargo: str, entry: dict, summary: list[str]) -> bool:
    label = f"{entry['crate']} [{entry['filter'] or '*'}]"
    names = selected_tests(cargo, entry)
    if not names:
        print(f"ZERO_SELECTED_TESTS: {label} selects no test", file=sys.stderr)
        summary.append(f"### {label}\n\nZERO_SELECTED_TESTS\n")
        return False
    run = subprocess.run(_command(cargo, entry), check=False)
    verdict = "passed" if run.returncode == 0 else "FAILED"
    summary.append(f"### {label}: {verdict}\n\n" + "\n".join(f"- `{name}`" for name in names) + "\n")
    if run.returncode != 0:
        print(f"TEST_FAILED: {label}", file=sys.stderr)
    return run.returncode == 0


def write_summary(lines: list[str]) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo", help="cargo executable")
    args = parser.parse_args(argv)
    try:
        entries = read_entries(args.manifest, "entry", {"crate": str, "filter": str, "features": list})
        if not entries:
            raise CannotRun(f"{args.manifest} declares no [[entry]]")
        summary = ["## Required runtime tests"]
        results = [gate_entry(args.cargo, entry, summary) for entry in entries]
    except CannotRun as exc:
        print(f"required-runtime: {exc}", file=sys.stderr)
        return 2
    write_summary(summary)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
