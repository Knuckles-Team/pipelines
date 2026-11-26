"""PIPE-RELEASE-R006.7--R006.12: static version inventory completeness and its consumer binding."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.cli import GATES
from tests.hooks.conftest import Repo
from pipelines_hooks.release.project_version import (
    VERSION_DISCOVERY_POLICY,
    VERSION_FILE_SELECTOR,
    check_inventory,
    compare_version_inventory,
    discover_version_locations,
    parse_inventory,
    require_complete_version_inventory,
)

VERSION = "1.2.3"
CONFIG = f"""[bumpversion]
current_version = {VERSION}
commit = False
tag = False

[bumpversion:file(metadata):pyproject.toml]
search = version = \"{{current_version}}\"
replace = version = \"{{new_version}}\"

[bumpversion:file(source):pkg/version.py]
search = __version__ = \"{{current_version}}\"
replace = __version__ = \"{{new_version}}\"

[bumpversion:file(documentation):README.md]
search = <!-- project-version: {{current_version}} -->
replace = <!-- project-version: {{new_version}} -->
"""
VERSION_CONFIG = (
    CONFIG
    + f"""
[bumpversion:file(source):VERSION]
selector = {VERSION_FILE_SELECTOR}
search = {{current_version}}
replace = {{new_version}}
"""
)


def _inventory():
    return parse_inventory(CONFIG, config_digest="sha256:config", snapshot="tree:fixture")


def _version_inventory():
    return parse_inventory(VERSION_CONFIG, config_digest="sha256:version-config", snapshot="tree:fixture")


def _contents() -> dict[str, str]:
    return {
        ".config/bumpversion.cfg": CONFIG,
        "pyproject.toml": f'[project]\nname = "fixture"\nversion = "{VERSION}"\n',
        "pkg/version.py": f'__version__ = "{VERSION}"\n',
        "README.md": f"# fixture\n<!-- project-version: {VERSION} -->\n",
        "vendor/VERSION": "9.9.9\n",
        "docs/history.md": "Released 9.9.9 before the current project version.\n",
    }


def _version_contents() -> dict[str, str]:
    contents = _contents()
    contents["VERSION"] = f"{VERSION}\n"
    return contents


# spec: PIPE-RELEASE-R006.7
def test_version_inventory_completeness_model() -> None:
    discovered = discover_version_locations(_contents(), first_party_roots=("pkg",))
    assert VERSION_DISCOVERY_POLICY == "project-version-inventory/v1"
    assert _inventory().policy_version == VERSION_DISCOVERY_POLICY
    assert [(item.role, item.path, item.selector, item.value, item.line) for item in discovered] == [
        ("documentation", "README.md", "documentation.project-version", VERSION, 2),
        ("metadata", "pyproject.toml", "project.version", VERSION, 3),
        ("source", "pkg/version.py", "module.__version__", VERSION, 1),
    ]
    report = compare_version_inventory(_inventory(), discovered)
    assert report.complete
    assert report.unmapped == ()
    assert report.missing == ()
    assert report.selector_mismatch == ()
    assert report.value_mismatch == ()

    owned_inventory = _version_inventory()
    owned_discovered = discover_version_locations(
        _version_contents(), first_party_roots=("pkg",), inventory=owned_inventory
    )
    assert ("source", "VERSION", VERSION_FILE_SELECTOR, VERSION, 1) in [
        (item.role, item.path, item.selector, item.value, item.line) for item in owned_discovered
    ]
    assert all(item.path != "vendor/VERSION" for item in owned_discovered)
    owned_report = compare_version_inventory(owned_inventory, owned_discovered)
    assert owned_report.complete
    assert owned_report.policy_version == VERSION_DISCOVERY_POLICY
    owned_checks = check_inventory(owned_inventory, _version_contents())
    assert [(check.path, check.actual) for check in owned_checks if check.path == "VERSION"] == [("VERSION", VERSION)]


# spec: PIPE-RELEASE-R006.8
def test_version_inventory_completeness_refuses_unmapped_and_dynamic_surfaces() -> None:
    contents = _contents()
    contents["pkg/extra.py"] = '__version__ = "1.2.3"\n'
    discovered = discover_version_locations(contents, first_party_roots=("pkg",))
    report = compare_version_inventory(_inventory(), discovered)
    assert [(item.path, item.line) for item in report.unmapped] == [("pkg/extra.py", 1)]
    with pytest.raises(CannotRun, match=r"unmapped discovered locations \(pkg/extra.py:1\)"):
        require_complete_version_inventory(report)

    mismatched = _contents()
    mismatched["pkg/version.py"] = '__version__ = "9.9.9"\n'
    value_report = compare_version_inventory(
        _inventory(), discover_version_locations(mismatched, first_party_roots=("pkg",))
    )
    assert [(item.path, item.value) for item in value_report.value_mismatch] == [("pkg/version.py", "9.9.9")]
    with pytest.raises(CannotRun, match=r"version-mismatch: discovered values differ"):
        require_complete_version_inventory(value_report)

    dynamic = _contents()
    dynamic["pkg/version.py"] = "from build import version\n__version__ = version()\n"
    with pytest.raises(CannotRun, match="dynamic __version__ assignment"):
        discover_version_locations(dynamic, first_party_roots=("pkg",))

    missing_doc = _contents()
    del missing_doc["README.md"]
    missing = compare_version_inventory(
        _inventory(), discover_version_locations(missing_doc, first_party_roots=("pkg",))
    )
    assert [(item.role, item.path) for item in missing.missing] == [("documentation", "README.md")]


ENTRY = """import subprocess


def propose_version(version):
    subprocess.run(["pipelines-hook", "project-version-sync", "--completeness"], check=True)
    return version
"""
BARE_ENTRY = "def propose_version(version):\n    return version\n"
FILES = {
    ".config/bumpversion.cfg": CONFIG,
    "pyproject.toml": f'[project]\nname = "fixture"\nversion = "{VERSION}"\n',
    "pkg/__init__.py": '"""Fixture package."""\n',
    "pkg/version.py": f'__version__ = "{VERSION}"\n',
    "README.md": f"# fixture\n<!-- project-version: {VERSION} -->\n",
}
ARGS = ("--completeness", "--first-party-root", "pkg")


def _owner(tmp_path: Path, entry: str) -> tuple[Repo, str]:
    owner = Repo(tmp_path / "owner")
    owner.root.mkdir()
    owner.git("init", "-q", "-b", "main")
    return owner, owner.commit({"ce/entry.py": entry}, "entry")


def _binding(tmp_path: Path, rev: str, digest: str, **override: object) -> str:
    payload = {
        "owner_repository": "code-enhancer-owner",
        "revision": rev,
        "entry_path": "ce/entry.py",
        "entry_function": "propose_version",
        "invocation_argv": ["pipelines-hook", "project-version-sync", "--completeness"],
        "inventory_digest": digest,
        **override,
    }
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _digest(repo: Repo) -> str:
    from pipelines_hooks.release.project_version import _sha256

    return _sha256((repo.root / ".config/bumpversion.cfg").read_text(encoding="utf-8"))


# spec: PIPE-RELEASE-R006.9
def test_version_inventory_completeness_wiring(repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert GATES["project-version-sync"] == "pipelines_hooks.release.project_version"
    repo.commit(FILES, "fixture")
    assert repo.run("project-version-sync", *ARGS) == 0
    evidence = json.loads(capsys.readouterr().out.split("evidence ", 1)[1].splitlines()[0])
    assert evidence["consumer_integration"].startswith("unproved")

    owner, revision = _owner(tmp_path, ENTRY)
    binding = _binding(tmp_path, revision, _digest(repo))
    assert repo.run("project-version-sync", *ARGS, "--consumer-binding", binding, "--owner-root", str(owner.root)) == 0
    assert "verified" in capsys.readouterr().out

    # an owner checkout whose entry never calls the gate is refused
    bare_owner = Repo(tmp_path / "bare")
    bare_owner.root.mkdir()
    bare_owner.git("init", "-q", "-b", "main")
    bare_revision = bare_owner.commit({"ce/entry.py": BARE_ENTRY}, "entry")
    bare = _binding(tmp_path, bare_revision, _digest(repo))
    assert (
        repo.run("project-version-sync", *ARGS, "--consumer-binding", bare, "--owner-root", str(bare_owner.root)) == 2
    )
    assert "consumer-binding-unproved" in capsys.readouterr().err
    for override, message in (
        ({"inventory_digest": "sha256:old"}, "consumer-binding-stale"),
        ({"revision": "0" * 40}, "consumer-binding-stale"),
        ({"entry_function": "missing"}, "consumer-binding-unresolved"),
        ({"invocation_argv": ["true"]}, "consumer-binding-invalid"),
        ({"entry_path": "../x.py"}, "consumer-binding-invalid"),
    ):
        path = _binding(tmp_path, revision, _digest(repo), **override)
        assert repo.run("project-version-sync", *ARGS, "--consumer-binding", path, "--owner-root", str(owner.root)) == 2
        assert message in capsys.readouterr().err
    assert (
        repo.run("project-version-sync", *ARGS, "--consumer-binding", str(tmp_path / "none.json"), "--owner-root", "x")
        == 2
    )


# spec: PIPE-RELEASE-R006.10
def test_version_inventory_completeness_refusal(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit(FILES, "fixture")
    repo.commit({"pkg/extra.py": '__version__ = "1.2.3"\n'}, "unmapped")
    assert repo.run("project-version-sync", *ARGS) == 1
    out = capsys.readouterr().out
    assert "unmapped discovered location pkg/extra.py:1 (source, module.__version__)" in out
    repo.commit({"pkg/extra.py": "from build import version\n__version__ = version()\n"}, "dynamic")
    assert repo.run("project-version-sync", *ARGS) == 2
    assert "dynamic __version__ assignment" in capsys.readouterr().err
    repo.commit({"pkg/extra.py": "VALUE = 1\n"}, "clean again")
    assert repo.run("project-version-sync", "--completeness", "--first-party-root", "nowhere") == 2
    assert "first-party root has no tracked files" in capsys.readouterr().err
    repo.commit({"pkg/bad.py": "def (:\n"}, "unsupported grammar")
    assert repo.run("project-version-sync", *ARGS) == 2
    assert "cannot parse first-party source pkg/bad.py" in capsys.readouterr().err
    repo.commit({"pkg/bad.py": "VALUE = 2\n", ".bumpversion.cfg": CONFIG}, "competing authority")
    assert repo.run("project-version-sync", *ARGS) == 2
    assert "config-ambiguous" in capsys.readouterr().err
    repo.git("rm", "-q", ".bumpversion.cfg")
    repo.git("commit", "-q", "-m", "drop competing authority")
    repo.commit({"README.md": "# fixture\n<!-- project-version: 1.2.3 -->\nVERSION = '9.9.9'\n"}, "undeclared text")
    assert repo.run("project-version-sync", *ARGS) == 0  # a bare VERSION mention is outside the grammar, not rewritten


# spec: PIPE-RELEASE-R006.11
def test_version_inventory_completeness_evidence(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit(FILES, "fixture")
    repo.commit({"pkg/extra.py": '__version__ = "1.2.3"\n'}, "unmapped")
    target = tmp_path / "evidence.json"
    assert repo.run("project-version-sync", *ARGS, "--evidence", str(target)) == 1
    evidence = json.loads(target.read_text(encoding="utf-8"))
    assert evidence["policy_version"] == "project-version-inventory/v1" and evidence["policy_digest"].startswith(
        "sha256:"
    )
    assert evidence["snapshot"].startswith("index-tree:") or evidence["snapshot"].startswith("commit:")
    assert {(d["path"], d["role"], d["selector"]) for d in evidence["discovered"]} == {
        ("README.md", "documentation", "documentation.project-version"),
        ("pkg/extra.py", "source", "module.__version__"),
        ("pkg/version.py", "source", "module.__version__"),
        ("pyproject.toml", "metadata", "project.version"),
    }
    assert len(evidence["configured"]) == 3
    assert evidence["difference"]["unmapped"] == [
        {"path": "pkg/extra.py", "line": 1, "role": "source", "selector": "module.__version__"}
    ]
    assert evidence["complete"] is False
    assert "pyproject.toml project.version" in evidence["grammar"]["supported"]
    assert "historical release text" in evidence["grammar"]["excluded"]
    assert "within the stated grammar only" in evidence["scope"]
    capsys.readouterr()
    # a pass is evidence too, with the same scope statement
    repo.git("rm", "-q", "pkg/extra.py")
    repo.git("commit", "-q", "-m", "remove")
    assert repo.run("project-version-sync", *ARGS, "--evidence", str(target)) == 0
    passing = json.loads(target.read_text(encoding="utf-8"))
    assert passing["complete"] is True and passing["difference"]["unmapped"] == []
    assert "within the stated grammar only" in passing["scope"]


# spec: PIPE-RELEASE-R006.12
def test_version_inventory_completeness_cli(repo: Repo, tmp_path: Path) -> None:
    repo.commit(FILES, "fixture")
    history = "Released 9.9.9 before the current project version.\n"
    dependency = 'VERSION = "9.9.9"\n'
    repo.commit(
        {"docs/history.md": history, "pkg/deps.py": dependency, "pkg/extra.py": '__version__ = "1.2.3"\n'}, "files"
    )
    command = [sys.executable, "-m", "pipelines_hooks", "project-version-sync", "--root", str(repo.root), *ARGS]
    env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2]), "PATH": "/usr/bin:/bin"}

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, env=env, check=False)  # noqa: S603

    assert run().returncode == 1
    mapped = (
        CONFIG
        + '\n[bumpversion:file(source):pkg/extra.py]\nsearch = __version__ = "{current_version}"\nreplace = __version__ = "{new_version}"\n'
    )
    repo.commit({".config/bumpversion.cfg": mapped}, "map")
    assert run().returncode == 0
    assert (repo.root / "docs/history.md").read_text(encoding="utf-8") == history
    assert (repo.root / "pkg/deps.py").read_text(encoding="utf-8") == dependency

    # integration stays unproved without a resolvable consumer binding
    missing = subprocess.run(
        [*command, "--consumer-binding", str(tmp_path / "none.json"), "--owner-root", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )  # noqa: S603
    assert missing.returncode == 2 and "consumer-binding-unresolved" in missing.stderr
