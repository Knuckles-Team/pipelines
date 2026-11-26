"""Post one release record after a tag publish (PIPE-RELEASE-R009.1).

The record names the repository, the tag, the frozen source commit and the sha256 of every built artifact. It goes
over plain HTTP to the endpoint in ``RELEASE_RECORD_URL`` as the arbora operation ``release.record``. With no endpoint
set the step says so and exits zero. A failure marks the run but never withdraws the release.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
_SOURCE = ROOT / ".github/actions/verify-release-source/verify_release_source.py"
ARTIFACT_GLOBS = ("dist/*.whl", "dist-sdist/*.tar.gz")
OPERATION = "release.record"


def _frozen_source(environment: dict) -> str:
    spec = importlib.util.spec_from_file_location("verify_release_source", _SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.frozen_source(environment)


def artifact_digests(root: Path) -> list[dict]:
    """``{name, sha256}`` for every built wheel and sdist, sorted by name."""
    found = sorted(p for pattern in ARTIFACT_GLOBS for p in root.glob(pattern))
    return [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in found]


def build_record(environment: dict, root: Path) -> dict:
    """The release record: repository, tag, frozen commit and artifact digests."""
    artifacts = artifact_digests(root)
    if not artifacts:
        raise ValueError("no built artifact to record")
    return {
        "repository": environment["RELEASE_REPOSITORY"],
        "tag": environment["RELEASE_TAG"],
        "commit": _frozen_source(environment),
        "artifacts": artifacts,
    }


def post(url: str, record: dict, timeout: float = 15) -> int:
    body = json.dumps({"op": OPERATION, "params": record}, sort_keys=True).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - the endpoint is operator configuration
        return response.status


def main(argv: list[str] | None = None, environment: dict | None = None, root: Path | None = None) -> int:
    env = dict(os.environ if environment is None else environment)
    url = env.get("RELEASE_RECORD_URL", "")
    if not url:
        print("record-release skipped: no RELEASE_RECORD_URL set")
        return 0
    try:
        status = post(url, build_record(env, root or Path.cwd()))
    except (OSError, ValueError, KeyError) as exc:
        print(f"record-release failed (the release stands): {exc}", file=sys.stderr)
        return 1
    print(f"release recorded (HTTP {status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
