"""Verify transport of a producer-qualified offline context; never resolve packages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def hex_value(value: str, length: int = 64) -> bool:
    return bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value)) and set(value) != {"0"}


def normalized(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def local_path(root: Path, value: str) -> Path:
    require(value and not value.startswith("/") and "\\" not in value, "Expected relative path")
    parts = value.split("/")
    require(not any(part in ("..", "") for part in parts), "Unsafe relative path")
    require(not any(part.startswith(".git") or part == ".pipeline-contract" for part in parts), "Reserved path")
    current = root
    for part in parts:
        current = current / part
        require(not current.is_symlink(), "Symlink path is forbidden")
    require(current.resolve().is_relative_to(root.resolve()), "Path escapes root")
    return current


class Runtime:
    def __init__(self, environment: dict[str, str]):
        self.env = environment
        self.inputs = json.loads(environment["RUNTIME_INPUTS"])
        self.workspace = Path(environment["GITHUB_WORKSPACE"]).resolve()
        self.context = local_path(self.workspace, self.inputs["build-context"])
        self.destination = local_path(self.context, "build-artifacts/runtime")

    def prepare(self) -> None:
        values = self.inputs
        require(re.fullmatch(r"[1-9][0-9]*", values["artifact-id"]), "One immutable artifact ID is required")
        require(re.fullmatch(r"graphos|connector/[a-z0-9]+(?:-[a-z0-9]+)*", values["profile"]), "Invalid runtime profile")
        for key in ("lock-sha256", "freeze-sha256"):
            require(hex_value(values[key]), f"Missing or invalid {key}")
        require(hex_value(values["source-revision"], 40), "Full source revision is required")
        graph = values["graph-os-revision"]
        require(not graph or hex_value(graph, 40), "Invalid GraphOS revision")
        require(self.context.is_dir(), "Local build context is required")
        require(not self.destination.exists(), "Runtime destination already exists; refusing overlay")
        for root, expected in ((self.workspace, self.env["EXPECTED_SOURCE"]),
                               (self.workspace / ".pipeline-contract", self.env["EXPECTED_PIPELINE"])):
            actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            require(hex_value(expected, 40) and actual == expected, "Checkout revision mismatch")
        require(values["source-revision"] == self.env["EXPECTED_SOURCE"], "Caller source revision mismatch")

    def profile(self, manifest: dict) -> dict:
        profile = manifest["profile"]
        require(profile["name"] == self.inputs["profile"], "Profile mismatch")
        require(profile["target"] == {"python": "3.14", "implementation": "cpython", "os": "linux", "arch": "x86_64"}, "Unsupported runtime target")
        require(isinstance(profile["explicit_third_party_roots"], list), "Missing explicit roots")
        first_party = {}
        for item in profile["first_party"]:
            name = normalized(item["distribution"])
            require(name not in first_party and item["version"], "Duplicate or incomplete first-party identity")
            require(hex_value(item["source_sha"], 40) and hex_value(item["pyproject_sha256"]), "Invalid frozen source identity")
            require(isinstance(item["extras"], list) and all(isinstance(extra, str) for extra in item["extras"]), "Missing extras")
            first_party[name] = item
        require(first_party, "No first-party sources")
        self.bind_sources(first_party)
        return first_party

    def bind_sources(self, first_party: dict) -> None:
        caller = self.env["CALLER_REPOSITORY"]
        repositories = {caller, caller.split("/")[-1], f"https://github.com/{caller}", f"https://github.com/{caller}.git"}
        matches = [item for item in first_party.values() if item["repository"] in repositories]
        require(len(matches) == 1 and matches[0]["source_sha"] == self.inputs["source-revision"], "Caller source absent or mismatched in freeze")
        graph = first_party.get("graph-os", {}).get("source_sha", "")
        require(graph == self.inputs["graph-os-revision"], "GraphOS source mismatch")
        profile = self.inputs["profile"]
        require(profile != "graphos" or graph, "GraphOS profile requires graph-os")
        if profile.startswith("connector/"):
            connector = profile.split("/", 1)[1]
            require(connector == normalized(matches[0]["distribution"]), "Connector profile must match caller")
            require("mcp" in matches[0]["extras"], "Connector profile requires mcp extra")

    def artifacts(self, root: Path, manifest: dict, *, first_party: dict) -> dict:
        artifacts = {}
        paths = set()
        for item in manifest["artifacts"]:
            name = normalized(item["distribution"])
            relative = item["path"]
            require(re.fullmatch(r"(?:wheels|eg-wheel)/[A-Za-z0-9_.+!-]+\.whl", relative), "Invalid wheel path")
            require(name not in artifacts and relative not in paths, "Duplicate wheel identity")
            require(hex_value(item["sha256"]) and digest(local_path(root, relative)) == item["sha256"], "Wheel digest mismatch")
            require(hex_value(item["payload_manifest_sha256"]), "Missing payload receipt")
            expected_source = first_party.get(name)
            if expected_source:
                source = item["source"]
                require(item["version"] == expected_source["version"], "First-party version mismatch")
                require(all(source[key] == expected_source[key] for key in ("repository", "source_sha")), "Wheel source mismatch")
                require(hex_value(source["receipt_sha256"]), "Missing source receipt")
            else:
                require(item["source"] is None, "Undeclared first-party source")
            require((name == "epistemic-graph") == relative.startswith("eg-wheel/"), "Invalid EG wheel placement")
            paths.add(relative)
            artifacts[name] = item
        require(set(first_party) <= artifacts.keys(), "Missing first-party wheel")
        expected = paths | {"requirements.lock", "source-freeze.json"}
        actual = set()
        for path in root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            require(not path.is_symlink(), "Symlinks are forbidden")
            require(path.is_file() or relative in ("wheels", "eg-wheel"), "Unexpected directory or special file")
            if path.is_file():
                actual.add(relative)
        require(actual == expected, "Runtime file inventory mismatch")
        return artifacts

    def lock(self, root: Path, artifacts: dict, *, first_party: dict) -> None:
        content = (root / "requirements.lock").read_text(encoding="utf-8")
        lines = [line for line in content.splitlines() if not line.lstrip().startswith("#")]
        entries = "\n".join(lines).replace("\\\n", "").splitlines()
        seen = set()
        pattern = (r"([A-Za-z0-9_.-]+)(?:\[([A-Za-z0-9_,.-]+)\])?\s*"
                   r"(?:==([^\s;]+)|@\s*file:///opt/graphos-runtime/([^\s;]+))\s+"
                   r"((?:--hash=sha256:[0-9a-f]{64}\s*)+)")
        for line in filter(str.strip, entries):
            match = re.fullmatch(pattern, line.strip())
            require(match, "Lock must contain only exact hashed wheel requirements")
            name, extras, version, relative, hashes = match.groups()
            name = normalized(name)
            require(name in artifacts and name not in seen, "Unknown or duplicate lock requirement")
            item = artifacts[name]
            require(set(re.findall(r"sha256:([0-9a-f]{64})", hashes)) == {item["sha256"]}, "Lock wheel hash mismatch")
            require(relative == item["path"] if relative else version == item["version"], "Lock artifact mismatch")
            if name in first_party:
                require(relative == item["path"], "First-party requirement must use its local wheel")
                require(set((extras or "").split(",")) - {""} == set(first_party[name]["extras"]), "First-party extras mismatch")
            seen.add(name)
        require(seen == artifacts.keys(), "Lock does not cover the exact wheel inventory")

    def verify(self, root: Path) -> None:
        freeze = local_path(root, "source-freeze.json")
        require(digest(freeze) == self.inputs["freeze-sha256"], "Source freeze digest mismatch")
        manifest = json.loads(freeze.read_text(encoding="utf-8"))
        require(manifest["schema"] == "graphos-runtime-wheel-inputs/1", "Unsupported freeze schema")
        for key in ("resolver_receipt_sha256", "verification_receipt_sha256"):
            require(hex_value(manifest[key]), f"Missing {key}")
        expected_lock = {"path": "requirements.lock", "sha256": self.inputs["lock-sha256"]}
        require(manifest["requirements_lock"] == expected_lock, "Frozen lock identity mismatch")
        require(digest(local_path(root, "requirements.lock")) == expected_lock["sha256"], "Lock digest mismatch")
        first_party = self.profile(manifest)
        artifacts = self.artifacts(root, manifest, first_party=first_party)
        self.lock(root, artifacts, first_party=first_party)

    def stage(self, download: Path) -> None:
        require(download.is_dir() and not download.is_symlink(), "Missing download directory")
        self.verify(download)
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".runtime-", dir=self.destination.parent) as temporary:
            candidate = Path(temporary) / "runtime"
            shutil.copytree(download, candidate, symlinks=True)
            self.verify(candidate)
            require(not self.destination.exists(), "Runtime destination appeared during staging")
            candidate.rename(self.destination)


def main() -> int:
    runtime = Runtime(dict(os.environ))
    runtime.prepare()
    if sys.argv[1:] == ["prepare"]:
        download = tempfile.mkdtemp(prefix="container-runtime-", dir=os.environ["RUNNER_TEMP"])
        output = f"download-path={download}\n"
    else:
        require(sys.argv[1:] == ["stage"], "Expected prepare or stage")
        runtime.stage(Path(os.environ["RUNTIME_DOWNLOAD"]))
        arguments = {"SOURCE_REVISION": "source-revision", "GRAPH_OS_REVISION": "graph-os-revision",
                     "RUNTIME_LOCK_SHA256": "lock-sha256", "SOURCE_FREEZE_SHA256": "freeze-sha256"}
        values = [f"{name}={runtime.inputs[key]}" for name, key in arguments.items() if runtime.inputs[key]]
        output = "build-args<<RUNTIME_ARGS\n" + "\n".join(values) + "\nRUNTIME_ARGS\n"
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Runtime staging refused: {error}", file=sys.stderr)
        raise SystemExit(1) from error
