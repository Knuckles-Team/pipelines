"""PIPE-PAGES-R020.25 to R020.30: the project configuration inventory and its templates."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.hygiene import config_inventory as ci
from tests.hooks.conftest import Repo

DECLARATION = """schema = 1
template = "1"

[[project]]
path = "."
[project.parameters]
name = "alpha"
python = "3.12"

[[project]]
path = "svc"
[project.parameters]
name = "beta"
python = "3.13"
"""


def _inventory(text: str = DECLARATION) -> ci.ProjectConfigInventory:
    import tomllib

    data = tomllib.loads(text)
    return ci.ProjectConfigInventory(data["template"], {p["path"]: dict(p["parameters"]) for p in data["project"]})


def _repo(tmp_path: Path, declaration: str = DECLARATION) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir(parents=True)
    repo.git("init", "-q")
    out = tmp_path / "scratch"
    ci.render(_inventory(declaration), out)
    files = {str(p.relative_to(out)): p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file()}
    repo.stage({ci.DECLARATION: declaration, **files})
    return repo


# spec: PIPE-PAGES-R020.25
def test_config_inventory_model() -> None:
    inventory = _inventory()
    assert sorted(inventory.projects) == [".", "svc"]
    assert inventory.file_of("svc", "pytest") == "svc/pyproject.toml"
    assert inventory.file_of(".", "pytest") == inventory.file_of(".", "project-metadata") == "pyproject.toml"
    assert set(ci.ROLES) == {"version-bump", "pre-commit", "project-metadata", "pytest"}
    assert inventory.params_digest(".") != inventory.params_digest("svc")
    bad = ci.ProjectConfigInventory
    with pytest.raises(CannotRun):
        bad("2", {".": {"name": "a", "python": "3"}})
    with pytest.raises(CannotRun):
        bad("1", {".": {"name": "a"}})
    with pytest.raises(CannotRun):
        bad("1", {"../x": {"name": "a", "python": "3"}})
    with pytest.raises(CannotRun):
        bad("1", {})


# spec: PIPE-PAGES-R020.26
def test_config_inventory_behavior(tmp_path: Path) -> None:
    inventory = _inventory()
    first = {r: ci.render_file(inventory, ".", r) for r in ci.ROLES}
    assert first == {r: ci.render_file(inventory, ".", r) for r in ci.ROLES}
    repo = _repo(tmp_path)
    findings, receipts = ci.check(repo.root, inventory)
    assert findings == [] and len(receipts) == 8 and all(r.expected_digest == r.observed_digest for r in receipts)
    repo.stage({"pyproject.toml": first["pytest"].replace('"-p no:cacheprovider"', '"-q"')})
    findings, _ = ci.check(repo.root, inventory)
    assert any("role pytest" in f and "drifted" in f for f in findings)
    custom = first["pytest"].replace('version = "0.0.0"', 'version = "9.9.9"\ndescription = "custom"')
    repo.stage({"pyproject.toml": custom})
    assert ci.check(repo.root, inventory)[0] == []  # owned custom fields survive


# spec: PIPE-PAGES-R020.27
def test_config_inventory_wiring(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert GATES["config-inventory"] == "pipelines_hooks.hygiene.config_inventory"
    hooks = (Path(__file__).resolve().parents[2] / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "entry: pipelines-hook config-inventory --check" in hooks
    repo = _repo(tmp_path)
    assert repo.run("config-inventory", "--check") == 0
    scratch = tmp_path / "scratch-two"
    assert repo.run("config-inventory", "--render", str(scratch)) == 0
    assert (scratch / "svc" / ".pre-commit-config.yaml").read_text() == (
        tmp_path / "scratch" / "svc" / ".pre-commit-config.yaml"
    ).read_text()
    capsys.readouterr()


# spec: PIPE-PAGES-R020.28
def test_config_inventory_refusal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    existing = tmp_path / "exists"
    existing.mkdir()
    assert repo.run("config-inventory", "--render", str(existing)) == 2
    assert not list(existing.iterdir())
    for broken in (
        DECLARATION.replace('path = "svc"', 'path = "../escape"'),
        DECLARATION.replace('template = "1"', 'template = "7"'),
        DECLARATION.replace('path = "svc"', 'path = "."'),
        DECLARATION.replace("schema = 1", "schema = 9"),
    ):
        repo.stage({ci.DECLARATION: broken})
        assert repo.run("config-inventory", "--check") == 2
    other = _repo(tmp_path / "o")
    other.git("rm", "-q", "-f", ci.DECLARATION)
    assert other.run("config-inventory", "--check") == 2
    omitted = _repo(tmp_path / "p")
    omitted.stage({"tools/pyproject.toml": "[project]\nname = 'x'\n"})
    assert omitted.run("config-inventory", "--check") == 1


# spec: PIPE-PAGES-R020.29
def test_config_inventory_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert repo.run("config-inventory", "--check") == 0
    out = capsys.readouterr().out
    receipts = [line for line in out.splitlines() if line.startswith("receipt ")]
    assert len(receipts) == 8 and "projects: declared=['.', 'svc'] discovered=['.', 'svc']" in out
    assert {r.split()[2] for r in receipts} == {f"role={r}" for r in ci.ROLES}
    assert all("parser=" in r and "template=1" in r and "params=" in r and "expected=" in r for r in receipts)
    bump = (tmp_path / "scratch" / "svc" / ".bumpversion.cfg").read_text()
    repo.stage({"svc/.bumpversion.cfg": bump.replace("search = version", "search = release")})
    assert repo.run("config-inventory", "--check") == 1
    out = capsys.readouterr().out
    assert "svc/.bumpversion.cfg:6: project 'svc' role version-bump: managed section" in out and "drifted" in out
    assert "role version-bump" not in "\n".join(
        line for line in out.splitlines() if line.startswith("receipt project=. ")
    )


# spec: PIPE-PAGES-R020.30
def test_config_inventory_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert repo.run("config-inventory", "--check") == 0
    before = (repo.git("write-tree"), (repo.root / "pyproject.toml").read_text())
    scratch = tmp_path / "scratch"
    originals = {
        p: (scratch / p).read_text()
        for p in ("svc/.bumpversion.cfg", "svc/.pre-commit-config.yaml", "svc/pyproject.toml")
    }
    cases = {
        "svc/.bumpversion.cfg": ("version-bump", None),
        "svc/.pre-commit-config.yaml": ("pre-commit", None),
    }
    for path, (role, _x) in cases.items():
        repo.git("rm", "-q", "-f", path)
        capsys.readouterr()
        assert repo.run("config-inventory", "--check") == 1
        assert f"project 'svc' role {role}" in capsys.readouterr().out
        repo.stage({path: originals[path]})
    repo.stage({"svc/pyproject.toml": "[project\nname =\n"})
    assert repo.run("config-inventory", "--check") == 1
    assert "svc/pyproject.toml: invalid toml format" in capsys.readouterr().out
    repo.stage({"svc/pyproject.toml": originals["svc/pyproject.toml"].replace('"beta"', '"gamma"')})
    assert repo.run("config-inventory", "--check") == 1
    assert "role project-metadata" in capsys.readouterr().out
    repo.stage({"svc/pyproject.toml": originals["svc/pyproject.toml"]})
    assert repo.run("config-inventory", "--check") == 0
    repo.stage({"extra/pyproject.toml": "[project]\nname = 'x'\n"})
    assert repo.run("config-inventory", "--check") == 1
    assert "extra: project root is not in the declared inventory" in capsys.readouterr().out
    assert (repo.root / "pyproject.toml").read_text() == before[1]  # check mode wrote nothing to the tree
