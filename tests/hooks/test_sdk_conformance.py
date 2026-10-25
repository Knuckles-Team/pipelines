"""PIPE-GATES-R013: a connector uses the SDK capability instead of its own copy."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.hygiene import sdk_conformance

pytestmark = pytest.mark.spec("PIPE-GATES-R013")

_PYPROJECT = """[project]
name = "demo-api"
dependencies = ["agent-connector-sdk[mcp]>=0.3.11", "pymongo>=4.19.0"]
[project.optional-dependencies]
all = ["pymongo>=4.19.0", "gql[requests]>=4.4.0"]
"""

_VIOLATIONS = {
    "R001": [
        "import requests\n",
        "client = httpx.Client(timeout=5)\n",
        "for attempt in range(3):\n    pass\n",
        "wait = response.headers.get('Retry-After')\n",
    ],
    "R008": [
        "session.get(url, verify=False)\n",
        "urllib3.disable_warnings(InsecureRequestWarning)\n",
        "context = ssl.create_default_context(cafile=bundle)\n",
    ],
    "R009": ["if text.startswith(('env://', 'openbao://')):\n    pass\n"],
    "R016": ["from gql.transport.requests import RequestsHTTPTransport\n", "from gql import Client, gql\n"],
}


def _connector(root: Path, source: str, *, pyproject: str = _PYPROJECT) -> Path:
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    package = root / "demo_api"
    package.mkdir(exist_ok=True)
    (package / "client.py").write_text(source, encoding="utf-8")
    return root


def _rows(root: Path) -> list[str]:
    return [finding.row for finding in sdk_conformance.findings(root)]


@pytest.mark.parametrize(("row", "source"), [(row, src) for row, sources in _VIOLATIONS.items() for src in sources])
def test_each_reimplementation_cites_its_row(tmp_path: Path, row: str, source: str) -> None:
    found = sdk_conformance.findings(_connector(tmp_path, source))
    assert any(finding.row == row and finding.location == "demo_api/client.py:1" for finding in found)
    assert all(finding.render().startswith("SDK-CENTRALIZED-CAPABILITIES-") for finding in found)


def test_sdk_usage_is_clean(tmp_path: Path) -> None:
    source = (
        "import httpx\n"
        "from agent_connector_sdk.http import create_http_client\n"
        "from agent_connector_sdk.tls import resolve_tls_profile\n"
        "# import requests\n"
        "headers['Retry-After'] = str(seconds)\n"
        "response: httpx.Response\n"
    )
    pyproject = '[project]\nname = "demo-api"\ndependencies = ["agent-connector-sdk[db]>=0.3.11"]\n'
    assert sdk_conformance.findings(_connector(tmp_path, source, pyproject=pyproject)) == []


def test_branded_sdk_distribution_is_checked_and_exempt_when_it_is_the_sdk(tmp_path: Path) -> None:
    pyproject = '[project]\nname = "demo-api"\ndependencies = ["scion-sdk[db]>=0.3.11"]\n'
    found = [
        finding for finding in sdk_conformance.findings(_connector(tmp_path, "import requests\n", pyproject=pyproject))
    ]
    assert any(finding.row == "R001" for finding in found)
    sdk = tmp_path / "branded-sdk"
    sdk.mkdir()
    _connector(sdk, "import requests\n", pyproject='[project]\nname = "scion-sdk"\ndependencies = []\n')
    assert sdk_conformance.findings(sdk) == []


def test_extra_pins_are_one_finding_per_package_and_skip_graphql(tmp_path: Path) -> None:
    found = [finding for finding in sdk_conformance.findings(_connector(tmp_path, "")) if finding.row == "R040"]
    assert len(found) == 1
    assert "[project.dependencies]" in found[0].location
    assert "[project.optional-dependencies.all]" in found[0].location
    assert "agent-connector-sdk[db]" in found[0].message


def test_tests_scripts_and_non_connectors_are_skipped(tmp_path: Path) -> None:
    root = _connector(tmp_path, "")
    for folder in ("tests", "scripts"):
        (root / folder).mkdir()
        (root / folder / "helper.py").write_text("import requests\n", encoding="utf-8")
    (root / "demo_api" / "test_client.py").write_text("import requests\n", encoding="utf-8")
    assert "R001" not in _rows(root)

    other = tmp_path / "other"
    other.mkdir()
    _connector(other, "import requests\n", pyproject='[project]\nname = "plain"\ndependencies = ["httpx"]\n')
    assert sdk_conformance.findings(other) == []

    sdk = tmp_path / "sdk"
    sdk.mkdir()
    _connector(sdk, "import requests\n", pyproject='[project]\nname = "agent-connector-sdk"\ndependencies = []\n')
    assert sdk_conformance.findings(sdk) == []


def test_warns_by_default_and_fails_under_strict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _connector(tmp_path, "import requests\n")
    assert sdk_conformance.main(["--root", str(root)]) == 0
    assert "sdk-conformance: WARN: SDK-CENTRALIZED-CAPABILITIES-R001: demo_api/client.py:1" in capsys.readouterr().out
    assert sdk_conformance.main(["--root", str(root), "--strict"]) == 1
    assert "sdk-conformance: FAIL:" in capsys.readouterr().out
