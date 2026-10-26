"""Bind a published pure-Python package payload to reviewed container source."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from zipfile import ZipFile


def reviewed_payload(root: Path, module: str) -> dict[str, bytes]:
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module):
        raise ValueError("Package module must be an explicit dotted Python package")
    prefix = module.replace(".", "/") + "/"
    files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", prefix], cwd=root, text=True
    ).splitlines()
    if not files:
        raise ValueError("Reviewed package payload is empty")
    return {name: subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=root) for name in files}


def verify_payload(data: bytes, digest: str, expected: dict[str, bytes], module: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Public wheel digest differs from the PyPI receipt")
    prefix = module.replace(".", "/") + "/"
    with ZipFile(io.BytesIO(data)) as wheel:
        entries = [name for name in wheel.namelist() if name.startswith(prefix) and not name.endswith("/")]
        if len(entries) != len(set(entries)) or set(entries) != expected.keys():
            raise ValueError("Public wheel package inventory differs from reviewed source")
        for name in entries:
            if wheel.read(name) != expected[name]:
                raise ValueError(f"Public wheel payload differs from reviewed source: {name}")


def read_public(url: str) -> bytes:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in {"pypi.org", "files.pythonhosted.org"}:
        raise ValueError("Wheel evidence must come from the public PyPI hosts over HTTPS")
    with urlopen(url, timeout=30) as response:
        return response.read()


def verify_release(root: Path, distribution: str, module: str, dockerfile: str, extras: str) -> dict[str, object]:
    project = tomllib.loads(subprocess.check_output(["git", "show", "HEAD:pyproject.toml"], cwd=root, text=True))[
        "project"
    ]
    if project["name"] != distribution:
        raise ValueError("Explicit distribution differs from reviewed project metadata")
    version = project["version"]
    suffix = f"[{extras}]" if extras else ""
    pin = f"{distribution}{suffix}=={version}"
    docker = subprocess.check_output(["git", "show", f"HEAD:{dockerfile}"], cwd=root, text=True)
    if pin not in docker.split():
        raise ValueError("Dockerfile must pin the reviewed package version")
    expected = reviewed_payload(root, module)
    metadata = json.loads(read_public(f"https://pypi.org/pypi/{distribution}/{version}/json"))
    wheels = [item for item in metadata["urls"] if item["filename"].endswith("-py3-none-any.whl")]
    if len(wheels) != 1:
        raise ValueError("Exactly one public pure-Python wheel is required")
    item = wheels[0]
    digest = item["digests"]["sha256"]
    verify_payload(read_public(item["url"]), digest, expected, module)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    return {
        "package": distribution,
        "module": module,
        "version": version,
        "source_revision": revision,
        "wheel_sha256": digest,
        "verified_payload_files": len(expected),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--distribution", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--dockerfile", default="docker/Dockerfile")
    parser.add_argument("--extras", default="mcp")
    args = parser.parse_args()
    print(
        json.dumps(
            verify_release(args.root, args.distribution, args.module, args.dockerfile, args.extras), sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
