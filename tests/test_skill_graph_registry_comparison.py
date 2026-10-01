"""Generated architecture/reference and API-contract pages match their source registries.

PIPE-PAGES-R005: architecture, capability, and reference documentation pages
are generated directly from the underlying registries and contracts rather
than hand-authored, proven by a build-time comparison between each page and
its source registry.

PIPE-PAGES-R010: API contract documentation pages are generated from the
canonical contract and method registry, proven by a build-time comparison
between the generated pages and the source contract registry.

Both use a disposable fixture workspace shaped like the cross-repo workspace
``scripts/build_skill_graph.py`` reads (one subdirectory per declared repo);
no sibling checkout of the real ``epistemic-graph`` repository is required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from skill_graph.cli import main as skill_graph_main  # noqa: E402
from skill_graph.corpus import build_graph  # noqa: E402
from skill_graph.render_components_au import render_components_au  # noqa: E402
from skill_graph.render_components import render_components_eg  # noqa: E402
from skill_graph.render_repo import render_repo_reference_md  # noqa: E402

REGISTRY = {
    "components": [
        {
            "component_id": "proof-engine",
            "layer": "reasoning",
            "status": "active",
            "concepts": ["Proof"],
            "summary": "Binds a claim to its supporting evidence.",
            "child_component_ids": ["proof-ledger"],
        },
        {
            "component_id": "proof-ledger",
            "layer": "storage",
            "status": "active",
            "concepts": [],
            "summary": "Durable record of accepted proofs.",
        },
    ]
}

METHODS = {
    "method_count": 2,
    "methods": [
        {"id": "proof.submit", "domain": "proof"},
        {"id": "proof.verify", "domain": "proof"},
    ],
}


def _add_revoke_method(repo_root: Path) -> None:
    """Append a third method, bumping ``method_count`` -- a contract drift fixture."""
    methods_path = repo_root / "contract" / "methods.json"
    data = json.loads(methods_path.read_text(encoding="utf-8"))
    data["methods"].append({"id": "proof.revoke", "domain": "proof"})
    data["method_count"] = 3
    methods_path.write_text(json.dumps(data), encoding="utf-8")


def _seed_eg_repo(workspace: Path) -> Path:
    repo_root = workspace / "epistemic-graph"
    (repo_root / "architecture").mkdir(parents=True)
    (repo_root / "contract").mkdir(parents=True)
    (repo_root / "architecture" / "component-registry.yml").write_text(
        yaml.safe_dump(REGISTRY, sort_keys=False), encoding="utf-8"
    )
    (repo_root / "contract" / "methods.json").write_text(json.dumps(METHODS), encoding="utf-8")
    return repo_root


def test_component_registry_page_matches_its_registry(tmp_path: Path) -> None:
    # proof-ledger is a child of proof-engine (child_component_ids), so it is
    # rendered nested inside proof-engine's page, not as its own top-level page --
    # see _top_level_registry_components in render_components.py.
    repo_root = _seed_eg_repo(tmp_path)
    corpus = build_graph(tmp_path)
    files = render_components_eg(corpus)
    assert "components/proof-engine.md" in files
    assert "components/proof-ledger.md" not in files
    assert "Binds a claim to its supporting evidence." in files["components/proof-engine.md"]
    assert "proof-ledger" in files["components/proof-engine.md"].lower()
    assert files == render_components_eg(build_graph(tmp_path))  # deterministic re-render

    registry_path = repo_root / "architecture" / "component-registry.yml"
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    data["components"][0]["summary"] = "Changed summary, not yet regenerated."
    registry_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    drifted = render_components_eg(build_graph(tmp_path))
    assert drifted["components/proof-engine.md"] != files["components/proof-engine.md"]
    assert "Changed summary, not yet regenerated." in drifted["components/proof-engine.md"]


def test_check_components_mode_fails_closed_on_registry_drift(tmp_path: Path, capsys) -> None:
    repo_root = _seed_eg_repo(tmp_path)
    out_dir = repo_root / "docs" / "generated"

    assert skill_graph_main([
        "emit-components", "--slug", "epistemic-graph", "--workspace", str(tmp_path), "--out-dir", str(out_dir),
    ]) == 0
    assert skill_graph_main([
        "check-components", "--slug", "epistemic-graph", "--workspace", str(tmp_path), "--out-dir", str(out_dir),
    ]) == 0

    registry_path = repo_root / "architecture" / "component-registry.yml"
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    data["components"][0]["summary"] = "A registry change the committed page has not absorbed."
    registry_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    exit_code = skill_graph_main([
        "check-components", "--slug", "epistemic-graph", "--workspace", str(tmp_path), "--out-dir", str(out_dir),
    ])
    assert exit_code == 1
    assert "out of sync with source registries" in capsys.readouterr().err


def test_contract_methods_page_matches_the_method_registry(tmp_path: Path) -> None:
    # The rendered reference page names the contract domain and its method
    # count (component_extra_bits), not each individual method id; the method
    # id list itself is carried on the Component node for machine consumers
    # (see eg.py's module docstring) and asserted directly below.
    repo_root = _seed_eg_repo(tmp_path)
    corpus = build_graph(tmp_path)
    page = render_repo_reference_md(corpus, "epistemic-graph")
    assert "proof (contract domain)" in page
    assert "2 methods" in page
    assert page == render_repo_reference_md(build_graph(tmp_path), "epistemic-graph")  # deterministic re-render

    nodes_by_id = {n["id"]: n for n in corpus["@graph"]}
    contract_domain = nodes_by_id["component/epistemic-graph/contract-domain/proof"]
    assert contract_domain["methods"] == ["proof.submit", "proof.verify"]

    _add_revoke_method(repo_root)

    drifted_corpus = build_graph(tmp_path)
    drifted = render_repo_reference_md(drifted_corpus, "epistemic-graph")
    assert "3 methods" in drifted
    assert drifted != page
    drifted_nodes = {n["id"]: n for n in drifted_corpus["@graph"]}
    assert drifted_nodes["component/epistemic-graph/contract-domain/proof"]["methods"] == [
        "proof.revoke", "proof.submit", "proof.verify",
    ]


def test_check_repo_mode_fails_closed_on_contract_drift(tmp_path: Path, capsys) -> None:
    repo_root = _seed_eg_repo(tmp_path)
    out_path = repo_root / "docs" / "reference" / "skill-graph.generated.md"

    assert skill_graph_main([
        "emit-repo", "--slug", "epistemic-graph", "--workspace", str(tmp_path), "--out", str(out_path),
    ]) == 0
    assert skill_graph_main([
        "check-repo", "--slug", "epistemic-graph", "--workspace", str(tmp_path), "--out", str(out_path),
    ]) == 0

    _add_revoke_method(repo_root)

    exit_code = skill_graph_main([
        "check-repo", "--slug", "epistemic-graph", "--workspace", str(tmp_path), "--out", str(out_path),
    ])
    assert exit_code == 1
    assert "out of sync with source registries" in capsys.readouterr().err


def test_agent_utilities_components_mode_returns_empty_without_a_components_registry(tmp_path: Path) -> None:
    # agent-utilities projects its component tier from docs/concepts.yaml pillars,
    # not architecture/component-registry.yml; an absent pillar file is a graceful
    # no-op (an empty page set), never a crash, matching render_components_au's contract.
    repo_root = tmp_path / "agent-utilities"
    repo_root.mkdir()
    assert render_components_au(repo_root) == {}
