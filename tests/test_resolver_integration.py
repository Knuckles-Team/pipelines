"""Real pip resolution with offline HTTP fixtures and tiny synthetic installations."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from tests.test_wheel_readiness import ACTION, guard, wheel

RUNNER = Path(__file__).with_name("resolver_fixture_runner.py")


def response(payload: bytes, content_type="application/octet-stream", **changes):
    return {"body": base64.b64encode(payload).decode(), "type": content_type, **changes}


def dependency_wheel(path, name="dep", version="2", requires=(), extras=()):
    result = path / f"{name}-{version}-py3-none-any.whl"
    metadata = ["Metadata-Version: 2.3", "Name: " + name, "Version: " + version]
    metadata += ["Requires-Dist: " + item for item in requires]
    metadata += ["Provides-Extra: " + item for item in extras]
    with zipfile.ZipFile(result, "w") as archive:
        prefix = f"{name}-{version}.dist-info/"
        archive.writestr(prefix + "METADATA", "\n".join(metadata) + "\n")
        archive.writestr(prefix + "WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr(prefix + "RECORD", "")
    return result


def index_for(path, name="dep"):
    url = "https://files.pythonhosted.org/" + path.name
    payload = path.read_bytes()
    html = f'<a href="{url}#sha256={hashlib.sha256(payload).hexdigest()}">{path.name}</a>'.encode()
    return {"https://pypi.org/simple/" + name + "/": response(html, "text/html"), url: response(payload)}


def run(tmp_path, root, responses, profile="base", poison=None, install=False):
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps({"root": str(root), "responses": responses, "profile": profile, "install": install}))
    if poison:
        (tmp_path / "pip.conf").write_text("[global]\nindex-url = https://poison.invalid/simple\n")
    environment = guard.clean_environment(tmp_path, root)
    result = subprocess.run([sys.executable, "-I", str(RUNNER), str(ACTION), str(scenario)],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15)
    return result, json.loads((tmp_path / "requests.json").read_text())


def test_real_resolver_base_and_transitive_wheel(tmp_path):
    root = wheel(tmp_path, requires=["dep>=2"])
    dep = dependency_wheel(tmp_path)
    result, requests = run(tmp_path, root, index_for(dep))
    assert result.returncode == 0, result.stdout + result.stderr
    assert requests == ["https://pypi.org/simple/dep/", "https://files.pythonhosted.org/" + dep.name]
    assert (tmp_path / "validated.json").exists()


@pytest.mark.parametrize("profile", ["mcp", "agent", "all"])
def test_real_resolver_advertised_extra_closure(tmp_path, profile):
    root = wheel(tmp_path, requires=[f'dep[feature]>=2; extra == "{profile}"'], extras=[profile])
    dep = dependency_wheel(tmp_path, extras=["feature"])
    result, _ = run(tmp_path, root, index_for(dep), profile)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("requirement", ["dep>=3", "dep[absent]>=2", "dep>=2, <2"])
def test_real_resolver_missing_version_extra_and_conflict(tmp_path, requirement):
    root = wheel(tmp_path, requires=[requirement])
    dep = dependency_wheel(tmp_path)
    result, _ = run(tmp_path, root, index_for(dep))
    assert result.returncode != 0
    assert not (tmp_path / "validated.json").exists()


@pytest.mark.parametrize("url", ["file:///tmp/other-1-py3-none-any.whl", "https://outside.invalid/other-1-py3-none-any.whl",
                                  "git+https://outside.invalid/repository",
                                  "https://files.pythonhosted.org/other-1-py3-none-any.whl"])
def test_real_resolver_blocks_transitive_direct_sources(tmp_path, url):
    root = wheel(tmp_path, requires=["dep>=2"])
    dep = dependency_wheel(tmp_path, requires=["other @ " + url])
    result, requests = run(tmp_path, root, index_for(dep))
    assert result.returncode != 0
    assert all("outside.invalid" not in value and "other-1" not in value for value in requests)
    assert "Packages installed from PyPI cannot depend" in result.stderr
    assert not (tmp_path / "validated.json").exists()


@pytest.mark.parametrize("status", [302, 503])
def test_real_resolver_rejects_redirects_and_index_errors(tmp_path, status):
    root = wheel(tmp_path, requires=["dep>=2"])
    fixture = {"https://pypi.org/simple/dep/": response(b"", "text/html", status=status,
               headers={"Location": "https://outside.invalid/"})}
    result, requests = run(tmp_path, root, fixture)
    assert result.returncode != 0
    assert requests == ["https://pypi.org/simple/dep/"]
    assert not (tmp_path / "validated.json").exists()


def test_real_resolver_ignores_installed_packages(tmp_path):
    # pytest is already installed in the test interpreter. It must nevertheless
    # be obtained from the public-index fixture for a successful release proof.
    root = wheel(tmp_path, requires=["pytest==9.1.1"])
    result, requests = run(tmp_path, root, {"https://pypi.org/simple/pytest/": response(b"", "text/html", status=404)})
    assert result.returncode != 0
    assert requests == ["https://pypi.org/simple/pytest/"]


def test_real_resolver_neutralizes_caller_configuration(tmp_path, monkeypatch):
    root = wheel(tmp_path, requires=["dep>=2"])
    dep = dependency_wheel(tmp_path)
    for key in ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "UV_INDEX_URL", "HTTP_PROXY", "HTTPS_PROXY"):
        monkeypatch.setenv(key, "https://poison.invalid/")
    for key in ("PYTHONPATH", "PIP_CONFIG_FILE", "PIP_CONSTRAINT", "UV_CONFIG_FILE", "SSL_CERT_FILE"):
        monkeypatch.setenv(key, str(tmp_path / "poison"))
    (tmp_path / ".config/pip").mkdir(parents=True)
    (tmp_path / ".config/pip/pip.conf").write_text("[global]\nindex-url=https://poison.invalid/simple\n")
    (tmp_path / "pyproject.toml").write_text('[tool.uv.sources]\ndep={path="./poison"}\n')
    (tmp_path / "sitecustomize.py").write_text('raise RuntimeError("caller import override executed")\n')
    result, requests = run(tmp_path, root, index_for(dep), poison=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert all("poison" not in url for url in requests)


def test_real_resolver_rejects_wrong_python_before_any_request(tmp_path):
    root = wheel(tmp_path, python=">=99")
    result, requests = run(tmp_path, root, {})
    assert result.returncode != 0
    assert not requests


def test_real_resolver_installs_synthetic_wheels_without_importing_them(tmp_path):
    root = wheel(tmp_path, requires=["dep>=2"])
    sentinel = tmp_path / "startup-executed"
    with zipfile.ZipFile(root, "a") as archive:
        archive.writestr("fixture_startup.pth", f"import pathlib; pathlib.Path({str(sentinel)!r}).touch()\n")
    dep = dependency_wheel(tmp_path)
    result, _ = run(tmp_path, root, index_for(dep), install=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "installed/fixture_startup.pth").exists()
    assert (tmp_path / "installed/dep-2.dist-info/METADATA").exists()
    assert not sentinel.exists()


def test_real_resolver_rejects_transitive_version_conflict(tmp_path):
    root = wheel(tmp_path, requires=["dep>=2", "other>=2"])
    dep = dependency_wheel(tmp_path, requires=["other<2"])
    other = dependency_wheel(tmp_path, name="other")
    result, _ = run(tmp_path, root, {**index_for(dep), **index_for(other, "other")})
    assert result.returncode != 0
    assert "ResolutionImpossible" in result.stderr
    assert not (tmp_path / "validated.json").exists()
