"""Exact staged-file identity at PyPI; supplements, never replaces, runtime proof."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import stat
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

spec = importlib.util.spec_from_file_location(
    "readiness", Path(__file__).with_name("readiness.py")
)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
require = guard.require


def staged(directory: Path, package: str, version: str) -> dict[str, str]:
    require(
        directory.is_dir() and not directory.is_symlink(), "invalid staging directory"
    )
    files = {}
    for path in sorted(directory.iterdir()):
        info = path.lstat()
        require(
            stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
            "linked/nonregular staged file",
        )
        parser = (
            guard.parse_wheel_filename
            if path.name.endswith(".whl")
            else guard.parse_sdist_filename
        )
        name, release, *_ = parser(path.name)
        require(
            name == package and str(release) == version,
            "staged package/version differs",
        )
        files[path.name] = guard.digest(path)
    require(bool(files), "empty staging directory")
    return files


def manifest(directory: Path, package: str, version: str) -> dict:
    package = guard.canonicalize_name(package)
    version = str(guard.Version(version))
    require(bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", package)), "invalid package")
    require(bool(re.fullmatch(r"[A-Za-z0-9.!+_-]+", version)), "invalid version")
    execution = {
        key: os.environ.get(key, "") for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
    }
    require(
        all(re.fullmatch(r"[1-9][0-9]*", value) for value in execution.values()),
        "missing run identity",
    )
    return {
        "schema": 1,
        "package": package,
        "version": version,
        **guard.identity(),
        **execution,
        "files": staged(directory, package, version),
    }


def remote_files(expected: dict) -> dict[str, str]:
    url = f"https://pypi.org/pypi/{expected['package']}/{expected['version']}/json"
    try:
        with urlopen(url, timeout=30) as response:
            require(response.geturl() == url, "unexpected index redirect")
            data = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return {}
        raise
    require(
        isinstance(data, dict) and isinstance(data.get("info"), dict),
        "malformed index response",
    )
    info = data["info"]
    require(
        guard.canonicalize_name(info.get("name", "")) == expected["package"],
        "remote package differs",
    )
    require(
        str(guard.Version(info.get("version", ""))) == expected["version"],
        "remote version differs",
    )
    require(isinstance(data.get("urls"), list), "missing remote file list")
    result = {}
    for item in data["urls"]:
        require(isinstance(item, dict), "malformed remote file")
        name = item.get("filename")
        checksum = (
            item.get("digests", {}).get("sha256")
            if isinstance(item.get("digests"), dict)
            else None
        )
        require(
            isinstance(name, str) and name in expected["files"],
            "unexpected remote filename",
        )
        require(name not in result, "duplicate remote filename")
        require(
            isinstance(checksum, str) and bool(re.fullmatch(r"[0-9a-f]{64}", checksum)),
            "invalid remote digest",
        )
        require(
            checksum == expected["files"][name], "remote bytes differ from staged bytes"
        )
        result[name] = checksum
    return result


def missing(expected: dict) -> list[str]:
    return sorted(set(expected["files"]) - set(remote_files(expected)))


def postverify(expected: dict, attempts: int = 8, delay: int = 20) -> None:
    for attempt in range(attempts):
        if not missing(expected):
            return
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise ValueError("required filenames/digests are not all published")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "missing", "postverify"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    expected = manifest(args.directory, args.package, args.version)
    if args.mode == "preflight":
        pending = missing(expected)
        args.manifest.write_text(json.dumps(expected, sort_keys=True, indent=2) + "\n")
    else:
        require(
            json.loads(args.manifest.read_text()) == expected,
            "staging or publication identity changed",
        )
        if args.mode == "postverify":
            postverify(expected)
            return
        pending = missing(expected)
    print(json.dumps(pending))


if __name__ == "__main__":
    main()
