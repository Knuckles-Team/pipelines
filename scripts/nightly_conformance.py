"""Nightly attached-source conformance gate (PIPE-GATES-R020).

``python scripts/nightly_conformance.py --manifest conformance/attached_matrix.toml``
reads the consumer's ``[[entry]]`` tables ``{dialect, image, digest, version}``
and its ``conformance/deviations.toml`` ``[[deviation]]`` tables
``{dialect, version, reason, reviewed_by}``. For each entry it starts the image
by digest, waits up to ``--timeout-minutes`` (default 10, range 1 to 60) for it
to run, and runs ``cargo test --test attached_conformance`` with the
``CONFORMANCE_DIALECT``, ``CONFORMANCE_VERSION`` and ``CONFORMANCE_CONTAINER``
environment. An entry passes when its tests pass, or when they fail and a
reviewed deviation (non-empty ``reviewed_by``) covers its dialect and version.
An image that does not start, or a failure without a reviewed deviation, fails
the gate. Results go to the job summary. Scheduled runs only: never a pull
request gate. Exit 0 green, 1 blocked, 2 an unreadable manifest.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from required_runtime import CannotRun, read_entries, write_summary  # noqa: E402

ENTRY = {"dialect": str, "image": str, "digest": str, "version": str}
DEVIATION = {"dialect": str, "version": str, "reason": str, "reviewed_by": str}
POLL_SECONDS = 2


def start_image(docker: str, entry: dict, timeout_minutes: int) -> str | None:
    """The running container id, or None when it does not start in time."""
    if not entry["digest"].startswith("sha256:"):
        raise CannotRun(f"{entry['dialect']} {entry['version']}: digest must be sha256:<hex>")
    reference = f"{entry['image']}@{entry['digest']}"
    started = subprocess.run([docker, "run", "-d", "--rm", "-P", reference], capture_output=True, text=True)
    if started.returncode != 0:
        return None
    container = started.stdout.strip()
    deadline = time.monotonic() + timeout_minutes * 60
    while time.monotonic() < deadline:
        state = subprocess.run(
            [
                docker,
                "inspect",
                "-f",
                "{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
                container,
            ],
            capture_output=True,
            text=True,
        ).stdout.split()
        if state[:1] == ["true"] and state[1:] in ([], ["healthy"]):
            return container
        time.sleep(POLL_SECONDS)
    subprocess.run([docker, "rm", "-f", container], capture_output=True)
    return None


def gate_entry(docker: str, cargo: str, entry: dict, reviewed: set, timeout: int, summary: list[str]) -> bool:
    label = f"{entry['dialect']} {entry['version']}"
    container = start_image(docker, entry, timeout)
    if container is None:
        summary.append(f"- {label}: FAILED, the image did not start within {timeout} minutes")
        return False
    try:
        env = os.environ | {
            "CONFORMANCE_DIALECT": entry["dialect"],
            "CONFORMANCE_VERSION": entry["version"],
            "CONFORMANCE_CONTAINER": container,
        }
        green = subprocess.run([cargo, "test", "--test", "attached_conformance"], env=env).returncode == 0
    finally:
        subprocess.run([docker, "rm", "-f", container], capture_output=True)
    if green:
        summary.append(f"- {label}: passed")
        return True
    if (entry["dialect"], entry["version"]) in reviewed:
        summary.append(f"- {label}: failed, covered by a reviewed deviation")
        return True
    summary.append(f"- {label}: FAILED, no reviewed deviation")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("conformance/attached_matrix.toml"))
    parser.add_argument("--deviations", type=Path, default=None, help="default: deviations.toml beside the manifest")
    parser.add_argument("--timeout-minutes", type=int, default=10)
    parser.add_argument("--docker", default="docker", help="container runtime executable")
    parser.add_argument("--cargo", default="cargo", help="cargo executable")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.timeout_minutes <= 60:
            raise CannotRun("--timeout-minutes must be in [1, 60]")
        entries = read_entries(args.manifest, "entry", ENTRY)
        if not entries:
            raise CannotRun(f"{args.manifest} declares no [[entry]]")
        deviations_path = args.deviations or args.manifest.parent / "deviations.toml"
        deviations = read_entries(deviations_path, "deviation", DEVIATION) if deviations_path.is_file() else []
        reviewed = {(d["dialect"], d["version"]) for d in deviations if d["reviewed_by"].strip()}
        summary = ["## Attached-source conformance"]
        results = [
            gate_entry(args.docker, args.cargo, entry, reviewed, args.timeout_minutes, summary) for entry in entries
        ]
    except CannotRun as exc:
        print(f"nightly-conformance: {exc}", file=sys.stderr)
        return 2
    write_summary(summary)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
