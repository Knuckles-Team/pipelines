"""Build ``scaffold_fingerprints.json`` for the wave 1 rule h from the connector fleet.

For each connector repository under the fleet directory, ``git show origin/main:tests/<name>`` is normalised (repo,
fleet and package names and semvers become placeholders; blank and comment lines are dropped) and hashed. A hash is kept
only when it occurs in at least ``--min-repos`` repositories, so only generator scaffolds survive.

Usage: ``python scripts/connector_central_fingerprints.py [--fleet DIR] [--out FILE] [--min-repos 5]``
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines_hooks.hygiene.connector_central.fleet import WORKSPACE_ROOT  # noqa: E402
from pipelines_hooks.hygiene.connector_central.wave1 import (  # noqa: E402
    FINGERPRINTS_PATH,
    SCAFFOLD_TESTS,
    digest,
    normalise,
)

DEFAULT_FLEET = WORKSPACE_ROOT / "agent-packages" / "agents"


def _show(repo: Path, path: str) -> str | None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = subprocess.run(["git", "-C", str(repo), "show", f"origin/main:{path}"], capture_output=True, text=True, env=env)
    return r.stdout if r.returncode == 0 else None


def _names(repo: Path) -> tuple[str, str, str] | None:
    text = _show(repo, "pyproject.toml")
    if text is None:
        return None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    eps = data.get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
    if len(eps) != 1:
        return None
    ((fleet, value),) = eps.items()
    return data["project"]["name"], fleet, re.split(r"[:.]", str(value))[0]


def build(fleet_dir: Path, min_repos: int) -> dict[str, list[str]]:
    seen: dict[str, dict[str, set[str]]] = {n: defaultdict(set) for n in SCAFFOLD_TESTS}
    for repo in sorted(p for p in fleet_dir.iterdir() if p.is_dir()):
        names = _names(repo)
        if names is None:
            continue
        for test in SCAFFOLD_TESTS:
            text = _show(repo, f"tests/{test}")
            if text is not None:
                seen[test][digest(normalise(names, text))].add(repo.name)
    return {
        test: sorted(h for h, repos in by_hash.items() if len(repos) >= min_repos) for test, by_hash in seen.items()
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fleet", type=Path, default=DEFAULT_FLEET)
    ap.add_argument("--out", type=Path, default=FINGERPRINTS_PATH)
    ap.add_argument("--min-repos", type=int, default=5)
    args = ap.parse_args(argv)
    table = build(args.fleet, args.min_repos)
    args.out.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for test, hashes in table.items():
        print(f"{test}: {len(hashes)} fingerprint(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
