"""Fail-closed public-index installability proof for exact Python wheel bytes."""
from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

# The checker venv uses pip's vendored parser; project tests use the locked
# packaging dependency. Isolated execution (-I) prevents caller import overrides.
try:
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.tags import sys_tags
    from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
    from pip._vendor.packaging.version import Version
except ImportError:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.tags import sys_tags
    from packaging.utils import canonicalize_name, parse_wheel_filename
    from packaging.version import Version

PUBLIC_INDEX = "https://pypi.org/simple"
ADVERTISED = {"mcp", "agent", "all"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity() -> dict:
    source = os.environ.get("SOURCE_COMMIT", "")
    contract = os.environ.get("PIPELINES_CONTRACT_COMMIT", "")
    for commit in (source, contract):
        require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "missing source/contract identity")
    for directory, expected in ((Path.cwd(), source), (Path(".pipeline-contract"), contract)):
        actual = subprocess.check_output(
            ["git", "-C", str(directory), "rev-parse", "HEAD"], text=True
        ).strip()
        require(actual == expected, "source or contract identity changed")
    return {"source_commit": source, "contract_commit": contract}


def profiles(raw: str, extras: list[str]) -> list[str]:
    selected = json.loads(raw)
    require(isinstance(selected, list) and bool(selected), "runtime profiles must be explicit")
    require(all(isinstance(item, str) for item in selected), "invalid runtime profile")
    require(all(re.fullmatch(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", item) for item in selected),
            "invalid runtime profile name")
    require(len(set(selected)) == len(selected), "duplicate runtime profile")
    require("base" in selected, "base profile is mandatory")
    require(set(selected) <= {"base", *extras}, "unknown runtime extra")
    require(ADVERTISED.intersection(extras) <= set(selected), "advertised runtime profile omitted")
    return sorted(selected)


def metadata(path: Path) -> dict:
    name, version, _, tags = parse_wheel_filename(path.name)
    require(bool(tags.intersection(sys_tags())), "wheel needs proof on its target interpreter/platform")
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        records = [item for item in names if item.endswith(".dist-info/METADATA")]
        require(len(names) == len(set(names)) and len(records) == 1, "ambiguous wheel metadata")
        message = email.parser.BytesParser().parsebytes(wheel.read(records[0]))
    require(len(message.get_all("Name", [])) == 1, "missing/duplicate package name")
    require(len(message.get_all("Version", [])) == 1, "missing/duplicate package version")
    require(canonicalize_name(message["Name"]) == name, "wheel name disagrees with metadata")
    require(Version(message["Version"]) == version, "wheel version disagrees with metadata")
    require(Version(platform.python_version()) in SpecifierSet(message.get("Requires-Python", "")),
            "wheel does not support the readiness interpreter")
    requirements = message.get_all("Requires-Dist", [])
    for raw in requirements:
        require(Requirement(raw).url is None, "direct URL dependency is forbidden")
    return {
        "name": name, "version": str(version),
        "provides_extra": [canonicalize_name(extra) for extra in message.get_all("Provides-Extra", [])],
        "requires_dist": requirements,
    }


def clean_environment(home: Path, wheel: Path) -> dict[str, str]:
    # No index, proxy, certificate, source, constraint, Python, or user config
    # inherited from the caller. pip's null config disables even global config.
    return {
        "PATH": os.defpath, "HOME": str(home), "USERPROFILE": str(home),
        "PIP_CONFIG_FILE": os.devnull, "PYTHONNOUSERSITE": "1",
        "READINESS_ROOT_WHEEL": str(wheel),
        **({"SYSTEMROOT": os.environ["SYSTEMROOT"]} if "SYSTEMROOT" in os.environ else {}),
    }


def validate_report(report: dict, wheel: Path, root: dict, profile: str, expected_digest: str | None = None) -> None:
    require(report.get("version") == "1", "unsupported resolver report")
    require(report.get("environment") == default_environment(), "resolver interpreter/markers changed")
    installs = report.get("install")
    require(isinstance(installs, list) and bool(installs), "empty resolver proof")
    packages = {}
    roots = 0
    for item in installs:
        data = item["metadata"]
        require(Version(platform.python_version()) in SpecifierSet(data.get("requires_python", "")),
                "dependency does not support the readiness interpreter")
        name = canonicalize_name(data["name"])
        require(name not in packages, "duplicate resolved package")
        packages[name] = data
        download = item["download_info"]
        url = urlsplit(download["url"])
        hashes = download["archive_info"]["hashes"]
        require(bool(re.fullmatch(r"[0-9a-f]{64}", hashes.get("sha256", ""))), "missing artifact hash")
        if name == root["name"]:
            roots += 1
            require(download["url"] == wheel.as_uri(), "resolver replaced the root wheel")
            require(hashes["sha256"] == (expected_digest or digest(wheel)), "root wheel digest mismatch")
            require(data["version"] == root["version"], "root wheel version mismatch")
            require(data.get("requires_dist", []) == root["requires_dist"], "root requirements changed")
        else:
            require(not item.get("is_direct", False), "direct dependency in resolution")
            require(url.scheme == "https" and url.hostname == "files.pythonhosted.org", "non-public artifact")
            require(url.port in (None, 443) and url.username is None and url.password is None, "invalid artifact origin")
            require(url.path.endswith(".whl"), "source dependencies cannot prove wheel readiness")
        for raw in data.get("requires_dist", []):
            require(Requirement(raw).url is None, "transitive direct URL dependency")
    require(roots == 1, "exactly one root wheel required")
    check_closure(packages, root["name"], profile, report["environment"])


def check_closure(packages: dict, root: str, profile: str, environment: dict) -> None:
    pending = [(root, "" if profile == "base" else profile)]
    visited = set()
    while pending:
        name, extra = pending.pop()
        if (name, extra) in visited:
            continue
        visited.add((name, extra))
        package = packages[name]
        available = {canonicalize_name(value) for value in package.get("provides_extra", [])}
        require(not extra or extra in available, "unknown transitive extra")
        for raw in package.get("requires_dist", []):
            req = Requirement(raw)
            if req.marker and not req.marker.evaluate({**environment, "extra": extra}):
                continue
            dependency = canonicalize_name(req.name)
            require(dependency in packages, "missing transitive runtime dependency")
            require(Version(packages[dependency]["version"]) in req.specifier, "unsatisfied runtime constraint")
            pending.extend((dependency, item) for item in {"", *req.extras})


def resolve(wheel: Path, root: dict, selected: list[str], scratch: Path) -> list[dict]:
    resolver = Path(__file__).with_name("resolve.py").resolve()
    evidence = []
    for profile in selected:
        home = scratch / profile
        home.mkdir()
        env = clean_environment(home, wheel)
        venv = home / "venv"
        subprocess.run([sys.executable, "-I", "-m", "venv", str(venv)], env=env, cwd=home, check=True)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        report_path = home / "report.json"
        target = str(wheel) + (f"[{profile}]" if profile != "base" else "")
        subprocess.run(
            [str(python), "-I", str(resolver), "install", "--ignore-installed",
             "--no-cache-dir", "--disable-pip-version-check", "--no-input", "--only-binary=:all:",
             "--index-url", PUBLIC_INDEX, "--report", str(report_path), target],
            env=env, cwd=home, check=True, timeout=600,
        )
        # Do not start Python in the populated venv: installed .pth files must
        # not execute. Validate the report in the separate checker interpreter.
        report = json.loads(report_path.read_text())
        validate_report(report, wheel, root, profile)
        evidence.append({"profile": profile, "report": report})
    return evidence


def wheel_set(directory: Path) -> list[Path]:
    files = sorted(directory.iterdir())
    require(bool(files), "no wheels to validate")
    require(all(path.is_file() and not path.is_symlink() and path.suffix == ".whl" for path in files),
            "release directory must contain only regular wheels; sdists need separate proof")
    return files


def interpreter() -> dict:
    return {"implementation": platform.python_implementation(), "version": platform.python_version(),
            "platform": sys.platform, "machine": platform.machine()}


def check(directory: Path, receipt: Path, raw: str) -> None:
    receipt.unlink(missing_ok=True)
    proof = {"schema": 1, "index": PUBLIC_INDEX, "scope": "all-runtime-dependencies",
             **identity(), "interpreter": interpreter(), "wheels": []}
    for wheel in wheel_set(directory):
        root = metadata(wheel)
        selected = profiles(raw, root["provides_extra"])
        original = digest(wheel)
        with tempfile.TemporaryDirectory(prefix="wheel-readiness-") as temp:
            scratch = Path(temp)
            copy = scratch / wheel.name
            shutil.copyfile(wheel, copy)
            require(digest(copy) == original, "wheel changed while copying")
            evidence = resolve(copy, root, selected, scratch)
        require(digest(wheel) == original, "wheel changed during readiness check")
        proof["wheels"].append({"file": wheel.name, "sha256": original,
                                "metadata": root, "profiles": selected, "evidence": evidence})
    require(identity()["source_commit"] == proof["source_commit"], "source changed")
    receipt.write_text(json.dumps(proof, indent=2) + "\n")


def verify(directory: Path, receipt: Path, raw: str) -> None:
    proof = json.loads(receipt.read_text())
    require(proof["schema"] == 1 and proof["scope"] == "all-runtime-dependencies", "invalid proof scope")
    require(proof["index"] == PUBLIC_INDEX, "invalid proof index")
    require(proof["interpreter"] == interpreter(), "proof interpreter changed")
    for key, value in identity().items():
        require(proof[key] == value, "proof source/contract identity mismatch")
    files = wheel_set(directory)
    require([path.name for path in files] == [item["file"] for item in proof["wheels"]], "wheel set changed")
    for path, item in zip(files, proof["wheels"], strict=True):
        require(digest(path) == item["sha256"], "wheel bytes changed")
        require(profiles(raw, metadata(path)["provides_extra"]) == item["profiles"], "profiles changed")
        require([entry["profile"] for entry in item["evidence"]] == item["profiles"], "profile proof missing")
        for entry in item["evidence"]:
            report = entry["report"]
            candidates = [candidate for candidate in report["install"]
                          if canonicalize_name(candidate["metadata"]["name"]) == item["metadata"]["name"]]
            require(len(candidates) == 1, "missing root evidence")
            root_url = urlsplit(candidates[0]["download_info"]["url"])
            require(root_url.scheme == "file", "root proof must refer to a local wheel")
            original = Path(unquote(root_url.path))
            require(original.name == path.name, "proof wheel filename changed")
            validate_report(report, original, metadata(path), entry["profile"], digest(path))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("check", "verify"))
    parser.add_argument("--directory", type=Path, default=Path("dist"))
    parser.add_argument("--receipt", type=Path, default=Path("release-readiness.json"))
    args = parser.parse_args()
    try:
        {"check": check, "verify": verify}[args.phase](
            args.directory.resolve(), args.receipt.resolve(), os.environ.get("RUNTIME_PROFILES", "")
        )
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"Release readiness blocked: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
