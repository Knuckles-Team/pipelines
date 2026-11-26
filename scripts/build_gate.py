"""Build gate for the root library and its lint profiles (PIPE-GATES-R021).

``python scripts/build_gate.py --manifest build-gate.toml`` builds the root library with all
features, runs ``cargo clippy --all-features --all-targets -- -D warnings`` once per ``[[clippy]]``
profile the manifest declares (``{name, args}``; ``args`` select the packages), and then runs the
``[[suite]]`` entries (``{crate, filter, features}``, the scanner and catalog tests) through the
reader and runner of ``required_runtime.py`` (PIPE-GATES-R017). The consumer owns the manifest;
this script holds no repository names. Exit 0 green, 1 a failed step or a clippy warning, 2 a
manifest that cannot be read.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import required_runtime  # noqa: E402
from required_runtime import CannotRun, read_entries, write_summary  # noqa: E402


def build_step(cargo: str) -> tuple[str, list[str]]:
    return "build", [cargo, "build", "--lib", "--all-features"]


def clippy_step(cargo: str, profile: dict) -> tuple[str, list[str]]:
    command = [cargo, "clippy", "--all-features", "--all-targets", *profile["args"], "--", "-D", "warnings"]
    return f"clippy {profile['name']}", command


def run_step(label: str, command: list[str], summary: list[str]) -> bool:
    ok = subprocess.run(command, check=False).returncode == 0
    summary.append(f"- {label}: {'passed' if ok else 'FAILED'}")
    if not ok:
        print(f"BUILD_GATE_FAILED: {label}: {' '.join(command)}", file=sys.stderr)
    return ok


def gate(cargo: str, manifest: Path) -> int:
    profiles = read_entries(manifest, "clippy", {"name": str, "args": list})
    suites = read_entries(manifest, "suite", {"crate": str, "filter": str, "features": list})
    summary = ["## Build gate"]
    results = [run_step(*build_step(cargo), summary)]
    results += [run_step(*clippy_step(cargo, profile), summary) for profile in profiles]
    results += [required_runtime.gate_entry(cargo, suite, summary) for suite in suites]
    write_summary(summary)
    return 0 if all(results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo", help="cargo executable")
    args = parser.parse_args(argv)
    try:
        return gate(args.cargo, args.manifest)
    except CannotRun as exc:
        print(f"build-gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
