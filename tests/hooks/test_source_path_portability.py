"""Focused proof for PIPE-PAGES-R031's source-path portability contract."""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.hygiene import path_portability
from tests.hooks.conftest import Repo


def _policy(*roots: str) -> path_portability.PathPortabilityPolicy:
    return path_portability.PathPortabilityPolicy(package_roots=tuple(roots) or ("pkg",))


def _project(*roots: str) -> str:
    packages = ", ".join(json.dumps(root) for root in roots)
    return f'[project]\nname = "fixture"\nversion = "0"\n\n[tool.pipelines_hooks]\npackages = [{packages}]\n'


@pytest.mark.spec("PIPE-PAGES-R031.1")
def test_source_path_portability_model() -> None:
    policy = _policy()
    policy.validate()
    assert policy.version == 1
    assert policy.max_path_utf16 == 240
    assert policy.max_component_utf8 == 255
    assert policy.supported_platforms == ("linux", "macos", "windows")
    boundary = "pkg/" + ("x" * 233) + ".py"
    report = path_portability.inspect_paths([boundary], policy)
    assert len(boundary) == 240
    assert report.clean
    with pytest.raises(CannotRun, match="unsupported.*version"):
        path_portability.PathPortabilityPolicy(version=2, package_roots=("pkg",)).validate()


@pytest.mark.spec("PIPE-PAGES-R031.2")
def test_source_path_portability_behavior() -> None:
    paths = (
        "pkg/CON.txt",
        "pkg/auxiliary.txt",
        "pkg/with:colon.py",
        "pkg/name. ",
        "pkg/../outside.py",
        "pkg/é.py",
        "pkg/e\u0301.py",
    )
    report = path_portability.inspect_paths(paths, _policy(), source_snapshot="fixture")
    rules = {violation.rule for violation in report.violations}
    assert rules >= {
        "reserved_name",
        "windows_invalid_character",
        "trailing_space_or_period",
        "traversal_or_empty_component",
        "casefold_nfc_collision",
    }
    collisions = [item for item in report.violations if item.rule == "casefold_nfc_collision"]
    assert {item.path for item in collisions} == {"pkg/é.py", "pkg/e\u0301.py"}
    assert all(set(item.related_paths) == {"pkg/é.py", "pkg/e\u0301.py"} for item in collisions)


@pytest.mark.spec("PIPE-PAGES-R031")
@pytest.mark.spec("PIPE-PAGES-R031.3")
def test_source_path_portability_wiring(repo: Repo) -> None:
    policy = path_portability.load_policy(repo.root)
    assert policy.package_roots == ("pkg",)
    report = path_portability.scan(repo.root, policy)
    assert report.clean
    assert [row["path"] for row in report.checked_paths] == ["pkg/__init__.py"]
    assert path_portability.main(["--root", str(repo.root)]) == 0


@pytest.mark.spec("PIPE-PAGES-R031.3")
@pytest.mark.parametrize(
    ("staged_root", "worktree_root"),
    (("staged_pkg", "worktree_pkg"), ("worktree_pkg", "staged_pkg")),
)
def test_scan_binds_policy_to_staged_index(repo: Repo, staged_root: str, worktree_root: str) -> None:
    repo.commit(
        {
            "staged_pkg/__init__.py": '"""Staged package."""\n',
            "worktree_pkg/__init__.py": '"""Worktree package."""\n',
        },
        "plant policy alternatives",
    )
    staged_source = _project(staged_root)
    repo.write("pyproject.toml", staged_source)
    repo.git("add", "--", "pyproject.toml")
    repo.write("pyproject.toml", _project(worktree_root))

    report = path_portability.scan(repo.root)
    assert report.package_roots == (staged_root,)
    assert [row["path"] for row in report.checked_paths] == [f"{staged_root}/__init__.py"]
    assert report.config_digest == f"sha256:{hashlib.sha256(staged_source.encode('utf-8')).hexdigest()}"
    with pytest.raises(CannotRun, match="does not match the selected Git index"):
        path_portability.scan(repo.root, _policy(worktree_root))


@pytest.mark.spec("PIPE-PAGES-R031.4")
def test_source_path_portability_refusal(repo: Repo) -> None:
    source = repo.write("pkg/CON.py", "ORIGINAL = 'preserved'\n")
    repo.git("add", "--", "pkg/CON.py")
    repo.git("commit", "-q", "-m", "plant reserved path")
    assert path_portability.main(["--root", str(repo.root)]) == 1
    assert source.read_text(encoding="utf-8") == "ORIGINAL = 'preserved'\n"

    repo.git("rm", "-q", "pkg/CON.py")
    repo.git("commit", "-q", "-m", "remove reserved path")
    assert path_portability.main(["--root", str(repo.root)]) == 0

    long_rel = "pkg/" + ("a" * 120) + "/" + ("b" * 120) + "/module.py"
    repo.commit({long_rel: "VALUE = 1\n"}, "plant long path")
    assert path_portability.main(["--root", str(repo.root)]) == 1
    repo.git("rm", "-q", long_rel)
    repo.git("commit", "-q", "-m", "remove long path")
    assert path_portability.main(["--root", str(repo.root)]) == 0


@pytest.mark.spec("PIPE-PAGES-R031.4")
def test_scan_refuses_malformed_staged_policy(repo: Repo) -> None:
    repo.write("pyproject.toml", "[tool.pipelines_hooks\npackages = ['pkg']\n")
    repo.git("add", "--", "pyproject.toml")
    repo.write("pyproject.toml", _project("pkg"))
    with pytest.raises(CannotRun, match="cannot parse selected pyproject.toml"):
        path_portability.scan(repo.root)


@pytest.mark.spec("PIPE-PAGES-R031.4")
def test_scan_refuses_symlinked_staged_policy(repo: Repo) -> None:
    repo.git("rm", "-q", "pyproject.toml")
    repo.write("pyproject-target.txt", _project("pkg"))
    os.symlink("pyproject-target.txt", repo.root / "pyproject.toml")
    repo.git("add", "--", "pyproject.toml", "pyproject-target.txt")
    with pytest.raises(CannotRun, match="refuses a symlinked pyproject.toml"):
        path_portability.scan(repo.root)


@pytest.mark.spec("PIPE-PAGES-R031.5")
def test_source_path_portability_evidence(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit({"pkg/CON.txt": "fixture\n"}, "plant reserved path")
    assert path_portability.main(["--root", str(repo.root), "--json"]) == 1
    evidence = json.loads(capsys.readouterr().out)
    assert evidence["schema"] == "source-path-portability/v1"
    assert evidence["policy_version"] == 1
    assert evidence["source_snapshot"] == repo.git("rev-parse", "HEAD").strip()
    assert evidence["package_roots"] == ["pkg"]
    assert evidence["supported_platforms"] == ["linux", "macos", "windows"]
    assert evidence["inventory_digest"].startswith("sha256:")
    config_source = repo.git("show", ":pyproject.toml")
    assert evidence["config_digest"] == f"sha256:{hashlib.sha256(config_source.encode('utf-8')).hexdigest()}"
    finding = next(item for item in evidence["violations"] if item["rule"] == "reserved_name")
    assert finding["path"] == "pkg/CON.txt"
    assert finding["component"] == "CON.txt"
    assert finding["normalized_key"] == "pkg/con.txt"


@pytest.mark.spec("PIPE-PAGES-R031.6")
def test_path_portability_cli(repo: Repo) -> None:
    long_rel = "pkg/" + ("u" * 120) + "/" + ("v" * 120) + "/module.py"
    repo.commit({"pkg/PRN.md": "reserved\n", long_rel: "long\n"}, "plant portability defects")
    assert path_portability.main(["--root", str(repo.root)]) == 1

    repo.git("rm", "-q", "pkg/PRN.md", long_rel)
    repo.git("commit", "-q", "-m", "repair portability defects")
    assert path_portability.main(["--root", str(repo.root)]) == 0
