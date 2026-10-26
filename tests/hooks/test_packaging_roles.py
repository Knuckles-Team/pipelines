"""PIPE-PAGES-R025 role/extra closure contract tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release.packaging_roles import RoleContract, parse_contract, validate_metadata, verify

ROOT = Path(__file__).parents[2]
READINESS = ROOT / ".github/actions/wheel-readiness/readiness.py"


def contract() -> RoleContract:
    return parse_contract(
        {
            "version": 1,
            "roles": [
                {"role": "base", "extra": None},
                {"role": "mcp", "extra": "mcp"},
            ],
        }
    )


def metadata() -> dict[str, list[str]]:
    return {"provides_extra": ["mcp"]}


def load_readiness():
    spec = importlib.util.spec_from_file_location("test_packaging_roles_readiness", READINESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wheel(tmp_path: Path) -> Path:
    path = tmp_path / "fixture-1.0-py3-none-any.whl"
    metadata_text = "\n".join(
        [
            "Metadata-Version: 2.3",
            "Name: fixture",
            "Version: 1.0",
            "Requires-Python: >=3.12",
            "Provides-Extra: mcp",
        ]
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fixture-1.0.dist-info/METADATA", metadata_text + "\n")
        archive.writestr(
            "fixture-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("fixture-1.0.dist-info/RECORD", "")
    return path


def readiness_fixture(tmp_path: Path) -> tuple[Path, str, dict, Path]:
    guard = load_readiness()
    artifact = wheel(tmp_path)
    context = guard.observed_context()
    root = guard.metadata(artifact, context)
    digest = guard.digest(artifact)
    pip_version = guard.sibling("bootstrap").PIN["version"]

    def report() -> dict:
        return {
            "version": "1",
            "pip_version": pip_version,
            "environment": context["environment"],
            "install": [
                {
                    "metadata": root,
                    "is_direct": True,
                    "download_info": {
                        "url": artifact.as_uri(),
                        "archive_info": {"hashes": {"sha256": digest}},
                    },
                }
            ],
        }

    item = {
        "file": artifact.name,
        "sha256": digest,
        "metadata": root,
        "profiles": ["base", "mcp"],
        "evidence": [{"profile": profile, "report": report()} for profile in ("base", "mcp")],
    }
    receipt = {
        "schema": 1,
        "scope": "all-runtime-dependencies",
        "index": guard.PUBLIC_INDEX,
        "context": context,
        "interpreter": context["interpreter"],
        "source_builds": [],
        "wheels": [item],
    }
    receipt_path = tmp_path / "release-readiness.json"
    receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    return artifact, digest, receipt, receipt_path


@pytest.mark.spec("PIPE-PAGES-R025.1")
def test_contract_model_uses_authoritative_profile_values_without_defaults() -> None:
    parsed = contract()
    assert parsed.version == 1
    assert [(item.role, item.extra) for item in parsed.bindings] == [("base", None), ("mcp", "mcp")]
    assert validate_metadata(parsed, metadata()) == parsed.bindings


@pytest.mark.spec("PIPE-PAGES-R025.2")
def test_role_gate_verifies_actual_wheel_readiness_closure(tmp_path: Path) -> None:
    artifact, digest, receipt, _ = readiness_fixture(tmp_path)
    result = verify(contract(), artifact, digest, receipt, READINESS, runtime_profiles="[]")
    assert result["schema"] == 1
    assert result["status"] == "pass"
    assert result["artifact"]["sha256"] == digest
    assert result["roles"] == [
        {"role": "base", "extra": None},
        {"role": "mcp", "extra": "mcp"},
    ]
    assert [item["status"] for item in result["evidence"]] == ["pass", "pass"]
    assert all(len(item["evidence_digest"]) == 64 for item in result["evidence"])


@pytest.mark.spec("PIPE-PAGES-R025.4")
@pytest.mark.parametrize(
    "bad",
    [
        {"version": 1, "roles": [{"role": "base", "extra": None}, {"role": "mcp", "extra": "missing"}]},
        {"version": 1, "roles": [{"role": "base", "extra": None}, {"role": "base", "extra": "foo-bar"}]},
        {"version": 2, "roles": [{"role": "base", "extra": None}]},
    ],
)
def test_role_contract_refuses_undeclared_duplicate_or_unknown_shapes(bad: dict[str, object]) -> None:
    with pytest.raises(CannotRun):
        parsed = parse_contract(bad)
        validate_metadata(parsed, metadata())


@pytest.mark.spec("PIPE-PAGES-R025.4")
def test_role_gate_refuses_tampered_artifact_digest_and_receipt_metadata(tmp_path: Path) -> None:
    artifact, digest, receipt, _ = readiness_fixture(tmp_path)
    with pytest.raises(CannotRun, match="wheel bytes"):
        verify(contract(), artifact, "b" * 64, receipt, READINESS)
    receipt["wheels"][0]["metadata"]["provides_extra"] = []
    with pytest.raises(CannotRun, match="metadata does not match"):
        verify(contract(), artifact, digest, receipt, READINESS)


def test_role_gate_refuses_runtime_profile_inventory_mismatch(tmp_path: Path) -> None:
    artifact, digest, receipt, _ = readiness_fixture(tmp_path)
    with pytest.raises(CannotRun, match="runtime profiles"):
        verify(contract(), artifact, digest, receipt, READINESS, runtime_profiles='["agent"]')


@pytest.mark.spec("PIPE-PAGES-R025.5")
def test_role_gate_evidence_digest_is_bound_to_verified_resolver_report(tmp_path: Path) -> None:
    artifact, digest, receipt, _ = readiness_fixture(tmp_path)
    result = verify(contract(), artifact, digest, receipt, READINESS)
    expected = hashlib.sha256(
        json.dumps(receipt["wheels"][0]["evidence"][0], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert result["evidence"][0]["evidence_digest"] == expected


@pytest.mark.spec("PIPE-PAGES-R025.6")
def test_packaging_role_closure_cli(tmp_path: Path) -> None:
    """The published dispatcher reaches the role closure gate with real files."""
    artifact, digest, _, receipt_path = readiness_fixture(tmp_path)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        json.dumps({"version": 1, "roles": [{"role": "base", "extra": None}, {"role": "mcp", "extra": "mcp"}]}) + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "pipelines-hook",
            "packaging-roles",
            "--contract",
            str(contract_path),
            "--wheel",
            str(artifact),
            "--wheel-sha256",
            digest,
            "--receipt",
            str(receipt_path),
            "--readiness-checker",
            str(READINESS),
            "--runtime-profiles",
            "[]",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["status"] == "pass"
    assert output["artifact"]["sha256"] == digest
    assert GATES["packaging-roles"] == "pipelines_hooks.release.packaging_roles"
