"""Connector security and setup scaffold owned by pipelines (PIPE-VALIDATION-R001.10-.12)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES, run_gate
from pipelines_hooks.connector import api_parity, files, security
from pipelines_hooks.connector import cli as connector_cli
from pipelines_hooks.core.errors import CannotRun
from tests.git_fixture_environment import fixture_git_environment

PYPROJECT = '[project]\nname = "demo-mcp"\nversion = "1.2.3"\n'
PINNED = "a" * 40
CLEAN_WORKFLOW = f"on: push\npermissions: {{}}\njobs:\n  x:\n    steps:\n      - uses: actions/checkout@{PINNED}\n"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], env=fixture_git_environment(), check=True, capture_output=True)


def _repo(tmp_path: Path, pyproject: str = PYPROJECT) -> Path:
    root = tmp_path / "demo-mcp"
    (root / "demo_mcp").mkdir(parents=True)
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    _git(root, "init", "-q")
    return root


def _write(root: Path, name: str, text: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text, encoding="utf-8")


# --- PIPE-VALIDATION-R001.10: .security/* is provided -----------------------------------------------------------
@pytest.mark.spec("PIPE-VALIDATION-R001.10")
def test_fuzz_and_negative_checks_write_the_evidence_the_contract_expects(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "data.json", '{"a": 1}')
    _write(root, ".github/workflows/ci.yml", CLEAN_WORKFLOW)
    fuzz, negative = tmp_path / "out/fuzz.json", tmp_path / "out/neg.json"
    assert connector_cli.main(["security", "--root", str(root), "fuzz", str(fuzz)]) == 0
    assert connector_cli.main(["security", "--root", str(root), "authenticated-negative", str(negative)]) == 0
    hooks = security.contract(root)["hooks"]
    report = json.loads(fuzz.read_text(encoding="utf-8"))
    assert report["passed"] and report["cases"] >= hooks["fuzz"]["min_cases"] and report["crashes"] == 0
    report = json.loads(negative.read_text(encoding="utf-8"))
    assert report["passed"] and report["cases"] >= hooks["authenticated_negative"]["min_cases"]
    assert report["unauthorized_acceptances"] == 0


@pytest.mark.spec("PIPE-VALIDATION-R001.10")
@pytest.mark.parametrize(
    ("workflow", "finding"),
    [
        ("on:\n  pull_request_target:\npermissions: {}\n", "privileged pull-request trigger"),
        ("on: push\npermissions: write-all\n", "broad token permissions"),
        ("on: push\npermissions: {}\njobs:\n  x:\n    steps:\n      - uses: a/b@main\n", "mutable action"),
        ("on: push\njobs:\n  x:\n    steps:\n      - uses: docker://img:1\n", "mutable container action"),
        (
            "on: push\njobs:\n  x:\n    steps:\n      - run: |\n          echo ${{ secrets.T }}\n",
            "secret expression in shell",
        ),
    ],
)
def test_a_risky_workflow_is_a_finding_and_fails_the_check(tmp_path: Path, workflow: str, finding: str) -> None:
    root = _repo(tmp_path)
    _write(root, ".github/workflows/bad.yml", workflow)
    assert finding in security.violations(workflow)
    assert any("authenticated_negative failed" in line for line in security.check(root))
    assert run_gate("connector-standard", ["--root", str(root)]) in (1, 2)
    assert security.violations(CLEAN_WORKFLOW) == [] and security.violations("./local@x") == []


OWN = "Knuckles-Team/pipelines/.github/workflows/python_pipeline.yml@main"


def _caller(ref: str) -> str:
    return f"on: push\npermissions: {{}}\njobs:\n  x:\n    uses: {ref}\n"


@pytest.mark.spec("PIPE-VALIDATION-R001.10")
def test_the_organizations_own_shared_workflows_are_allowed_at_main(tmp_path: Path) -> None:
    assert security.violations(_caller(OWN)) == []
    root = _repo(tmp_path)
    _write(root, ".github/workflows/ci.yml", _caller(OWN))
    assert security.check(root) == []


@pytest.mark.spec("PIPE-VALIDATION-R001.10")
@pytest.mark.parametrize(
    "ref",
    [
        "Knuckles-Team/other-repo/.github/workflows/python_pipeline.yml@main",
        "Knuckles-Team/pipelines-evil/.github/workflows/python_pipeline.yml@main",
        "Other-Org/pipelines/.github/workflows/python_pipeline.yml@main",
        "Knuckles-Team/pipelines/.github/workflows/python_pipeline.yml@v1",
        "Knuckles-Team/pipelines/.github/actions/x@main",
        "actions/checkout@main",
        "actions/checkout@v4",
    ],
)
def test_every_other_branch_or_tag_reference_stays_a_mutable_action(ref: str) -> None:
    assert "mutable action" in security.violations(_caller(ref))


@pytest.mark.spec("PIPE-VALIDATION-R001.10")
def test_contract_is_the_shared_default_plus_pyproject_license_additions(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    default = security.contract(root)
    assert default["version"] == 1 and "MIT" in default["license_policy"]["allowed"]
    assert default["license_policy"]["allow_unknown"] is False
    assert default["hooks"]["fuzz"]["argv"][:3] == ["pipelines-connector", "security", "fuzz"]
    extended = _repo(
        tmp_path / "x",
        PYPROJECT + '[tool.pipelines.security]\nlicense_allowed = ["PSF-2.0"]\nlicense_denied = ["SSPL-1.0"]\n',
    )
    policy = security.contract(extended)["license_policy"]
    assert (
        "PSF-2.0" in policy["allowed"]
        and "SSPL-1.0" in policy["denied"]
        and policy["allowed"] == sorted(policy["allowed"])
    )
    out = tmp_path / "rendered.json"
    assert connector_cli.main(["security", "--root", str(extended), "contract", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == security.contract(extended)


@pytest.mark.spec("PIPE-VALIDATION-R001.10")
def test_contract_refuses_unknown_keys_and_an_allow_deny_overlap(tmp_path: Path) -> None:
    unknown = _repo(tmp_path / "a", PYPROJECT + "[tool.pipelines.security]\nlicense_alowed = []\n")
    with pytest.raises(CannotRun, match="unknown keys"):
        security.contract(unknown)
    overlap = _repo(tmp_path / "b", PYPROJECT + '[tool.pipelines.security]\nlicense_denied = ["MIT"]\n')
    with pytest.raises(CannotRun, match="allows and denies"):
        security.contract(overlap)


@pytest.mark.spec("PIPE-VALIDATION-R001.10")
def test_committed_security_files_are_findings_unless_a_legacy_validator_reads_the_contract(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    planted = [
        ".security/repository_fuzz.py",
        ".security/authenticated_negative.py",
        ".security/security-contract.json",
    ]
    for name in planted:
        _write(root, name, "x\n")
    _git(root, "add", "--", *planted)
    assert len(files.findings(root)) == 3
    _write(root, "scripts/security_contract.py", "x\n")
    _git(root, "add", "--", "scripts/security_contract.py")
    found = files.findings(root)
    assert len(found) == 2 and not any("security-contract.json" in line for line in found)


# --- PIPE-VALIDATION-R001.11: bootstrap.sh is dead -----------------------------------------------------------
@pytest.mark.spec("PIPE-VALIDATION-R001.11")
def test_committed_bootstrap_script_is_a_finding_that_names_what_replaces_it(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "scripts/bootstrap.sh", "#!/usr/bin/env bash\n")
    _git(root, "add", "--", "scripts/bootstrap.sh")
    (line,) = files.findings(root)
    assert "scripts/bootstrap.sh" in line and "uv sync --locked" in line and "pre-commit install" in line


# --- PIPE-VALIDATION-R001.12: API-to-MCP parity -----------------------------------------------------------------
CLIENT = """class DemoApi:
    def authenticate(self): ...
    def _private(self): ...
    def get_a(self): ...
    def get_b(self): ...
    def get_c(self): ...
    def get_d(self): ...
"""
SERVER = """DEMO_ACTIONS = ("get_c", "get_d")

@mcp.tool()
def one(client):
    return client.get_a()

@mcp.tool
def many(action, client):
    action = resolve_action(action, DEMO_ACTIONS)
    return getattr(client, action)()

def demo_plain(client):
    return client.get_b()
"""


def _parity_repo(tmp_path: Path, table: str = "") -> Path:
    root = _repo(tmp_path, PYPROJECT + table)
    _write(root, "demo_mcp/api_client.py", CLIENT)
    _write(root, "demo_mcp/mcp_server.py", SERVER)
    return root


@pytest.mark.spec("PIPE-VALIDATION-R001.12")
def test_parity_counts_decorated_tools_and_catalog_dispatch_and_prefixed_tools_only_when_configured(
    tmp_path: Path,
) -> None:
    root = _parity_repo(tmp_path)
    plain = api_parity.measure(root, ())
    assert plain is not None and plain["total"] == 4 and plain["unmapped"] == ["get_b"] and plain["coverage"] == 75.0
    prefixed = api_parity.measure(root, ("demo_",))
    assert prefixed is not None and prefixed["coverage"] == 100.0 and prefixed["unmapped"] == []


@pytest.mark.spec("PIPE-VALIDATION-R001.12")
def test_parity_fails_below_the_pyproject_baseline_and_lists_unmapped_methods(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    low = _parity_repo(tmp_path / "low", "[tool.pipelines.api_integration]\nbaseline = 75.0\n")
    assert api_parity.main(["--root", str(low)]) == 0
    assert "get_b" in capsys.readouterr().out
    high = _parity_repo(tmp_path / "high", "[tool.pipelines.api_integration]\nbaseline = 90\n")
    assert api_parity.main(["--root", str(high)]) == 1
    assert "FAILED" in capsys.readouterr().out
    default = _parity_repo(tmp_path / "default")
    assert api_parity.main(["--root", str(default)]) == 0


@pytest.mark.spec("PIPE-VALIDATION-R001.12")
def test_parity_passes_without_a_client_or_server_and_refuses_bad_configuration(tmp_path: Path) -> None:
    root = _repo(tmp_path / "none")
    assert api_parity.main(["--root", str(root)]) == 0
    for bad in (
        "[tool.pipelines.api_integration]\nbaselin = 1\n",
        "[tool.pipelines.api_integration]\nbaseline = 101\n",
        '[tool.pipelines.api_integration]\ntool_prefixes = "x"\n',
    ):
        with pytest.raises(CannotRun):
            api_parity.main(["--root", str(_parity_repo(tmp_path / str(abs(hash(bad))), bad))])


@pytest.mark.spec("PIPE-VALIDATION-R001.12")
def test_a_committed_parity_script_is_a_finding_and_standard_runs_every_member(tmp_path: Path) -> None:
    root = _parity_repo(tmp_path, "[tool.pipelines.api_integration]\nbaseline = 99\n")
    assert GATES["connector-standard"] == "pipelines_hooks.connector.standard"
    assert run_gate("connector-standard", ["--root", str(root)]) in (1, 2)
    clean = _parity_repo(tmp_path / "clean")
    _write(clean, "scripts/verify_api_integration.py", "x\n")
    _write(clean, "tests/test_verify_api_integration.py", "x\n")
    _git(clean, "add", "--", "scripts/verify_api_integration.py", "tests/test_verify_api_integration.py")
    assert len(files.findings(clean)) == 2
