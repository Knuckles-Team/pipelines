"""PIPE-PAGES-R020.85 to R020.90: the ontology governance hook reads the engine authority, never invents policy."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs import ontology_governance as og
from pipelines_hooks.docs.gate_io import sha
from tests.hooks.conftest import Repo

AUTHORITY = ".config/ontology-authority.json"
ONTOLOGY = "ontology/core.ttl"
TTL = "@prefix : <https://knuckles-team.github.io/ontology/core#> .\n:Thing a :Class .\n"
RULES = [
    {"id": "ONT-SYN-1", "class": "syntax"},
    {"id": "ONT-NS-1", "class": "namespace"},
    {"id": "ONT-DUP-1", "class": "duplicate-identity"},
    {"id": "ONT-SHACL-1", "class": "shape"},
    {"id": "ONT-VOC-1", "class": "vocabulary"},
]


def verdicts(fail: dict[str, tuple[int, str]] | None = None, drop: str | None = None) -> list[dict]:
    out = []
    for rule in RULES:
        if rule["id"] == drop:
            continue
        bad = (fail or {}).get(rule["id"])
        out.append(
            {"rule": rule["id"], "status": "fail" if bad else "pass", "provenance": "generated-check"}
            | ({"line": bad[0], "message": bad[1]} if bad else {})
        )
    return out


def build(tmp_path: Path, *, fail=None, drop=None, text: str = TTL, judged: str | None = None, extra=None) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.root.mkdir(parents=True)
    repo.git("init", "-q")
    authority = {
        "format": "ontology-authority/1",
        "authority": "fixture-engine",
        "rules": RULES,
        "files": {ONTOLOGY: {"sha": sha(judged if judged is not None else text), "verdicts": verdicts(fail, drop)}},
    }
    decl = {"schema": 1, "roots": ["ontology/"], "formats": {".ttl": "turtle"}, "authority": AUTHORITY}
    repo.stage({ONTOLOGY: text, AUTHORITY: json.dumps(authority), og.DECLARATION: json.dumps(decl), **(extra or {})})
    return repo


# spec: PIPE-PAGES-R020.85
def test_ontology_governance_hook_model(tmp_path: Path) -> None:
    profile = og.load_profile(build(tmp_path).root)
    assert profile.roots == ("ontology/",) and profile.formats == {".ttl": "turtle"}
    assert set(profile.rules.values()) == set(og.RULE_CLASSES) and profile.authority_owner == "fixture-engine"
    (item,) = profile.files
    assert item.digest == sha(TTL) and {v.provenance for v in item.verdicts} == {"generated-check"}
    with pytest.raises(CannotRun, match="required classes"):
        repo = build(tmp_path / "x")
        data = json.loads((repo.root / AUTHORITY).read_text())
        data["rules"] = [r for r in RULES if r["class"] != "shape"]
        repo.stage({AUTHORITY: json.dumps(data)})
        og.load_profile(repo.root)


# spec: PIPE-PAGES-R020.86
def test_ontology_governance_hook_behavior(tmp_path: Path) -> None:
    assert og.check(build(tmp_path).root).findings == []
    result = og.check(build(tmp_path / "f", fail={"ONT-NS-1": (2, "namespace not owned by this repository")}).root)
    assert result.findings == [f"{ONTOLOGY}:2: ONT-NS-1 (namespace): namespace not owned by this repository"]
    # a parser-clean file is no pass: the syntax verdict alone is not governance
    with pytest.raises(CannotRun, match="lacks evidence for rule classes \\['shape'\\]"):
        og.check(build(tmp_path / "p", drop="ONT-SHACL-1").root)
    # an unstaged repair never hides the staged defect
    repo = build(tmp_path / "u", fail={"ONT-SHACL-1": (2, "minCount violated")})
    (repo.root / ONTOLOGY).write_text(TTL + "# repaired in the work tree only\n")
    assert og.check(repo.root).findings


# spec: PIPE-PAGES-R020.87
def test_ontology_governance_hook_wiring() -> None:
    from pipelines_hooks.cli import GATES

    assert GATES["ontology-governance"] == "pipelines_hooks.docs.ontology_governance"
    root = Path(__file__).resolve().parents[2]
    hooks = (root / ".pre-commit-hooks.yaml").read_text()
    block = hooks[hooks.index("- id: ontology-governance") :].split("\n- id:", 1)[0]
    assert "entry: pipelines-hook ontology-governance" in block and "stages: [pre-commit]" in block
    assert "http" not in (root / "pipelines_hooks/docs/ontology_governance.py").read_text().split('"""', 2)[2]


# spec: PIPE-PAGES-R020.88
def test_ontology_governance_hook_refusal(tmp_path: Path) -> None:
    assert build(tmp_path / "v", fail={"ONT-DUP-1": (1, "duplicate identity")}).run("ontology-governance") == 1
    assert build(tmp_path / "stale", judged="# older bytes\n").run("ontology-governance") == 2
    repo = build(tmp_path / "noauth")
    subprocess.run(["git", "rm", "-q", "-f", "--", AUTHORITY], cwd=repo.root, check=True)
    assert repo.run("ontology-governance") == 2
    unsupported = build(tmp_path / "fmt", extra={"ontology/other.owl": "<rdf/>"})
    assert unsupported.run("ontology-governance") == 2
    undeclared = Repo(tmp_path / "none")
    undeclared.root.mkdir()
    undeclared.git("init", "-q")
    undeclared.stage({ONTOLOGY: TTL})
    assert undeclared.run("ontology-governance") == 2
    unjudged = build(tmp_path / "unjudged", extra={"ontology/new.ttl": TTL})
    assert unjudged.run("ontology-governance") == 2


# spec: PIPE-PAGES-R020.89
def test_ontology_governance_hook_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert build(tmp_path).run("ontology-governance") == 0
    out = capsys.readouterr().out
    assert "authority owner=fixture-engine path=.config/ontology-authority.json digest=" in out
    assert f"file path={ONTOLOGY} format=turtle input-digest={sha(TTL)}" in out
    for cls, rule in (("syntax", "ONT-SYN-1"), ("shape", "ONT-SHACL-1"), ("vocabulary", "ONT-VOC-1")):
        assert f"{cls}=[{rule}=pass/generated-check]" in out
    assert "ontology governance: clean" in out


# spec: PIPE-PAGES-R020.90
def test_ontology_governance_hook_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for rule, line, msg in (("ONT-SHACL-1", 2, "shape violation"), ("ONT-NS-1", 1, "foreign namespace")):
        repo = build(tmp_path / rule, fail={rule: (line, msg)})
        assert repo.run("ontology-governance") == 1
        assert f"{ONTOLOGY}:{line}: {rule}" in capsys.readouterr().out
    repo = build(tmp_path / "net")
    subprocess.run(["git", "rm", "-q", "-f", "--", AUTHORITY], cwd=repo.root, check=True)
    assert repo.run("ontology-governance") == 2
