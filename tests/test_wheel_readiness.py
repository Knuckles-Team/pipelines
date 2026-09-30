"""Offline adversarial tests for the publication-only wheel guard."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import zipfile

import pytest
import yaml

ROOT = Path(__file__).parents[1]
ACTION = ROOT / ".github/actions/wheel-readiness"
spec = importlib.util.spec_from_file_location("wheel_readiness", ACTION / "readiness.py")
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def wheel(tmp_path, *, requires=(), extras=(), python=">=3.11", name="fixture-1.0-py3-none-any.whl"):
    path = tmp_path / name
    lines = ["Metadata-Version: 2.3", "Name: fixture", "Version: 1.0", f"Requires-Python: {python}"]
    lines += [f"Requires-Dist: {req}" for req in requires]
    lines += [f"Provides-Extra: {extra}" for extra in extras]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fixture-1.0.dist-info/METADATA", "\n".join(lines) + "\n")
        archive.writestr("fixture-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr("fixture-1.0.dist-info/RECORD", "")
    return path


def report(path, root, dependencies=()):
    return {"version": "1", "environment": guard.default_environment(), "install": [
        {"metadata": root, "is_direct": True, "download_info": {
            "url": path.as_uri(), "archive_info": {"hashes": {"sha256": guard.digest(path)}}}},
        *dependencies,
    ]}


def dependency(*, requires=(), extras=(), url="https://files.pythonhosted.org/packages/dep-2-py3-none-any.whl"):
    return {"metadata": {"name": "dep", "version": "2", "requires_dist": list(requires), "provides_extra": list(extras)},
            "is_direct": False, "download_info": {"url": url, "archive_info": {"hashes": {"sha256": "a" * 64}}}}


def test_base_and_extra_closures(tmp_path):
    path = wheel(tmp_path, requires=('dep[feature]>=2; extra == "mcp"',), extras=("mcp",))
    root = guard.metadata(path)
    guard.validate_report(report(path, root), path, root, "base")
    guard.validate_report(report(path, root, [dependency(extras=["feature"])]), path, root, "mcp")
    with pytest.raises(ValueError, match="missing transitive"):
        guard.validate_report(report(path, root), path, root, "mcp")
    with pytest.raises(ValueError, match="unknown transitive extra"):
        guard.validate_report(report(path, root, [dependency()]), path, root, "mcp")


@pytest.mark.parametrize("requires", ['dep @ file:///tmp/dep.whl', 'dep @ https://example.invalid/dep.whl', 'dep @ git+https://example.invalid/dep'])
def test_root_direct_dependencies_rejected_even_when_inactive(tmp_path, requires):
    path = wheel(tmp_path, requires=[requires + ' ; extra == "dev"'])
    with pytest.raises(ValueError, match="direct URL"):
        guard.metadata(path)


@pytest.mark.parametrize("raw", ['[]', '["mcp"]', '["base","missing"]', '["base","base"]', 'null', '[1]'])
def test_profiles_fail_closed(raw):
    with pytest.raises(ValueError):
        guard.profiles(raw, ["mcp"])


def test_advertised_profiles_cannot_be_silently_omitted():
    with pytest.raises(ValueError, match="advertised"):
        guard.profiles('["base"]', ["mcp", "agent", "all", "dev"])
    assert guard.profiles('["base","mcp","agent","all"]', ["mcp", "agent", "all", "dev"]) == ["agent", "all", "base", "mcp"]


@pytest.mark.parametrize("change", ["url", "direct", "hash", "requires", "version", "python", "missing"])
def test_transitive_bad_evidence_rejected(tmp_path, change):
    path = wheel(tmp_path, requires=["dep>=2"])
    root = guard.metadata(path)
    dep = dependency()
    if change == "url":
        dep["download_info"]["url"] = "https://mirror.invalid/dep.whl"
    elif change == "direct":
        dep["is_direct"] = True
    elif change == "hash":
        dep["download_info"]["archive_info"]["hashes"] = {}
    elif change == "requires":
        dep["metadata"]["requires_dist"] = ["other @ file:///tmp/other.whl"]
    elif change == "version":
        dep["metadata"]["version"] = "1"
    elif change == "python":
        dep["metadata"]["requires_python"] = ">=99"
    elif change == "missing":
        dep["metadata"]["requires_dist"] = ["other>=1"]
    with pytest.raises(ValueError):
        guard.validate_report(report(path, root, [dep]), path, root, "base")


@pytest.mark.parametrize("kwargs", [{"python": ">=99"}, {"name": "fixture-1.0-cp299-cp299-win32.whl"}])
def test_incompatible_interpreter_blocks(tmp_path, kwargs):
    with pytest.raises(ValueError):
        guard.metadata(wheel(tmp_path, **kwargs))


def test_environment_drops_every_poisoned_setting(tmp_path, monkeypatch):
    poisoned = {"PIP_INDEX_URL": "http://evil", "UV_INDEX": "http://evil", "PIP_CONSTRAINT": "bad.txt",
                "PYTHONPATH": "/tmp/evil", "HTTP_PROXY": "http://evil", "SSL_CERT_FILE": "/tmp/evil",
                "UV_CONFIG_FILE": "/tmp/evil", "PIP_CONFIG_FILE": "/tmp/evil"}
    for key, value in poisoned.items():
        monkeypatch.setenv(key, value)
    clean = guard.clean_environment(tmp_path, tmp_path / "fixture.whl")
    assert not (set(poisoned) - {"PIP_CONFIG_FILE"}) & clean.keys()
    assert clean["PIP_CONFIG_FILE"] == os.devnull


def test_changed_wheel_and_missing_receipt_block(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    path = wheel(dist)
    receipt = tmp_path / "proof.json"
    monkeypatch.setattr(guard, "identity", lambda: {"source_commit": "a" * 40, "contract_commit": "b" * 40})
    monkeypatch.setattr(guard, "resolve", lambda path, root, *_: [{"profile": "base", "report": report(path, root)}])
    guard.check(dist, receipt, '["base"]')
    guard.verify(dist, receipt, '["base"]')
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="bytes changed"):
        guard.verify(dist, receipt, '["base"]')
    receipt.unlink()
    with pytest.raises(FileNotFoundError):
        guard.verify(dist, receipt, '["base"]')


def test_failed_resolution_removes_stale_success(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel(dist)
    receipt = tmp_path / "proof.json"
    receipt.write_text('{"schema": 1}')
    monkeypatch.setattr(guard, "identity", lambda: {})
    def unavailable(*args):
        raise ValueError("index unavailable")
    monkeypatch.setattr(guard, "resolve", unavailable)
    with pytest.raises(ValueError, match="unavailable"):
        guard.check(dist, receipt, '["base"]')
    assert not receipt.exists()


def test_source_archive_and_extra_files_cannot_escape_guard(tmp_path):
    wheel(tmp_path)
    (tmp_path / "fixture.tar.gz").write_bytes(b"unproven")
    with pytest.raises(ValueError, match="only regular wheels"):
        guard.wheel_set(tmp_path)


def test_all_python_publication_paths_guard_before_upload_and_release():
    python = yaml.safe_load((ROOT / ".github/actions/publish-python-package/action.yml").read_text())
    steps = python["runs"]["steps"]
    names = [step["name"] for step in steps]
    assert names.index("Prove wheel runtime readiness") < names.index("Publish package") < names.index("Create Release")
    upload = next(step for step in steps if step["name"] == "Publish package")
    assert upload["run"].index("readiness.py verify") < upload["run"].index("twine upload")
    assert "dist/*.whl" in upload["run"]
    assert "|| true" not in str(steps) and "skip-existing" not in str(steps)
    native = yaml.safe_load((ROOT / ".github/workflows/maturin_pipeline.yml").read_text())
    steps = native["jobs"]["publish"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Prove wheel runtime readiness") < names.index("Reverify exact upload bytes") < names.index("Publish to PyPI") < names.index("Create Release")
    assert "skip-existing" not in str(steps)
    release = yaml.safe_load((ROOT / ".github/actions/create-version-release/action.yml").read_text())
    assert "readiness.py verify" in release["runs"]["steps"][0]["run"]
    for item in (python, release):
        assert item["inputs"]["runtime-profiles"]["required"] is True


def test_transport_rejects_poisoned_origins_and_direct_candidates(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    calls = []
    class Session:
        def request(self, *args, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status_code=200)

    class Preparer:
        def prepare_linked_requirement(self, req, *args, **kwargs):
            return "wheel metadata"

    monkeypatch.setitem(sys.modules, "pip._internal.cli.main", SimpleNamespace(main=lambda _: 0))
    monkeypatch.setitem(sys.modules, "pip._internal.network.session", SimpleNamespace(PipSession=Session))
    monkeypatch.setitem(sys.modules, "pip._internal.operations.prepare", SimpleNamespace(RequirementPreparer=Preparer))
    resolver_spec = importlib.util.spec_from_file_location("resolver_transport", ACTION / "resolve.py")
    resolver = importlib.util.module_from_spec(resolver_spec)
    resolver_spec.loader.exec_module(resolver)
    root = tmp_path / "fixture.whl"
    resolver.constrain(root)
    session = Session()
    session.request("GET", "https://pypi.org/simple/dep/")
    assert calls == [{"allow_redirects": False}]
    for url in ("http://pypi.org/simple", "https://pypi.org.evil/", "file:///tmp/a", "https://evil/", "https://user@pypi.org/", "https://pypi.org:8080/"):
        with pytest.raises(ValueError):
            session.request("GET", url)
    link = SimpleNamespace(is_wheel=True, is_file=True, url=root.as_uri())
    req = SimpleNamespace(link=link, editable=False, user_supplied=True, is_direct=True)
    assert Preparer().prepare_linked_requirement(req) == "wheel metadata"
    req.user_supplied = False
    with pytest.raises(ValueError, match="exact root"):
        Preparer().prepare_linked_requirement(req)
    req.link = SimpleNamespace(is_wheel=True, is_file=False, url="https://files.pythonhosted.org/a.whl")
    with pytest.raises(ValueError, match="direct URL"):
        Preparer().prepare_linked_requirement(req)
    req.is_direct = False
    assert Preparer().prepare_linked_requirement(req) == "wheel metadata"
    with pytest.raises(ValueError, match="editable"):
        Preparer().prepare_editable_requirement(req)


@pytest.mark.parametrize("field,value", [("scope", "fleet-only"), ("index", "https://mirror.invalid"), ("interpreter", {}), ("source_commit", "c" * 40)])
def test_poisoned_receipt_is_not_publication_proof(tmp_path, monkeypatch, field, value):
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel(dist)
    receipt = tmp_path / "proof.json"
    monkeypatch.setattr(guard, "identity", lambda: {"source_commit": "a" * 40, "contract_commit": "b" * 40})
    monkeypatch.setattr(guard, "resolve", lambda path, root, *_: [{"profile": "base", "report": report(path, root)}])
    guard.check(dist, receipt, '["base"]')
    payload = json.loads(receipt.read_text())
    payload[field] = value
    receipt.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        guard.verify(dist, receipt, '["base"]')


def test_profile_names_cannot_escape_isolated_directory():
    with pytest.raises(ValueError, match="profile name"):
        guard.profiles('["base","../escape"]', ["../escape"])
