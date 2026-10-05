"""Fixtures that model a caller without pipeline-owned action files."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from pipelines_hooks.core.gitenv import sanitized_env


def external_caller(tmp_path: Path, root: Path, name: str, workflow: str) -> Path:
    caller = tmp_path / name
    workflow_dir = caller / ".github/workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "release.yml").write_text(workflow, encoding="utf-8")
    contract_actions = caller / ".pipeline-contract/.github/actions"
    contract_actions.mkdir(parents=True)
    for action in (root / ".github/actions").iterdir():
        if action.is_dir():
            shutil.copytree(action, contract_actions / action.name)
    return caller


def runtime_checkout(root: Path) -> str:
    """Make an isolated source identity without using the operator's Git identity."""
    environment = sanitized_env()
    for arguments in (("init", "-q"), ("-c", "user.name=workflow-fixture", "-c",
                                       "user.email=workflow@example.invalid", "-c", "commit.gpgsign=false",
                                       "commit", "--allow-empty", "-qm", "runtime fixture")):
        subprocess.run(["git", "-C", str(root), *arguments], env=environment, check=True)
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], env=environment, text=True).strip()


def runtime_artifact(download: Path, name: str, *, source: str = "") -> dict:
    """Synthetic wheel bytes exercise transport checks, not producer qualification."""
    directory = "eg-wheel" if name == "epistemic-graph" else "wheels"
    relative = f"{directory}/{name.replace('-', '_')}-1.0-py3-none-any.whl"
    path = download / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"synthetic transport fixture: {name}".encode())
    receipt = hashlib.sha256(name.encode()).hexdigest()
    return {"distribution": name, "version": "1.0", "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "payload_manifest_sha256": receipt,
            "source": {"repository": f"Example/{name}", "source_sha": source, "receipt_sha256": receipt} if source else None}


def runtime_manifest(download: Path, source: str) -> dict:
    artifacts = [runtime_artifact(download, name, source=source) for name in ("agent-utilities", "graph-os", "epistemic-graph")]
    artifacts.append(runtime_artifact(download, "dependency"))
    first_party = [{"distribution": item["distribution"], "version": item["version"],
                    "repository": item["source"]["repository"], "source_sha": source,
                    "extras": [], "pyproject_sha256": item["sha256"]} for item in artifacts[:3]]
    lock = "\n".join(f"{item['distribution']} @ file:///opt/graphos-runtime/{item['path']} \\\n    --hash=sha256:{item['sha256']}" for item in artifacts) + "\n"
    lock = lock.replace(f"dependency @ file:///opt/graphos-runtime/{artifacts[-1]['path']}", "dependency==1.0")
    (download / "requirements.lock").write_text(lock, encoding="utf-8")
    receipt = hashlib.sha256(lock.encode()).hexdigest()
    return {"schema": "graphos-runtime-wheel-inputs/1",
            "profile": {"name": "graphos", "target": {"python": "3.14", "implementation": "cpython", "os": "linux", "arch": "x86_64"},
                        "first_party": first_party, "explicit_third_party_roots": ["dependency==1.0"]},
            "requirements_lock": {"path": "requirements.lock", "sha256": receipt}, "artifacts": artifacts,
            "resolver_receipt_sha256": receipt, "verification_receipt_sha256": receipt}


def runtime_case(tmp_path: Path, root: Path) -> dict:
    caller = external_caller(tmp_path, root, "caller", "name: Container caller\n")
    source = runtime_checkout(caller)
    pipeline = runtime_checkout(caller / ".pipeline-contract")
    download = tmp_path / "download"
    download.mkdir()
    manifest = runtime_manifest(download, source)
    environment = {**sanitized_env(), "GITHUB_WORKSPACE": str(caller), "RUNNER_TEMP": str(tmp_path),
                   "GITHUB_OUTPUT": str(tmp_path / "outputs"), "RUNTIME_DOWNLOAD": str(download),
                   "EXPECTED_SOURCE": source, "EXPECTED_PIPELINE": pipeline, "CALLER_REPOSITORY": "Example/agent-utilities"}
    inputs = {"build-context": ".", "artifact-id": "1234", "profile": "graphos", "source-revision": source,
              "graph-os-revision": source, "lock-sha256": manifest["requirements_lock"]["sha256"], "freeze-sha256": ""}
    return {"caller": caller, "download": download, "manifest": manifest, "environment": environment, "inputs": inputs}


def freeze_runtime(case: dict) -> None:
    freeze = case["download"] / "source-freeze.json"
    freeze.write_text(json.dumps(case["manifest"]), encoding="utf-8")
    case["inputs"]["freeze-sha256"] = hashlib.sha256(freeze.read_bytes()).hexdigest()
    case["environment"]["RUNTIME_INPUTS"] = json.dumps(case["inputs"])


def run_runtime_helper(case: dict, phase: str = "stage") -> subprocess.CompletedProcess:
    script = case["caller"] / ".pipeline-contract/.github/actions/stage-container-runtime/stage_runtime.py"
    return subprocess.run([sys.executable, "-I", str(script), phase], cwd=case["caller"],
                          env=case["environment"], text=True, capture_output=True)
