"""PIPE-PAGES-R025 role/extra closure contract tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release.packaging_roles import RoleContract, parse_contract, validate_metadata, verify


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


def evidence(
    *, status: str = "pass", role: str = "mcp", extra: str | None = "mcp"
) -> dict[str, list[dict[str, str | None]]]:
    return {
        "roles": [
            {"role": "base", "extra": None, "status": "pass", "evidence_digest": "a" * 64},
            {"role": role, "extra": extra, "status": status, "evidence_digest": "b" * 64},
        ]
    }


@pytest.mark.spec("PIPE-PAGES-R025.1")
def test_contract_model_normalizes_extras_without_inventing_roles() -> None:
    parsed = contract()
    assert parsed.version == 1
    assert [(item.role, item.extra) for item in parsed.bindings] == [("base", None), ("mcp", "mcp")]
    assert validate_metadata(parsed, metadata()) == parsed.bindings


@pytest.mark.spec("PIPE-PAGES-R025.2")
def test_role_closure_evidence_is_deterministic_and_reports_status() -> None:
    result = verify(contract(), metadata(), evidence())
    assert result["schema"] == 1
    assert result["status"] == "pass"
    assert result["roles"] == [
        {"role": "base", "extra": None},
        {"role": "mcp", "extra": "mcp"},
    ]
    assert result["evidence"][1]["evidence_digest"] == "b" * 64


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
def test_role_evidence_refuses_missing_or_mismatched_roles() -> None:
    with pytest.raises(CannotRun, match="inventory mismatch"):
        verify(contract(), metadata(), {"roles": evidence()["roles"][:1]})
    with pytest.raises(CannotRun, match="extra mismatch"):
        verify(contract(), metadata(), evidence(extra="other"))


@pytest.mark.spec("PIPE-PAGES-R025.5")
def test_role_evidence_retains_independent_digest_and_failure_state() -> None:
    result = verify(contract(), metadata(), evidence(status="fail"))
    assert result["status"] == "fail"
    assert [item["evidence_digest"] for item in result["evidence"]] == ["a" * 64, "b" * 64]


def test_role_module_cli_executes_bound_json_contract(tmp_path: Path) -> None:
    """The module boundary emits JSON for the later published-hook adapter."""
    payloads = {
        "contract.json": {
            "version": 1,
            "roles": [{"role": "base", "extra": None}, {"role": "mcp", "extra": "mcp"}],
        },
        "metadata.json": metadata(),
        "evidence.json": {
            "roles": [
                {
                    "role": "base",
                    "extra": None,
                    "status": "pass",
                    "evidence_digest": "a" * 64,
                },
                {
                    "role": "mcp",
                    "extra": "mcp",
                    "status": "pass",
                    "evidence_digest": "b" * 64,
                },
            ]
        },
    }
    for name, value in payloads.items():
        path = tmp_path / name
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        assert json.loads(path.read_text(encoding="utf-8")) == value
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipelines_hooks.release.packaging_roles",
            "--contract",
            str(tmp_path / "contract.json"),
            "--metadata",
            str(tmp_path / "metadata.json"),
            "--evidence",
            str(tmp_path / "evidence.json"),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "pass"
