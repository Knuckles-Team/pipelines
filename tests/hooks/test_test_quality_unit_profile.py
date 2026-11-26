"""PIPE-PAGES-R021.55-.60: the hermetic unit profile denies network and container access."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pipelines_hooks.code import unit_profile
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo

CATEGORIES = ("adapter", "retriever", "server", "cli")
POLICY = """version = 1
runner = ["{py}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist", "--rootdir=."]
required_categories = ["adapter", "retriever", "server", "cli"]
seed = 1234
clock = "2026-01-01T00:00:00Z"
{categories}
[[seams]]
name = "database"
double = "tests/doubles.py"
contract = "tests/contracts.md"
"""
DOUBLES = "import os\n\nCLOCK = os.environ['PIPELINES_UNIT_CLOCK']\nSEED = int(os.environ['PIPELINES_UNIT_SEED'])\n"
CLEAN = "from tests.doubles import CLOCK, SEED\n\n\ndef test_{name}():\n    assert CLOCK == '2026-01-01T00:00:00Z' and SEED == 1234\n"


def policy(**omit: bool) -> str:
    blocks = "".join(
        f'[[categories]]\nname = "{c}"\ntests = ["tests/test_{c}.py"]\n' for c in CATEGORIES if c not in omit
    )
    if "retriever" in omit:
        blocks += '[[categories]]\nname = "retriever"\ntests = []\n'
    return POLICY.format(py=sys.executable, categories=blocks)


def build(tmp_path: Path, **override: str) -> Repo:
    files = {f"tests/test_{c}.py": CLEAN.format(name=c) for c in CATEGORIES}
    files.update(
        {
            "tests/doubles.py": DOUBLES,
            "tests/__init__.py": "",
            "tests/contracts.md": "the database double returns fixed rows\n",
            "pytest.ini": "[pytest]\npythonpath = .\n",
            ".pipelines/unit.toml": policy(),
            "coverage.json": json.dumps({"totals": {"percent_covered": 99}}),
        }
    )
    files.update(override)
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.commit(files)
    return repo


SOCKET = (
    "import socket\n\nimport pytest\n\n\ndef test_egress():\n"
    "    with pytest.raises(PermissionError):\n"
    "        socket.create_connection(('203.0.113.9', 80), timeout=1)\n"
)
CONTAINER = (
    "import subprocess\n\nimport pytest\n\n\ndef test_container():\n"
    "    with pytest.raises(PermissionError):\n"
    "        subprocess.run(['docker', 'ps'], check=False)\n"
)
CHILD = (
    "import subprocess\nimport sys\n\n\ndef test_child_process():\n"
    "    code = \"import socket; socket.create_connection(('203.0.113.9', 80), timeout=1)\"\n"
    "    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)\n"
    "    assert 'unit profile denies' in out.stderr\n"
)


# spec: PIPE-PAGES-R021.55
def test_profile_inventories_categories_and_doubles(tmp_path: Path) -> None:
    build(tmp_path)
    ev = unit_profile.check(tmp_path, tmp_path / ".pipelines/unit.toml").evidence
    assert sorted(ev["categories"]) == sorted(CATEGORIES)  # type: ignore[arg-type]
    assert ev["doubles"] == [{"seam": "database", "double": "tests/doubles.py", "contract": "tests/contracts.md"}]
    assert (ev["seed"], ev["clock"]) == (1234, "2026-01-01T00:00:00Z")


# spec: PIPE-PAGES-R021.56
def test_runner_isolates_state_and_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_API_TOKEN", "must-not-leak")
    leak = "import os\nfrom pathlib import Path\n\n\ndef test_adapter():\n    assert 'SERVICE_API_TOKEN' not in os.environ\n    assert not str(Path.home()).startswith('/home')\n"
    build(tmp_path, **{"tests/test_adapter.py": leak})
    assert unit_profile.check(tmp_path, tmp_path / ".pipelines/unit.toml").findings == []


# spec: PIPE-PAGES-R021.57
def test_explicit_selection_and_subprocess_enforcement(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = build(tmp_path, **{"tests/test_server.py": CHILD})
    assert repo.run("test-quality", "--unit-profile", ".pipelines/unit.toml") == 1
    assert (
        "tests/test_server.py:1 isolation-violation" in capsys.readouterr().out
    )  # the child's attempt is denied and logged
    result = unit_profile.check(tmp_path, tmp_path / ".pipelines/unit.toml")
    assert [d["kind"] for d in result.evidence["denied"]] == ["network"]  # type: ignore[attr-defined,union-attr]


# spec: PIPE-PAGES-R021.58
def test_denials_fail_with_identity_and_missing_inputs_refuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = build(tmp_path, **{"tests/test_cli.py": SOCKET})
    assert repo.run("test-quality", "--unit-profile", ".pipelines/unit.toml") == 1
    assert "tests/test_cli.py:1 isolation-violation" in capsys.readouterr().out
    repo.commit({".pipelines/unit.toml": policy(retriever=True)})
    assert repo.run("test-quality", "--unit-profile", ".pipelines/unit.toml") == 2
    repo.commit({".pipelines/unit.toml": policy().replace(sys.executable, "/bin/sh")})
    with pytest.raises(CannotRun, match="unsupported isolation"):
        unit_profile.check(tmp_path, tmp_path / ".pipelines/unit.toml")
    repo.commit({".pipelines/unit.toml": policy(), "tests/doubles.py": DOUBLES})
    repo.git("rm", "-q", "tests/doubles.py")
    repo.git("commit", "-q", "-m", "drop double")
    with pytest.raises(CannotRun, match="deterministic double"):
        unit_profile.check(tmp_path, tmp_path / ".pipelines/unit.toml")


# spec: PIPE-PAGES-R021.59
def test_evidence_binds_digests_and_keeps_integration_separate(tmp_path: Path) -> None:
    repo = build(tmp_path, **{"tests/test_cli.py": CONTAINER})
    ev = unit_profile.check(tmp_path, tmp_path / ".pipelines/unit.toml").evidence
    assert [(d["kind"], d["target"]) for d in ev["denied"]] == [("container-or-network-client", "['docker', 'ps']")]  # type: ignore[attr-defined,union-attr]
    assert ev["denied"][0]["who"].startswith("tests/test_cli.py::test_container")  # type: ignore[index]
    assert len(str(ev["policy_digest"])) == 64 and len(str(ev["source_digest"])) == 64
    assert "required separately" in str(ev["integration_receipts"])
    assert repo.root == tmp_path


# spec: PIPE-PAGES-R021.60
def test_hot_path_socket_container_and_subprocess_attempts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    attempts = {"tests/test_adapter.py": SOCKET, "tests/test_retriever.py": CONTAINER, "tests/test_server.py": CHILD}
    repo = build(tmp_path, **attempts)
    assert repo.run("test-quality", "--unit-profile", ".pipelines/unit.toml") == 1
    out = capsys.readouterr().out
    assert (
        "tests/test_adapter.py:1 isolation-violation" in out and "tests/test_retriever.py:1 isolation-violation" in out
    )
    clean = {f"tests/test_{c}.py": CLEAN.format(name=c) for c in CATEGORIES}
    repo.commit(clean)
    first = unit_profile.check(tmp_path, tmp_path / ".pipelines/unit.toml").evidence
    second = unit_profile.check(tmp_path, tmp_path / ".pipelines/unit.toml").evidence
    assert first == second and first["denied"] == []
    assert "integration" in str(first["integration_receipts"])
