"""Bind a published pure-Python package payload to reviewed container source."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shlex
import subprocess
import sys
import tempfile
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


def _rendered_dockerfile(root: Path) -> str:
    """Render the canonical Dockerfile from the reviewed ``HEAD`` metadata."""
    provider_root = Path(__file__).resolve().parents[3]
    if not (provider_root / "pipelines_hooks" / "connector" / "container.py").is_file():
        raise ValueError("Generated Dockerfile verification requires the provider renderer checkout")
    sys.path.insert(0, str(provider_root))
    try:
        from pipelines_hooks.connector.container import render
    finally:
        sys.path.pop(0)

    with tempfile.TemporaryDirectory(prefix="public-wheel-source-") as directory:
        source = Path(directory)
        pyproject = subprocess.check_output(
            ["git", "show", "HEAD:pyproject.toml"], cwd=root, text=False, stderr=subprocess.DEVNULL
        )
        try:
            document = tomllib.loads(pyproject.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise ValueError("Generated Dockerfile verification requires readable reviewed pyproject.toml") from error
        points = document.get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
        tracked_sources = subprocess.check_output(
            ["git", "ls-files", "--", "*connector_sources.py"], cwd=root, text=True
        ).splitlines()
        if (not isinstance(points, dict) or not points) and not any(
            Path(path).name == "connector_sources.py" for path in tracked_sources
        ):
            raise ValueError("Generated Dockerfile verification requires a connector identity")
        (source / "pyproject.toml").write_bytes(pyproject)
        return render(source)["Dockerfile"]


def _reviewed_dockerfile(root: Path, dockerfile: str) -> str:
    """Read a tracked Dockerfile or the provider-rendered canonical one."""
    try:
        return subprocess.check_output(
            ["git", "show", f"HEAD:{dockerfile}"], cwd=root, text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as error:
        if dockerfile != "docker/Dockerfile":
            raise ValueError(f"Reviewed Dockerfile is not tracked: {dockerfile}") from error
        return _rendered_dockerfile(root)


def verify_release(root: Path, distribution: str, module: str, dockerfile: str, extras: str) -> dict[str, object]:
    project = tomllib.loads(subprocess.check_output(["git", "show", "HEAD:pyproject.toml"], cwd=root, text=True))[
        "project"
    ]
    if project["name"] != distribution:
        raise ValueError("Explicit distribution differs from reviewed project metadata")
    version = project["version"]
    suffix = f"[{extras}]" if extras else ""
    pin = f"{distribution}{suffix}=={version}"
    docker = _reviewed_dockerfile(root, dockerfile)
    if pin not in shlex.split(docker, comments=True):
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
