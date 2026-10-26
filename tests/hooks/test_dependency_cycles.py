"""Focused proofs for PIPE-RELEASE-R005 dependency-group cycle gating."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.supply_chain.dependency_cycles import (
    DependencyLoop,
    find_loops,
    group_edges,
    loop_findings,
)
from pipelines_hooks.supply_chain.dependencies import dependency_findings
from tests.hooks.conftest import Repo


def _loop_document() -> dict:
    return {
        "project": {
            "name": "fixture",
            "dependencies": ["fixture[cli]"],
            "optional-dependencies": {"cli": ["packaging"]},
        },
        "dependency-groups": {
            "dev": [{"include-group": "test"}],
            "test": [{"include-group": "dev"}],
        },
    }


def _manifest(document: str) -> str:
    return document.strip() + "\n"


# spec: PIPE-RELEASE-R005.1
def test_group_graph_model() -> None:
    edges = group_edges(_loop_document())
    assert {(edge.source_group, edge.target_group) for edge in edges} == {
        ("root", "cli"),
        ("dev", "test"),
        ("test", "dev"),
    }
    assert {group for edge in edges for group in (edge.source_group, edge.target_group)} == {
        "root",
        "cli",
        "dev",
        "test",
    }


# spec: PIPE-RELEASE-R005.2
def test_include_group_cycle_found() -> None:
    loops = find_loops(group_edges(_loop_document()))
    assert loops == [DependencyLoop(("dev", "test"))]

    self_cycle = {
        "project": {"name": "fixture"},
        "dependency-groups": {"dev": [{"include-group": "dev"}]},
    }
    assert find_loops(group_edges(self_cycle)) == [DependencyLoop(("dev",))]


# spec: PIPE-RELEASE-R005.3
def test_dependency_findings_include_loops(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        _manifest(
            """
        [project]
        name = "fixture"

        [dependency-groups]
        dev = [{include-group = "test"}]
        test = [{include-group = "dev"}]
    """
        ),
        encoding="utf-8",
    )
    lock = tmp_path / "uv.lock"
    lock.write_text("version = 1\n", encoding="utf-8")
    findings = dependency_findings(
        "fixture",
        tmp_path,
        (pyproject, lock),
        reader=lambda path: path.read_text(encoding="utf-8"),
    )
    assert [finding.rule for finding in findings] == ["SC-DEP-LOOP"]


# spec: PIPE-RELEASE-R005.4
def test_unparseable_manifest_is_not_a_pass(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project\nname = 'fixture'\n", encoding="utf-8")
    lock = tmp_path / "uv.lock"
    lock.write_text("version = 1\n", encoding="utf-8")
    findings = dependency_findings(
        "fixture",
        tmp_path,
        (pyproject, lock),
        reader=lambda path: path.read_text(encoding="utf-8"),
    )
    assert any(finding.rule == "SC-DEP-004" for finding in findings)
    assert not any(finding.rule == "SC-DEP-LOOP" for finding in findings)


# spec: PIPE-RELEASE-R005.5
def test_loop_finding_lists_sorted_members(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    text = _manifest(
        """
        [project]
        name = "fixture"

        [dependency-groups]
        zeta = [{include-group = "alpha"}]
        alpha = [{include-group = "zeta"}]
    """
    )
    pyproject.write_text(text, encoding="utf-8")
    findings = loop_findings("fixture", pyproject, lambda path: path.read_text(encoding="utf-8"))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule == "SC-DEP-LOOP"
    assert finding.path == "pyproject.toml"
    assert finding.line > 0
    assert finding.message.endswith("alpha, zeta")


# spec: PIPE-RELEASE-R005.6
def test_supply_chain_hook_blocks_dependency_loop(repo: Repo, capsys) -> None:
    repo.commit(
        {
            "pyproject.toml": _manifest(
                """
                [project]
                name = "fixture"

                [dependency-groups]
                dev = [{include-group = "test"}]
                test = [{include-group = "dev"}]
            """
            ),
            "uv.lock": "version = 1\n",
        }
    )
    assert repo.run("supply-chain", str(repo.root)) == 1
    output = capsys.readouterr().out
    assert "SC-DEP-LOOP" in output
    assert "dev, test" in output
