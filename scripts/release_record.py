"""Post one release record after a tag publish (PIPE-RELEASE-R009.1).

The record has the engine's release shape: ``repo`` (the distribution name), ``version``, ``git_ref``,
``changeset_head`` (the frozen source commit), ``published_at`` and ``artifact_digests``, the ``sha256:`` digest of
every built artifact. For a connector, ``RELEASE_DIGESTS_FILE`` names the file ``connector-release-digest`` wrote
before publication, and its ``artifact_digests`` (including the wheel content digest a runner verifies) join the
record (PIPE-RELEASE-R019). It goes over plain HTTP to the endpoint in ``RELEASE_RECORD_URL`` as the arbora operation
``release.record``. With no endpoint set the step says so and exits zero, except for a connector, whose release is
refused by every runner until it is recorded, so the step fails. A failure marks the run but never withdraws the release.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import time
import tomllib
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


def artifact_digests(root: Path) -> list[str]:
    """``sha256:<hex>`` for every built wheel and sdist, sorted."""
    found = sorted(p for pattern in ARTIFACT_GLOBS for p in root.glob(pattern))
    return sorted(f"sha256:{hashlib.sha256(p.read_bytes()).hexdigest()}" for p in found)


def _distribution(root: Path) -> str:
    return str(tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["name"])


def _connector_digests(path: str) -> list[str]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return [str(item) for item in document["artifact_digests"]]


def build_record(environment: dict, root: Path) -> dict:
    """The release record in the engine's release shape."""
    digests = artifact_digests(root)
    if not digests:
        raise ValueError("no built artifact to record")
    if environment.get("RELEASE_DIGESTS_FILE"):
        digests = sorted({*digests, *_connector_digests(environment["RELEASE_DIGESTS_FILE"])})
    tag = environment["RELEASE_TAG"]
    return {
        "repo": _distribution(root),
        "version": tag.removeprefix("refs/tags/").removeprefix("v"),
        "git_ref": tag if tag.startswith("refs/") else f"refs/tags/{tag}",
        "changeset_head": _frozen_source(environment),
        "artifact_digests": digests,
        "published_at": int(time.time()),
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
        if env.get("RELEASE_DIGESTS_FILE"):
            print(
                "record-release failed: a connector release must be recorded; set release-record-url", file=sys.stderr
            )
            return 1
        print("record-release skipped: no RELEASE_RECORD_URL set")
        return 0
    try:
        status = post(url, build_record(env, root or Path.cwd()))
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(f"record-release failed (the release stands): {exc}", file=sys.stderr)
        return 1
    print(f"release recorded (HTTP {status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
