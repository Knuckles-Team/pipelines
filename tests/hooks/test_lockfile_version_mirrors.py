"""PIPE-GATES-R008: preserve the retired checker metadata contract."""

import pytest

from pipelines_hooks.cli import main

PROJECT = """[project]
name = "my-package"
version = "1.2.3"
dependencies = ["agent-utilities>=3,<4", "other==2"]
"""


# spec: PIPE-GATES-R008
def test_absent_artifacts_are_valid(repo):
    repo.write("pyproject.toml", PROJECT)
    assert repo.run("lockfile-version-mirrors") == 0


@pytest.mark.parametrize(
    "entry,status",
    [
        ('version = "1.2.3"', 0),
        ('version = "1.2.2"', 1),
        ('source = {editable = "."}', 0),
        ('source = {registry = "https://example.org"}', 1),
    ],
)
def test_self_version(repo, entry, status):
    repo.write("pyproject.toml", PROJECT)
    repo.write("uv.lock", '[[package]]\nname = "my_package"\n' + entry)
    assert repo.run("lockfile-version-mirrors") == status


def test_dynamic_version_uses_bump_authority(repo):
    repo.write("pyproject.toml", PROJECT.replace('version = "1.2.3"', 'dynamic = ["version"]'))
    repo.write(".bumpversion.cfg", "[bumpversion]\ncurrent_version = 1.2.3\n")
    repo.write("uv.lock", '[[package]]\nname="my-package"\nversion="1.2.3"')
    assert repo.run("lockfile-version-mirrors") == 0


@pytest.mark.parametrize(
    "requirement,status",
    [
        ("agent_utilities==3.5 # via project", 0),
        ("agent-utilities==2.9", 1),
        ("agent-utilities==3.*", 1),
        ("agent-utilities==2.9 \\ \n    --hash=sha256:123", 1),
        ("agent-utilities>=3,<4", 0),
        ("agent-utilities>=2,<4", 1),
        ("transitive==0.1", 0),
        ("# exported requirements\nother==2", 0),
    ],
)
def test_direct_pins_and_ranges(repo, requirement, status):
    repo.write("pyproject.toml", PROJECT)
    repo.write("requirements.txt", requirement)
    assert repo.run("lockfile-version-mirrors") == status


def test_root_cannot_silently_be_a_package(repo):
    repo.write("pyproject.toml", PROJECT)
    package = repo.root / "pkg"
    package.mkdir(exist_ok=True)
    assert main(["lockfile-version-mirrors", "--root", str(package)]) == 2
