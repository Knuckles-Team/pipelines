"""PIPE-RELEASE-R006.1--R006.6: exact project-version synchronization."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release.project_version import (
    ROLES,
    ProjectVersionInventory,
    VersionCheck,
    check_inventory,
    parse_inventory,
)
from tests.hooks.conftest import Repo


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

FILES = {
    ".config/bumpversion.cfg": CONFIG,
    "pyproject.toml": f'[project]\nname = "fixture"\nversion = "{VERSION}"\n',
    "pkg/version.py": f'__version__ = "{VERSION}"\n',
    "README.md": f"# fixture\n<!-- project-version: {VERSION} -->\n",
}


def _inventory() -> ProjectVersionInventory:
    return parse_inventory(CONFIG, config_digest="sha256:config", snapshot="index-tree:fixture")


def _contents(version: str = VERSION) -> dict[str, str]:
    return {
        "pyproject.toml": f'[project]\nname = "fixture"\nversion = "{version}"\n',
        "pkg/version.py": f'__version__ = "{version}"\n',
        "README.md": f"# fixture\n<!-- project-version: {version} -->\n",
    }


def _fixture(repo: Repo) -> str:
    return repo.commit(FILES, message="fixture")


def test_project_version_inventory() -> None:
    inventory = _inventory()
    assert isinstance(inventory, ProjectVersionInventory)
    assert {location.role for location in inventory.locations} == set(ROLES)
    assert [location.path for location in inventory.locations] == [
        "README.md",
        "pyproject.toml",
        "pkg/version.py",
    ]
    assert all(location.repository_relative_path == location.path for location in inventory.locations)
    assert all(location.expected_matches == 1 for location in inventory.locations)

    unknown = CONFIG.replace("file(source)", "file(other)")
    with pytest.raises(CannotRun, match="inventory-incomplete: unknown role"):
        parse_inventory(unknown)
    duplicate = CONFIG.replace("file(source):pkg/version.py", "file(source):pyproject.toml")
    with pytest.raises(CannotRun, match="duplicate version locations"):
        parse_inventory(duplicate)
    missing = CONFIG.split("[bumpversion:file(documentation):README.md]", 1)[0]
    with pytest.raises(CannotRun, match="missing role coverage"):
        parse_inventory(missing)


def test_project_version_values() -> None:
    inventory = _inventory()
    checks = check_inventory(inventory, _contents())
    assert len(checks) == 3
    assert all(isinstance(check, VersionCheck) and check.status == "pass" for check in checks)
    assert {check.expected for check in checks} == {VERSION}
    assert {check.line for check in checks} == {1, 2, 3}

    for path in ("pyproject.toml", "pkg/version.py", "README.md"):
        contents = _contents()
        contents[path] = contents[path].replace(VERSION, "9.9.9")
        checks = check_inventory(inventory, contents)
        changed = [check for check in checks if check.path == path]
        assert len(changed) == 1
        assert changed[0].status == "version-mismatch"
        assert changed[0].actual == "9.9.9"
        assert changed[0].line == (3 if path == "pyproject.toml" else 1 if path == "pkg/version.py" else 2)

    changed_config = parse_inventory(CONFIG.replace(VERSION, "9.9.9"), snapshot="index-tree:changed")
    checks = check_inventory(changed_config, _contents())
    assert {check.status for check in checks} == {"version-mismatch"}

    with pytest.raises(CannotRun, match="replacement changes text"):
        parse_inventory(CONFIG.replace('replace = version = "{new_version}"', 'replace = release = "{new_version}"'))
    with pytest.raises(CannotRun, match="selector is too broad"):
        parse_inventory(CONFIG.replace('search = version = "{current_version}"', "search = {current_version}"))


def test_project_version_assignment_does_not_match_similar_manifest_keys() -> None:
    contents = _contents()
    contents["pyproject.toml"] += '\n[tool.ruff]\ntarget-version = "py312"\n[tool.mypy]\npython_version = "3.12"\n'
    checks = check_inventory(_inventory(), contents)
    metadata = [check for check in checks if check.role == "metadata"]
    assert len(metadata) == 1
    assert metadata[0].actual == VERSION


def test_project_version_refusals() -> None:
    with pytest.raises(CannotRun, match="config-invalid: malformed"):
        parse_inventory("[bumpversion\ncurrent_version = 1\n")
    with pytest.raises(CannotRun, match="config-invalid: missing"):
        parse_inventory("[project]\nname = 'fixture'\n")
    with pytest.raises(CannotRun, match="expected_count must be positive"):
        parse_inventory(
            CONFIG.replace(
                "[bumpversion:file(source):pkg/version.py]\n",
                "[bumpversion:file(source):pkg/version.py]\nexpected_count = 0\n",
            )
        )
    with pytest.raises(CannotRun, match="literal assignment"):
        parse_inventory(
            CONFIG.replace(
                'search = __version__ = "{current_version}"',
                'search = __version__ = get_version("{current_version}")',
            ).replace(
                'replace = __version__ = "{new_version}"',
                'replace = __version__ = get_version("{new_version}")',
            )
        )
    with pytest.raises(CannotRun, match="project-version"):
        parse_inventory(
            CONFIG.replace("<!-- project-version: {current_version} -->", "release: {current_version}").replace(
                "<!-- project-version: {new_version} -->", "release: {new_version}"
            )
        )


def test_project_version_evidence() -> None:
    checks = check_inventory(_inventory(), _contents())
    assert [(check.role, check.path, check.line) for check in checks] == [
        ("documentation", "README.md", 2),
        ("metadata", "pyproject.toml", 3),
        ("source", "pkg/version.py", 1),
    ]
    for check in checks:
        assert check.expected == VERSION
        assert check.actual == VERSION
        assert check.location.extraction_selector == check.location.selector
        assert check.checked_count == check.expected_count == 1
        assert check.config_digest == "sha256:config"
        assert check.blob_digest.startswith("sha256:")
        assert check.snapshot == "index-tree:fixture"


def test_project_version_hook_wiring(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    """The integration owner supplies the registry/catalogue/self-run entries."""
    assert GATES["project-version-sync"] == "pipelines_hooks.release.project_version"
    _fixture(repo)
    assert repo.run("project-version-sync") == 0
    repo.stage({"pkg/version.py": '__version__ = "9.9.9"\n'})
    assert repo.run("project-version-sync") == 1
    output = capsys.readouterr().out
    assert "source pkg/version.py:1" in output
    assert "version-mismatch" in output


def test_project_version_sync_cli(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = _fixture(repo)
    assert repo.run("project-version-sync") == 0

    repo.stage({"pyproject.toml": '[project]\nname = "fixture"\nversion = "9.9.9"\n'})
    assert repo.run("project-version-sync") == 1
    assert "metadata pyproject.toml:3" in capsys.readouterr().out
    repo.git("reset", "--hard", "HEAD")

    repo.stage({"pkg/version.py": '__version__ = "9.9.9"\n'})
    repo.write("pkg/version.py", f'__version__ = "{VERSION}"\n')
    assert repo.run("project-version-sync") == 1
    assert "source pkg/version.py:1" in capsys.readouterr().out
    repo.git("reset", "--hard", "HEAD")

    repo.stage({"README.md": "# fixture\n<!-- project-version: 9.9.9 -->\n"})
    assert repo.run("project-version-sync") == 1
    assert "documentation README.md:2" in capsys.readouterr().out
    repo.git("reset", "--hard", "HEAD")

    repo.git("rm", "--cached", "-q", "--", ".config/bumpversion.cfg")
    assert repo.run("project-version-sync") == 2
    assert "config-missing" in capsys.readouterr().err
    repo.git("reset", "--hard", "HEAD")

    repo.stage({".config/bumpversion.cfg": "[bumpversion\ncurrent_version = 1.2.3\n"})
    assert repo.run("project-version-sync") == 2
    assert "config-invalid" in capsys.readouterr().err
    repo.git("reset", "--hard", "HEAD")

    repo.stage({".bumpversion.cfg": CONFIG})
    assert repo.run("project-version-sync") == 2
    assert "config-ambiguous" in capsys.readouterr().err
    repo.git("reset", "--hard", "HEAD")
    repo.git("clean", "-fd", "--", ".bumpversion.cfg")

    repo.stage({"pkg/version.py": '__version__ = "1.2.3"\n__version__ = "1.2.3"\n'})
    assert repo.run("project-version-sync") == 2
    assert "selector-ambiguous" in capsys.readouterr().err
    repo.git("reset", "--hard", "HEAD")

    repo.write("README.md", "# fixture\n<!-- project-version: 9.9.9 -->\n")
    assert repo.run("project-version-sync") == 0
    assert repo.run("project-version-sync", "--base-ref", base) == 0
    repo.git("reset", "--hard", "HEAD")

    bump = shutil.which("bump2version")
    assert bump is not None, "the configured bump tool is required for the R006 hot-path proof"
    subprocess.run(
        [bump, "--config-file", ".config/bumpversion.cfg", "--allow-dirty", "patch"],
        cwd=repo.root,
        check=True,
        capture_output=True,
        text=True,
    )
    for path in (".config/bumpversion.cfg", "pyproject.toml", "pkg/version.py", "README.md"):
        repo.git("add", "--", path)
    status_before_gate = repo.git("status", "--short")
    assert repo.run("project-version-sync") == 0
    captured = capsys.readouterr().out
    assert "project-version-sync: PASS" in captured
    assert "snapshot=index-tree:" in captured
    assert repo.git("status", "--short") == status_before_gate
